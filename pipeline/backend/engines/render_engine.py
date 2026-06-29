"""Render Engine — submits visual prompts to Higgsfield and tracks generation job IDs.

Auth: set HIGGSFIELD_API_KEY in pipeline/.env.
The base URL and exact endpoint paths are documented below; verify against
https://docs.higgsfield.ai when wiring up for real.

Known model IDs (from MCP catalog):
  video: seedance_2_0, kling3_0_turbo, kling3_0, cinematic_studio_video
  image: soul_2, flux_1_1_ultra, nano_banana_pro
"""
import json
import os
import time
from typing import Optional

try:
    import requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

from engines.editor_engine import CREDITS_PER_VIDEO_CLIP, CREDITS_PER_STATIC_IMAGE

HIGGSFIELD_API_BASE = "https://api.higgsfield.ai"
# TODO: confirm endpoint paths once you have a paid plan and API docs access.
# Likely: POST /v1/generation/video  and  POST /v1/generation/image
VIDEO_ENDPOINT = f"{HIGGSFIELD_API_BASE}/v1/generation/video"
IMAGE_ENDPOINT = f"{HIGGSFIELD_API_BASE}/v1/generation/image"
BALANCE_ENDPOINT = f"{HIGGSFIELD_API_BASE}/v1/account/balance"

DEFAULT_CLIP_DURATION = 5   # seconds per video clip
DEFAULT_RESOLUTION = "720p"


def _api_key() -> str:
    key = os.environ.get("HIGGSFIELD_API_KEY", "")
    if not key:
        # Re-read .env in case it was updated after server start
        from dotenv import load_dotenv
        from pathlib import Path
        load_dotenv(Path(__file__).parent.parent.parent / ".env", override=True)
        key = os.environ.get("HIGGSFIELD_API_KEY", "")
    if not key:
        raise RuntimeError("HIGGSFIELD_API_KEY not set — add it to pipeline/.env")
    return key


def _headers() -> dict:
    return {"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"}


def get_balance() -> float:
    """Return current Higgsfield credit balance. Returns -1 if API unreachable."""
    if not _REQUESTS_AVAILABLE:
        return -1
    try:
        r = requests.get(BALANCE_ENDPOINT, headers=_headers(), timeout=10)
        r.raise_for_status()
        data = r.json()
        # Field name TBC — try common variants
        return float(data.get("credits") or data.get("balance") or data.get("remaining") or 0)
    except Exception:
        return -1


def estimate_job_credits(visual_prompts: list[dict]) -> float:
    """Return total estimated credits needed to render all scenes."""
    total = 0.0
    for p in visual_prompts:
        if p.get("render_type") == "video_clip":
            total += CREDITS_PER_VIDEO_CLIP
        else:
            total += CREDITS_PER_STATIC_IMAGE
    return round(total, 1)


_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504, 522, 524}
_MAX_RETRIES = 4
_RETRY_BACKOFF = [2, 5, 15, 30]  # seconds between attempts


def _is_retryable(exc: Exception) -> bool:
    import requests as req
    if isinstance(exc, req.exceptions.ConnectionError):
        return True
    if isinstance(exc, req.exceptions.Timeout):
        return True
    if isinstance(exc, req.exceptions.HTTPError):
        code = exc.response.status_code if exc.response is not None else 0
        return code in _RETRYABLE_STATUS_CODES
    return False


