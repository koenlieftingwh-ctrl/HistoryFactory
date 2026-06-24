"""Editor agent — Stages 8, 13, 14, 15: Visual Prompts, EDL, Thumbnails, Metadata."""
import json

SYSTEM = """You are the Editor — the final agent in the History Shorts Generator pipeline.
Your job: take the directed storyboard and produce everything needed to render and publish the video.

You run four stages:
1. VISUAL PROMPTS (Stage 8): Convert each storyboard scene into a Higgsfield-ready generation prompt,
   choosing the right model (seedance_2_0 / soul_2 / flux_1_1_ultra) and media type (image/video).
2. EDL (Stage 13): Edit Decision List — map scenes to timeline with start/end times and transitions.
3. THUMBNAILS (Stage 14): 3 thumbnail concepts with overlay text, optimised for CTR.
4. METADATA (Stage 15): Platform-optimised title, description, tags, and hashtags.

You can discuss creative choices: visual style preferences, thumbnail text ideas, platform strategy.

TO GENERATE VISUAL PROMPTS, output:
<action>{"type":"visual_prompts"}</action>

TO GENERATE THE EDL, output:
<action>{"type":"edl"}</action>

TO GENERATE THUMBNAIL CONCEPTS, output:
<action>{"type":"thumbnails"}</action>

TO GENERATE PUBLISHING METADATA, output:
<action>{"type":"metadata"}</action>

TO RUN ALL FOUR IN SEQUENCE, output:
<action>{"type":"all"}</action>

After all stages complete, the job is DONE. Summarise the output package:
- Number of visual prompts (image vs video split)
- Top thumbnail concept overlay text
- Final title for publishing
- Any warnings or next steps (e.g. "upload these prompts to Higgsfield to generate visuals")."""


def build_system(job: dict | None) -> str:
    lines = [SYSTEM]
    if not job:
        lines.append("\nNO ACTIVE JOB: Ask the user to start a job in the Topic Hunter.")
        return "\n".join(lines)

    topic = job.get("topic", {})
    config = job.get("config", {})
    stage_done = job.get("stage_completed", [])

    lines.append(f"\nACTIVE JOB: {job['job_id']}")
    lines.append(f"Topic: {topic.get('title')}")
    lines.append(f"Platform: {config.get('target_platform')} | Style: {config.get('visual_style')}")

    if "director" not in stage_done:
        lines.append("\nWARNING: Director stage not complete. Script and storyboard must be finished first.")
    else:
        storyboard = job.get("storyboard", {})
        lines.append(f"Storyboard: {len(storyboard.get('scenes', []))} scenes ready.")

    if job.get("visual_prompts"):
        vp = job["visual_prompts"]
        n_video = sum(1 for p in vp if p.get("media_type") == "video")
        n_image = len(vp) - n_video
        lines.append(f"\nVISUAL PROMPTS: {len(vp)} total ({n_video} video, {n_image} image)")

    if job.get("edl"):
        lines.append(f"EDL: {len(job['edl'])} timeline entries")

    if job.get("thumbnail_concepts"):
        tc = job["thumbnail_concepts"]
        lines.append(f"THUMBNAILS: {len(tc)} concepts — top: \"{tc[0].get('overlay_text') if tc else ''}\"")

    if job.get("publish_metadata"):
        m = job["publish_metadata"]
        lines.append(f"METADATA: Title: \"{m.get('title')}\"")

    if job.get("status") == "completed":
        lines.append("\nJOB STATUS: COMPLETED. All stages done.")

    return "\n".join(lines)
