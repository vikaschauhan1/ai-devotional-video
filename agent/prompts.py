"""Prompt templates for the AI agent.

Prompts live in one place so we can iterate on them without touching
call sites. All prompts must yield JSON that validates against the
Pydantic schemas in ``backend/app/schemas/lyrics.py`` and
``backend/app/schemas/scenes.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

LYRICS_ANALYSIS_SYSTEM = """You are a musicologist specialising in Hindu devotional music
(bhajan, mantra, aarti, stotra, chalisa, shlok, kirtan, and Indian classical
devotional forms). You understand Hindi, Sanskrit and other Indian languages.
You always reply in strict JSON matching the requested schema."""


def build_lyrics_analysis_prompt(
    *,
    lyrics: str,
    hint_deity: str | None,
    hint_language: str | None,
    audio_duration: float | None,
    transcript_hint: str | None,
) -> str:
    hints = []
    if hint_deity:
        hints.append(f"- Suggested deity (may be wrong): {hint_deity}")
    if hint_language:
        hints.append(f"- Suggested language (may be wrong): {hint_language}")
    if audio_duration is not None:
        hints.append(f"- Total audio duration in seconds: {audio_duration:.2f}")
    if transcript_hint:
        hints.append("- ASR transcript (may contain errors): " + transcript_hint[:500])
    hint_block = "\n".join(hints) if hints else "(no additional hints)"

    return f"""Analyse the following devotional song lyrics.

Lyrics (in the original script):
\"\"\"
{lyrics.strip()}
\"\"\"

Hints:
{hint_block}

