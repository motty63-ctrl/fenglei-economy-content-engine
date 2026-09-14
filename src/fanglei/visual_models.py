"""Typed renderer-agnostic beats and renderer-specific storyboard contracts."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


RendererType = Literal["program_animation", "stroke_story"]
VisualStructure = Literal[
    "single_scene", "dual_semantic_island", "causal_chain", "comparison", "numeric_animation", "process_flow"
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VisualBeat(StrictModel):
    beat_id: str
    order: int = Field(ge=1)
    cognitive_purpose: str
    narrative_role: Literal["hook", "phenomenon", "mechanism", "judgment"]
    sentence_ids: list[str] = Field(min_length=1)
    narration_summary: str
    core_visual_relationship: str
    key_objects: list[str] = Field(default_factory=list)
    emphasis_objects: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    recommended_renderer: RendererType
    estimated_duration_seconds: float = Field(gt=0)


class VisualBeatPlan(StrictModel):
    schema_version: Literal["4.0"] = "4.0"
    run_id: str
    script_id: str
    timing_basis: Literal["estimated_speech"] = "estimated_speech"
    provider: dict[str, str] | None = None
    beats: list[VisualBeat] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_order_and_coverage(self) -> "VisualBeatPlan":
        if [beat.order for beat in self.beats] != list(range(1, len(self.beats) + 1)):
            raise ValueError("beat order must be contiguous")
        sentence_ids = [sid for beat in self.beats for sid in beat.sentence_ids]
        if len(sentence_ids) != len(set(sentence_ids)):
            raise ValueError("sentence IDs must be unique across beats")
        return self


class Placement(StrictModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def stays_on_canvas(self) -> "Placement":
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("placement exceeds normalized canvas")
        return self


class StoryboardObject(StrictModel):
    object_id: str
    object_type: Literal["text", "number", "shape", "icon", "arrow", "illustration", "metaphor"]
    content: str
    factual: bool = False
    sentence_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    deterministic_render: bool = False
    placement: Placement
    appearance_order: int = Field(ge=1)
    emphasis: Literal["none", "primary", "secondary"] = "none"


class MicroAnimationStep(StrictModel):
    step_id: str
    target_object_ids: list[str] = Field(min_length=1)
    actions: list[str] = Field(min_length=1)


class RendererDirectives(StrictModel):
    primary_route: RendererType
    structure: VisualStructure
    animation_primitives: list[str] = Field(default_factory=list)
    draw_order: list[str] = Field(default_factory=list)
    semantic_regions: list[str] = Field(default_factory=list)
    deterministic_overlay_object_ids: list[str] = Field(default_factory=list)
    micro_animation_sequence: list[MicroAnimationStep] = Field(default_factory=list)


class StoryboardScene(StrictModel):
    scene_id: str
    order: int = Field(ge=1)
    beat_ids: list[str] = Field(min_length=1)
    sentence_ids: list[str] = Field(min_length=1)
    narrative_role: Literal["hook", "phenomenon", "mechanism", "judgment"]
    estimated_duration_seconds: float = Field(gt=0)
    relative_start: float = Field(ge=0, le=1)
    relative_end: float = Field(ge=0, le=1)
    layout: str
    objects: list[StoryboardObject] = Field(default_factory=list)
    persistent_objects: list[str] = Field(default_factory=list)
    inherited_objects: list[str] = Field(default_factory=list)
    introduced_objects: list[str] = Field(default_factory=list)
    removed_objects: list[str] = Field(default_factory=list)
    appearance_sequence: list[str] = Field(default_factory=list)
    transition_in: str = "hold"
    transition_out: str = "hold"
    renderer_directives: RendererDirectives

    @model_validator(mode="after")
    def relative_window_is_valid(self) -> "StoryboardScene":
        if self.relative_end <= self.relative_start:
            raise ValueError("relative timing must advance")
        return self


class StoryboardGateIssue(StrictModel):
    code: str
    message: str
    scene_id: str | None = None
    object_id: str | None = None
    severity: Literal["error", "warning"] = "error"


class StoryboardGateResult(StrictModel):
    passed: bool
    issues: list[StoryboardGateIssue] = Field(default_factory=list)
    sentence_coverage_ratio: float = Field(ge=0, le=1)
    scene_sentence_ratio: float = Field(ge=0)


class Storyboard(StrictModel):
    schema_version: Literal["4.0"] = "4.0"
    run_id: str
    script_id: str
    timing_basis: Literal["estimated_speech"] = "estimated_speech"
    total_estimated_duration_seconds: float = Field(gt=0)
    renderer_selection: dict[str, Any]
    scenes: list[StoryboardScene] = Field(min_length=1)
    quality_gate: StoryboardGateResult | None = None

    @model_validator(mode="after")
    def scene_order_is_contiguous(self) -> "Storyboard":
        if [scene.order for scene in self.scenes] != list(range(1, len(self.scenes) + 1)):
            raise ValueError("scene order must be contiguous")
        return self
