# History Shorts Generator (HSG)
## Production Architecture Specification v1.0

A fully automated pipeline that generates, scores, scripts, renders, and publishes unlimited short-form historical videos with minimal human involvement. Built on Claude (orchestration + reasoning), Higgsfield (visuals), TTS (voice), generative audio (music), and a deterministic assembly layer (rendering/publishing).

---

## 1. HIGH-LEVEL SYSTEM ARCHITECTURE

```
                         ┌─────────────────────────┐
                         │   SCHEDULER / CRON       │
                         │ (upload_frequency config)│
                         └────────────┬─────────────┘
                                      │
                         ┌────────────▼─────────────┐
                         │   ORCHESTRATOR (Claude)   │
                         │ State machine over stages │
                         └────────────┬─────────────┘
        ┌────────────┬────────────┬──┴───────────┬─────────────┬─────────────┐
        ▼            ▼            ▼               ▼             ▼             ▼
  [1] Topic      [2] Scoring  [3] Research   [4] Validation [5] Script   [6] Storyboard
  Generator       Engine       Engine          Engine        Engine       Engine
        │                                                                     │
        └──────────────────────────────┬──────────────────────────────────────┘
                                        ▼
                         ┌──────────────────────────────┐
                         │  [7] Style Bible / Character   │
                         │      Consistency Engine        │
                         └──────────────┬────────────────┘
                                        ▼
                         ┌──────────────────────────────┐
                         │ [8] Visual Prompt Generator    │
                         └──────────────┬────────────────┘
                                        ▼
                         ┌──────────────────────────────┐
                         │ [9] Higgsfield Scene Generator │
                         │ (generate_image/video, Soul,   │
                         │  Elements, dubbing, voice)      │
                         └──────────────┬────────────────┘
        ┌────────────┬───────────────┬─┴────────────┬─────────────┐
        ▼            ▼               ▼               ▼             ▼
 [10] Voiceover  [11] Subtitles  [12] Music     [13] Assembly  [14] Thumbnail
   Engine          Engine         Selection        Engine        Engine
        └────────────┴───────────────┴───────────────┴─────────────┘
                                        ▼
                         ┌──────────────────────────────┐
                         │ [15] Publishing Workflow       │
                         │  (platform adapters, metadata, │
                         │   scheduling, analytics loop)  │
                         └──────────────┬────────────────┘
                                        ▼
                         ┌──────────────────────────────┐
                         │   ANALYTICS FEEDBACK STORE      │
                         │ feeds back into Topic Scoring   │
                         └──────────────────────────────┘
```

**Core design principle:** every stage is a pure function — `f(state_json) → state_json'` — so the orchestrator is just a state machine that calls Claude (for reasoning/text stages) or Higgsfield/TTS/Audio APIs (for generation stages), validates the output schema, and either advances or retries. This makes the whole pipeline horizontally scalable: run N pipelines in parallel, each a fresh state object.

### Component responsibilities

| Component | Role |
|---|---|
| **Orchestrator** | Claude-driven controller. Owns the state machine, retry logic, and stage sequencing. Implemented as a queue worker (e.g. Temporal, Step Functions, or a simple job queue) with Claude called at each decision/generation point. |
| **Topic Generator** | Claude call producing a batch of candidate topics per category/era. |
| **Scoring Engine** | Claude call (structured JSON output) that scores topics on the 6 quality axes. |
| **Research Engine** | Claude + web_search tool, grounded fact retrieval with citations. |
| **Validation Engine** | Second-pass Claude call that cross-checks facts against research, flags unverifiable claims, assigns a confidence score. |
| **Script Engine** | Claude call generating the structured script (Hook/Setup/Escalation/Twist/Payoff) per `video_length`. |
| **Storyboard Engine** | Claude call breaking the script into N scenes with shot descriptions, characters, duration. |
| **Style Bible Engine** | Maintains a persistent JSON "style bible" per category/era — locks art style, color palette, lighting, camera language, and registers recurring characters as Higgsfield Soul/Elements IDs. |
| **Visual Prompt Generator** | Claude call that converts each storyboard scene + style bible into a standardized Higgsfield prompt. |
| **Higgsfield Scene Generator** | Calls `higgsfield:generate_image` / `generate_video`, `show_characters`/`show_reference_elements` for consistency, `outpaint_image`/`reframe` for platform aspect ratios, `upscale_*` for quality. |
| **Voiceover Engine** | TTS generation (e.g. via Higgsfield `generate_audio` text2speech models, or ElevenLabs API) per narration_style/speed/language. |
| **Subtitle Engine** | Forced-alignment (e.g. Whisper timestamps) of voiceover audio → SRT/VTT, styled burn-in. |
| **Music Engine** | Selects/generates background music matched to music_intensity and emotional arc. |
| **Assembly Engine** | Deterministic video compositor (e.g. ffmpeg / Remotion) that merges scenes, voiceover, subtitles, music, transitions. |
| **Thumbnail Engine** | Generates 2-3 thumbnail candidates via Higgsfield image model, A/B-scored by Claude. |
| **Publishing Workflow** | Platform-specific upload adapters (YouTube Shorts, TikTok, Instagram Reels), metadata generation, scheduling per upload_frequency. |
| **Analytics Feedback Store** | Captures post-publish performance, feeds back into Topic Scoring weights. |

