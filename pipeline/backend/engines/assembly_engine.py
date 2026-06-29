"""Stage 13 — Video Assembly via ffmpeg.

Downloads scene assets (images/videos) from their result_url or local path,
then assembles them per the EDL with voiceover, subtitles, and optional BGM.

Output: data/assets/<job_id>_final.mp4
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path

import requests

ASSETS_DIR = Path(__file__).parent.parent.parent / "data" / "assets"
FFMPEG = "ffmpeg"

# Target output spec for YouTube Shorts / TikTok / Reels
OUTPUT_WIDTH = 720
OUTPUT_HEIGHT = 1280
OUTPUT_FPS = 30
OUTPUT_BITRATE = "4M"


def _download(url: str, dest: Path) -> Path:
    """Download a URL to dest. Returns dest."""
    r = requests.get(url, timeout=60, stream=True)
    r.raise_for_status()
    dest.write_bytes(r.content)
    return dest


def _get_scene_asset(render_job: dict, tmp_dir: Path) -> Path | None:
    """Return a local path for a render job's asset, downloading if needed."""
    result_url = render_job.get("result_url")
    if not result_url:
        return None
    scene_id = render_job["scene_id"]
    ext = ".mp4" if render_job.get("render_type") == "video_clip" else ".png"
    dest = tmp_dir / f"{scene_id}{ext}"
    if dest.exists():
        return dest
    try:
        return _download(result_url, dest)
    except Exception:
        return None


def _image_to_clip(img_path: Path, duration: float, out_path: Path) -> bool:
    """Convert a static image to a video clip of given duration."""
    cmd = [
        FFMPEG, "-y",
        "-loop", "1", "-i", str(img_path),
        "-t", str(duration),
        "-vf", f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=decrease,"
               f"pad={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1",
        "-r", str(OUTPUT_FPS),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0


def _normalize_video(src: Path, duration: float, out_path: Path) -> bool:
    """Re-encode a video clip to consistent size/fps/codec."""
    cmd = [
        FFMPEG, "-y", "-i", str(src),
        "-t", str(duration),
        "-vf", f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=decrease,"
               f"pad={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1",
        "-r", str(OUTPUT_FPS),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0


def assemble_video(job: dict) -> dict:
    """
    Assemble the final video from rendered scenes, voiceover, subtitles,
    and optional BGM track.  Writes output to data/assets/<job_id>_final.mp4.
    """
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    render_jobs = job.get("render_jobs") or []
    edl = job.get("edl") or []
    voiceover = job.get("voiceover") or {}
    subtitles = job.get("subtitles") or {}
    music = job.get("music") or {}

    if not render_jobs:
        raise ValueError("No render jobs found — scenes must be rendered first.")
    if not edl:
        raise ValueError("No EDL found — run the Editor stage first.")

    # Build scene lookup by scene_id
    render_by_scene = {r["scene_id"]: r for r in render_jobs}

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)

        # 1. Download / locate each scene asset and convert to normalised clip
        clip_paths: list[Path] = []
        for entry in edl:
            scene_id = entry["scene_id"]
            rj = render_by_scene.get(scene_id)
            if not rj or rj.get("status") != "done":
                # Insert a black placeholder for missing scenes
                placeholder = tmp / f"{scene_id}_placeholder.mp4"
                duration = entry["end"] - entry["start"]
                cmd = [
                    FFMPEG, "-y",
                    "-f", "lavfi", "-i", f"color=black:s={OUTPUT_WIDTH}x{OUTPUT_HEIGHT}:r={OUTPUT_FPS}",
                    "-t", str(duration), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    str(placeholder),
                ]
                subprocess.run(cmd, capture_output=True)
                clip_paths.append(placeholder)
                continue

            asset = _get_scene_asset(rj, tmp)
            duration = entry["end"] - entry["start"]
            clip_out = tmp / f"{scene_id}_clip.mp4"

            if asset and asset.suffix == ".png":
                ok = _image_to_clip(asset, duration, clip_out)
            elif asset and asset.suffix == ".mp4":
                ok = _normalize_video(asset, duration, clip_out)
            else:
                ok = False

            if ok:
                clip_paths.append(clip_out)
            else:
                # Black placeholder
                placeholder = tmp / f"{scene_id}_placeholder.mp4"
                subprocess.run([
                    FFMPEG, "-y",
                    "-f", "lavfi", "-i", f"color=black:s={OUTPUT_WIDTH}x{OUTPUT_HEIGHT}:r={OUTPUT_FPS}",
                    "-t", str(duration), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    str(placeholder),
                ], capture_output=True)
                clip_paths.append(placeholder)

        # 2. Concatenate clips
        concat_list = tmp / "concat.txt"
        concat_list.write_text(
            "\n".join(f"file '{p}'" for p in clip_paths), encoding="utf-8"
        )
        silent_video = tmp / "silent.mp4"
        subprocess.run([
            FFMPEG, "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(silent_video),
        ], capture_output=True, check=True)

        # 3. Merge voiceover
        vo_path = voiceover.get("audio_path")
        with_voice = tmp / "with_voice.mp4"
        if vo_path and Path(vo_path).exists():
            subprocess.run([
                FFMPEG, "-y",
                "-i", str(silent_video), "-i", vo_path,
                "-c:v", "copy", "-c:a", "aac", "-shortest",
                str(with_voice),
            ], capture_output=True, check=True)
        else:
            with_voice = silent_video

        # 4. Mix in BGM (if available)
        music_path = music.get("track_path")
        music_volume = music.get("volume", 0.18)
        with_music = tmp / "with_music.mp4"
        if music_path and Path(music_path).exists():
            subprocess.run([
                FFMPEG, "-y",
                "-i", str(with_voice), "-i", music_path,
                "-filter_complex",
                f"[1:a]volume={music_volume},aloop=loop=-1:size=2e+09[bg];"
                "[0:a][bg]amix=inputs=2:duration=first[aout]",
                "-map", "0:v", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac",
                str(with_music),
            ], capture_output=True, check=True)
        else:
            with_music = with_voice

        # 5. Burn subtitles
        srt_path = subtitles.get("srt_path")
        final_path = ASSETS_DIR / f"{job['job_id']}_final.mp4"
        if srt_path and Path(srt_path).exists():
            # ffmpeg needs forward slashes and escaped colons on Windows
            srt_escaped = str(Path(srt_path)).replace("\\", "/").replace(":", "\\:")
            subprocess.run([
                FFMPEG, "-y", "-i", str(with_music),
                "-vf", f"subtitles='{srt_escaped}':force_style='FontName=Arial,FontSize=18,"
                       "PrimaryColour=&HFFFFFF,OutlineColour=&H000000,Outline=2,Alignment=2'",
                "-c:a", "copy", "-b:v", OUTPUT_BITRATE,
                str(final_path),
            ], capture_output=True, check=True)
        else:
            subprocess.run([
                FFMPEG, "-y", "-i", str(with_music),
                "-c:v", "libx264", "-c:a", "copy",
                str(final_path),
            ], capture_output=True, check=True)

    total_duration = sum(e["end"] - e["start"] for e in edl)
    job["assembly"] = {
        "final_video_path": str(final_path),
        "final_video_url": None,
        "resolution": f"{OUTPUT_WIDTH}x{OUTPUT_HEIGHT}",
        "duration_sec": round(total_duration, 1),
        "platform_variants": [
            {"platform": "youtube_shorts", "aspect_ratio": "9:16", "path": str(final_path)}
        ],
    }
    job["status"] = "assembling"
    return job
