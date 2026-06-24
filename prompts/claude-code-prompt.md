# Prompt for Claude Code

Copy/paste everything below into Claude Code in the `pipeline/` repo.

---

I need to fix a bug and reduce rendering costs in the HistoryFactory pipeline. Context: this is the 4-agent pipeline (Topic Hunter → Historian → Director → Editor) documented in `handoff-02.md`. Current job `16b6dcdb` has a 15-scene storyboard where every visual prompt's `model` field is `null`, blocking Higgsfield rendering entirely. Even once fixed, 15 scenes × 5s clips (~7.5 credits each on kling3_0_turbo/720p) costs ~112 credits per video, which isn't sustainable on a small budget.

Please implement the following changes:

## 1. Fix the null `model` field bug
In `pipeline/backend/engines/editor_engine.py`, in `generate_visual_prompts`, stop asking Gemini to choose the `model` field — it's unreliable. Instead, hardcode the assignment after Gemini returns the prompts:
- `media_type: "video"` → `seedance_2_0`
- `media_type: "image"` with a portrait/character subject → `soul_2`
- Any other `media_type: "image"` → leave as a static image (no video model needed)

## 2. Reduce scene count
Update the storyboard generation step in `pipeline/backend/engines/script_engine.py` (`generate_storyboard`) so the system prompt targets **5-7 scenes total** for a 60-90 second script, not 15. Each scene should cover roughly 10-15 seconds of narration instead of ~4 seconds.

## 3. Add a `render_type` field per scene
In the visual prompts output, add a `render_type` field per scene: either `"video_clip"` or `"static_image"`. Apply this rule:
- Scenes with significant motion/action (e.g. battles, movement, ships sailing) → `"video_clip"`
- Establishing shots, portraits, maps, or static scenes → `"static_image"`
- Target roughly 40-50% of scenes as `static_image` to cut credit usage

## 4. Update `render_engine.py` (new or in-progress file per the handoff's "Next Steps")
When submitting jobs to Higgsfield:
- `render_type: "video_clip"` → call the video generation model assigned in step 1
- `render_type: "static_image"` → call an image generation model only (skip video credits entirely); these will be animated later in editing via Ken Burns pan/zoom, not rendered as motion by Higgsfield
- Before submitting, calculate and log total estimated credit cost for the job (sum of video clip costs only, using 7.5 credits/clip as the current known rate) and compare against current account balance (check via the Higgsfield balance/credits endpoint or MCP tool if available). If insufficient, halt and report the shortfall instead of partially rendering.

## 5. Fix job.status sync (from handoff's known issues list)
Wherever `job["status"]` is set as a manual string (e.g. `"storyboarding"`), replace it with logic that derives status from `job["stage_completed"]` — e.g. a small `compute_status(stage_completed)` helper used everywhere instead of scattered manual string assignments.

## 6. Frontend
In `pipeline/frontend/index.html`, on the scene list / render section, show each scene's `render_type` badge (video vs static image) and the running total estimated credit cost before the user clicks "Render All."

Please implement these in order, test stage 1-2 against the existing job `16b6dcdb` or a fresh test job, and report back what changed and what still needs manual verification (especially the Higgsfield REST API auth, which the handoff notes is still unresolved — MCP is connected to Claude Code but not to the FastAPI backend).
