import json
import os
import re
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# Allow sibling imports
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from engines.claude_client import chat as gemini_chat
from engines.topic_engine import generate_and_score
from engines.research_engine import research_topic, validate_research
from engines.script_engine import generate_script, generate_storyboard
from engines.editor_engine import (
    generate_visual_prompts, generate_edl,
    generate_thumbnail_concepts, generate_metadata,
    estimate_render_credits,
)
from engines.render_engine import submit_render_jobs, estimate_job_credits, get_balance
from job_store import create_job, get_job, update_job, list_jobs, mark_stage_complete, add_llm_cost
import agents.topic_hunter as topic_hunter_agent
import agents.historian as historian_agent
import agents.director as director_agent
import agents.editor as editor_agent

app = FastAPI(title="HSG Pipeline")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []
    job_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    job: dict | None = None
    topics: list[dict] = []
    action: str | None = None


FALLBACK_REPLIES = {
    "research": "Researching the topic now — pulling together the historical facts...",
    "validate": "Running adversarial validation on the research...",
    "script": "Writing the five-act script now...",
    "storyboard": "Generating the storyboard from the script...",
    "visual_prompts": "Generating visual prompts for each scene...",
    "edl": "Building the edit decision list...",
    "thumbnails": "Creating thumbnail concepts...",
    "metadata": "Generating publishing metadata...",
    "all": "Running all editor stages: visual prompts, EDL, thumbnails, and metadata...",
    "generate": "Generating and scoring topics...",
}


def _extract_action(text: str) -> tuple[str, dict | None]:
    m = re.search(r"<action>(.*?)</action>", text, re.DOTALL)
    if not m:
        return text, None
    clean = text.replace(m.group(0), "").strip()
    try:
        action = json.loads(m.group(1))
        if not clean:
            clean = FALLBACK_REPLIES.get(action.get("type", ""), "Working on it...")
        return clean, action
    except json.JSONDecodeError:
        return text, None


def _get_used_titles() -> list[str]:
    """Collect titles from all existing jobs."""
    return [j["topic"]["title"] for j in list_jobs() if j.get("topic")]


# ---------- /agent/topic-hunter/chat ----------

@app.post("/agent/topic-hunter/chat", response_model=ChatResponse)
async def topic_hunter_chat(req: ChatRequest):
    job = get_job(req.job_id) if req.job_id else None
    used_titles = _get_used_titles()
    system = topic_hunter_agent.build_system(job, used_titles)

    reply_raw, _chat_usage = gemini_chat(system, list(req.history), req.message, max_tokens=512)
    reply, action = _extract_action(reply_raw)
    topics: list[dict] = []

    if action:
        atype = action.get("type")

        if atype == "generate":
            topics = generate_and_score(
                category=action.get("category", "weird_history"),
                historical_era=action.get("historical_era", "general"),
                batch_size=action.get("batch_size", 5),
                video_length_sec=action.get("video_length_sec", 60),
                previously_used_titles=used_titles,
            )

        elif atype == "create_job":
            topic_id = action.get("topic_id")
            # Find topic in the last generated batch (or request caller passes it)
            # Caller must pass full topic data in action or we look it up
            topic_data = action.get("topic")
            if not topic_data:
                return ChatResponse(reply="I need the full topic data to create a job. Please regenerate topics.", job=job)
            config = action.get("config", {})
            job = create_job(topic_data, config)
            mark_stage_complete(job, "topic_hunter")
            return ChatResponse(reply=reply, job=job, action=atype)

    return ChatResponse(reply=reply, job=job, topics=topics, action=action.get("type") if action else None)


# ---------- /agent/historian/chat ----------