---

## 2. DATA SCHEMA

All stages read/write a single growing **Job Object**. Each stage appends its own namespaced key. This is the canonical schema (TypeScript-flavored for clarity).

```typescript
interface HSGJob {
  job_id: string;                 // uuid
  created_at: string;             // ISO8601
  status: "pending" | "researching" | "scripting" | "storyboarding" |
          "rendering" | "assembling" | "publishing" | "completed" | "failed";
  config: VideoConfig;
  topic?: Topic;
  research?: ResearchBundle;
  validation?: ValidationResult;
  script?: Script;
  storyboard?: Storyboard;
  style_bible_ref?: string;       // style_bible_id
  visual_prompts?: VisualPrompt[];
  scenes?: GeneratedScene[];
  voiceover?: VoiceoverAsset;
  subtitles?: SubtitleAsset;
  music?: MusicAsset;
  assembly?: AssemblyResult;
  thumbnail?: ThumbnailAsset;
  publish?: PublishResult;
  quality_scores?: QualityScores;
  errors?: ErrorLog[];
  retries?: Record<string, number>; // per-stage retry count
}

interface VideoConfig {
  video_length_sec: 30 | 45 | 60 | 90;
  narration_speed: "slow" | "normal" | "fast";
  narration_style: "documentary" | "dramatic" | "conversational" | "mysterious" | "comedic";
  target_platform: "youtube_shorts" | "tiktok" | "instagram_reels" | "multi";
  historical_era: string;          // e.g. "Ancient Rome", "Medieval Europe"
  topic_category: TopicCategory;
  visual_style: "painterly" | "photoreal_cinematic" | "graphic_novel" |
                "claymation" | "noir" | "watercolor" | "3d_animated";
  music_intensity: "subtle" | "moderate" | "intense";
  language: string;                // ISO 639-1, e.g. "en", "es", "ja"
  upload_frequency: "daily" | "3x_week" | "weekly" | "burst_100";
}

type TopicCategory =
  | "weird_history" | "ancient_rome" | "ancient_egypt" | "medieval_europe"
  | "vikings" | "pirates" | "historical_disasters" | "forgotten_leaders"
  | "strange_laws" | "military_history" | "historical_mysteries";

interface Topic {
  topic_id: string;
  title: string;
  one_line_premise: string;
  category: TopicCategory;
  era: string;
  hook_angle: string;            // why this is surprising
  scores?: QualityScores;
}

interface ResearchBundle {
  topic_id: string;
  facts: FactClaim[];
  sources: Source[];
  research_confidence: number;   // 0-100
}

interface FactClaim {
  claim_id: string;
  statement: string;
  source_ids: string[];
  certainty: "established" | "debated" | "disputed" | "legendary";
}

interface Source {
  source_id: string;
  title: string;
  url?: string;
  type: "primary" | "academic" | "encyclopedic" | "popular";
}

interface ValidationResult {
  topic_id: string;
  verified_claims: string[];     // claim_ids
  flagged_claims: { claim_id: string; reason: string }[];
  overall_accuracy_score: number; // 0-100
  publishable: boolean;
  required_disclaimers: string[]; // e.g. "disputed by some historians"
}

interface Script {
  script_id: string;
  language: string;
  segments: ScriptSegment[];
  total_word_count: number;
  estimated_duration_sec: number;
}

interface ScriptSegment {
  segment_type: "hook" | "setup" | "escalation" | "twist" | "payoff";
  start_pct: number;             // % of total duration
  end_pct: number;
  text: string;
  emotional_tone: string;
  claim_ids: string[];           // ties back to validated facts
}

interface Storyboard {
  storyboard_id: string;
  scenes: StoryboardScene[];
}

interface StoryboardScene {
  scene_id: string;
  segment_type: string;
  duration_sec: number;
  shot_description: string;
  camera: string;                // e.g. "slow push-in, low angle"
  characters: string[];          // character_ids referenced
  setting: string;
  mood: string;
  on_screen_text?: string;
}

interface StyleBible {
  style_bible_id: string;
  category: TopicCategory;
  visual_style: string;
  color_palette: string[];
  lighting_rules: string;
  camera_language: string;
  negative_prompt: string;       // standardized exclusions
  characters: CharacterRecord[];
}

interface CharacterRecord {
  character_id: string;
  name: string;
  description: string;
  higgsfield_ref_type: "soul" | "element";
  higgsfield_ref_id: string;
}

interface VisualPrompt {
  scene_id: string;
  prompt: string;
  model: string;                 // e.g. "soul_2", "seedance_2_0"
  aspect_ratio: string;
  reference_ids: string[];       // soul_id / element_id used
}

interface GeneratedScene {
  scene_id: string;
  media_type: "image" | "video";
  job_id: string;                // higgsfield job id
  asset_url: string;
  duration_sec: number;
  status: "pending" | "completed" | "failed";
}

interface VoiceoverAsset {
  audio_url: string;
  duration_sec: number;
  voice_id: string;
  language: string;
  word_timestamps: { word: string; start: number; end: number }[];
}

interface SubtitleAsset {
  srt_url: string;
  vtt_url: string;
  style: Record<string, string>;
}

interface MusicAsset {
  track_url: string;
  intensity: string;
  bpm: number;
  mood_tags: string[];
}

interface AssemblyResult {
  final_video_url: string;
  resolution: string;
  duration_sec: number;
  platform_variants: { platform: string; url: string; aspect_ratio: string }[];
}

interface ThumbnailAsset {
  candidates: { url: string; ctr_score: number }[];
  selected_url: string;
}

interface PublishResult {
  platform: string;
  post_id: string;
  scheduled_time: string;
  metadata: { title: string; description: string; tags: string[] };
}

interface QualityScores {
  historical_accuracy: number;
  visual_potential: number;
  retention_potential: number;
  novelty: number;
  emotional_impact: number;
  shareability: number;
  composite: number;             // weighted average
}

interface ErrorLog {
  stage: string;
  error: string;
  timestamp: string;
  retry_count: number;
}
```

