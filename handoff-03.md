# Handoff 03 — HistoryFactory Pipeline

**Date:** 2026-06-27  
**Branch:** `initial-setup`  
**Last commit:** `6d4e27e checkpoint proof of concept`

---

## Goals

1. **Live cost tracking in HSGJob** — track every Gemini API call's token count and USD cost, plus Higgsfield render credit estimates, accumulated directly in the job JSON as the pipeline runs.
2. **Display cost tracking in the UI** — surface `cost_tracking` in the frontend alongside the existing render estimate card.
3. **Fix the Higgsfield REST API** — `api.higgsfield.ai` returns 522. Currently renders must be submitted manually via MCP from a Claude Code session. Need a working programmatic path.
4. **Complete pending render submissions** — WWI Pigeon Corps and Roman Bathhouse jobs have all 6 scenes submitted via MCP; IDs have been saved to their JSON files.

---

## Current State of the Code

### Pipeline Architecture

FastAPI backend on port 8001 (`pipeline/backend/`), static HTML frontend at `pipeline/frontend/index.html`, job JSONs persisted at `pipeline/data/jobs/{job_id}.json`.

4-agent flow: **Topic Hunter → Historian → Director → Editor**  
Each agent sends `<action>{"type":"..."}` tags; backend strips and runs the relevant engine.  
`stage_completed[]` is the authoritative progression tracker; `compute_status()` derives `job.status` from it.

### HSGJob Schema (current fields)

```json
{
  "job_id": "...",
  "status": "pending|researching|scripting|render_ready|rendering|completed|failed",
  "config": {...},
  "topic": {...},
  "research": null,
  "validation": null,
  "script": null,
  "storyboard": null,
  "visual_prompts": null,
  "render_estimate": {
    "video_clip_count": 3,
    "static_image_count": 3,
    "credits_video": 22.5,
    "credits_image": 1.5,
    "credits_total": 24.0
  },
  "render_jobs": [
    {
      "scene_id": "scene_001",
      "render_type": "video_clip|static_image",
      "model": "kling3_0_turbo|soul_cinematic|cinematic_studio_2_5",
      "higgsfield_job_id": "uuid-from-mcp",
      "status": "submitted|done|failed"
    }
  ],
  "render_status": "rendering|completed|insufficient_credits|null",
  "thumbnail_concepts": null,
  "publish_metadata": null,
  "edl": null,
  "errors": [],
  "stage_completed": ["topic_hunter", "historian", "director", "editor"],
  "cost_tracking": {
    "llm_calls": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "llm_cost_usd": 0.0,
    "render_credits_estimated": 0.0,
    "render_credits_used": 0.0
  }
}
```

`cost_tracking` is new — only populated on jobs created after this session. Existing jobs don't have it; `add_llm_cost()` uses `setdefault` so it back-fills gracefully if the field is missing.

### Existing Jobs

| job_id | Topic | render_status | Notes |
|--------|-------|---------------|-------|
| `16b6dcdb` | Viking Silk Road | `completed` | All 6 scenes done with result URLs |
| `02ddb993` | Roman Bathhouse | `rendering` | 6 MCP job IDs saved (2 video, 4 image) |
| `fae72b81` | WWI Pigeon Corps | `rendering` | 6 MCP job IDs saved (3 video, 3 image) |
| `ec55d45d` | (unknown) | `researching` | Stopped after topic_hunter |
| `a6bafc5a` | (unknown) | `researching` | Stopped after topic_hunter |
| `e8855b25` | (unknown) | `researching` | Stopped after topic_hunter |

### Render job IDs (Roman Bathhouse `02ddb993`)