@app.post("/agent/historian/chat", response_model=ChatResponse)
async def historian_chat(req: ChatRequest):
    job = get_job(req.job_id) if req.job_id else None
    system = historian_agent.build_system(job)

    reply_raw, _chat_usage = gemini_chat(system, list(req.history), req.message, max_tokens=512)
    if job:
        add_llm_cost(job, _chat_usage)
    reply, action = _extract_action(reply_raw)

    if action and job:
        atype = action.get("type")

        if atype == "research":
            job = research_topic(job)
            update_job(job)

        elif atype == "validate":
            if not job.get("research"):
                return ChatResponse(reply="Research must be completed before validation. Ask me to research first.", job=job)
            job = validate_research(job)
            if job.get("validation", {}).get("publishable", True):
                mark_stage_complete(job, "historian")
            update_job(job)

    return ChatResponse(reply=reply, job=job, action=action.get("type") if action else None)


# ---------- /agent/director/chat ----------

@app.post("/agent/director/chat", response_model=ChatResponse)
async def director_chat(req: ChatRequest):
    job = get_job(req.job_id) if req.job_id else None
    system = director_agent.build_system(job)

    reply_raw, _chat_usage = gemini_chat(system, list(req.history), req.message, max_tokens=512)
    if job:
        add_llm_cost(job, _chat_usage)
    reply, action = _extract_action(reply_raw)

    if action and job:
        atype = action.get("type")

        if atype == "script":
            if "historian" not in job.get("stage_completed", []):
                return ChatResponse(reply="Historian stage must be complete before scripting.", job=job)
            job = generate_script(job)
            update_job(job)

        elif atype == "storyboard":
            if not job.get("script"):
                return ChatResponse(reply="Script must be written before generating a storyboard.", job=job)
            job = generate_storyboard(job)
            mark_stage_complete(job, "director")
            update_job(job)

    return ChatResponse(reply=reply, job=job, action=action.get("type") if action else None)


# ---------- /agent/editor/chat ----------

@app.post("/agent/editor/chat", response_model=ChatResponse)
async def editor_chat(req: ChatRequest):
    job = get_job(req.job_id) if req.job_id else None
    system = editor_agent.build_system(job)

    reply_raw, _chat_usage = gemini_chat(system, list(req.history), req.message, max_tokens=512)
    if job:
        add_llm_cost(job, _chat_usage)
    reply, action = _extract_action(reply_raw)

    if action and job:
        if "director" not in job.get("stage_completed", []):
            return ChatResponse(reply="Director stage must be complete before editing.", job=job)

        atype = action.get("type")

        if atype in ("visual_prompts", "all"):
            job = generate_visual_prompts(job)
            update_job(job)

        if atype in ("edl", "all"):
            if not job.get("storyboard"):
                return ChatResponse(reply="Storyboard required for EDL.", job=job)
            job = generate_edl(job)
            update_job(job)

        if atype in ("thumbnails", "all"):
            job = generate_thumbnail_concepts(job)
            update_job(job)

        if atype in ("metadata", "all"):
            job = generate_metadata(job)
            mark_stage_complete(job, "editor")
            update_job(job)

    return ChatResponse(reply=reply, job=job, action=action.get("type") if action else None)


# ---------- Autorun ----------

@app.post("/jobs/autorun")
async def autorun_job(payload: dict):
    """
    Full pipeline in one call: generate topics → pick best → research →
    validate → script → storyboard → visual prompts → EDL → thumbnails →
    metadata. Returns the completed render_ready job.
    """
    category = payload.get("category", "weird_history")
    era = payload.get("historical_era", "general")
    batch_size = int(payload.get("batch_size", 5))
    config_overrides = payload.get("config", {})

    # 1. Generate and score topics
    used_titles = _get_used_titles()
    topics = generate_and_score(
        category=category,
        historical_era=era,
        batch_size=batch_size,
        video_length_sec=config_overrides.get("video_length_sec", 60),
        previously_used_titles=used_titles,
    )
    if not topics:
        raise HTTPException(status_code=500, detail="Topic generation produced no results")

    best = max(topics, key=lambda t: t.get("scores", {}).get("composite", 0))

    config = {
        "video_length_sec": 60,
        "narration_speed": "normal",
        "narration_style": "documentary",
        "target_platform": "youtube_shorts",
        "historical_era": era,
        "topic_category": category,
        "visual_style": "photoreal_cinematic",
        "music_intensity": "moderate",
        "language": "en",
        "upload_frequency": "weekly",
        **config_overrides,
    }

    # 2. Create job
    job = create_job(best, config)
    mark_stage_complete(job, "topic_hunter")
    update_job(job)

    # 3. Research + validate
    job = research_topic(job)
    update_job(job)
    job = validate_research(job)
    mark_stage_complete(job, "historian")
    update_job(job)

    # 4. Script + storyboard
    job = generate_script(job)
    update_job(job)
    job = generate_storyboard(job)
    mark_stage_complete(job, "director")
    update_job(job)

    # 5. Editor: visual prompts → EDL → thumbnails → metadata
    job = generate_visual_prompts(job)
    update_job(job)
    job = generate_edl(job)
    update_job(job)
    job = generate_thumbnail_concepts(job)
    update_job(job)
    job = generate_metadata(job)
    mark_stage_complete(job, "editor")
    update_job(job)

    return job


