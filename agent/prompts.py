"""Prompt templates for the AI agent.

Prompts live in one place so we can iterate on them without touching
call sites. All prompts must yield JSON that validates against the
Pydantic schemas in ``backend/app/schemas/lyrics.py``.
"""

from __future__ import annotations

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