| Scene | Type | Model | Higgsfield ID |
|-------|------|-------|---------------|
| scene_01 | video_clip | kling3_0_turbo | `5389e4f5-f301-436f-b700-5ea07556494a` |
| scene_02 | static_image | soul_cinematic | `2a7ae715-46ba-446b-b6d1-7dac39d2d86a` |
| scene_03 | static_image | soul_cinematic | `8ca06e6e-fc70-4ff2-9533-337e593c2588` |
| scene_04 | static_image | soul_cinematic | `d0cde3ca-77c4-4afe-9311-28c63291180e` |
| scene_05 | video_clip | kling3_0_turbo | `ea211da3-9ef6-4044-a40d-dd446452f403` |
| scene_06 | static_image | soul_cinematic | `c3778458-de7b-4499-9a42-069b592447c9` |

### Render job IDs (WWI Pigeon Corps `fae72b81`)

| Scene | Type | Model | Higgsfield ID |
|-------|------|-------|---------------|
| scene_001 | video_clip | kling3_0_turbo | `5539b217-11bb-474a-88cc-3dd969071d12` |
| scene_002 | static_image | soul_cinematic | `dd9af749-20fb-499c-a375-126e4d14d8eb` |
| scene_003 | video_clip | kling3_0_turbo | `f87ea22a-e6da-4184-8b9a-42b0778f29d0` |
| scene_004 | video_clip | kling3_0_turbo | `3323657e-034c-4a48-895b-7f611bb83085` |
| scene_005 | static_image | soul_cinematic | `0955c0d6-8392-437a-a504-0ce3832a460c` |
| scene_006 | static_image | soul_cinematic | `9e0f9994-ffab-4707-a1eb-d2b639d871a3` |

---

## Files Actively Edited This Session

### `pipeline/backend/engines/claude_client.py`
**What changed:** `generate()` and `chat()` now return `(text, usage_dict)` instead of just `text`. Added `_extract_usage()` which reads `response.usage_metadata` and computes USD cost.

```python
_INPUT_COST_PER_M = 0.075   # Gemini 2.5 Flash non-thinking input
_OUTPUT_COST_PER_M = 0.30   # Gemini 2.5 Flash non-thinking output
```

**Watch out:** The linter/formatter in this session kept reverting changes to this file. If edits aren't sticking, use `Write` (full file rewrite) instead of `Edit`.

### `pipeline/backend/job_store.py`
**What changed:**
- `create_job()` now includes `cost_tracking` field with zero values
- New `add_llm_cost(job, usage)` helper that accumulates tokens and cost into `job["cost_tracking"]`

**Watch out:** Same revert problem as above — was reverted by linter mid-session and had to be rewritten.

### `pipeline/backend/engines/research_engine.py`
**What changed:** Both `generate()` calls now unpack `(raw, usage)` and call `add_llm_cost(job, usage)`.

### `pipeline/backend/engines/script_engine.py`
**What changed:** Same — both `generate()` calls track usage.

### `pipeline/backend/engines/editor_engine.py`
**What changed:** All 4 `generate()` calls track usage. Additionally, after `generate_visual_prompts()` sets `job["render_estimate"]`, it copies `credits_total` into `job["cost_tracking"]["render_credits_estimated"]`.

### `pipeline/backend/engines/topic_engine.py`
**What changed:** Both `generate()` calls now unpack `(raw, _)` — discarding usage since there's no job object at topic generation time (topics are selected before a job is created).

### `pipeline/backend/main.py`
**What changed:** All 3 agent `gemini_chat()` calls (historian, director, editor) now unpack `(reply_raw, _chat_usage)` and call `add_llm_cost(job, _chat_usage)` if a job is loaded. Topic hunter discards usage (`_usage`) since the job may not exist yet.
Also added `add_llm_cost` to the `from job_store import ...` line.

### `pipeline/data/jobs/02ddb993.json` and `fae72b81.json`
**What changed:** `render_jobs` array was patched from all `"status": "failed"` with null IDs to `"status": "submitted"` with real Higgsfield job IDs from MCP submissions.

---

## What Was Tried and Failed

### Linter reverting file edits
Using `Edit` tool with `old_string` matching to change specific lines in the engine files repeatedly failed — the linter would reset the files back to the pre-edit state. Verified by grepping after edits and finding the old code still present. **Fix:** Use `Write` (full file rewrite) instead of `Edit` for these files.

