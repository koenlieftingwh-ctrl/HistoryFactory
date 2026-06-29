"""Stage 1 — Topic Generation & Stage 2 — Topic Scoring."""
import json
import uuid
from engines.claude_client import generate

SCORE_WEIGHTS = {
    "historical_accuracy": 0.20,
    "visual_potential": 0.20,
    "retention_potential": 0.20,
    "novelty": 0.15,
    "emotional_impact": 0.15,
    "shareability": 0.10,
}


def generate_topics(
    category: str,
    historical_era: str,
    batch_size: int = 5,
    video_length_sec: int = 60,
    previously_used_titles: list[str] = [],
) -> list[dict]:
    exclusion = ", ".join(previously_used_titles) if previously_used_titles else "none"
    system = (
        "You are the Topic Engine for an automated history-shorts pipeline.\n"
        f"Generate {batch_size} distinct historical story topics for:\n"
        f"  category: {category}\n"
        f"  era: {historical_era}\n"
        f"Each topic must be a genuinely surprising, little-known, or bizarre "
        f"historical event or figure suitable for a {video_length_sec}-second "
        "short-form video. Avoid topics already in this exclusion list:\n"
        f"{exclusion}\n\n"
        "Prioritize: surprising facts, bizarre events, unknown stories, strong "
        "visual potential, short-form retention.\n\n"
        "Return ONLY valid JSON, no preamble, no markdown:\n"
        '{"topics": [{"title": string, "one_line_premise": string, '
        '"hook_angle": string, "era": string, "category": string}]}'
    )
    raw, _ = generate(system, "Generate the topics now.", max_tokens=2048)
    data = json.loads(raw)
    topics = []
    for item in data["topics"]:
        topics.append({
            "topic_id": str(uuid.uuid4())[:8],
            "title": item["title"],
            "one_line_premise": item["one_line_premise"],
            "category": item.get("category", category),
            "era": item.get("era", historical_era),
            "hook_angle": item["hook_angle"],
            "scores": None,
        })
    return topics


def score_topic(topic: dict) -> dict:
    topic_json = json.dumps({k: topic[k] for k in ("topic_id", "title", "one_line_premise", "hook_angle", "era", "category")})
    system = (
        "You are the Quality Scoring Engine. Score the following topic on six "
        "axes, each 0-100. Be strict — most topics should NOT score above 85 on any axis.\n\n"
        "Rubrics:\n"
        "- historical_accuracy: verifiability/documentation plausibility\n"
        "- visual_potential: translation into striking AI visuals\n"
        "- retention_potential: likelihood of holding short-form viewers\n"
        "- novelty: how unfamiliar to a general audience\n"
        "- emotional_impact: shock, awe, humor, horror strength\n"
        "- shareability: likelihood of being shared/commented on\n\n"
        f"Topic: {topic_json}\n\n"
        "Return ONLY valid JSON (no preamble, no markdown):\n"
        '{"topic_id": string, "historical_accuracy": int, "visual_potential": int, '
        '"retention_potential": int, "novelty": int, "emotional_impact": int, '
        '"shareability": int, "rationale": string}'
    )
    raw, _ = generate(system, "Score this topic.", max_tokens=512)
    data = json.loads(raw)
    composite = round(sum(data[a] * w for a, w in SCORE_WEIGHTS.items()), 1)
    topic["scores"] = {
        "historical_accuracy": data["historical_accuracy"],
        "visual_potential": data["visual_potential"],
        "retention_potential": data["retention_potential"],
        "novelty": data["novelty"],
        "emotional_impact": data["emotional_impact"],
        "shareability": data["shareability"],
        "composite": composite,
        "rationale": data.get("rationale", ""),
    }
    return topic


def generate_and_score(
    category: str,
    historical_era: str,
    batch_size: int = 5,
    video_length_sec: int = 60,
    previously_used_titles: list[str] = [],
) -> list[dict]:
    topics = generate_topics(category, historical_era, batch_size, video_length_sec, previously_used_titles)
    scored = [score_topic(t) for t in topics]
    scored.sort(key=lambda t: (t["scores"] or {}).get("composite", 0), reverse=True)
    return scored
