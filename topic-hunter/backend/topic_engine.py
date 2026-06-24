import json
import os
from google import genai
from google.genai import types
from schemas import Topic, QualityScores
from storage import assign_topic_id

MODEL = "gemini-2.5-flash"

_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    return _client


def _generate(system: str, user: str, max_tokens: int = 2048) -> str:
    response = get_client().models.generate_content(
        model=MODEL,
        contents=user,
        config=types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            max_output_tokens=max_tokens,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    return response.text


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
) -> list[Topic]:
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
        "Return ONLY valid JSON matching this schema:\n"
        '{"topics": [{"title": string, "one_line_premise": string, '
        '"hook_angle": string, "era": string, "category": string}]}'
    )

    raw = _generate(system, "Generate the topics now.", max_tokens=2048)
    data = json.loads(raw)

    topics = []
    for item in data["topics"]:
        topics.append(
            Topic(
                topic_id=assign_topic_id(),
                title=item["title"],
                one_line_premise=item["one_line_premise"],
                category=item.get("category", category),
                era=item.get("era", historical_era),
                hook_angle=item["hook_angle"],
            )
        )
    return topics


def score_topic(topic: Topic) -> Topic:
    topic_json = json.dumps({
        "topic_id": topic.topic_id,
        "title": topic.title,
        "one_line_premise": topic.one_line_premise,
        "hook_angle": topic.hook_angle,
        "era": topic.era,
        "category": topic.category,
    })

    system = (
        "You are the Quality Scoring Engine. Score the following topic on six "
        "axes, each 0-100. Be strict — most topics should NOT score above 85 on any axis.\n\n"
        "Rubrics:\n"
        "- historical_accuracy: how verifiable/well-documented is this topic likely to be\n"
        "- visual_potential: how well this translates into striking AI-generated visuals\n"
        "- retention_potential: likelihood of holding a short-form viewer for the full duration\n"
        "- novelty: how unfamiliar this is to a general audience\n"
        "- emotional_impact: strength of emotional reaction (shock, awe, humor, horror)\n"
        "- shareability: likelihood of being shared/commented on\n\n"
        f"Topic: {topic_json}\n\n"
        "Return ONLY valid JSON:\n"
        '{"topic_id": string, "historical_accuracy": int, "visual_potential": int, '
        '"retention_potential": int, "novelty": int, "emotional_impact": int, '
        '"shareability": int, "rationale": string}'
    )

    raw = _generate(system, "Score this topic.", max_tokens=512)
    data = json.loads(raw)

    composite = sum(data[axis] * weight for axis, weight in SCORE_WEIGHTS.items())

    scores = QualityScores(
        historical_accuracy=data["historical_accuracy"],
        visual_potential=data["visual_potential"],
        retention_potential=data["retention_potential"],
        novelty=data["novelty"],
        emotional_impact=data["emotional_impact"],
        shareability=data["shareability"],
        composite=round(composite, 1),
        rationale=data.get("rationale"),
    )

    return topic.model_copy(update={"scores": scores})


def generate_and_score_topics(
    category: str,
    historical_era: str,
    batch_size: int = 5,
    video_length_sec: int = 60,
    previously_used_titles: list[str] = [],
) -> list[Topic]:
    topics = generate_topics(category, historical_era, batch_size, video_length_sec, previously_used_titles)
    scored = [score_topic(t) for t in topics]
    scored.sort(key=lambda t: t.scores.composite if t.scores else 0, reverse=True)
    return scored
