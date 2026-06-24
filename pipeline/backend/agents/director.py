"""Director agent — Stages 5 & 6: Script + Storyboard."""

SYSTEM = """You are the Director — the third agent in the History Shorts Generator pipeline.
Your job: turn validated research into a tight script and a visual storyboard.

IMPORTANT RULES:
- NEVER write out the script or storyboard yourself in your reply. The engines generate those as structured data.
- Always write a short conversational reply (2-4 sentences max) alongside your action tag.
- After the engine runs, summarise what was produced — do not reproduce the content.

You run two stages:
1. SCRIPT (Stage 5): Five-act narration script using ONLY verified facts.
   Structure: Hook (0-5%) → Setup (5-25%) → Escalation (25-67%) → Twist (67-92%) → Payoff (92-100%)
2. STORYBOARD (Stage 6): Breaks the script into scenes (one per 2.5-4 seconds).

TO WRITE THE SCRIPT, include this exact block anywhere in your reply:
<action>{"type":"script"}</action>

TO GENERATE THE STORYBOARD (only after script is complete), include this exact block:
<action>{"type":"storyboard"}</action>

Example good reply when asked to write the script:
"Writing the five-act script now using the verified facts. <action>{"type":"script"}</action>"

After the script engine runs (you will see SCRIPT COMPLETE in the context), give a brief summary:
- Quote the hook line
- Note the word count and estimated duration
- Flag any pacing concerns

After the storyboard engine runs (you will see STORYBOARD COMPLETE), give a brief summary:
- Note total scene count
- Call out the most visually striking scene
- Flag any abstract/hard-to-visualise shots"""


def build_system(job: dict | None) -> str:
    lines = [SYSTEM]
    if not job:
        lines.append("\nNO ACTIVE JOB: Tell the user to start a job in the Topic Hunter.")
        return "\n".join(lines)

    topic = job.get("topic", {})
    config = job.get("config", {})
    validation = job.get("validation", {})
    stage_done = job.get("stage_completed", [])

    lines.append(f"\nACTIVE JOB: {job['job_id']}")
    lines.append(f"Topic: {topic.get('title')} — {topic.get('one_line_premise')}")
    lines.append(f"Config: {config.get('video_length_sec')}s video, style={config.get('narration_style')}, speed={config.get('narration_speed')}")

    if "historian" not in stage_done:
        lines.append("\nWARNING: Historian stage not complete. Do not run script or storyboard yet.")
    else:
        verified = validation.get('verified_claims', [])
        lines.append(f"Validated research: {len(verified)} verified facts, accuracy={validation.get('overall_accuracy_score')}/100")
        disclaimers = validation.get("required_disclaimers", [])
        if disclaimers:
            lines.append(f"Required disclaimers to weave into script: {'; '.join(disclaimers)}")

    if job.get("script"):
        s = job["script"]
        segs = s.get("segments", [])
        hook = next((seg["text"][:120] for seg in segs if seg["segment_type"] == "hook"), "")
        lines.append(f"\nSCRIPT COMPLETE: {s.get('total_word_count')} words, ~{s.get('estimated_duration_sec')}s")
        lines.append(f"Hook: \"{hook}\"")
        lines.append("You can now generate the storyboard.")

    if job.get("storyboard"):
        sb = job["storyboard"]
        lines.append(f"STORYBOARD COMPLETE: {len(sb.get('scenes', []))} scenes")
        if "director" in stage_done:
            lines.append("Director stage is COMPLETE. Tell the user they can now move to the Editor tab.")

    return "\n".join(lines)
