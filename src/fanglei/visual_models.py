"""Typed renderer-agnostic beats and renderer-specific storyboard contracts."""
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


RendererType = Literal["program_animation", "stroke_story"]
VisualStructure = Literal[
    "single_scene", "dual_semantic_island", "causal_chain", "comparison", "numeric_animation", "process_flow"
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VisualComparison(StrictModel):
    label: str = Field(min_length=1)
    before_value: str = Field(min_length=1)
    after_value: str = Field(min_length=1)
    change: str | None = None


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
    comparison: VisualComparison | None = None
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


class TimedNarrationSegment(StrictModel):
    sentence_id: str = Field(min_length=1)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    display_text: str = Field(min_length=1)
    subtitle_cue_id: str = Field(min_length=1)
    claim_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def timing_advances(self) -> "TimedNarrationSegment":
        if self.end_ms <= self.start_ms:
            raise ValueError("timed narration segment must advance")
        if len(self.claim_ids) != len(set(self.claim_ids)):
            raise ValueError("timed narration claim IDs must be unique")
        return self


class TimedSubtitleCue(StrictModel):
    cue_id: str = Field(min_length=1)
    sentence_id: str = Field(min_length=1)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    display_text: str = Field(min_length=1)

    @model_validator(mode="after")
    def timing_advances(self) -> "TimedSubtitleCue":
        if self.end_ms <= self.start_ms:
            raise ValueError("timed subtitle cue must advance")
        return self


class EligibleVisualClaim(StrictModel):
    claim_id: str = Field(min_length=1)
    claim_text: str = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)
    verification_basis: Literal[
        "independent_corroboration", "authoritative_primary_attestation"
    ]
    attribution: str | None = None
    scope: dict[str, Any] | None = None


class TimingAwareVisualContext(StrictModel):
    schema_version: Literal["timing-aware-visual-context/1.0"] = "timing-aware-visual-context/1.0"
    run_id: str = Field(min_length=1)
    selected_angle_id: str = Field(min_length=1)
    selected_angle_title: str = Field(min_length=1)
    selected_angle_hook: str = Field(min_length=1)
    selected_angle_core_question: str = Field(min_length=1)
    selected_angle_core_insight: str = Field(min_length=1)
    angle_selection_sha256: str = Field(min_length=64, max_length=64)
    script_id: str = Field(min_length=1)
    script_sha256: str = Field(min_length=64, max_length=64)
    target_language: str = Field(min_length=2)
    audio_sha256: str = Field(min_length=64, max_length=64)
    audio_duration_ms: int = Field(gt=0)
    voice_review_sha256: str = Field(min_length=64, max_length=64)
    alignment_sha256: str = Field(min_length=64, max_length=64)
    alignment_method: str = Field(min_length=1)
    timing_quality: Literal["measured", "estimated"]
    subtitle_sha256: str = Field(min_length=64, max_length=64)
    allowed_claim_ids: list[str]
    eligible_claims: list[EligibleVisualClaim]
    segments: list[TimedNarrationSegment] = Field(min_length=1)
    subtitle_cues: list[TimedSubtitleCue] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_bound_segments(self) -> "TimingAwareVisualContext":
        hashes = (
            self.angle_selection_sha256, self.script_sha256, self.audio_sha256,
            self.voice_review_sha256, self.alignment_sha256, self.subtitle_sha256,
        )
        if any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes):
            raise ValueError("timing-aware context hashes must be lowercase SHA-256")
        sentence_ids = [row.sentence_id for row in self.segments]
        cue_sentence_ids = [row.sentence_id for row in self.subtitle_cues]
        if len(sentence_ids) != len(set(sentence_ids)) or cue_sentence_ids != sentence_ids:
            raise ValueError("timing-aware narration/subtitle IDs must match exactly")
        cue_ids = [row.cue_id for row in self.subtitle_cues]
        if len(cue_ids) != len(set(cue_ids)):
            raise ValueError("timing-aware subtitle cue IDs must be unique")
        allowed = set(self.allowed_claim_ids)
        claim_ids = [claim.claim_id for claim in self.eligible_claims]
        if len(allowed) != len(self.allowed_claim_ids) or set(claim_ids) != allowed:
            raise ValueError("timing-aware claim context must exactly match its allowlist")
        previous_end = -1
        for segment, cue in zip(self.segments, self.subtitle_cues, strict=True):
            if segment.start_ms < previous_end or segment.end_ms > self.audio_duration_ms:
                raise ValueError("timing-aware segment timing is overlapping or out of bounds")
            if (segment.subtitle_cue_id != cue.cue_id or segment.display_text != cue.display_text
                    or segment.start_ms != cue.start_ms or segment.end_ms != cue.end_ms):
                raise ValueError("timing-aware subtitle cue does not match its canonical segment")
            if not set(segment.claim_ids).issubset(allowed):
                raise ValueError("timing-aware segment references a non-eligible claim")
            previous_end = segment.end_ms
        return self


class StoryboardTimingProvenance(StrictModel):
    audio_sha256: str = Field(min_length=64, max_length=64)
    audio_duration_ms: int = Field(gt=0)
    voice_review_sha256: str = Field(min_length=64, max_length=64)
    alignment_sha256: str = Field(min_length=64, max_length=64)
    alignment_method: str = Field(min_length=1)
    subtitle_sha256: str = Field(min_length=64, max_length=64)
    scene_range_source: Literal["alignment-derived"] = "alignment-derived"
    timing_quality: Literal["measured", "estimated"]
    final_render_approval_inferred: Literal[False] = False


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
    start_ms: int | None = Field(default=None, ge=0, exclude_if=lambda value: value is None)
    end_ms: int | None = Field(default=None, gt=0, exclude_if=lambda value: value is None)
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
        if (self.start_ms is None) != (self.end_ms is None):
            raise ValueError("scene alignment timing requires both start_ms and end_ms")
        if self.start_ms is not None and self.end_ms is not None and self.end_ms <= self.start_ms:
            raise ValueError("scene alignment timing must advance")
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
    schema_version: Literal["4.0", "5.0"] = "4.0"
    run_id: str
    script_id: str
    timing_basis: Literal["estimated_speech", "alignment_derived"] = "estimated_speech"
    total_estimated_duration_seconds: float = Field(gt=0)
    renderer_selection: dict[str, Any]
    scenes: list[StoryboardScene] = Field(min_length=1)
    timing_provenance: StoryboardTimingProvenance | None = Field(
        default=None, exclude_if=lambda value: value is None,
    )
    quality_gate: StoryboardGateResult | None = None

    @model_validator(mode="after")
    def scene_order_is_contiguous(self) -> "Storyboard":
        if [scene.order for scene in self.scenes] != list(range(1, len(self.scenes) + 1)):
            raise ValueError("scene order must be contiguous")
        if self.timing_basis == "alignment_derived":
            if self.schema_version != "5.0" or self.timing_provenance is None or any(
                scene.start_ms is None or scene.end_ms is None for scene in self.scenes
            ):
                raise ValueError("alignment-derived storyboard requires timing provenance and scene ranges")
        elif self.schema_version != "4.0" or self.timing_provenance is not None or any(
            scene.start_ms is not None or scene.end_ms is not None for scene in self.scenes
        ):
            raise ValueError("legacy estimated-speech storyboard cannot carry alignment-derived ranges")
        return self
