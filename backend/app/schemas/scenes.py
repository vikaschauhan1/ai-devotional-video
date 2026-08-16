"""Scene-plan schemas (Phase 10).

Pydantic-validated form of the JSON the scene-planner LLM produces.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TransitionType(StrEnum):
    CROSSFADE = "crossfade"
    CUT = "cut"
    DIP_TO_BLACK = "dip-to-black"
    DIP_TO_WHITE = "dip-to-white"
    WHIP_PAN = "whip-pan"


class SceneOut(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    scene_id: int = Field(ge=1)
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    lyrics: str = ""
    prompt: str = Field(min_length=1)
    negative_prompt: str = ""
    camera: str = ""
    lighting: str = ""
    mood: str = ""
    transition: TransitionType = TransitionType.CROSSFADE

    @field_validator("end")
    @classmethod
    def end_after_start(cls, v: float, info) -> float:
        start = info.data.get("start", 0.0)
        if v < start:
            raise ValueError("end must be >= start")
        return v


class ScenePlan(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    theme: str = Field(min_length=1)
    aspect_ratio: str = Field(min_length=1)
    style_preset: str = Field(min_length=1)
    scenes: list[SceneOut] = Field(min_length=1)

    @field_validator("scenes")
    @classmethod
    def sequential_scene_ids(cls, v: list[SceneOut]) -> list[SceneOut]:
        expected = list(range(1, len(v) + 1))
        actual = [s.scene_id for s in v]
        if actual != expected:
            raise ValueError(
                f"scene_id must be sequential from 1: expected {expected}, got {actual}"
            )
        return v


class PlanScenesRequest(BaseModel):
    """Optional overrides for the /plan-scenes endpoint."""

    style_preset: str | None = Field(default=None, max_length=64)
    target_scene_count: int = Field(default=6, ge=2, le=20)
    reference_hints: list[str] | None = None


class PlanScenesResponse(BaseModel):
    project_id: str
    engine: str
    model: str
    plan: ScenePlan
    plan_asset_id: str
    plan_path: str
    scene_count: int
