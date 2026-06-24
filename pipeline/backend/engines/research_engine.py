"""Stage 3 — Fact Research & Stage 4 — Fact Validation."""
import json
from engines.claude_client import generate
from job_store import compute_status


def research_topic(job: dict) -> dict:
    topic = job["topic"]
    video_length_sec = job["config"].get("video_length_sec", 60)

    system = (
        "You are the Research Engine for a history-shorts pipeline.\n"
        f'Gather verifiable facts about: "{topic["title"]}" ({topic["era"]}).\n\n'
        "For each discrete fact note:\n"
        "- the claim statement\n"
        "- which sources support it (cite real academic/encyclopedic sources by name)\n"
        "- a certainty label: established | debated | disputed | legendary\n\n"
        "Prefer academic/encyclopedic sources over popular/blog sources.\n"
        f"Gather 6-12 facts sufficient to write a {video_length_sec}s script.\n\n"
        "Return ONLY valid JSON (no preamble, no markdown):\n"
        '{"topic_id": string, "facts": [{"claim_id": string, "statement": string, '
        '"source_ids": [string], "certainty": string}], '
        '"sources": [{"source_id": string, "title": string, "url": string, "type": string}], '
        '"research_confidence": int}'
    )

    raw = generate(system, f'Research: {topic["title"]}', max_tokens=3000)
    data = json.loads(raw)
    data["topic_id"] = topic["topic_id"]
    for i, fact in enumerate(data.get("facts", [])):
        if not fact.get("claim_id"):
            fact["claim_id"] = f"c{i+1:03d}"

    job["research"] = data
    return job


def validate_research(job: dict) -> dict:
    research = job["research"]
    research_json = json.dumps(research)

    system = (
        "You are the Fact Validation Engine — an adversarial checker.\n"
        "Re-examine each claim in the research bundle below. Flag any claim that:\n"
        "- is sourced only from a single low-quality source\n"
        "- is commonly cited as myth/legend by historians\n"
        "- cannot be corroborated\n\n"
        "Assign overall_accuracy_score (0-100).\n"
        "Set publishable=false if >30% of claims are flagged, or if any "
        "'disputed'/'legendary' claim is load-bearing without a disclaimer.\n\n"
        f"Research bundle: {research_json}\n\n"
        "Return ONLY valid JSON (no preamble, no markdown):\n"
        '{"topic_id": string, "verified_claims": [string], '
        '"flagged_claims": [{"claim_id": string, "reason": string}], '
        '"overall_accuracy_score": int, "publishable": boolean, '
        '"required_disclaimers": [string]}'
    )

    raw = generate(system, "Validate the research now.", max_tokens=1500)
    data = json.loads(raw)
    data["topic_id"] = job["topic"]["topic_id"]

    job["validation"] = data
    if data.get("publishable", True):
        job["status"] = compute_status(job.get("stage_completed", []))
    else:
        job["status"] = "failed"
        job["errors"].append({
            "stage": "validation",
            "error": f"publishable=false — accuracy score {data.get('overall_accuracy_score')}",
            "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
            "retry_count": 0,
        })
    return job