---

## 3. WORKFLOW STAGES (pipeline order)

```
1. Topic Generation        → produces N Topic[] candidates
2. Topic Scoring            → ranks candidates, selects top 1 per job slot
3. Fact Research            → ResearchBundle
4. Fact Validation          → ValidationResult (gate: publishable=true required)
5. Script Generation        → Script
6. Storyboard Generation    → Storyboard
7. Character Consistency    → StyleBible.characters resolved/created
8. Visual Prompt Generation → VisualPrompt[]
9. Higgsfield Scene Gen     → GeneratedScene[]
10. Voiceover Generation    → VoiceoverAsset
11. Subtitle Generation     → SubtitleAsset
12. Music Selection         → MusicAsset
13. Video Assembly          → AssemblyResult
14. Thumbnail Creation      → ThumbnailAsset
15. Publishing Workflow     → PublishResult
```

Each stage is a **gated transition**: if validation fails (schema invalid, score below threshold, fact-check fails), the job either retries the stage (bounded by `retries[stage] < max_retries`), falls back to an alternate topic/prompt, or moves to `failed` with a full error log for human review. This keeps unattended runs safe.

---

## 4. PROMPT TEMPLATES (per stage)

All Claude calls use **strict JSON-only system prompts** with explicit schemas, so outputs can be parsed without fragile regex.

### 4.1 Topic Generation
```
SYSTEM:
You are the Topic Engine for an automated history-shorts pipeline.
Generate {{batch_size}} distinct historical story topics for:
  category: {{topic_category}}
  era: {{historical_era}}
Each topic must be a genuinely surprising, little-known, or bizarre
historical event or figure suitable for a {{video_length_sec}}-second
short-form video. Avoid topics already in this exclusion list:
{{previously_used_titles}}

Prioritize: surprising facts, bizarre events, unknown stories, strong
visual potential, short-form retention.

Return ONLY valid JSON matching this schema, no preamble, no markdown:
{
  "topics": [
    {
      "title": string,
      "one_line_premise": string,
      "hook_angle": string,
      "era": string,
      "category": string
    }
  ]
}
```

### 4.2 Topic Scoring
```
SYSTEM:
You are the Quality Scoring Engine. Score the following topic on six
axes, each 0-100, using the rubrics below. Be strict — most topics
should NOT score above 85 on any axis.

Rubrics:
- historical_accuracy: how verifiable/well-documented is this topic likely to be (not final fact-check, just plausibility)
- visual_potential: how well this translates into striking AI-generated visuals
- retention_potential: likelihood of holding a short-form viewer for the full duration
- novelty: how unfamiliar this is to a general audience
- emotional_impact: strength of emotional reaction (shock, awe, humor, horror)
- shareability: likelihood of being shared/commented on

Topic: {{topic_json}}

Return ONLY:
{
  "topic_id": string,
  "historical_accuracy": int,
  "visual_potential": int,
  "retention_potential": int,
  "novelty": int,
  "emotional_impact": int,
  "shareability": int,
  "composite": int,
  "rationale": string
}
```

### 4.3 Fact Research
```
SYSTEM:
You are the Research Engine. Using web_search, gather verifiable facts
about: "{{topic.title}}" ({{topic.era}}).

For each discrete fact, note:
- the claim
- which source(s) support it
- a certainty label: established | debated | disputed | legendary

Prefer academic/encyclopedic sources over popular/blog sources.
Gather 6-12 facts sufficient to write a {{video_length_sec}}s script.

Return ONLY:
{
  "topic_id": string,
  "facts": [
    {"claim_id": string, "statement": string, "source_ids": [string], "certainty": string}
  ],
  "sources": [
    {"source_id": string, "title": string, "url": string, "type": string}
  ],
  "research_confidence": int
}
```

### 4.4 Fact Validation
```
SYSTEM:
You are the Fact Validation Engine — an adversarial checker. Re-examine
each claim in {{research_bundle_json}}. Flag any claim that:
- is sourced only from a single low-quality source
- is commonly cited as myth/legend by historians
- cannot be corroborated

Assign overall_accuracy_score (0-100). Set publishable=false if more
than 30% of claims are flagged, or if any "disputed"/"legendary" claim
is load-bearing to the script's central premise without a disclaimer.

Return ONLY:
{
  "topic_id": string,
  "verified_claims": [string],
  "flagged_claims": [{"claim_id": string, "reason": string}],
  "overall_accuracy_score": int,
  "publishable": boolean,
  "required_disclaimers": [string]
}
```