# ---------- REST helpers ----------

@app.get("/jobs")
async def get_jobs():
    return {"jobs": list_jobs()}


@app.get("/jobs/{job_id}")
async def get_job_detail(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _run_render_in_background(job: dict):
    """Called by BackgroundTasks — updates job in place so the client can poll."""
    try:
        job = submit_render_jobs(job)
    except RuntimeError:
        pass  # submit_render_jobs already sets render_status on the job
    update_job(job)


@app.post("/jobs/{job_id}/render")
async def start_render(job_id: str, background_tasks: BackgroundTasks):
    """Enqueue Higgsfield submission in the background. Poll /render-status for progress."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.get("visual_prompts"):
        raise HTTPException(status_code=400, detail="Run the Editor stage first to generate visual prompts.")
    job["render_status"] = "submitting"
    update_job(job)
    background_tasks.add_task(_run_render_in_background, job)
    return {"status": "submitting", "job_id": job_id, "message": "Render submission started — poll /render-status for updates."}


@app.get("/jobs/{job_id}/render-status")
async def render_status(job_id: str):
    """Poll Higgsfield for status updates on in-flight render jobs."""
    from engines.render_engine import poll_render_status
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.get("render_jobs"):
        raise HTTPException(status_code=400, detail="No render jobs found for this job.")
    job = poll_render_status(job)
    update_job(job)
    return job


@app.get("/render/balance")
async def higgsfield_balance():
    """Return current Higgsfield credit balance."""
    balance = get_balance()
    return {"credits": balance, "available": balance >= 0}


@app.post("/agent/topic-hunter/select-topic")
async def select_topic(payload: dict):
    """Create a job directly from a topic dict (called from the UI topic card)."""
    topic = payload.get("topic")
    config = payload.get("config", {})
    if not topic:
        raise HTTPException(status_code=400, detail="topic required")
    config.setdefault("video_length_sec", 60)
    config.setdefault("narration_speed", "normal")
    config.setdefault("narration_style", "documentary")
    config.setdefault("target_platform", "youtube_shorts")
    config.setdefault("historical_era", topic.get("era", "general"))
    config.setdefault("topic_category", topic.get("category", "weird_history"))
    config.setdefault("visual_style", "photoreal_cinematic")
    config.setdefault("music_intensity", "moderate")
    config.setdefault("language", "en")
    config.setdefault("upload_frequency", "weekly")
    job = create_job(topic, config)
    mark_stage_complete(job, "topic_hunter")
    return job




@app.get("/jobs/{job_id}/render-estimate")
async def render_estimate(job_id: str):
    """Return credit estimate without submitting."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    prompts = job.get("visual_prompts") or []
    needed = estimate_job_credits(prompts)
    balance = get_balance()
    return {
        "credits_needed": needed,
        "credits_balance": balance,
        "sufficient": balance < 0 or balance >= needed,
    }


@app.get("/")
async def root():
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"message": "HSG Pipeline API running."}
