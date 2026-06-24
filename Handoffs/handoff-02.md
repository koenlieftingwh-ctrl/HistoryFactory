# HistoryFactory — Handoff 02

**Date:** 2026-06-24  
**Branch:** `initial-setup`  
**Backend:** `http://localhost:8001` (pipeline FastAPI)

---

## Goals

1. **Full 4-agent pipeline functional in the browser** — Topic Hunter → Historian → Director → Editor, with gated tab progression and a shared HSGJob state object.
2. **Actual video output** — The pipeline currently produces text assets only. The missing step is calling Higgsfield's video/image generation API to render the storyboard scenes into actual clips.
3. **Render stage integration** — Add a "Render" step after the Editor that submits each visual prompt to Higgsfield and tracks generation job IDs back in the HSGJob.

---

## Current Code State

### What works end-to-end (confirmed via curl)

| Stage | Endpoint | Status |
|---|---|---|
| Topic Hunter — generate & score topics | `POST /agent/topic-hunter/chat` | ✅ |
| Topic Hunter — create job | `POST /agent/topic-hunter/select-topic` | ✅ |
| Historian — research (Stage 3) | `POST /agent/historian/chat` | ✅ |
| Historian — validate (Stage 4) | `POST /agent/historian/chat` | ✅ |
| Director — script (Stage 5) | `POST /agent/director/chat` | ✅ |
| Director — storyboard (Stage 6) | `POST /agent/director/chat` | ✅ |
| Editor — visual prompts (Stage 8) | `POST /agent/editor/chat` | ✅ |
| Editor — EDL (Stage 13) | not yet tested in browser | ⚠️ |
| Editor — thumbnails/metadata (Stages 14-15) | not yet tested in browser | ⚠️ |
| **Higgsfield render** | not wired | ❌ |