### Higgsfield REST API (`api.higgsfield.ai`)
All POST requests to `https://api.higgsfield.ai/v1/generation/video` and `/image` return 522 (connection timeout). This URL is wrong — the MCP tool uses an internal Anthropic gateway that doesn't match this public address. `get_balance()` in `render_engine.py` returns -1 because of this. The "Render All" button in the UI hits this broken path and always fails. **Workaround:** Submit renders manually from a Claude Code session using the `mcp__e07ad072-31af-4da5-81cc-9f3dc69d5342__generate_video` and `generate_image` MCP tools, then patch the job JSON with the returned IDs.

### `seedance_2_0` model
Requires Plus plan — fails on Starter plan (280 credits). Switched to `kling3_0_turbo`.

### `flux_1_1_ultra` model
Does not exist in the Higgsfield catalog. Switched to `cinematic_studio_2_5`.

### `soul_2` model
Requires a reference image parameter. Switched to `soul_cinematic` (no reference needed).

---

## Pending / Next Steps

### 1. Show `cost_tracking` in the UI
The data is now in every new job's JSON but the frontend (`pipeline/frontend/index.html`) doesn't display it yet. Add a "💰 Cost" section to the job state card in `renderJobState()` showing:
- LLM calls made, input/output tokens, USD cost
- Render credits estimated (from `cost_tracking.render_credits_estimated`)

### 2. Fix "Render All" button
The button calls `POST /jobs/{job_id}/render` → `submit_render_jobs()` which hits the broken REST API. Options:
- **Short-term:** Disable the button with a tooltip explaining renders must be submitted via Claude Code session.
- **Long-term:** Build a local bridge server/proxy that translates REST calls to MCP tool calls. Or find the real internal Higgsfield API endpoint (check network traffic from the Higgsfield web app).

### 3. Poll render results for Roman Bathhouse and WWI Pigeon Corps
Both jobs have Higgsfield IDs saved. The MCP `job_display` tool can check status. Once renders complete, update `render_jobs[].status` to `"done"` and add `result_url`, then set `render_status: "completed"`.

To check status via MCP:
```
mcp__e07ad072-31af-4da5-81cc-9f3dc69d5342__job_display with the job IDs
```

### 4. `render_credits_used` field
Currently always 0. Should be updated when renders complete (when polling confirms `status: "done"`). Each done video_clip should add `CREDITS_PER_VIDEO_CLIP` (7.5) and each done static_image should add `CREDITS_PER_STATIC_IMAGE` (0.5) to `cost_tracking.render_credits_used`.

### 5. Back-fill `cost_tracking` on old jobs
Existing jobs (`16b6dcdb`, `02ddb993`, `fae72b81`, etc.) don't have the `cost_tracking` field. They'll work fine (the `add_llm_cost` setdefault handles missing field), but if you want historical cost data, you'd need to add the field manually to those JSONs.

---

## Environment

```
Server:         py -m uvicorn main:app --port 8001 --reload
Working dir:    pipeline/backend/
Frontend:       http://localhost:8001/ (served as static files)
Env file:       pipeline/.env
  GOOGLE_API_KEY=AIzaSyB-7ECY3z47L09FIxyy739kRAF7SqafR00
  HIGGSFIELD_API_KEY=65c3099a-b282-4ef6-bb81-7dfeeb9738fe
Account:        Higgsfield Starter plan, 280 credits total
  kling3_0_turbo: 7.5 credits / 5s video @ 720p
  soul_cinematic: ~0.5 credits / image
  cinematic_studio_2_5: ~0.5 credits / image
```

## Cost Estimate per Video

| Cost type | Amount |
|-----------|--------|
| Gemini 2.5 Flash LLM (~10 calls, ~15k tokens) | ~$0.001 |
| Higgsfield renders (3 video + 3 image) | ~24 credits |
| Total at $0.0004/credit estimate | ~$0.01 |
