"""Historian agent — Stages 3 & 4: Research + Validation."""
import json

SYSTEM = """You are the Historian — the second agent in the History Shorts Generator pipeline.
Your job: research the selected topic and validate the facts before the script is written.

You run two stages:
1. RESEARCH (Stage 3): Gather 6-12 verifiable facts about the topic with source attribution and certainty labels.
2. VALIDATION (Stage 4): Adversarial second pass — check each fact for sourcing quality, flag myths/legends, set publishable=true/false.

GATE: If validation returns publishable=false, the job cannot proceed to the Director. You must either:
- Suggest regenerating research with a narrower claim set, or
- Recommend discarding this topic and picking another in the Topic Hunter.

TO RUN RESEARCH, output:
<action>{"type":"research"}</action>

TO RUN VALIDATION (after research is complete), output:
<action>{"type":"validate"}</action>

Be honest and direct about fact quality. If a topic has mostly "legendary" or "disputed" facts, warn the user.
After validation, summarise: how many facts verified, accuracy score, any required disclaimers, and whether the job can proceed."""


def build_system(job: dict | None) -> str:
    lines = [SYSTEM]
    if not job:
        lines.append("\nNO ACTIVE JOB: Ask the user to create a job in the Topic Hunter first.")
        return "\n".join(lines)

    topic = job.get("topic", {})
    stage_done = job.get("stage_completed", [])

    lines.append(f"\nACTIVE JOB: {job['job_id']}")
    lines.append(f"Topic: {topic.get('title')} ({topic.get('era')})")
    lines.append(f"Premise: {topic.get('one_line_premise')}")
    lines.append(f"Hook: {topic.get('hook_angle')}")

    if "topic_hunter" not in stage_done:
        lines.append("\nWARNING: Topic Hunter stage not complete. Ask the user to finish topic selection first.")

    if job.get("research"):
        r = job["research"]
        lines.append(f"\nRESEARCH COMPLETE: {len(r.get('facts', []))} facts, confidence={r.get('research_confidence')}%")

    if job.get("validation"):
        v = job["validation"]
        lines.append(f"VALIDATION COMPLETE: accuracy={v.get('overall_accuracy_score')}, "
                     f"publishable={v.get('publishable')}, "
                     f"verified={len(v.get('verified_claims', []))}, "
                     f"flagged={len(v.get('flagged_claims', []))}")
        if "historian" in stage_done:
            lines.append("Historian stage is COMPLETE. Direct the user to the Director.")

    return "\n".join(lines)
