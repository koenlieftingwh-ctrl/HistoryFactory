# Handoff 01 — History Shorts Generator Pipeline
_Branch: `initial-setup` | Date: 2026-06-24_

---

## Goals

Build a fully functional conversational pipeline for the **History Shorts Generator (HSG)** — an AI system that takes a user from raw topic ideation all the way to a packaged, publish-ready short-form history video.

The pipeline is divided into four chat agents, each covering a specific stage group from `history-shorts-generator-spec.md`:

| Agent | Spec Stages | Responsibility |
|---|---|---|
| **Topic Hunter** | 1 & 2 | Generate and score historical topic ideas; create a production job |
| **Historian** | 3 & 4 | Research facts; adversarially validate them before scripting |
| **Director** | 5 & 6 | Write the five-act narration script; produce a visual storyboard |
| **Editor** | 8, 13, 14, 15 | Generate Higgsfield visual prompts, EDL, thumbnail concepts, and publish metadata |

Each agent is a conversational Claude chat. The workflow is gated: each tab only unlocks after the previous agent marks its stage complete. The full job state (`HSGJob`) persists to disk as a JSON file and is passed into every agent call so all agents share context.

The end-to-end output for each job is:
- A scored topic
- A validated research bundle (6–12 facts with certainty labels)
- A five-act narration script
- A scene-by-scene storyboard
- Higgsfield-ready visual prompts per scene
- An edit decision list (EDL) for assembly
- 3 thumbnail concepts with overlay text
- Platform-optimised title, description, tags, and hashtags

---

## Current State of the Code

### What exists and is complete

#### `topic-hunter/` — standalone prototype (superseded but functional)
An earlier, self-contained FastAPI app built in the first session. It runs on its own and demonstrates topic generation + scoring. Kept for reference; not the active version.

```
topic-hunter/
  backend/
    main.py          FastAPI with /chat endpoint and orchestrator system prompt
    topic_engine.py  Stage 1 + 2 engines (generate_topics, score_topic, generate_and_score)
    storage.py       JSON persistence for backlog and used-title history
    schemas.py       Pydantic models (Topic, QualityScores, ChatRequest, ChatResponse)
  frontend/
    index.html       Single-page chat UI with scored topic cards sidebar
  requirements.txt
  .env.example
```

Has been run and confirmed to start (`__pycache__` present, `.env` populated).

#### `pipeline/` — the active, full pipeline (written this session, NOT yet run)
The real implementation. All four agents, shared job state, unified frontend.

```
pipeline/
  backend/
    main.py                    Unified FastAPI — 4 POST /agent/{name}/chat endpoints
                               + GET /jobs, GET /jobs/{id}
                               + POST /agent/topic-hunter/select-topic
    job_store.py               HSGJob CRUD — one .json file per job in data/jobs/
    agents/
      topic_hunter.py          System prompt builder for Stage 1+2 agent
      historian.py             System prompt builder for Stage 3+4 agent
      director.py              System prompt builder for Stage 5+6 agent
      editor.py                System prompt builder for Stage 8/13/14/15 agent
    engines/
      claude_client.py         Shared Anthropic client; model constants (HAIKU = claude-haiku-4-5)
      topic_engine.py          generate_topics(), score_topic(), generate_and_score()
      research_engine.py       research_topic(), validate_research()
      script_engine.py         generate_script(), generate_storyboard()
      editor_engine.py         generate_visual_prompts(), generate_edl(),
                               generate_thumbnail_concepts(), generate_metadata()
  frontend/
    index.html                 Unified 4-tab pipeline UI:
                               - Left sidebar: job list + "New Job" button
                               - Tab bar: Topic Hunter / Historian / Director / Editor
                                 (tabs lock/unlock based on stage_completed[])
                               - Chat pane: active agent conversation
                               - Topics panel (topic-hunter tab only): scored topic cards
                                 with "Select → Create Job" buttons
                               - Right panel (other tabs): live job state viewer
                                 with collapsible sections per stage
  data/
    jobs/                      Auto-created; empty until first run
  requirements.txt
  .env.example
```

### Key design decisions made

- **All models = `claude-haiku-4-5`** throughout for dev. Spec §11 says Script/Validation should use Sonnet-tier for production quality — this is the clearest upgrade path once testing is done.
- **Action tag protocol**: agents embed `<action>{"type":"...","param":"..."}</action>` blocks in their replies. The backend strips these, parses them, runs the appropriate engine, and returns the clean reply + updated job. This keeps the LLM's conversational output separate from operational triggers.
- **`stage_completed[]` array on the job**: each stage appends a string key when done (`"topic_hunter"`, `"historian"`, `"director"`, `"editor"`). The frontend uses this to lock/unlock tabs; the backend uses it to gate engine calls.
- **Research engine uses Claude knowledge, not live web search**: spec §3 calls for `Claude + web_search tool`, but tool-use integration is not wired up yet. Research quality is limited to Claude's training data. This is the single biggest fidelity gap.
- **`topic-hunter/` and `pipeline/` are separate apps** with their own `requirements.txt`. The pipeline does not import from topic-hunter.

### What has NOT been built yet

- Stages 7 (Character Consistency / Style Bible), 9 (Higgsfield scene generation), 10 (Voiceover), 11 (Subtitles), 12 (Music Selection) — these require external APIs (Higgsfield, TTS) and are out of scope for this sprint
- Any authentication or multi-user isolation
- Analytics feedback loop (spec §10 / §13 step 7)
- Embedding-based dedup check for near-duplicate topics (spec §13 step 6)
- The `pipeline/` app has never been started; it has not been tested end-to-end

---