### Active job
- **Job ID:** `16b6dcdb`
- **Topic:** "The Viking 'Silk Road' to Baghdad"
- **Stages complete:** `topic_hunter`, `historian`, `director`
- **Has:** research, validation, script (156 words, ~62s), storyboard (15 scenes), visual_prompts (15 prompts, all `media_type: video`)
- **Missing:** edl, thumbnail_concepts, publish_metadata
- **Job status field:** "storyboarding" (stale — director is actually done; job.status isn't being synced with stage_completed)

### Visual prompts format issue
`generate_visual_prompts` asks Gemini to select a `model` field (`seedance_2_0` / `soul_2` / `flux_1_1_ultra`) but the returned JSON has `model: null` for all 15 prompts. The engine instruction works but the model selection logic isn't being followed. All prompts default to null — this must be filled in before Higgsfield calls can be made.

### Higgsfield account
- **Plan:** Free
- **Credits:** 10
- **Cost per 5s clip:** 7.5 credits (kling3_0_turbo, 720p, 9:16)
- **Cost per full video (15 scenes × 5s):** ~112 credits
- **Conclusion:** Can generate 1 demo clip on current balance; need paid plan for full renders

---

## File Map

```
pipeline/
├── backend/
│   ├── main.py                        # FastAPI app — 4 agent chat endpoints + REST helpers
│   ├── job_store.py                   # HSGJob CRUD (pipeline/data/jobs/{job_id}.json)
│   ├── agents/
│   │   ├── topic_hunter.py            # System prompt builder for Topic Hunter
│   │   ├── historian.py               # System prompt builder for Historian
│   │   ├── director.py                # System prompt builder for Director
│   │   └── editor.py                  # System prompt builder for Editor
│   └── engines/
│       ├── claude_client.py           # Gemini 2.5 Flash client (generate + chat)
│       ├── topic_engine.py            # generate_topics, score_topic, generate_and_score
│       ├── research_engine.py         # research_topic, validate_research
│       ├── script_engine.py           # generate_script, generate_storyboard
│       └── editor_engine.py           # generate_visual_prompts, generate_edl,
│                                      #   generate_thumbnail_concepts, generate_metadata
├── frontend/
│   └── index.html                     # 4-tab UI, job sidebar, job state panel
├── data/
│   └── jobs/
│       └── 16b6dcdb.json             # Only job — Viking Silk Road to Baghdad
└── .env                               # GOOGLE_API_KEY=...

topic-hunter/                          # Standalone topic chat app (port 8000, separate)
```

---

## Files Actively Edited This Session

| File | What changed |
|---|---|
| `pipeline/backend/agents/historian.py` | Rewrote system prompt — explicit "NEVER write content yourself", added example replies with action tags, added fallback-friendly context |
| `pipeline/backend/agents/director.py` | Same — added "NEVER write the script/storyboard in the reply" rule, tightened action tag instructions |
| `pipeline/backend/agents/editor.py` | Same pattern — added "NEVER write prompts/metadata yourself", added "all" action example |
| `pipeline/backend/main.py` | Added `FALLBACK_REPLIES` dict — when Gemini emits only `<action>` tag with no text, the stripped reply was `""` (blank bubble in UI). Fallback now provides a short status message. Also changed `max_tokens=1024` → `512` for all agent chat calls |
| `pipeline/frontend/index.html` | Added auto-select: `loadJobs()` now fetches and sets `currentJob` to the most recent job on page load, so tab locks work correctly after a page refresh |

---

## What Failed

### 1. Empty reply bug — blank bubbles in chat
**Problem:** Gemini would emit `<action>{"type":"validate"}</action>` with nothing else. After stripping the action tag, `reply = ""`. The UI showed a blank assistant bubble. Users assumed the action didn't run.  
**Fix:** Added `FALLBACK_REPLIES` dict in `main.py`. If `clean.strip() == ""` after extraction, inject e.g. `"Running adversarial validation on the research..."`.

### 2. Director tab locked after page refresh
**Problem:** `currentJob` lives only in JS memory. On any page refresh, it resets to `null`, which causes the tab-unlock logic (`if (!completed.includes(prevStage)) return`) to treat all tabs as locked.  
**Fix:** `loadJobs()` now auto-selects the most recent job from the API on first load.

### 3. Agent replies too verbose — model writes full content in chat
**Problem:** Gemini ignores "don't write the script yourself" in the system prompt and dumps the entire script/storyboard/validation into the chat reply in addition to emitting the action tag. This is a model instruction-following failure, not a code bug.  
**Partial fix:** Reduced `max_tokens` to 512 so the reply is cut off after ~380 words. This limits damage but doesn't stop the model from starting to write content. The engine still runs correctly regardless.  
**What didn't work:** More explicit "NEVER write X" instructions in the system prompt — Gemini ignores them when the user asks a question that naturally elicits that content (e.g. "what did the storyboard produce?").

### 4. Visual prompt `model` field returns null
**Problem:** `generate_visual_prompts` asks the model to choose `seedance_2_0` / `soul_2` / `flux_1_1_ultra` per scene but Gemini returns `"model": null` for all 15 prompts in the current job.  
**Status:** Not yet fixed. The visual prompts exist and are usable — the model selection just needs to be hardcoded (e.g. all video scenes → `seedance_2_0`) or fixed in the prompt.

### 5. job.status field is stale
**Problem:** `job["status"]` is set to string values like `"storyboarding"` or `"scripting"` manually inside the engines, but `stage_completed[]` is the authoritative source of truth and they diverge. Current job shows `status: "storyboarding"` even though director is complete.  
**Status:** Not yet fixed. The frontend uses `stage_completed[]` for tab logic so this doesn't break anything, but it's misleading in the job state panel.

---

## Next Steps (in priority order)

### 1. Fix visual prompt model selection
In `editor_engine.py`, hardcode the model assignment instead of asking Gemini to choose:
- Any `media_type: "video"` scene → `seedance_2_0`
- Any `media_type: "image"` portrait/character scene → `soul_2`
- Everything else → `kling3_0_turbo`

This unblocks Higgsfield rendering.

### 2. Wire Higgsfield render into the pipeline

**Architecture:**
- Add `pipeline/backend/engines/render_engine.py`
- Function: `submit_render_jobs(job) -> job` — loops through `job["visual_prompts"]`, calls Higgsfield REST API per scene, saves returned generation job IDs to `job["render_jobs"] = [{"scene_id", "higgsfield_job_id", "status": "pending"}]`
- Add a poll endpoint: `GET /jobs/{job_id}/render-status` — re-checks each pending Higgsfield job ID and updates status
- Add `POST /agent/editor/render` (or a button in the UI) to trigger the render

**Higgsfield REST API:** The MCP is connected to Claude Code but the FastAPI backend needs direct REST calls. Need to find the Higgsfield API base URL and auth token format. The MCP tools show model IDs (`seedance_2_0`, `kling3_0_turbo`) and parameters — the REST endpoint likely mirrors the MCP schema. Storing the Higgsfield API key in `pipeline/.env` as `HIGGSFIELD_API_KEY=...`.

**Credit reality check:** Free plan = 10 credits = 1 clip (7.5 credits each at kling3_0_turbo/720p/5s). Need a paid plan (~$20-50/mo) to render full videos. Until then, the render stage should gracefully handle an "insufficient credits" error and show remaining credits in the UI.

### 3. Add a "Render" tab or section to the frontend
After the Editor tab completes, show:
- A list of the 15 scenes with their prompts
- A "Render All" button (submits all, with cost preflight)
- Per-scene status indicators (pending / generating / done)
- Thumbnails of completed generations

### 4. Fix job.status sync
Set `job["status"]` at the end of each `mark_stage_complete()` call based on `stage_completed[]` length, or remove it and derive status from `stage_completed` everywhere.

### 5. Complete the full browser run-through
The Editor tab (EDL, thumbnails, metadata) hasn't been tested in the browser yet — only the visual_prompts sub-stage was confirmed working. Run a complete end-to-end pass:
1. Open `http://localhost:8001`
2. Job `16b6dcdb` auto-loads (historian + director complete)
3. Click Director tab → generate storyboard (already done)
4. Click Editor tab → trigger `all` action → confirm edl + thumbnails + metadata save to job
5. Verify Editor tab marks `editor` in `stage_completed`

---

## Environment

- **Backend:** `py -m uvicorn main:app --port 8001 --reload` (run from `pipeline/backend/`)
- **Google API Key:** in `pipeline/.env` as `GOOGLE_API_KEY`
- **Model:** `gemini-2.5-flash` with `thinking_budget=0`
- **Higgsfield MCP:** connected to Claude Code session (not to the FastAPI backend)
- **Higgsfield credits:** 10 (free plan) — check balance before any render call
