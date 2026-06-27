import os
from google import genai
from google.genai import types

MODEL = "gemini-2.5-flash"

# Gemini 2.5 Flash non-thinking pricing (thinking_budget=0)
_INPUT_COST_PER_M = 0.075   # USD per million input tokens
_OUTPUT_COST_PER_M = 0.30   # USD per million output tokens

_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    return _client


def _extract_usage(response) -> dict:
    meta = getattr(response, "usage_metadata", None)
    inp = int(getattr(meta, "prompt_token_count", 0) or 0)
    out = int(getattr(meta, "candidates_token_count", 0) or 0)
    cost = (inp * _INPUT_COST_PER_M + out * _OUTPUT_COST_PER_M) / 1_000_000
    return {"input_tokens": inp, "output_tokens": out, "cost_usd": round(cost, 6)}


def generate(system: str, user: str, max_tokens: int = 2048) -> tuple[str, dict]:
    """Single-turn JSON generation. Returns (text, usage)."""
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
    return response.text, _extract_usage(response)


def chat(system: str, history: list[dict], message: str, max_tokens: int = 1024) -> tuple[str, dict]:
    """Multi-turn conversational chat. Returns (text, usage)."""
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
    return response.text, _extract_usage(response)
