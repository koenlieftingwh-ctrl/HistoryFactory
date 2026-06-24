"""Director agent — Stages 5 & 6: Script + Storyboard."""
import json

SYSTEM = """You are the Director — the third agent in the History Shorts Generator pipeline.
Your job: turn validated research into a tight script and a visual storyboard.

You run two stages:
1. SCRIPT (Stage 5): Five-act narration script using ONLY verified facts.
   Structure: Hook (0-5%) → Setup (5-25%) → Escalation (25-67%) → Twist (67-92%) → Payoff (92-100%)
2. STORYBOARD (Stage 6): Break the script into scenes (one scene per 2.5-4 seconds).
   Each scene gets: shot description, camera movement, characters, setting, mood, on-screen text.

You can discuss the creative direction before running, e.g. help the user choose narration style, suggest the best hook angle, or brainstorm visual ideas.

TO WRITE THE SCRIPT, output:
<action>{"type":"script"}</action>

TO GENERATE THE STORYBOARD (after script is complete), output:
<action>{"type":"storyboard"}</action>

After each stage, give the user a brief creative summary:
- Script: read the hook line aloud, note the word count and estimated duration, flag any pacing concerns.
- Storyboard: note the total scene count, call out the most visually striking scene, flag any abstract/hard-to-visualise shots."""


def build_system(job: dict | None) -> str:
    lines = [SYSTEM]
    if not job:
        lines.append("\nNO ACTIVE JOB: Ask the user to start a job in the Topic Hunter.")
        return "\n".join(lines)

    topic = job.get("topic", {})
    config = job.get("config", {})
    validation = job.get("validation", {})
    stage_done = job.get("stage_completed", [])

    lines.append(f"\nACTIVE JOB: {job['job_id']}")
    lines.append(f"Topic: {topic.get('title')} — {topic.get('one_line_premise')}")
    lines.append(f"Config: {config.get('video_length_sec')}s, {config.get('narration_style')}, {config.get('narration_speed')} speed")

    if "historian" not in stage_done:
        lines.append("\nWARNING: Historian stage not complete. Research and validation must finish first.")
    else:
        lines.append(f"Validation: {len(validation.get('verified_claims', []))} verified facts, "
                     f"accuracy={validation.get('overall_accuracy_score')}, "
                     f"publishable={validation.get('publishable')}")
        disclaimers = validation.get("required_disclaimers", [])
        if disclaimers:
            lines.append(f"Required disclaimers: {'; '.join(disclaimers)}")

    if job.get("script"):
        s = job["script"]
        segs = s.get("segments", [])
        hook = next((seg["text"][:100] for seg in segs if seg["segment_type"] == "hook"), "")
        lines.append(f"\nSCRIPT COMPLETE: {s.get('total_word_count')} words, "
                     f"~{s.get('estimated_duration_sec')}s. Hook: \"{hook}...\"")

    if job.get("storyboard"):
        sb = job["storyboard"]
        lines.append(f"STORYBOARD COMPLETE: {len(sb.get('scenes', []))} scenes.")
        if "director" in stage_done:
            lines.append("Director stage is COMPLETE. Direct the user to the Editor.")

    return "\n".join(lines)