### 4.5 Script Generation
```
SYSTEM:
You are the Script Engine. Write a narration script using ONLY verified
claims from {{validation_result.verified_claims}} and facts {{facts_json}}.

Structure (percentages scale to {{video_length_sec}}s):
- Hook       0-5%    : a shocking question or statement, <2 sentences
- Setup      5-25%   : establish time/place/who, plain and vivid
- Escalation 25-67%  : build tension, stack surprising details
- Twist      67-92%  : the unexpected turn / payoff fact
- Payoff     92-100% : final punch line + soft CTA ("follow for more")

Style: {{narration_style}}. Speed: {{narration_speed}} (affects pacing/word
density, not just TTS rate — fast = shorter sentences, more cuts).
Language: {{language}}. Include required disclaimers naturally if any:
{{required_disclaimers}}.

Target word count: ~{{video_length_sec}} * {{words_per_sec_for_style}}.

Return ONLY:
{
  "script_id": string,
  "language": string,
  "segments": [
    {"segment_type": string, "start_pct": number, "end_pct": number,
     "text": string, "emotional_tone": string, "claim_ids": [string]}
  ],
  "total_word_count": int,
  "estimated_duration_sec": number
}
```

### 4.6 Storyboard Generation
```
SYSTEM:
You are the Storyboard Engine. Convert this script into a shot list.
Rule of thumb: one new scene every 2.5-4 seconds for fast retention pacing.
For a {{video_length_sec}}s video, produce {{scene_count_estimate}} scenes.

For each scene specify: duration, shot_description (concrete visual,
not abstract), camera movement, characters present (reuse existing
character names where the script references the same person/figure),
setting, mood, and optional on-screen text (big bold key fact/number).

Script: {{script_json}}

Return ONLY:
{
  "storyboard_id": string,
  "scenes": [
    {"scene_id": string, "segment_type": string, "duration_sec": number,
     "shot_description": string, "camera": string, "characters": [string],
     "setting": string, "mood": string, "on_screen_text": string|null}
  ]
}
```

### 4.7 Character Consistency (Style Bible resolution)
```
SYSTEM:
You are the Character Consistency Engine. Given storyboard scenes
{{storyboard.scenes}} and the existing style bible for category
{{topic_category}} {{style_bible_json}}:

1. Identify every distinct character name referenced.
2. For each, check if a CharacterRecord already exists in the style
   bible (match by name+era). If yes, reuse its higgsfield_ref_id.
3. If not, output a "new_character_request" with a detailed visual
   description (face, build, clothing, era-accurate attire, signature
   props) suitable for Higgsfield Soul/Element creation.

Return ONLY:
{
  "resolved_characters": [{"name": string, "character_id": string}],
  "new_character_requests": [
    {"name": string, "description": string, "recommended_ref_type": "soul"|"element"}
  ]
}
```
*(New characters get created via `higgsfield:show_characters` (action=train) for recurring protagonists across a multi-part series, or `higgsfield:show_reference_elements` (action=create) for single-video or multi-subject scenes — see Section 8.)*

### 4.8 Visual Prompt Generation
```
SYSTEM:
You are the Visual Prompt Generator. Convert each storyboard scene into
a standardized Higgsfield prompt using the locked style bible.

Style bible constants (apply to every prompt verbatim):
  visual_style: {{style_bible.visual_style}}
  color_palette: {{style_bible.color_palette}}
  lighting_rules: {{style_bible.lighting_rules}}
  camera_language: {{style_bible.camera_language}}
  negative_prompt: {{style_bible.negative_prompt}}

Prompt template (fill brackets, keep structure fixed):
"[shot_description], [camera], {{visual_style}} style, [setting], lighting:
{{lighting_rules}}, palette: {{color_palette}}, mood: [mood] — featuring
<<<character_ref_id>>> where applicable. Negative: {{negative_prompt}}."

For each scene, decide image vs video (video for scenes with character
motion/action; image for static establishing/detail shots), and select
aspect_ratio matching {{target_platform}} (9:16 for shorts/reels/tiktok).

Scenes: {{storyboard.scenes}}

Return ONLY:
{
  "visual_prompts": [
    {"scene_id": string, "prompt": string, "media_type": "image"|"video",
     "model": string, "aspect_ratio": string, "reference_ids": [string]}
  ]
}
```

### 4.9 Higgsfield Scene Generation (tool-call layer, not free text)
Not a text prompt — this stage directly calls `higgsfield:generate_image` / `higgsfield:generate_video` per `VisualPrompt`, embedding `<<<character_ref_id>>>` placeholders for Elements, or passing `soul_id` for Soul-based characters. See Section 8 for the exact calling pattern.

### 4.10 Voiceover Generation prompt (voice direction, passed as TTS instruction where supported)
```
SYSTEM:
Generate narration audio for script {{script.segments}} using voice_id
{{voice_id}}, style {{narration_style}}, speed {{narration_speed}},
language {{language}}. Maintain consistent emotional tone per segment:
hook=sharp/intriguing, setup=measured, escalation=building intensity,
twist=sudden emphasis, payoff=satisfied/wry.
```

