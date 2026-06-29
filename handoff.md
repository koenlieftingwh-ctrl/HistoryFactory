# HSG Factory — Handoff Doc (Session 2026-06-29)

## Overall plan (5 phases)

1. **Postgres schema + Obsidian handoff layer** — ✅ done (prior session)
2. **Agent A — Generation pipeline** — ✅ done (prior session + this session)
3. **Agent B — Publishing** — not started
4. **Agent B — Reporting** — not started
5. **Scheduler / cron entrypoints per agent** — not started

---

## What we built this session

The existing Python/FastAPI pipeline already had stages 1–8 (Topic → Scoring →
Research → Validation → Script → Storyboard → Visual Prompts → EDL/Thumbnails/
Metadata). This session completed stages 9–13:

| Stage | What was built |
|---|---|
| 9 — Higgsfield Render | Fixed submission pipeline; rendered job `8b4c6bfb` via MCP tools |
| 10 — Voiceover | Google Cloud TTS (Neural2-D, REST API with `GOOGLE_TTS_KEY`) |
| 11 — Subtitles | Whisper forced alignment → SRT + VTT; falls back to even distribution |
| 12 — Music | Local royalty-free library selector (no tracks yet — graceful skip) |
| 13 — Assembly | ffmpeg: download scenes → concat → mix voiceover + BGM → burn subs |

---

## Current goal

