import json
import os
import re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from schemas import ChatRequest, ChatResponse, Topic
from topic_engine import generate_and_score_topics, get_client
from storage import get_used_titles, save_topics_to_backlog, mark_topic_used, get_backlog

app = FastAPI(title="Topic Hunter Chat")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

ORCHESTRATOR_SYSTEM = """You are the Topic Hunter — an AI assistant that helps content creators find
compelling historical topics for short-form videos.

You can help users:
- Generate batches of topic ideas for a given historical category and era
- Score and rank topics by virality potential (6 axes: accuracy, visual potential, retention, novelty, emotional impact, shareability)
- Browse and manage their topic backlog
- Mark topics as used

When the user asks you to generate topics, extract:
- category (default: weird_history): weird_history, ancient_rome, ancient_egypt, medieval_europe, vikings, pirates, historical_disasters, forgotten_leaders, strange_laws, military_history, historical_mysteries
- era (default: general): any time period string
- batch_size (default: 5): how many topics to generate
- video_length_sec (default: 60): 30, 45, 60, or 90

To trigger topic generation, output a JSON block inside your reply with this exact format:
<action>{"type":"generate","category":"...","historical_era":"...","batch_size":5,"video_length_sec":60}</action>

To show the backlog:
<action>{"type":"backlog"}</action>

Be conversational and encouraging. After generating topics, briefly highlight the top pick and why.
Always respond in plain text (no markdown headers), and keep responses concise."""


@app.get("/")
async def root():
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"message": "Topic Hunter API is running. Open index.html in frontend/."}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    messages = [{"role": m.role, "content": m.content} for m in request.history]
    messages.append({"role": "user", "content": request.message})

    client = get_client()
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1024,
        system=ORCHESTRATOR_SYSTEM,
        messages=messages,
    )

    reply_text: str = response.content[0].text
    topics: list[Topic] = []
    action_type = None

    action_match = re.search(r"<action>(.*?)</action>", reply_text, re.DOTALL)
    if action_match:
        try:
            action = json.loads(action_match.group(1))
            action_type = action.get("type")
            reply_text = reply_text.replace(action_match.group(0), "").strip()

            if action_type == "generate":
                used_titles = get_used_titles()
                topics = generate_and_score_topics(
                    category=action.get("category", "weird_history"),
                    historical_era=action.get("historical_era", "general"),
                    batch_size=action.get("batch_size", 5),
                    video_length_sec=action.get("video_length_sec", 60),
                    previously_used_titles=used_titles,
                )
                save_topics_to_backlog([t.model_dump() for t in topics])

            elif action_type == "backlog":
                backlog_raw = get_backlog()
                topics = [Topic(**t) for t in backlog_raw]

        except (json.JSONDecodeError, Exception) as e:
            reply_text += f"\n\n(Action error: {e})"

    return ChatResponse(reply=reply_text, topics=topics, action=action_type)


@app.post("/topics/{topic_id}/use")
async def use_topic(topic_id: str):
    backlog = get_backlog()
    topic = next((t for t in backlog if t["topic_id"] == topic_id), None)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found in backlog")
    mark_topic_used(topic)
    return {"status": "ok", "topic_id": topic_id}


@app.get("/backlog")
async def list_backlog():
    return {"topics": get_backlog()}


@app.get("/history")
async def list_history():
    return {"used_titles": get_used_titles()}
