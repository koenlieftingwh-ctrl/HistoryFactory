import os
from google import genai
from google.genai import types

MODEL = "gemini-2.5-flash"

_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    return _client


def _base_config(max_tokens: int, json_mode: bool) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        max_output_tokens=max_tokens,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
        **({"response_mime_type": "application/json"} if json_mode else {}),
    )


def generate(system: str, user: str, max_tokens: int = 2048) -> str:
    """Single-turn JSON generation."""
    response = get_client().models.generate_content(
        model=MODEL,
        contents=user,
        config=types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            response_mime_type="application/json",
        ),
    )
    return response.text


def chat(system: str, history: list[dict], message: str, max_tokens: int = 1024) -> str:
    """Multi-turn conversational chat."""
    gemini_history = []
    for m in history:
        role = "model" if m["role"] == "assistant" else "user"
        gemini_history.append(types.Content(role=role, parts=[types.Part(text=m["content"])]))

    session = get_client().chats.create(
        model=MODEL,
        config=types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
        history=gemini_history,
    )
    response = session.send_message(message)
    return response.text
