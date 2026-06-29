"""Stage 12 — Music Selection from local royalty-free library."""
from pathlib import Path

MUSIC_DIR = Path(__file__).parent.parent.parent / "data" / "music"

# Mood tag → filename mapping. Drop MP3s into data/music/ and register here.
MUSIC_LIBRARY: dict[str, list[str]] = {
    "epic":        ["epic_cinematic.mp3"],
    "mysterious":  ["mysterious_ambient.mp3"],
    "dramatic":    ["dramatic_orchestral.mp3"],
    "dark":        ["dark_tension.mp3"],
    "uplifting":   ["uplifting_adventure.mp3"],
    "neutral":     ["neutral_documentary.mp3"],
}

# Map narration_style → mood tag
STYLE_MOOD_MAP = {
    "documentary":   "neutral",
    "dramatic":      "dramatic",
    "conversational":"uplifting",
    "mysterious":    "mysterious",
    "comedic":       "uplifting",
}

# Map music_intensity → volume (0.0–1.0) relative to voiceover
INTENSITY_VOLUME = {
    "subtle":   0.10,
    "moderate": 0.18,
    "intense":  0.30,
}


def select_music(job: dict) -> dict:
    """
    Pick a track from the local library matching the job's narration style
    and music intensity.  If no matching file exists on disk, records the
    selection as pending so assembly can skip BGM gracefully.
    """
    config = job.get("config") or {}
    style = config.get("narration_style", "documentary")
    intensity = config.get("music_intensity", "moderate")

    mood = STYLE_MOOD_MAP.get(style, "neutral")
    candidates = MUSIC_LIBRARY.get(mood, MUSIC_LIBRARY["neutral"])
    volume = INTENSITY_VOLUME.get(intensity, 0.18)

    # Pick first candidate that exists on disk
    selected_path: str | None = None
    selected_name: str | None = None
    for fname in candidates:
        p = MUSIC_DIR / fname
        if p.exists():
            selected_path = str(p)
            selected_name = fname
            break

    job["music"] = {
        "track_path": selected_path,
        "track_name": selected_name,
        "mood": mood,
        "intensity": intensity,
        "volume": volume,
        "status": "ready" if selected_path else "missing",
        "missing_hint": (
            f"Place '{candidates[0]}' in pipeline/data/music/ to enable BGM."
            if not selected_path else None
        ),
    }
    return job