### 4.11 Subtitle Generation
Deterministic (no LLM creativity needed): force-align voiceover audio to script text (e.g. Whisper word-level timestamps) → generate SRT/VTT. Claude's only role here is selecting caption style per platform convention:
```
SYSTEM:
Given target_platform {{target_platform}} and visual_style {{visual_style}},
output a subtitle style spec (font, size, color, highlight-word color,
position, animation) appropriate for that platform's caption conventions.
Return ONLY: {"font": string, "size": int, "color": string,
"highlight_color": string, "position": string, "animation": string}
```

### 4.12 Music Selection
```
SYSTEM:
You are the Music Engine. Given the script's emotional arc
{{script.segments[*].emotional_tone}} and music_intensity {{music_intensity}},
either (a) select a track from the music library tagged with matching
mood/bpm, or (b) generate a generation prompt for an AI music model.

Return ONLY:
{
  "mode": "select"|"generate",
  "track_id_or_prompt": string,
  "bpm": int,
  "mood_tags": [string],
  "intensity": string
}
```

### 4.13 Video Assembly (orchestration spec, not LLM text)
Deterministic compositor job spec — Claude only produces the **edit decision list (EDL)**:
```
SYSTEM:
Produce an edit decision list mapping each scene to its timeline position,
transition type, and any on-screen text overlay timing, synced to
voiceover word_timestamps and subtitle cues.

Return ONLY:
{
  "edl": [
    {"scene_id": string, "start": number, "end": number,
     "transition_in": string, "transition_out": string,
     "overlay_text": string|null, "overlay_start": number|null}
  ]
}
```

### 4.14 Thumbnail Creation
```
SYSTEM:
You are the Thumbnail Engine. Given the topic, hook_angle, and the most
visually striking generated scene {{best_scene}}, produce 3 thumbnail
concepts optimized for CTR: bold focal subject, high contrast, 3-6 word
text overlay, curiosity gap.

Return ONLY:
{
  "concepts": [
    {"prompt": string, "overlay_text": string, "rationale": string}
  ]
}
```

### 4.15 Publishing Workflow (metadata)
```
SYSTEM:
Generate platform-optimized metadata for {{target_platform}}.

Return ONLY:
{
  "title": string (<=100 chars, curiosity-driven, no clickbait lies),
  "description": string (<=300 chars, includes 1 CTA + disclaimer if any),
  "tags": [string] (8-15 tags),
  "hashtags": [string] (platform-appropriate count)
}
```

---

## 5. JSON FORMATS PASSED BETWEEN STAGES

Already fully specified in Section 2 (`HSGJob` and its nested types). The contract: **every stage receives the full `HSGJob` object, mutates only its own namespaced key, and returns the whole object.** This avoids partial-state bugs and makes every stage replayable/idempotent — critical for retrying a failed stage without re-running upstream work.

Validation: each stage output is checked against a JSON Schema (e.g. via `zod`/`pydantic`) before being written back to the job. Invalid output triggers an automatic retry with the validation error appended to the next prompt ("your previous output failed schema validation: {error}; fix and resend").

---

## 6. ERROR HANDLING STRATEGY

| Failure type | Strategy |
|---|---|
| **Schema validation failure** (Claude returns malformed JSON) | Retry up to 3x with the error appended to the prompt. On 3rd failure, escalate to `failed` with full transcript logged. |
| **Higgsfield generation failure** (`recovery_tool` returned, NSFW flag, job failed) | Auto-apply `recovery_tool` if returned. Otherwise regenerate with adjusted prompt (strip flagged terms) up to 2x, then fall back to a simpler/safer prompt template (no characters, generic establishing shot). |
| **Fact validation gate fails** (`publishable=false`) | Do not proceed to scripting. Either (a) re-run research with a narrowed claim set, or (b) discard topic and pull the next-highest-scored topic from the queue. Never force-publish unverified content. |
| **TTS/voice failure** | Retry with fallback voice_id; if language unsupported, flag for human review rather than silently switching language. |
| **Assembly failure** (corrupt asset, duration mismatch) | Validate each asset (duration, resolution, codec) before assembly; if a scene asset is missing/corrupt, regenerate just that scene rather than restarting the whole job. |
| **Publishing failure** (platform API error, rate limit) | Exponential backoff retry; if persistent, queue for next scheduled slot and alert via webhook/Slack rather than dropping the video. |
| **Partial pipeline crash** | Because `HSGJob` is the single source of truth and every stage is idempotent given the same input, the orchestrator can resume any job from its last completed stage — no full restarts. |
| **Cost/rate-limit guardrails** | Per-job budget cap (max API spend); if exceeded mid-pipeline, pause and flag rather than burning unlimited credits on a single video. |

All errors append to `errors: ErrorLog[]` on the job so the full failure history is auditable.

---

## 7. FACT-CHECKING STRATEGY

Two-pass adversarial design, deliberately separating *gathering* from *judging*:

