import os
import google.generativeai as genai

_configured = False


def ensure_configured():
    global _configured
    if not _configured:
        genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
        _configured = True


def generate(system: str, user: str, max_tokens: int = 2048, json_mode: bool = True) -> str:
    ensure_configured()
    config = genai.GenerationConfig(max_output_tokens=max_tokens)
    if json_mode:
        config = genai.GenerationConfig(
            max_output_tokens=max_tokens,
            response_mime_type="application/json",
        )
    model = genai.GenerativeModel(
        model_name=FLASH,
        system_instruction=system,
        generation_config=config,
    )
    response = model.generate_content(user)
    return response.text


def chat(system: str, history: list[dict], message: str, max_tokens: int = 1024) -> str:
    """Multi-turn chat without JSON mode (for conversational agent replies)."""
    ensure_configured()
    model = genai.GenerativeModel(
        model_name=FLASH,
        system_instruction=system,
        generation_config=genai.GenerationConfig(max_output_tokens=max_tokens),
    )
    gemini_history = []
    for m in history:
        role = "model" if m["role"] == "assistant" else "user"
        gemini_history.append({"role": role, "parts": [m["content"]]})

    session = model.start_chat(history=gemini_history)
    response = session.send_message(message)
    return response.text


# gemini-1.5-flash: fast, cheap — equivalent to Haiku tier
# gemini-1.5-pro:   stronger reasoning — use for script/validation in production
FLASH = "gemini-1.5-flash"
PRO = "gemini-1.5-pro"
