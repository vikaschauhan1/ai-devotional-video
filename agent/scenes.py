"""Scene-planning agent.

Takes a validated ``LyricsAnalysis`` (dict), a resolved ``StylePreset``,
and an optional audio duration; asks the configured LLM engine for a
list of scenes; validates the result against ``ScenePlan``.

Nothing here writes to disk or touches the database — that belongs to
``backend/app/services/scenes.py``.
"""

from __future__ import annotations

import logging

from pydantic import ValidationError

from agent.prompts import (
    SCENE_PLAN_JSON_SCHEMA,
    SCENE_PLAN_SYSTEM,
    StylePreset,
    build_scene_plan_prompt,
)
from backend.app.schemas.scenes import ScenePlan
from models.llm.base import LLMEngine

log = logging.getLogger(__name__)


class ScenePlanningError(RuntimeError):
    pass


async def plan_scenes(
    *,
    engine: LLMEngine,
    lyrics_analysis: dict,
    audio_duration: float | None,
    preset: StylePreset,
    aspect_ratio: str,
    target_scene_count: int = 6,
    reference_hints: list[str] | None = None,
) -> ScenePlan:
    prompt = build_scene_plan_prompt(
        lyrics_analysis=lyrics_analysis,
        audio_duration=audio_duration,
        preset=preset,
        aspect_ratio=aspect_ratio,
        target_scene_count=target_scene_count,
        reference_hints=reference_hints,
    )
    log.info(
        "planning scenes preset=%s target=%d aspect=%s duration=%s engine=%s",
        preset.id,
        target_scene_count,
        aspect_ratio,
        f"{audio_duration:.2f}" if audio_duration else "unknown",
        engine.name,
    )
    raw = await engine.generate_json(
        prompt,
        schema=SCENE_PLAN_JSON_SCHEMA,
        system=SCENE_PLAN_SYSTEM,
    )
    try:
        return ScenePlan.model_validate(raw)
    except ValidationError as exc:
        log.warning("LLM produced scene plan that failed schema validation: %s", exc)
        raise ScenePlanningError(f"LLM returned schema-invalid plan: {exc}") from exc
