"""Stage 5 — Script Generation & Stage 6 — Storyboard Generation."""
import json
import uuid
from engines.claude_client import generate
from job_store import compute_status, add_llm_cost

WORDS_PER_SEC = {"slow": 2.2, "normal": 2.6, "fast": 3.0}


def generate_script(job: dict) -> dict:
    topic = job["topic"]
    config = job["config"]
    validation = job["validation"]
    research = job["research"]

    video_length_sec = config.get("video_length_sec", 60)
    narration_speed = config.get("narration_speed", "normal")
    narration_style = config.get("narration_style", "documentary")
    language = config.get("language", "en")

    words_per_sec = WORDS_PER_SEC.get(narration_speed, 2.6)
    target_words = int(video_length_sec * words_per_sec)

    verified_ids = set(validation.get("verified_claims", []))
    verified_facts = [f for f in research.get("facts", []) if f["claim_id"] in verified_ids]
    disclaimers = validation.get("required_disclaimers", [])
    disclaimers_str = "; ".join(disclaimers) if disclaimers else "none"
    facts_json = json.dumps(verified_facts)

    system = (
        "You are the Script Engine for a history-shorts pipeline.\n"
        "Write a narration script using ONLY the verified facts provided.\n\n"
        "Five-act structure (scale percentages to video length):\n"
        "- Hook       0-5%:   shocking question or statement, ≤2 sentences\n"
        "- Setup      5-25%:  establish time/place/who, plain and vivid\n"
        "- Escalation 25-67%: build tension, stack surprising details\n"
        "- Twist      67-92%: the unexpected turn / payoff fact\n"
        "- Payoff     92-100%: final punch line + soft CTA (follow for more)\n\n"
        f"Style: {narration_style}. Speed: {narration_speed}. Language: {language}.\n"
        f"Target word count: ~{target_words} words.\n"
        f"Required disclaimers to weave in naturally: {disclaimers_str}.\n\n"
        f"Topic: {topic['title']} — {topic['one_line_premise']}\n"
        f"Verified facts: {facts_json}\n\n"
        "Return ONLY valid JSON (no preamble, no markdown):\n"
        '{"script_id": string, "language": string, "segments": ['
        '{"segment_type": string, "start_pct": number, "end_pct": number, '
        '"text": string, "emotional_tone": string, "claim_ids": [string]}], '
        '"total_word_count": int, "estimated_duration_sec": number}'
    )

    raw, usage = generate(system, "Write the script now.", max_tokens=3000)
    add_llm_cost(job, usage)
    data = json.loads(raw)
    if not data.get("script_id"):
        data["script_id"] = str(uuid.uuid4())[:8]

    job["script"] = data
    job["status"] = compute_status(job.get("stage_completed", []))
    return job


def generate_storyboard(job: dict) -> dict:
    script = job["script"]
    config = job["config"]
    video_length_sec = config.get("video_length_sec", 60)
    # Target 5-7 scenes: each covers ~10-15s so roughly 1 scene per act + 1-2 for the hook
    scene_count = 6 if video_length_sec <= 60 else 7
    script_json = json.dumps(script)

    system = (
        "You are the Storyboard Engine for a history-shorts pipeline.\n"
        "Convert the script into a compact shot list for cost-efficient AI rendering.\n\n"
        f"TARGET: exactly {scene_count} scenes for a {video_length_sec}s video.\n"
        "Each scene covers 10-15 seconds of narration — do NOT split into more scenes than this.\n"
        "One scene per narrative beat (Hook, Setup, Escalation, Twist, Payoff + 1 closing).\n\n"
        "For each scene specify: duration_sec (10-15), shot_description (concrete visual, not abstract), "
        "camera movement, characters present, setting, mood, and optional on-screen text.\n\n"
        f"Script: {script_json}\n\n"
        "Return ONLY valid JSON (no preamble, no markdown):\n"
        '{"storyboard_id": string, "scenes": [{"scene_id": string, "segment_type": string, '
        '"duration_sec": number, "shot_description": string, "camera": string, '
        '"characters": [string], "setting": string, "mood": string, "on_screen_text": string|null}]}'
    )

    raw, usage = generate(system, "Generate the storyboard now.", max_tokens=4000)
    add_llm_cost(job, usage)
    data = json.loads(raw)
    if not data.get("storyboard_id"):
        data["storyboard_id"] = str(uuid.uuid4())[:8]

    job["storyboard"] = data
    job["status"] = compute_status(job.get("stage_completed", []))
    return job
