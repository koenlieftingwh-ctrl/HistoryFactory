"""Stage 8 — Visual Prompts, Stage 13 — EDL, Stage 14 — Thumbnails, Stage 15 — Metadata."""
import json
from engines.claude_client import generate
from job_store import add_llm_cost

PLATFORM_ASPECT = {
    "youtube_shorts": "9:16",
    "tiktok": "9:16",
    "instagram_reels": "9:16",
    "multi": "9:16",
}

# Credit costs per render type (kling3_0_turbo/720p/5s baseline)
CREDITS_PER_VIDEO_CLIP = 7.5
CREDITS_PER_STATIC_IMAGE = 0.5   # approximate; much cheaper than video

_STATIC_KEYWORDS = {
    "map", "coin", "artifact", "inscription", "manuscript", "document",
    "portrait", "close-up", "close up", "macro", "zoom in on", "detail of",
    "rune", "runestone", "scroll", "tablet", "painting", "illustration",
}
_CHARACTER_KEYWORDS = {"portrait", "character", "person", "people", "face", "figure", "trader", "soldier", "king", "queen", "warrior"}

# Motion verbs that strongly indicate a video clip is needed
_MOTION_KEYWORDS = {
    "sail", "sailing", "riding", "marching", "running", "moving", "battle",
    "fight", "crowd", "flowing", "burning", "animat", "trace", "sweep",
    "tracking", "journeying", "row", "rowing", "dancing",
}


def _assign_render_type(prompt: dict) -> str:
    """Deterministically assign render_type from the shot description keywords."""
    shot = (prompt.get("prompt", "") + " " + prompt.get("shot_description", "")).lower()
    # Explicit motion → always video
    if any(kw in shot for kw in _MOTION_KEYWORDS):
        return "video_clip"
    # Static artifacts/maps/portraits → static
    if any(kw in shot for kw in _STATIC_KEYWORDS):
        return "static_image"
    # Fallback: use what Gemini said, defaulting to video_clip
    return prompt.get("render_type", "video_clip")


def _assign_model(prompt: dict) -> dict:
    """Hardcode render_type and model — never trust what Gemini returns for these fields."""
    render_type = _assign_render_type(prompt)
    prompt["render_type"] = render_type
    shot = (prompt.get("prompt", "") + " " + prompt.get("shot_description", "")).lower()

    if render_type == "video_clip":
        prompt["model"] = "kling3_0_turbo"
    else:
        # cinematic_studio_2_5 is best for historical stills; soul_cinematic for close-up characters
        if any(kw in shot for kw in _CHARACTER_KEYWORDS):
            prompt["model"] = "soul_cinematic"
        else:
            prompt["model"] = "cinematic_studio_2_5"
    return prompt


def estimate_render_credits(visual_prompts: list[dict]) -> dict:
    """Return per-scene costs and total for display in the UI."""
    video_count = sum(1 for p in visual_prompts if p.get("render_type") == "video_clip")
    image_count = len(visual_prompts) - video_count
    total = (video_count * CREDITS_PER_VIDEO_CLIP) + (image_count * CREDITS_PER_STATIC_IMAGE)
    return {
        "video_clip_count": video_count,
        "static_image_count": image_count,
        "credits_video": round(video_count * CREDITS_PER_VIDEO_CLIP, 1),
        "credits_image": round(image_count * CREDITS_PER_STATIC_IMAGE, 1),
        "credits_total": round(total, 1),
    }


