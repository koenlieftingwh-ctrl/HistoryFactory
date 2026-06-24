import os
import anthropic

_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


# Per spec §11: Haiku for high-volume/low-stakes, Haiku for everything in dev.
# Upgrade SCRIPT_MODEL / RESEARCH_MODEL to claude-haiku-4-5 in production.
HAIKU = "claude-haiku-4-5"