**First full video produced end-to-end.** Job `8b4c6bfb` ("The Viking King Who
Converted") has a completed 25MB MP4 at
`pipeline/data/assets/8b4c6bfb_final.mp4`. The next step is Agent B (Publishing)
— picking up jobs where `assembly` is present, uploading to YouTube Shorts via
the YouTube Data API, and writing back the publish result.

---

## Current state

### Completed job: `8b4c6bfb`

```
topic_hunter  ✓  "The Viking King Who Converted (and then backslid)"
historian     ✓  11 facts, 90% accuracy, publishable
director      ✓  5-act script (159 words, ~63s) + 6-scene storyboard
editor        ✓  visual prompts, EDL, thumbnail concepts, metadata
render        ✓  6 scenes via Higgsfield MCP (5×soul_2 images + 1×kling3_0_turbo video)
voiceover     ✓  pipeline/data/assets/8b4c6bfb_voiceover.mp3 (625KB, Google TTS)
subtitles     ✓  pipeline/data/assets/8b4c6bfb_subtitles.srt/.vtt
music         —  skipped (no track file present)
assembly      ✓  pipeline/data/assets/8b4c6bfb_final.mp4 (25MB, 720×1280, 65s)
```

### Higgsfield REST API status

The direct REST API (`api.higgsfield.ai`) is returning 521/522 errors for this
account. **All Higgsfield rendering must go through the MCP tools** (available
inside Claude Code sessions). The Python render engine's HTTP calls will keep
failing until the REST API access issue is resolved separately.

### Server

FastAPI on `http://127.0.0.1:8001`, started manually with uvicorn. No cron or
daemon setup yet.

---

## Files touched this session

### New files

```
pipeline/backend/engines/voiceover_engine.py   Google Cloud TTS stage
pipeline/backend/engines/subtitle_engine.py    Whisper alignment → SRT/VTT
pipeline/backend/engines/music_engine.py       Local library track selector
pipeline/backend/engines/assembly_engine.py    ffmpeg assembly pipeline
pipeline/data/music/                           Empty — drop MP3s here
pipeline/data/assets/                          Created; holds audio/video outputs
```

### Modified files

```
pipeline/backend/main.py
  - Added BackgroundTasks import
  - Fixed topic_hunter_chat: unpacked gemini_chat tuple (was TypeError)
  - Made POST /jobs/{id}/render background (returns immediately, no more hangs)
  - Removed duplicate POST /jobs/{id}/render route
  - Added POST /jobs/{id}/voiceover
  - Added POST /jobs/{id}/subtitles
  - Added POST /jobs/{id}/music
  - Added POST /jobs/{id}/assemble (background)
  - Added POST /jobs/{id}/post-render (chains all 4 in background)

pipeline/backend/engines/render_engine.py
  - Added _post_with_retry() with exponential backoff [2,5,15,30s]
  - Retries on: 5xx, 522, 524, ConnectionError, Timeout
  - submit_render_jobs() now skips scenes already in submitted/done state
    (retry-safe — re-hitting /render won't re-submit completed scenes)

pipeline/backend/engines/topic_engine.py
  - Unpacked generate() return tuple in generate_topics() and score_topic()
    (pre-existing bug committed in prior session)

pipeline/frontend/index.html
  - Fixed render button: re-fetches full job after POST instead of using
    slim response (was wiping the job state panel)
  - Added "▶ Voiceover → Subtitles → Assemble" button (appears when
    render_status=completed and assembly not yet run)
  - Added assembly result card showing final video path + duration
  - Fixed post-render poll: checks for job.assembly presence, not job.status
    (status was already "completed" from render, causing false-positive early exit)
```

### Job data

```
pipeline/data/jobs/8b4c6bfb.json   Harald Bluetooth job, fully assembled
pipeline/data/assets/8b4c6bfb_voiceover.mp3
pipeline/data/assets/8b4c6bfb_subtitles.srt
pipeline/data/assets/8b4c6bfb_subtitles.vtt
pipeline/data/assets/8b4c6bfb_final.mp4
```

---

## What failed / known gaps

### Higgsfield REST API (521/522)

Direct HTTP calls to `api.higgsfield.ai` fail with Cloudflare 521/522 for
this account. The render engine still tries the REST path and will fail. Until
resolved, renders must be submitted manually via the MCP tools inside a Claude
Code session, then the job JSON updated with the returned IDs. See the
"render via MCP" pattern used for `8b4c6bfb` this session.

### Music library is empty

`pipeline/data/music/` exists but has no tracks. Assembly skips BGM gracefully
(`music.status = "missing"`). To enable BGM:
- Drop an MP3 into `pipeline/data/music/`
- Register it in `music_engine.py`'s `MUSIC_LIBRARY` dict under the matching
  mood key (e.g. `"neutral": ["neutral_documentary.mp3"]`)

### Subtitle quality (fallback path)

When Whisper can't run (import error, no CUDA, etc.) the subtitle engine falls
back to evenly distributing words across the voiceover duration. The fallback
produces correct timing structure but won't be word-accurate. On this machine
Whisper ran successfully.

### No video preview in UI

The final MP4 is a local file path — the frontend has no player or download
link yet. You can open it directly from `pipeline/data/assets/`.

### compute_status race condition

`job_store.compute_status()` returns `"completed"` as soon as
`render_status == "completed"`, even before assembly runs. The post-render
poll was accidentally triggering on this early "completed" state. Fixed in the
frontend by polling on `job.assembly` presence instead. The underlying
`compute_status` function should eventually gain an "assembling" state tracked
separately from `render_status`.

### No retry/backoff on TTS or assembly

`voiceover_engine.py` and `assembly_engine.py` have a single attempt with no
retry. A transient TTS API error will fail the whole post-render chain. Low
priority since TTS is very reliable, but worth noting.

### Cost tracking not updated for post-render stages

`cost_tracking` in the job JSON tracks LLM token costs and Higgsfield render
credits but does not currently record Google TTS spend (billed per character
externally). Worth adding a `tts_characters` field to `cost_tracking` later.

---

## What you should do next

### 1. Add video preview to the UI

The assembly card shows the file path but no player. Serve the `data/assets/`
directory as a static mount and add an `<video>` tag with a `/assets/<job_id>_final.mp4`
src. In `main.py`, add:
```python
app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")
```
Then update the assembly card in `renderJobState()` to render a `<video>` element.

### 2. Fix the Higgsfield REST API or fully move rendering to MCP

Option A: contact Higgsfield support about 521/522 errors on this API key.
Option B: since rendering currently requires a live Claude Code session (for MCP
access), document it as a manual step and focus on making the MCP submission
workflow faster (e.g. a helper that reads a job's visual_prompts and submits
them all in one message).

### 3. Build Agent B — Publishing

Reads jobs where `assembly` is present and `review_status = 'approved'`.
Steps:
- Use the YouTube Data API to upload `assembly.final_video_path`
- Use `publish_metadata` (title, description, tags) already generated by the
  Editor stage
- Call `db.recordPublishResult()` (already implemented in the Node scaffold;
  needs porting or equivalent in the Python stack)
- Write back `publish.post_id` and `publish.scheduled_time` to the job

Key file to create: `pipeline/backend/agents/publisher.py` +
`pipeline/backend/engines/publish_engine.py`

YouTube Data API credentials needed: OAuth2 client ID/secret + refresh token,
or a service account with YouTube scope. Add to `pipeline/.env`.

### 4. Build Agent B — Reporting

Weekly cadence. Pulls YouTube Analytics (views, CTR, retention) for published
jobs, joins against `hsg_jobs`, calls Claude to summarize, writes updated
`scoring_weights`. The Obsidian report note writer is already implemented in
the original Node scaffold (`src/obsidian.js`).

### 5. Add BGM

Drop a royalty-free MP3 (e.g. from Pixabay or ccMixter) into
`pipeline/data/music/neutral_documentary.mp3` to enable background music on
documentary-style jobs. The music engine will pick it up automatically — no
code change needed.

### 6. Fix compute_status to track assembly

Add `"assembling"` as a tracked state derived from `job["assembly"]` presence vs
`job["status"] == "assembling"` to prevent the race condition described above.
The cleanest fix: add `assembly_status` as a separate field (like `render_status`)
rather than overloading `status`.

### 7. Wire up the full autorun endpoint for new jobs

`POST /jobs/autorun` runs stages 1–8 but stops before render. Extend it to
optionally continue through post-render if a flag is passed, making fully
unattended job creation possible for future scheduler integration.
