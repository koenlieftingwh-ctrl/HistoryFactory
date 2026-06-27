"""Persistent HSGJob CRUD — one JSON file per job under data/jobs/."""
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

JOBS_DIR = Path(__file__).parent.parent / "data" / "jobs"


def _ensure():
    JOBS_DIR.mkdir(parents=True, exist_ok=True)


def _path(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.json"


def create_job(topic: dict, config: dict) -> dict:
    _ensure()
    job = {
        "job_id": str(uuid.uuid4())[:8],
        "created_at": datetime.utcnow().isoformat(),
        "status": "pending",
        "config": config,
        "topic": topic,
        "research": None,
        "validation": None,
        "script": None,
        "storyboard": None,
        "visual_prompts": None,
        "render_estimate": None,
        "render_jobs": None,
        "render_status": None,
        "thumbnail_concepts": None,
        "publish_metadata": None,
        "edl": None,
        "errors": [],
        "stage_completed": [],
        "cost_tracking": {
            "llm_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "llm_cost_usd": 0.0,
            "render_credits_estimated": 0.0,
            "render_credits_used": 0.0,
        },
    }
    _path(job["job_id"]).write_text(json.dumps(job, indent=2), encoding="utf-8")
    return job


def get_job(job_id: str) -> Optional[dict]:
    p = _path(job_id)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def update_job(job: dict) -> dict:
    _ensure()
    job["status"] = compute_status(job.get("stage_completed", []), job.get("render_status"))
    _path(job["job_id"]).write_text(json.dumps(job, indent=2), encoding="utf-8")
    return job


def list_jobs() -> list[dict]:
    _ensure()
    jobs = []
    for p in sorted(JOBS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            jobs.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass
    return jobs


def compute_status(stage_completed: list[str], render_status: Optional[str] = None) -> str:
    """Derive job status from stage_completed + optional render_status."""
    if render_status == "completed":
        return "completed"
    if render_status == "rendering":
        return "rendering"
    if render_status == "insufficient_credits":
        return "insufficient_credits"
    if not stage_completed:
        return "pending"
    stages_order = ["topic_hunter", "historian", "director", "editor"]
    last_done = None
    for s in stages_order:
        if s in stage_completed:
            last_done = s
    next_map = {
        "topic_hunter": "researching",
        "historian": "scripting",
        "director": "render_ready",
        "editor": "render_ready",
    }
    return next_map.get(last_done, "pending")


def add_llm_cost(job: dict, usage: dict) -> None:
    """Accumulate one LLM call's token usage into job["cost_tracking"]."""
    ct = job.setdefault("cost_tracking", {
        "llm_calls": 0, "input_tokens": 0, "output_tokens": 0,
        "llm_cost_usd": 0.0, "render_credits_estimated": 0.0, "render_credits_used": 0.0,
    })
    ct["llm_calls"] = ct.get("llm_calls", 0) + 1
    ct["input_tokens"] = ct.get("input_tokens", 0) + usage.get("input_tokens", 0)
    ct["output_tokens"] = ct.get("output_tokens", 0) + usage.get("output_tokens", 0)
    ct["llm_cost_usd"] = round(ct.get("llm_cost_usd", 0.0) + usage.get("cost_usd", 0.0), 6)


def mark_stage_complete(job: dict, stage: str) -> dict:
    if stage not in job.get("stage_completed", []):
        job.setdefault("stage_completed", []).append(stage)
    return update_job(job)