## Files Actively Edited This Session

All of these were created fresh this session (none existed before):

```
pipeline/backend/main.py
pipeline/backend/job_store.py
pipeline/backend/agents/topic_hunter.py
pipeline/backend/agents/historian.py
pipeline/backend/agents/director.py
pipeline/backend/agents/editor.py
pipeline/backend/engines/claude_client.py
pipeline/backend/engines/topic_engine.py
pipeline/backend/engines/research_engine.py
pipeline/backend/engines/script_engine.py
pipeline/backend/engines/editor_engine.py
pipeline/frontend/index.html
pipeline/requirements.txt
pipeline/.env.example
```

The `topic-hunter/` files were created in the prior session (before context was compacted) and were not modified this session.

---

## Everything Tried That Failed

Nothing has been tested at runtime yet — the `pipeline/` app was written but not started during this session. The `topic-hunter/` prototype was started and confirmed working (pycache present, .env populated) in a prior session.

Known risks going into first run:

1. **`sys.path` manipulation in `main.py`**: `main.py` inserts its own directory into `sys.path` so `from engines.X import` and `from job_store import` work when run as `uvicorn main:app`. If uvicorn is run from a different working directory, these imports will fail. The fix is either to run from `pipeline/backend/` or to add a proper `__init__.py` + package structure.

2. **`agents/` import path in `main.py`**: `import agents.topic_hunter as topic_hunter_agent` assumes `agents/` is a package visible from `backend/`. This works when `sys.path` includes `backend/` but will break if the package isn't found. Both `agents/__init__.py` and `engines/__init__.py` were created empty, which should be sufficient.

3. **`select-topic` endpoint — frontend sends partial topic**: the "Select → Create Job" button in the frontend sends the topic dict from `lastTopics[]` (populated after a generate call). If the user refreshes the page mid-session, `lastTopics` is lost and the button won't work. The fix is to have the frontend re-fetch the topic list or store it in `localStorage`.

4. **History accumulation in frontend**: each agent tab maintains its own `histories[tab]` array in JS memory. These are not persisted to the server or localStorage. A page refresh loses all chat history even though the job state is preserved on disk.

5. **`validate_research` before `research_topic`**: the historian endpoint has a guard (`if not job.get("research"): return error`) but the agent's system prompt also has this logic. If a user somehow triggers `validate` before `research`, they get a clear error message, but the chat history will then be inconsistent.

6. **`generate_and_score` in topic-hunter flow vs. `select-topic`**: the topic-hunter agent's `create_job` action (embedded in the LLM reply) requires a `topic` key in the action JSON — but the LLM has to construct that dict itself from memory. This is fragile. The frontend's "Select → Create Job" button approach (calling `POST /agent/topic-hunter/select-topic` directly with the topic object) is the correct path and should be the primary flow. The LLM-driven `create_job` action should probably be removed to avoid ambiguity.

---

## Next Steps

### Immediate — get the pipeline running

1. **Test the pipeline app for the first time**:
   ```bash
   cd pipeline
   cp .env.example .env   # fill in ANTHROPIC_API_KEY
   pip install -r requirements.txt
   cd backend
   uvicorn main:app --reload --port 8001
   # open http://localhost:8001
   ```
   Walk through the full workflow: generate topics → select one → research → validate → script → storyboard → all editor outputs.

2. **Fix any import errors** that surface (likely the `sys.path` / `agents` import issue described above). The cleanest fix is to add a `pyproject.toml` that declares `pipeline` as a package, or to restructure so `main.py` is at the `pipeline/` root and `backend/` becomes a package.

3. **Verify the action-tag parsing** in each agent. The regex `r"<action>(.*?)</action>"` uses non-greedy matching — confirm Claude (Haiku) reliably emits the `<action>` block without wrapping it in markdown code fences. If it does, extend the regex or add a fence-stripping step.

### Short-term — quality and robustness

4. **Add live web search to the Historian** (Stage 3). The research engine currently uses Claude's training knowledge. Wiring in a real search API (Brave, Tavily, or Anthropic's `web_search` tool) would dramatically improve fact quality. This is the highest-value spec-compliance gap.

5. **Upgrade Script and Validation to `claude-haiku-4-5`** (or Sonnet). Per spec §11, these stages most directly affect output quality. Change `HAIKU` to a separate `SCRIPT_MODEL` constant in `claude_client.py` to make this a one-line switch.

6. **Persist chat histories to the job file**. Add a `chat_histories: dict` key to the HSGJob so conversation context survives page refreshes. The backend already loads/saves the full job on every request — it's just a matter of writing the history in and reading it back.

7. **Remove the LLM-driven `create_job` action** from the topic-hunter agent system prompt. The frontend's direct "Select → Create Job" button is more reliable. Keeping two paths for job creation is a source of bugs.

### Medium-term — spec coverage

8. **Stage 7: Style Bible / Character Consistency** — a Claude call that identifies characters in the storyboard, checks a persistent registry, and outputs Higgsfield character creation requests for new figures. Can be built without Higgsfield integration (outputs the request data only).

9. **Higgsfield integration** — connect `generate_visual_prompts` output to the actual Higgsfield MCP tools (`generate_image`, `generate_video`) to produce real scene assets. The visual prompt format is already Higgsfield-compatible.

10. **Stage 10–12: Voiceover, Subtitles, Music** — requires TTS API (Higgsfield `generate_audio`, ElevenLabs, or similar). Out of scope until visual generation is working.

11. **Analytics feedback loop** — after a video is published, capture performance data and feed it back into `SCORE_WEIGHTS` in `topic_engine.py` to auto-tune which topics get surfaced.
