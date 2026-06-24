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
        "thumbnail_concepts": None,
        "publish_metadata": None,
        "edl": None,
        "errors": [],
        "stage_completed": [],
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


def mark_stage_complete(job: dict, stage: str) -> dict:
    if stage not in job.get("stage_completed", []):
        job.setdefault("stage_completed", []).append(stage)
    return update_job(job)