Do all of the following:
1. Detect the primary language of the lyrics. Prefer the ISO 639-1 code
   (\"hi\", \"sa\", \"en\", \"ta\", \"te\", \"kn\", \"ml\", \"mr\", \"gu\", \"bn\",
   \"pa\", \"or\", \"as\").
   Use \"sa\" for Sanskrit even if the script is Devanagari.
2. Detect the primary deity if one is clearly present (Shiva, Krishna, Ram, Hanuman,
   Ganesha, Durga, Devi, Vishnu, Saraswati, Lakshmi, ...). Use null when unclear.
3. Detect the overall mood (devotional, joyous, meditative, energetic, solemn).
4. Segment the lyrics into structural sections. Allowed types:
   intro, mukhda, antara, bridge, mantra, doha, chant, alap, outro.
   Each section MUST have a non-empty lyrics field containing the actual
   text of that section, and start/end times in seconds (floats). If you
   only have lyric text and no timings, spread evenly across the audio
   duration when known, otherwise use 0.0 for both start and end.
5. For each section, set visual_intensity to one of: low, medium, high.

Return the result as JSON matching the required schema exactly. Do not
add any prose."""


LYRICS_ANALYSIS_JSON_SCHEMA = {
    "type": "object",
    "required": ["theme", "language", "mood", "sections"],
    "properties": {
        "theme": {"type": "string"},
        "deity": {"type": ["string", "null"]},
        "language": {"type": "string"},
        "mood": {"type": "string"},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["type", "start", "end", "lyrics", "visual_intensity"],
                "properties": {
                    "type": {"type": "string"},
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "lyrics": {"type": "string"},
                    "visual_intensity": {"type": "string"},
                },
            },
        },
    },
}


# ─── Scene planner (Phase 10) ────────────────────────────────────────

SCENE_PLAN_SYSTEM = """You are a devotional cinematographer and prompt engineer.
You convert lyrics + song structure + deity/style hints into a sequence of short
cinematic scenes suitable for AI image and video generation. You know Hindu iconography
(Shiva's third eye and trishula, Krishna's flute and peacock feather, Hanuman's gada,
Ram's bow, temples, aartis, Himalayas, Ganga, jyotirlingas, ...), classical devotional
aesthetics, and lighting. You reply in strict JSON matching the requested schema."""


@dataclass(slots=True, frozen=True)
class StylePreset:
    id: str
    description: str  # Short human-readable
    visual: str      # Environment / iconography / clothing detail
    lighting: str    # Preferred lighting
    camera: str      # Preferred camera language
    mood: str        # Emotional tone
    negatives: str   # Comma-separated negative-prompt terms


# Presets referenced in the spec (Phase 21).
VISUAL_STYLE_PRESETS: dict[str, StylePreset] = {
    "shiva-himalayan": StylePreset(
        id="shiva-himalayan",
        description="Lord Shiva meditating in the snow-capped Himalayas",
        visual="Kailash range, snow, blue sky, ancient rudraksha beads, Shiva in tiger skin, matted hair, trishula, damaru",
        lighting="cold blue morning light with warm golden accents from the rising sun",
        camera="slow cinematic push-in, wide establishing shots, gentle dolly moves",
        mood="serene, contemplative, majestic",
        negatives="modern clothing, cars, cityscape, text, watermark, deformed hands, extra limbs, low quality",
    ),
    "shiva-temple": StylePreset(
        id="shiva-temple",
        description="Ancient Shiva temple with devotees and lamps",
        visual="carved stone temple, shivalinga, brass bells, garlands of belpatra, oil lamps, devotees in traditional dress",
        lighting="warm oil-lamp glow, candlelight, incense haze",
        camera="handheld intimate shots, slow orbital moves around the linga, close-ups of lamps and flowers",
        mood="reverent, warm, devotional",
        negatives="modern clothing, plastic decor, neon, text, watermark, low quality",
    ),
    "kailash": StylePreset(
        id="kailash",
        description="Mount Kailash, the abode of Shiva",
        visual="pyramidal snow-capped mountain, prayer flags, Mansarovar lake reflection, monasteries in the distance",
        lighting="high-altitude sunlight, long shadows, occasional lens flare",
        camera="epic wide aerial establishing shots, slow reveal push-outs",
        mood="cosmic, epic, transcendent",
        negatives="tourists, modern equipment, text, watermark, low quality",
    ),
    "ganga": StylePreset(
        id="ganga",
        description="Ganga flowing through the Himalayas or at ghats",
        visual="clear river, ghats with stone steps, boats, sadhus, floating diyas",
        lighting="dawn or dusk golden hour, mist over water",
        camera="slow tracking shots along the river, aerial reveals, close-ups of diyas",
        mood="sacred, flowing, luminous",
        negatives="polluted water, plastic waste, text, watermark, low quality",
    ),
    "jyotirlinga": StylePreset(
        id="jyotirlinga",
        description="One of the twelve jyotirlingas — pillar of light",
        visual="glowing linga, rising column of divine light, ancient sanctum, marigold garlands",
        lighting="volumetric light rays, ember glow, low-key with high-contrast highlights",
        camera="hero low-angle shots, slow reveal from darkness, radial camera moves",
        mood="powerful, awe-inspiring, sacred",
        negatives="modern lighting fixtures, neon, text, watermark, low quality",
    ),
    "cosmic-shiva": StylePreset(
        id="cosmic-shiva",
        description="Shiva as the cosmic dancer Nataraja or as the universe itself",
        visual="Nataraja pose, ring of fire, third eye open, cosmic starfield, galaxies, mandala patterns",
        lighting="cosmic starlight and inner luminescence, bloom, god-rays",
        camera="dolly-zooms, cosmic camera pull-outs, orbital moves",
        mood="cosmic, transcendent, powerful",
        negatives="cartoonish, chibi, text, watermark, deformed limbs, low quality",
    ),
    "meditating-shiva": StylePreset(
        id="meditating-shiva",
        description="Shiva in deep meditation",
        visual="lotus posture, closed eyes, matted hair with crescent moon, snake around neck, ashes on forehead, calm face",
        lighting="soft ambient light, gentle glow around the head",
        camera="slow close-ups, gentle push-ins on the face",
        mood="meditative, still, serene",
        negatives="aggressive expression, weapons drawn, text, watermark, low quality",
    ),
    "krishna-vrindavan": StylePreset(
        id="krishna-vrindavan",
        description="Young Krishna in Vrindavan with the flute",
        visual="peacock feather crown, yellow dhoti, bansuri flute, cows, gopis, kadamba tree, Yamuna river",
        lighting="soft afternoon light through leaves, dappled shadows",
        camera="playful handheld, slow pans, close-ups of the flute and eyes",
        mood="joyous, playful, romantic-devotional",
        negatives="modern clothing, dark horror, text, watermark, low quality",
    ),
    "ram-darbar": StylePreset(
        id="ram-darbar",
        description="Ram, Sita, Lakshman and Hanuman in the royal court",
        visual="Ram with bow, Sita by his side, Lakshman standing guard, Hanuman kneeling in devotion, ornate throne, garlands",
        lighting="warm golden throne-room light",
        camera="reverent wide shots, slow zoom-ins on faces",
        mood="regal, dignified, devotional",
        negatives="modern uniforms, text, watermark, low quality",
    ),
    "hanuman": StylePreset(
        id="hanuman",
        description="Hanuman, the mighty devotee of Ram",
        visual="orange fur, gada mace, sindoor on face, mountain in the background, Ram-nam embroidery on chest",
        lighting="warm sunset backlight, silhouette hero shots",
        camera="low-angle hero shots, slow push-in on the eyes",
        mood="powerful, devotional, courageous",
        negatives="cartoonish, chibi, text, watermark, deformed hands, low quality",
    ),
    "temple-aarti": StylePreset(
        id="temple-aarti",
        description="Evening aarti ceremony at a temple",
        visual="rows of oil lamps, priest waving aarti thali, bells, conch, incense smoke, devotees with folded hands",
        lighting="warm lamp glow, backlit smoke, high contrast",
        camera="close-ups of flames, tracking shots of the aarti thali circling, slow orbital moves",
        mood="reverent, luminous, sacred",
        negatives="modern LED lighting, text, watermark, low quality",
    ),
    "indian-classical": StylePreset(
        id="indian-classical",
        description="Indian classical music aesthetic — court or riverside",
        visual="tanpura, tabla, harmonium, silk garments, courtyards, jharokhas, riverside pavilions",
        lighting="warm interior lighting, morning riverside light",
        camera="steady centred compositions, slow zoom-ins",
        mood="refined, contemplative, sublime",
        negatives="modern instruments, neon, text, watermark, low quality",
    ),
    "traditional-indian-painting": StylePreset(
        id="traditional-indian-painting",
        description="Rendered in a Pahari / Rajput / Tanjore painting style",
        visual="flat perspective, decorative borders, ornate patterns, deep pigments, gold-leaf halos",
        lighting="flat even lighting typical of miniature paintings",
        camera="static compositions, no camera moves; treat each scene as an illustration",
        mood="devotional, decorative, timeless",
        negatives="photorealistic, 3D render, western cartoon, text, watermark, low quality",
    ),
    "cinematic-devotional": StylePreset(
        id="cinematic-devotional",
        description="Generic cinematic devotional look with anamorphic feel",
        visual="anamorphic bokeh, cinematic composition, symbolic props, temples or nature backdrops",
        lighting="cinematic three-point lighting, warm devotional palette",
        camera="slow cinematic push-ins, gentle dolly and crane moves, film-grain feel",
        mood="devotional, epic, warm",
        negatives="webcam, low quality, deformed hands, text, watermark",
    ),
}


DEFAULT_STYLE_PRESET_ID = "cinematic-devotional"


def resolve_style_preset(style: str | None, deity: str | None) -> StylePreset:
    """Pick the best-fit preset for a (style, deity) hint pair.

    Falls back to a deity-appropriate default and finally to the generic
    ``cinematic-devotional`` preset if nothing better is known.
    """
    if style and style in VISUAL_STYLE_PRESETS:
        return VISUAL_STYLE_PRESETS[style]

    deity_l = (deity or "").lower()
    fallback_by_deity: dict[str, str] = {
        "shiva": "shiva-himalayan",
        "mahadev": "shiva-himalayan",
        "shankar": "shiva-himalayan",
        "shambhu": "shiva-himalayan",
        "krishna": "krishna-vrindavan",
        "kanha": "krishna-vrindavan",
        "ram": "ram-darbar",
        "rama": "ram-darbar",
        "hanuman": "hanuman",
        "bajrangbali": "hanuman",
    }
    for key, preset_id in fallback_by_deity.items():
        if key in deity_l:
            return VISUAL_STYLE_PRESETS[preset_id]
    return VISUAL_STYLE_PRESETS[DEFAULT_STYLE_PRESET_ID]


def build_scene_plan_prompt(
    *,
    lyrics_analysis: dict,
    audio_duration: float | None,
    preset: StylePreset,
    aspect_ratio: str,
    target_scene_count: int,
    reference_hints: list[str] | None = None,
) -> str:
    refs = ""
    if reference_hints:
        refs = "\n\nReference imagery the user has uploaded (describe the intent, do not reproduce):\n"
        refs += "\n".join(f"- {r}" for r in reference_hints)

    dur_line = (
        f"Total audio duration: {audio_duration:.2f}s. Scene start/end times MUST cover the full duration."
        if audio_duration
        else "Audio duration is unknown. Distribute scenes evenly and use plausible times."
    )

    # Compact JSON view of the analysis so the model can align scenes with sections.
    import json as _json

    analysis_json = _json.dumps(lyrics_analysis, ensure_ascii=False, indent=2)

    return f"""Plan a sequence of cinematic scenes for a devotional short video.

Style preset: **{preset.id}** — {preset.description}
Preferred visuals: {preset.visual}
Preferred lighting: {preset.lighting}
Preferred camera language: {preset.camera}
Overall mood: {preset.mood}
Standard negative prompt terms: {preset.negatives}

Aspect ratio: {aspect_ratio}
Target scene count: {target_scene_count} (may be +/- 2 for musical reasons)

{dur_line}
{refs}

Song structure and lyrics (validated LyricsAnalysis JSON):
```json
{analysis_json}
```

Instructions:
1. Produce a scene list that TELLS THE MEANING OF THE LYRICS. Do not just repeat the deity name for every scene.
   For example \"तेरी कृपा से राह मिले\" should show DIVINE GRACE / A PATH BEING SHOWN, not just another Shiva portrait.
2. Each scene must have a positive prompt suitable for an image / video diffusion model:
   - Start with the subject and action.
   - Add environment, iconography, lighting, camera language from the preset.
   - Add cinematic quality tags (\"cinematic, highly detailed, sharp focus, film-grain\").
   - Do NOT include the aspect ratio or resolution in the prompt string.
3. Each scene must have a negative_prompt built from the preset negatives plus generic hallucination guards
   (\"text, watermark, low quality, extra fingers, deformed hands\").
4. Each scene must have camera, lighting, mood, transition fields — pick evocative but concise phrases.
   Allowed transitions: crossfade, cut, dip-to-black, dip-to-white, whip-pan.
5. Times: sum of scene durations should cover the full audio_duration when known. Scenes should be
   4-12 seconds long each; do not exceed 20 seconds.
6. Cover each section of the song. Longer sections should produce multiple scenes; very short intros
   or outros can share a single scene.
7. The scene_id field must be sequential integers starting from 1.

Reply with JSON matching the schema exactly. No prose, no markdown, no code fences."""


SCENE_PLAN_JSON_SCHEMA = {
    "type": "object",
    "required": ["theme", "aspect_ratio", "style_preset", "scenes"],
    "properties": {
        "theme": {"type": "string"},
        "aspect_ratio": {"type": "string"},
        "style_preset": {"type": "string"},
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "scene_id",
                    "start",
                    "end",
                    "lyrics",
                    "prompt",
                    "negative_prompt",
                    "camera",
                    "lighting",
                    "mood",
                    "transition",
                ],
                "properties": {
                    "scene_id": {"type": "integer"},
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "lyrics": {"type": "string"},
                    "prompt": {"type": "string"},
                    "negative_prompt": {"type": "string"},
                    "camera": {"type": "string"},
                    "lighting": {"type": "string"},
                    "mood": {"type": "string"},
                    "transition": {"type": "string"},
                },
            },
        },
    },
}