1. **Research pass (generous):** Claude + `web_search`, instructed to prefer academic/encyclopedic sources, gather more facts than needed, label certainty per claim.
2. **Validation pass (adversarial, separate call/context):** A second Claude call — primed to be skeptical, not generative — re-examines each claim independently, flags weak sourcing, and computes `overall_accuracy_score`. Running this as a *separate* call (not a continuation) avoids the model anchoring on its own research framing.
3. **Hard gate:** `publishable=false` blocks the pipeline from advancing to scripting. This is a structural safeguard, not a suggestion — the orchestrator enforces it in code, not just in the prompt.
4. **Disclaimers as first-class data:** "disputed"/"legendary" claims aren't deleted — they're preserved with a `required_disclaimers` field the Script Engine must weave in ("as the legend goes...", "historians still debate..."). This protects accuracy without flattening genuinely interesting folklore-adjacent stories.
5. **Source-type weighting:** primary/academic sources outweigh popular/blog sources when computing confidence — encoded directly in the rubric, not left to model judgment alone.
6. **Audit trail:** every script segment carries `claim_ids` linking narration text back to specific validated facts — enables spot-checking and is a defensible compliance trail if a video is ever challenged.

---

## 8. CHARACTER CONSISTENCY STRATEGY

Two Higgsfield mechanisms, chosen deliberately per use case:

- **Soul (`higgsfield:show_characters`, action=train):** for **recurring protagonists across a whole series** (e.g. a recurring narrator-mascot, or a figure like "Julius Caesar" who will appear in many Ancient Rome videos). Requires 5-20 reference images and ~10 min training, but yields strong identity-faithful results reusable indefinitely via `soul_id`. Worth the upfront cost only for characters that will recur across many jobs.
- **Reference Elements (`higgsfield:show_reference_elements`, action=create):** for **one-off or multi-character scenes** within a single video (e.g. two side characters appearing only in this episode, or non-person subjects like a specific ship or building that must stay visually consistent within the video). Instant creation, supports multiple elements per prompt via `<<<element_id>>>` placeholders.

**Decision rule (encoded in Character Consistency Engine, Section 4.7):**
- Character appears across multiple planned videos in the same category/era → train as Soul, store `soul_id` in the persistent `StyleBible.characters`.
- Character is local to one video, or scene has >1 character together → use Elements.

**Persistent registry:** the `StyleBible.characters` array is the single source of truth per category+era combination, stored in a database (not regenerated per job). Before creating any new character, the Character Consistency Engine checks this registry by name+era match to avoid duplicate Souls/Elements for the same historical figure across different jobs — this is what makes "Julius Caesar" look the same in video #4 and video #47.

**Validation step:** after generation, a lightweight visual QA pass (Claude with image input, or a CLIP-similarity check) compares the generated character against the reference to catch drift before assembly.

---

## 9. VISUAL CONSISTENCY STRATEGY (Style Bible System)

A **Style Bible** is a versioned, persistent JSON object per `(topic_category, visual_style)` pair — e.g. one for "Ancient Rome / photoreal_cinematic", another for "Vikings / graphic_novel". It is created once and reused across all future jobs in that category, not regenerated per video.

```
StyleBible {
  visual_style, color_palette, lighting_rules, camera_language,
  negative_prompt, characters[]
}
```

**Enforcement mechanisms:**
1. **Constants injected verbatim** into every Visual Prompt (Section 4.8) — the model/color/lighting/camera language strings are never paraphrased per scene, only the scene-specific content changes. This is the single biggest lever for cross-scene consistency.
2. **Negative prompt standardization** — a fixed exclusion list per style (e.g. "no modern objects, no anachronistic clothing, no text artifacts, no extra limbs") applied identically everywhere.
3. **Locked model selection per style** — each Style Bible specifies which Higgsfield model produces its signature look (e.g. `soul_2` for photoreal portraits, `seedance_2_0` for cinematic motion, a painterly model for "weird history" satire). Switching models mid-series is disallowed to prevent visual drift.
4. **Reference-image anchoring** — the first 1-2 generated scenes of a new Style Bible are manually approved (or auto-approved by a Claude visual-QA check) and stored as canonical reference images; later scenes can optionally pass these as style references.
5. **Versioning** — Style Bibles are versioned (`v1`, `v2`...) so a deliberate refresh (e.g. upgrading visual_style) doesn't silently break consistency for in-flight jobs; jobs pin to a specific version.
6. **Post-generation QA gate** — before assembly, a Claude vision check scores each scene against the style bible (palette match, anachronism check, character drift) and rejects/regenerates outliers.

---

## 10. SCALABILITY STRATEGY

**Target: 100+ unique shorts/week with minimal human involvement.**

