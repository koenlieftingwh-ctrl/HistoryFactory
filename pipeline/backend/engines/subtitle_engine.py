"""Stage 11 — Subtitle Generation via Whisper forced alignment."""
import json
import os
from pathlib import Path

ASSETS_DIR = Path(__file__).parent.parent.parent / "data" / "assets"


def _format_timestamp(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _words_to_srt(words: list[dict]) -> str:
    """Group word-level timestamps into ~5-word subtitle chunks → SRT."""
    if not words:
        return ""
    lines = []
    chunk_size = 5
    idx = 1
    for i in range(0, len(words), chunk_size):
        chunk = words[i : i + chunk_size]
        start = chunk[0]["start"]
        end = chunk[-1]["end"]
        text = " ".join(w["word"].strip() for w in chunk)
        lines.append(f"{idx}\n{_format_timestamp(start)} --> {_format_timestamp(end)}\n{text}\n")
        idx += 1
    return "\n".join(lines)


def _words_to_vtt(words: list[dict]) -> str:
    srt = _words_to_srt(words)
    # VTT uses . instead of , for milliseconds
    vtt = srt.replace(",", ".")
    # Strip numeric indices (VTT doesn't require them but they're harmless)
    return "WEBVTT\n\n" + vtt


def _estimate_word_timestamps(job: dict, duration_sec: float) -> list[dict]:
    """
    Fallback: distribute words evenly across the voiceover duration.
    Whisper alignment replaces this when the audio file is available.
    """
    segments = (job.get("script") or {}).get("segments") or []
    words = []
    for seg in segments:
        for w in seg["text"].split():
            words.append(w)

    if not words:
        return []

    step = duration_sec / len(words)
    result = []
    for i, w in enumerate(words):
        result.append({"word": w, "start": round(i * step, 3), "end": round((i + 1) * step, 3)})
    return result


def generate_subtitles(job: dict) -> dict:
    """
    Run Whisper on the voiceover MP3 to get word-level timestamps,
    then write SRT and VTT files.  Falls back to evenly-distributed
    timestamps if the audio file isn't found.
    """
    voiceover = job.get("voiceover") or {}
    audio_path = voiceover.get("audio_path")
    duration_sec = voiceover.get("duration_sec", 60)

    words: list[dict] = []

    if audio_path and Path(audio_path).exists():
        try:
            import whisper
            model = whisper.load_model("base")
            result = model.transcribe(audio_path, word_timestamps=True)
            for seg in result.get("segments") or []:
                for w in seg.get("words") or []:
                    words.append({
                        "word": w["word"],
                        "start": round(w["start"], 3),
                        "end": round(w["end"], 3),
                    })
        except Exception:
            words = _estimate_word_timestamps(job, duration_sec)
    else:
        words = _estimate_word_timestamps(job, duration_sec)

    # Persist timestamps back onto the voiceover asset
    if job.get("voiceover"):
        job["voiceover"]["word_timestamps"] = words

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    srt_path = ASSETS_DIR / f"{job['job_id']}_subtitles.srt"
    vtt_path = ASSETS_DIR / f"{job['job_id']}_subtitles.vtt"

    srt_path.write_text(_words_to_srt(words), encoding="utf-8")
    vtt_path.write_text(_words_to_vtt(words), encoding="utf-8")

    job["subtitles"] = {
        "srt_path": str(srt_path),
        "vtt_path": str(vtt_path),
        "style": {
            "font": "Arial",
            "size": 52,
            "color": "#FFFFFF",
            "highlight_color": "#FFDD00",
            "position": "bottom",
            "animation": "fade",
        },
    }
    return job
