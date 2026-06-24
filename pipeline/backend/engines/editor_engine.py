"""Stage 8 — Visual Prompts, Stage 13 — EDL, Stage 14 — Thumbnails, Stage 15 — Metadata."""
import json
import uuid
from engines.claude_client import get_client, HAIKU

PLATFORM_ASPECT = {
    "youtube_shorts": "9:16",
    "tiktok": "9:16",
    "instagram_reels": "9:16",
    "multi": "9:16",
}


def generate_visual_prompts(job: dict) -> dict:
    """Stage 8: Convert storyboard scenes into Higgsfield-ready prompts."""
    storyboard = job["storyboard"]
    config = job["config"]
    topic = job["topic"]

    visual_style = config.get("visual_style", "photoreal_cinematic")
    target_platform = config.get("target_platform", "youtube_shorts")
    aspect_ratio = PLATFORM_ASPECT.get(target_platform, "9:16")

    scenes_json = json.dumps(storyboard["scenes"])

    system = (
        "You are the Visual Prompt Generator for a history-shorts pipeline.\n"
        "Convert each storyboard scene into a standardized Higgsfield generation prompt.\n\n"
        f"Style constants (apply to every prompt):\n"
        f"  visual_style: {visual_style}\n"
        f"  aspect_ratio: {aspect_ratio}\n"
        f"  negative_prompt: no modern objects, no anachronistic clothing, "
        "no text artifacts, no extra limbs, no blurry faces\n\n"
        "Prompt template: '[shot_description], [camera], {visual_style} style, "
        "[setting], mood: [mood]. Negative: [negative_prompt].'\n\n"
        "For each scene, decide media_type: 'video' for scenes with character motion/action, "
        "'image' for static establishing/detail shots.\n"
        "Select model: use 'seedance_2_0' for video scenes, 'soul_2' for portrait/character shots, "
        "'flux_1_1_ultra' for wide establishing shots.\n\n"
        f"Topic: {topic['title']}\n"
        f"Scenes: {scenes_json}\n\n"
        "Return ONLY valid JSON (no preamble, no markdown):\n"
        '{"visual_prompts": [{"scene_id": string, "prompt": string, '
        '"media_type": "image"|"video", "model": string, "aspect_ratio": string, '
        '"reference_ids": []}]}'
    )

    resp = get_client().messages.create(
        model=HAIKU,
        max_tokens=4000,
        system=system,
        messages=[{"role": "user", "content": "Generate visual prompts now."}],
    )

    data = json.loads(resp.content[0].text)
    job["visual_prompts"] = data.get("visual_prompts", [])
    return job


def generate_edl(job: dict) -> dict:
    """Stage 13: Edit Decision List — maps scenes to timeline positions."""
    storyboard = job["storyboard"]
    script = job["script"]

    system = (
        "You are the Assembly Engine. Produce an edit decision list (EDL) mapping "
        "each scene to its timeline position, transition type, and on-screen text overlay timing.\n\n"
        f"Storyboard scenes: {json.dumps(storyboard['scenes'])}\n"
        f"Script estimated duration: {script.get('estimated_duration_sec', 60)}s\n\n"
        "Assign start/end times that sum to the total duration. Use transitions: "
        "cut, fade, cross_dissolve, zoom_in, zoom_out.\n\n"
        "Return ONLY valid JSON (no preamble, no markdown):\n"
        '{"edl": [{"scene_id": string, "start": number, "end": number, '
        '"transition_in": string, "transition_out": string, '
        '"overlay_text": string|null, "overlay_start": number|null}]}'
    )

    resp = get_client().messages.create(
        model=HAIKU,
        max_tokens=2000,
        system=system,
        messages=[{"role": "user", "content": "Generate the EDL now."}],
    )

    data = json.loads(resp.content[0].text)
    job["edl"] = data.get("edl", [])
    return job


def generate_thumbnail_concepts(job: dict) -> dict:
    """Stage 14: 3 thumbnail concepts optimised for CTR."""
    topic = job["topic"]
    storyboard = job["storyboard"]

    best_scene = storyboard["scenes"][0] if storyboard["scenes"] else {}

    system = (
        "You are the Thumbnail Engine. Produce 3 thumbnail concepts optimized for CTR: "
        "bold focal subject, high contrast, 3-6 word text overlay, curiosity gap.\n\n"
        f"Topic: {topic['title']}\n"
        f"Hook angle: {topic['hook_angle']}\n"
        f"Best scene reference: {json.dumps(best_scene)}\n\n"
        "Return ONLY valid JSON (no preamble, no markdown):\n"
        '{"concepts": [{"prompt": string, "overlay_text": string, "rationale": string}]}'
    )

    resp = get_client().messages.create(
        model=HAIKU,
        max_tokens=1000,
        system=system,
        messages=[{"role": "user", "content": "Generate thumbnail concepts now."}],
    )

    data = json.loads(resp.content[0].text)
    job["thumbnail_concepts"] = data.get("concepts", [])
    return job


def generate_metadata(job: dict) -> dict:
    """Stage 15: Platform-optimised publishing metadata."""
    topic = job["topic"]
    script = job["script"]
    config = job["config"]
    validation = job.get("validation", {})

    target_platform = config.get("target_platform", "youtube_shorts")
    disclaimers = validation.get("required_disclaimers", [])

    segments_text = " ".join(s["text"] for s in (script.get("segments") or []))

    system = (
        f"Generate platform-optimised metadata for {target_platform}.\n\n"
        f"Topic: {topic['title']}\n"
        f"Premise: {topic['one_line_premise']}\n"
        f"Script excerpt: {segments_text[:400]}\n"
        f"Required disclaimers: {'; '.join(disclaimers) if disclaimers else 'none'}\n\n"
        "Return ONLY valid JSON (no preamble, no markdown):\n"
        '{"title": string (<=100 chars, curiosity-driven), '
        '"description": string (<=300 chars, includes 1 CTA + disclaimer if any), '
        '"tags": [string] (8-15 tags), '
        '"hashtags": [string] (platform-appropriate)}'
    )

    resp = get_client().messages.create(
        model=HAIKU,
        max_tokens=800,
        system=system,
        messages=[{"role": "user", "content": "Generate metadata now."}],
    )

    data = json.loads(resp.content[0].text)
    job["publish_metadata"] = data
    job["status"] = "completed"
    return job