def generate_visual_prompts(job: dict) -> dict:
    storyboard = job["storyboard"]
    config = job["config"]
    topic = job["topic"]
    visual_style = config.get("visual_style", "photoreal_cinematic")
    aspect_ratio = PLATFORM_ASPECT.get(config.get("target_platform", "youtube_shorts"), "9:16")
    scenes_json = json.dumps(storyboard["scenes"])

    system = (
        "You are the Visual Prompt Generator for a history-shorts pipeline.\n"
        "Convert each storyboard scene into a Higgsfield generation prompt.\n\n"
        f"Style constants (apply to every prompt):\n"
        f"  visual_style: {visual_style}\n"
        f"  aspect_ratio: {aspect_ratio}\n"
        "  negative_prompt: no modern objects, no anachronistic clothing, "
        "no text artifacts, no extra limbs, no blurry faces\n\n"
        "Prompt template: '[shot_description], [camera], {visual_style} style, "
        "[setting], mood: [mood]. Negative: [negative_prompt].'\n\n"
        "For each scene assign:\n"
        "  media_type: 'video' for motion/action scenes, 'image' for static/portrait/map scenes\n"
        "  render_type: 'video_clip' for scenes with significant motion (battles, ships moving, "
        "crowds, fire, travel); 'static_image' for establishing shots, portraits, maps, "
        "close-ups of objects — aim for 40-50% static_image to save credits\n\n"
        f"Topic: {topic['title']}\nScenes: {scenes_json}\n\n"
        "Return ONLY valid JSON:\n"
        '{"visual_prompts": [{"scene_id": string, "prompt": string, '
        '"media_type": "image"|"video", "render_type": "video_clip"|"static_image", '
        '"aspect_ratio": string, "reference_ids": []}]}'
    )

    raw, usage = generate(system, "Generate visual prompts now.", max_tokens=4000)
    add_llm_cost(job, usage)
    data = json.loads(raw)
    prompts = data.get("visual_prompts", [])

    # Hardcode model — never rely on what Gemini returns
    prompts = [_assign_model(p) for p in prompts]

    # Attach credit estimate to the job for the UI
    job["visual_prompts"] = prompts
    job["render_estimate"] = estimate_render_credits(prompts)
    job.setdefault("cost_tracking", {})["render_credits_estimated"] = job["render_estimate"]["credits_total"]
    return job


def generate_edl(job: dict) -> dict:
    storyboard = job["storyboard"]
    script = job["script"]

    system = (
        "You are the Assembly Engine. Produce an edit decision list (EDL) mapping "
        "each scene to its timeline position, transition type, and on-screen text overlay timing.\n\n"
        f"Storyboard scenes: {json.dumps(storyboard['scenes'])}\n"
        f"Script estimated duration: {script.get('estimated_duration_sec', 60)}s\n\n"
        "Assign start/end times summing to total duration. "
        "Transitions: cut, fade, cross_dissolve, zoom_in, zoom_out.\n"
        "For static_image scenes, editors will apply Ken Burns pan/zoom in post — note this in the transition.\n\n"
        "Return ONLY valid JSON:\n"
        '{"edl": [{"scene_id": string, "start": number, "end": number, '
        '"transition_in": string, "transition_out": string, '
        '"overlay_text": string|null, "overlay_start": number|null}]}'
    )

    raw, usage = generate(system, "Generate the EDL now.", max_tokens=2000)
    add_llm_cost(job, usage)
    data = json.loads(raw)
    job["edl"] = data.get("edl", [])
    return job


def generate_thumbnail_concepts(job: dict) -> dict:
    topic = job["topic"]
    storyboard = job["storyboard"]
    best_scene = storyboard["scenes"][0] if storyboard["scenes"] else {}

    system = (
        "You are the Thumbnail Engine. Produce 3 thumbnail concepts optimized for CTR: "
        "bold focal subject, high contrast, 3-6 word text overlay, curiosity gap.\n\n"
        f"Topic: {topic['title']}\nHook angle: {topic['hook_angle']}\n"
        f"Best scene reference: {json.dumps(best_scene)}\n\n"
        "Return ONLY valid JSON:\n"
        '{"concepts": [{"prompt": string, "overlay_text": string, "rationale": string}]}'
    )

    raw, usage = generate(system, "Generate thumbnail concepts now.", max_tokens=1000)
    add_llm_cost(job, usage)
    data = json.loads(raw)
    job["thumbnail_concepts"] = data.get("concepts", [])
    return job


def generate_metadata(job: dict) -> dict:
    topic = job["topic"]
    script = job["script"]
    config = job["config"]
    validation = job.get("validation", {})
    target_platform = config.get("target_platform", "youtube_shorts")
    disclaimers = validation.get("required_disclaimers", [])
    segments_text = " ".join(s["text"] for s in (script.get("segments") or []))

    system = (
        f"Generate platform-optimised metadata for {target_platform}.\n\n"
        f"Topic: {topic['title']}\nPremise: {topic['one_line_premise']}\n"
        f"Script excerpt: {segments_text[:400]}\n"
        f"Required disclaimers: {'; '.join(disclaimers) if disclaimers else 'none'}\n\n"
        "Return ONLY valid JSON:\n"
        '{"title": string (<=100 chars, curiosity-driven), '
        '"description": string (<=300 chars, includes 1 CTA + disclaimer if any), '
        '"tags": [string] (8-15 tags), "hashtags": [string] (platform-appropriate)}'
    )

    raw, usage = generate(system, "Generate metadata now.", max_tokens=800)
    add_llm_cost(job, usage)
    data = json.loads(raw)
    job["publish_metadata"] = data
    return job