- **Stateless, parallel job workers.** Since every job is a self-contained `HSGJob` object processed through pure-function stages, the orchestrator can run dozens of jobs concurrently (e.g. via a job queue: SQS/Redis + worker pool). No shared mutable state between jobs except the read-mostly Style Bible registry.
- **Topic batching ahead of demand.** Topic Generation + Scoring run in large batches (hundreds of candidates per category, generated weekly) well ahead of the render pipeline, so there's always a ranked backlog ready — render capacity is never blocked on ideation.
- **Stage-level concurrency.** Within a job, independent stages (Voiceover, Music Selection, Thumbnail generation) can run in parallel once their shared dependency (script/storyboard) is ready, rather than fully serial.
- **Category/era sharding.** Style Bibles and character registries are sharded by category+era, so categories can scale independently (e.g. spin up more parallel jobs for "Weird History" if it's outperforming).
- **Upload-frequency-aware scheduling.** The Publishing Workflow is decoupled from generation — videos are generated continuously into a "ready" queue, then drip-published per `upload_frequency` config, smoothing platform rate limits and avoiding spammy clustering.
- **Idempotent retries.** Because stages are replayable, scaling failures (rate limits, transient API errors) cost only the failed stage's compute, not the whole pipeline — essential at 100+/week volume where some failure rate is guaranteed.
- **Analytics feedback loop.** Published-video performance flows back into Topic Scoring weights (e.g. boosting `novelty` weight if novel topics are consistently outperforming), so the system self-tunes without manual curation as volume grows.

---

## 11. COST OPTIMIZATION STRATEGY

- **Cheap-model triage, expensive-model commitment.** Use a smaller/cheaper Claude model (e.g. Haiku-tier) for high-volume, low-stakes stages (Topic Generation, Scoring of hundreds of candidates) and reserve a stronger model (Sonnet/Opus-tier) for stages where quality directly drives output value (Script, Storyboard, Validation).
- **Score before you spend.** The Topic Scoring gate happens *before* any Higgsfield/TTS spend — only the highest-composite-score topics ever reach the expensive generation stages. This is the single largest cost lever: rejecting a bad topic costs one cheap text call; rejecting a bad finished video costs the entire render budget.
- **`get_cost` preflighting.** Every Higgsfield generation call supports `get_cost:true`; the pipeline preflights cost on the first scene of a new style/model combination and aborts/adjusts before committing to a full 15-20 scene render if costs spike unexpectedly.
- **Resolution-matched rendering.** Render at the minimum resolution needed for the target platform (e.g. 1080p vertical, not 4K) and only `upscale_image`/`upscale_video` selectively for thumbnail or hero shots, not every scene.
- **Reuse over regenerate.** Persistent Style Bibles + character registry (Section 8/9) mean recurring characters and settings are generated once and reused via reference IDs across dozens of videos, not re-rendered from scratch each time.
- **Batch topic/script calls.** Generate topics and score them in large batches per Claude call rather than one-at-a-time, amortizing fixed prompt overhead.
- **Per-job budget caps.** Hard cost ceiling per job (Section 6) prevents runaway spend on any single problematic video (e.g. repeated regeneration loops).
- **Music/voice asset libraries.** Prefer "select" mode over "generate" mode for music (Section 4.12) when a suitable pre-generated track exists in the library — generation is reserved for genuinely novel mood requirements.

---

## 12. QUALITY SCORING FRAMEWORK

Every topic and (optionally) every finished video is scored 0-100 on six axes, computed by the Scoring Engine prompt (Section 4.2) and re-validated post-production via a finished-video QA pass.

| Score | Definition | Key signals |
|---|---|---|
| **historical_accuracy** | How well-documented/verifiable the core claims are | source quality mix, % of claims "established" vs "disputed/legendary", validation gate result |
| **visual_potential** | How well the premise translates into striking AI visuals | concrete physical action/imagery in the premise, availability of strong reference subjects, avoidance of abstract/talking-head-only content |
| **retention_potential** | Likelihood of holding viewers the full duration | strength of hook, pacing density, presence of a clear escalation arc, twist clarity |
| **novelty** | How unfamiliar this is to a general audience | rarity of the topic in existing short-form content, "I didn't know that" factor |
| **emotional_impact** | Strength of evoked reaction (shock, awe, humor, horror, outrage) | intensity of the central fact, stakes involved |
| **shareability** | Likelihood of comments/shares/duets | controversy-without-harm, "send this to a friend" quality, debate potential |

`composite = weighted_average(scores, weights)` — default weights `{accuracy: 0.20, visual: 0.20, retention: 0.20, novelty: 0.15, emotional: 0.15, shareability: 0.10}`, but these weights are **tunable per category** and **auto-adjusted by the analytics feedback loop** (Section 10) based on real published-video performance.

**Two scoring checkpoints:**
1. **Pre-production** (topic-level): gates which topics enter the expensive pipeline at all.
2. **Post-production** (finished-video QA, optional but recommended at scale): a Claude vision+text pass scores the assembled video against the same rubric, catching cases where execution underdelivered on a good topic — feeds directly into the analytics loop and can trigger a re-cut before publishing rather than after.

---

## 13. TOPIC ENGINE (detailed method)

**Goal:** generate hundreds of ranked ideas continuously, with zero manual ideation.

**Method:**
1. **Seed matrix expansion.** Cross every `topic_category` (11) × `historical_era` variant relevant to it × a rotating set of "angle" primes (e.g. "a law so strange it sounds fake", "a leader history forgot", "a disaster caused by one small mistake", "an everyday object with a brutal origin story"). This matrix alone yields hundreds of distinct generation prompts without repeating angles.
2. **Batch generation.** For each matrix cell, call the Topic Generation prompt (4.1) requesting 10-20 candidates, explicitly passing an `previously_used_titles` exclusion list (pulled from the persistent topic-history database) to prevent duplicates across weeks.
3. **Bulk scoring.** Every candidate is scored via the Scoring Engine (4.2) in batched calls (e.g. 20 topics per call) to keep cost low.
4. **Ranking + bucketing.** Sort by `composite` score; bucket by category to guarantee category diversity in the publishing queue rather than letting one high-scoring category dominate.
5. **Backlog maintenance.** Maintain a rolling backlog sized to ~4 weeks of `upload_frequency` ahead of current production, replenished weekly so render capacity is never idle waiting on ideation.
6. **Dedup + freshness check.** Before a topic enters production, a cheap similarity check (embedding cosine similarity against the topic-history database) blocks near-duplicate topics even if phrased differently.
7. **Feedback-weighted regeneration.** Weekly, the analytics feedback loop adjusts which "angle primes" and categories get heavier sampling in step 1, based on which past topics' composite scores correlated with actual view/retention performance.

---

## 14. VISUAL ENGINE (Style Bible system — implementation detail)

Building on Section 9, the operational lifecycle:

1. **Bootstrap (once per category+era+visual_style combo):**
   - Claude drafts the initial `StyleBible` (palette, lighting, camera language, negative prompt, model choice) given the category/era/visual_style config.
   - 2-3 test scenes are generated and visually reviewed (auto via Claude vision QA, or manual on first launch) to confirm the look is locked in.
   - Approved bible is persisted with `style_bible_id` and `version`.
2. **Per-job reuse:** every job for that category+era+style pulls the existing bible rather than regenerating one — this is the mechanism that keeps "all scenes share the same art style" true *across* videos, not just within one.
3. **Character registration:** new recurring characters get added to `StyleBible.characters` the first time they appear (Section 8) and are reused thereafter by reference ID — never regenerated from a text description twice.
4. **Standardized prompt assembly:** the Visual Prompt Generator (4.8) is structurally forbidden from improvising new style language — it fills a fixed template with bible constants, so prompt drift across hundreds of jobs is structurally prevented rather than relying on the model "remembering" to stay consistent.
5. **Drift detection:** periodic QA sampling (e.g. every 20th scene) runs a Claude-vision comparison against the bible's canonical reference images; if drift is detected, the bible enters a review state before further jobs consume it.
6. **Controlled evolution:** when a category's visual_style is deliberately refreshed (e.g. seasonal refresh), a new bible version is created rather than mutating the existing one, so historical videos and in-flight jobs aren't retroactively destabilized.

---

## 15. SCRIPT ENGINE (structure detail)

Fixed five-act structure, **percentage-based** so it scales cleanly across all supported `video_length_sec` values (30/45/60/90):

| Act | % of duration | Function | Pacing notes |
|---|---|---|---|
| Hook | 0-5% | Shock/question that stops the scroll | ≤2 sentences, no setup, maximum surprise density |
| Setup | 5-25% | Who/where/when, just enough context | Plain, vivid, no wasted words |
| Escalation | 25-67% | Stack surprising details, build tension | Highest scene-cut density; this is where most "weird facts" live |
| Twist | 67-92% | The unexpected turn — the actual payoff fact | Sentence rhythm slows slightly for emphasis right before the turn |
| Payoff | 92-100% | Punchline + soft CTA | Short, satisfying, ends on the strongest image/line |

**Length-adaptive behavior:** the Script Engine prompt (4.5) receives `video_length_sec` and a style-specific `words_per_sec_for_style` constant (narration_speed-dependent: slow ≈ 2.2 wps, normal ≈ 2.6 wps, fast ≈ 3.0 wps) and computes target word count per segment from the percentage bands — so a 30s video gets a tightly compressed 1-2 sentence Escalation while a 90s video gets room for 4-6 escalating beats, without changing the underlying five-act shape. This is what lets one prompt template serve every configured video length.

**Claim grounding:** every segment must cite `claim_ids` back to validated facts (Section 6 schema) — the Script Engine is structurally prevented from inventing details not present in the validated research bundle, since each segment's `claim_ids` field is checked against `ValidationResult.verified_claims` before the job is allowed to proceed to Storyboarding.

---

## Implementation Notes for the Developer

- **Orchestration:** implement as a durable workflow engine (Temporal, AWS Step Functions, or a custom queue-based state machine) — not a single long-running script — so multi-hour pipelines survive restarts and scale horizontally.
- **Claude calls:** use structured/JSON-mode prompting throughout (Section 4); validate every response against the schemas in Section 2 before persisting.
- **Higgsfield integration:** use `models_explore` to confirm current model IDs/params before hardcoding; use `get_cost:true` preflighting before bulk scene generation; always check `recovery_tool` in responses and apply immediately.
- **Storage:** Style Bibles, character registries, and topic-history live in a persistent database (Postgres/DynamoDB), not in-memory — they must outlive individual jobs and be shared across the whole category's job history.
- **Observability:** every job's full `HSGJob` object plus `errors[]` should be queryable for debugging; emit metrics per stage (latency, retry rate, cost) to catch systemic issues before they burn budget at 100+/week scale.
