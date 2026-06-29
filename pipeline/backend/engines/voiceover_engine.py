"""Stage 10 — Voiceover Generation via Google Cloud TTS REST API."""
import base64
import os
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

TTS_ENDPOINT = "https://texttospeech.googleapis.com/v1/text:synthesize"

# Narration style → voice name mapping (Neural2 voices)
STYLE_VOICE_MAP = {
    "documentary": "en-US-Neural2-D",    # male, authoritative
    "dramatic":    "en-US-Neural2-J",    # male, expressive
    "conversational": "en-US-Neural2-F", # female, warm
    "mysterious":  "en-US-Neural2-D",
    "comedic":     "en-US-Neural2-F",
}

SPEED_MAP = {"slow": 0.85, "normal": 1.0, "fast": 1.15}

ASSETS_DIR = Path(__file__).parent.parent.parent / "data" / "assets"


def _api_key() -> str:
    key = os.environ.get("GOOGLE_TTS_KEY", "")
    if not key:
        raise RuntimeError("GOOGLE_TTS_KEY not set — add it to pipeline/.env")
    return key


def _full_script_text(job: dict) -> str:
    segments = (job.get("script") or {}).get("segments") or []
    return " ".join(s["text"] for s in segments)


def generate_voiceover(job: dict) -> dict:
    """
    Call Google Cloud TTS, save MP3 to data/assets/<job_id>_voiceover.mp3,
    and write voiceover metadata to job["voiceover"].
    """
    config = job.get("config") or {}
    style = config.get("narration_style", "documentary")
    speed = config.get("narration_speed", "normal")
    language = config.get("language", "en")

    voice_name = STYLE_VOICE_MAP.get(style, "en-US-Neural2-D")
    language_code = f"{language}-US" if language == "en" else language
    speaking_rate = SPEED_MAP.get(speed, 1.0)

    text = _full_script_text(job)
    if not text:
        raise ValueError("No script text found — run the Director stage first.")

    payload = {
        "input": {"text": text},
        "voice": {"languageCode": language_code, "name": voice_name},
        "audioConfig": {
            "audioEncoding": "MP3",
            "speakingRate": speaking_rate,
            "pitch": 0.0,
        },
    }

    r = requests.post(
        f"{TTS_ENDPOINT}?key={_api_key()}",
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    audio_b64 = r.json()["audioContent"]
    audio_bytes = base64.b64decode(audio_b64)

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ASSETS_DIR / f"{job['job_id']}_voiceover.mp3"
    out_path.write_bytes(audio_bytes)

    # Estimate duration from word count + speaking rate
    word_count = len(text.split())
    words_per_sec = 2.6 * speaking_rate
    estimated_duration = round(word_count / words_per_sec, 1)

    job["voiceover"] = {
        "audio_path": str(out_path),
        "audio_url": None,           # local file; no CDN upload yet
        "duration_sec": estimated_duration,
        "voice_id": voice_name,
        "language": language_code,
        "word_timestamps": [],       # populated by subtitle_engine after Whisper
    }
    return job
