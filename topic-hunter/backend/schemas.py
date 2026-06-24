from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel

TopicCategory = Literal[
    "weird_history", "ancient_rome", "ancient_egypt", "medieval_europe",
    "vikings", "pirates", "historical_disasters", "forgotten_leaders",
    "strange_laws", "military_history", "historical_mysteries"
]


class QualityScores(BaseModel):
    historical_accuracy: int
    visual_potential: int
    retention_potential: int
    novelty: int
    emotional_impact: int
    shareability: int
    composite: float
    rationale: Optional[str] = None


class Topic(BaseModel):
    topic_id: str
    title: str
    one_line_premise: str
    category: str
    era: str
    hook_angle: str
    scores: Optional[QualityScores] = None


class GenerateTopicsRequest(BaseModel):
    category: str = "weird_history"
    historical_era: str = "Ancient Rome"
    batch_size: int = 5
    video_length_sec: int = 60
    previously_used_titles: list[str] = []


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


class ChatResponse(BaseModel):
    reply: str
    topics: list[Topic] = []
    action: Optional[str] = None