def _post_with_retry(url: str, payload: dict, timeout: int = 30) -> dict:
    last_exc = None
    for attempt in range(_MAX_RETRIES):
        try:
            r = requests.post(url, headers=_headers(), json=payload, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_exc = e
            if attempt < _MAX_RETRIES - 1 and _is_retryable(e):
                time.sleep(_RETRY_BACKOFF[attempt])
            else:
                break
    raise last_exc


def _submit_video(prompt: dict, aspect_ratio: str) -> dict:
    """POST one video generation request with retry. Returns raw API response."""
    payload = {
        "model": prompt["model"],
        "prompt": prompt["prompt"],
        "aspect_ratio": aspect_ratio,
        "duration": DEFAULT_CLIP_DURATION,
        "resolution": DEFAULT_RESOLUTION,
    }
    return _post_with_retry(VIDEO_ENDPOINT, payload)


def _submit_image(prompt: dict, aspect_ratio: str) -> dict:
    """POST one image generation request with retry. Returns raw API response."""
    payload = {
        "model": prompt["model"],
        "prompt": prompt["prompt"],
        "aspect_ratio": aspect_ratio,
    }
    return _post_with_retry(IMAGE_ENDPOINT, payload)


def submit_render_jobs(job: dict) -> dict:
    """
    Submit each visual prompt to Higgsfield. Saves generation job IDs to
    job["render_jobs"]. Performs a credit preflight check first.

    Returns the updated job dict with:
      job["render_jobs"] = [{"scene_id", "higgsfield_job_id", "render_type",
                              "model", "status": "submitted"|"failed", "error"?}]
      job["render_estimate"]["credits_balance"] = current balance
    """
    if not _REQUESTS_AVAILABLE:
        raise RuntimeError("requests library not installed — run: pip install requests")

    prompts = job.get("visual_prompts") or []
    if not prompts:
        raise ValueError("No visual prompts found — run the Editor stage first.")

    aspect_ratio = (job.get("visual_prompts") or [{}])[0].get("aspect_ratio", "9:16")

    # Preflight: credit check
    needed = estimate_job_credits(prompts)
    balance = get_balance()

    render_estimate = job.setdefault("render_estimate", {})
    render_estimate["credits_needed"] = needed
    render_estimate["credits_balance"] = balance

    if balance >= 0 and balance < needed:
        shortfall = round(needed - balance, 1)
        render_estimate["shortfall"] = shortfall
        job["render_status"] = "insufficient_credits"
        raise RuntimeError(
            f"Insufficient credits: need {needed}, have {balance}. "
            f"Shortfall: {shortfall} credits."
        )

    # Build a lookup of any previously submitted/done entries so we don't
    # re-submit scenes that already have a Higgsfield job ID.
    existing: dict[str, dict] = {
        e["scene_id"]: e for e in (job.get("render_jobs") or [])
    }

    render_jobs = []
    for prompt in prompts:
        scene_id = prompt.get("scene_id", "unknown")
        prev = existing.get(scene_id)

        # Skip scenes already successfully submitted or completed.
        if prev and prev.get("status") in ("submitted", "done"):
            render_jobs.append(prev)
            continue

        entry = {
            "scene_id": scene_id,
            "render_type": prompt.get("render_type", "video_clip"),
            "model": prompt.get("model"),
            "higgsfield_job_id": None,
            "status": "pending",
        }
        try:
            if prompt.get("render_type") == "video_clip":
                response = _submit_video(prompt, aspect_ratio)
            else:
                response = _submit_image(prompt, aspect_ratio)

            # Common response fields — adjust to actual API shape
            job_id = (
                response.get("job_id")
                or response.get("id")
                or response.get("generation_id")
            )
            entry["higgsfield_job_id"] = job_id
            entry["status"] = "submitted"
        except Exception as e:
            entry["status"] = "failed"
            entry["error"] = str(e)

        render_jobs.append(entry)

    job["render_jobs"] = render_jobs
    job["render_status"] = "rendering"
    return job


def poll_render_status(job: dict) -> dict:
    """
    Re-check each pending Higgsfield job. Updates status to "done" or "failed".
    Call repeatedly until job["render_status"] == "completed".
    """
    render_jobs = job.get("render_jobs") or []
    if not render_jobs:
        return job

    still_pending = False
    for entry in render_jobs:
        if entry["status"] in ("done", "failed") or not entry.get("higgsfield_job_id"):
            continue

        hid = entry["higgsfield_job_id"]
        # TODO: replace with the real status endpoint once confirmed
        status_url = f"{HIGGSFIELD_API_BASE}/v1/generation/{hid}"
        try:
            r = requests.get(status_url, headers=_headers(), timeout=10)
            r.raise_for_status()
            data = r.json()
            api_status = data.get("status", "").lower()
            if api_status in ("completed", "done", "succeeded"):
                entry["status"] = "done"
                entry["result_url"] = (
                    data.get("result_url")
                    or data.get("output_url")
                    or data.get("video_url")
                    or data.get("image_url")
                )
            elif api_status in ("failed", "error"):
                entry["status"] = "failed"
                entry["error"] = data.get("error") or "Unknown error"
            else:
                still_pending = True
        except Exception as e:
            entry["error"] = str(e)
            still_pending = True

    if not still_pending:
        all_done = all(e["status"] in ("done", "failed") for e in render_jobs)
        if all_done:
            job["render_status"] = "completed"

    return job
