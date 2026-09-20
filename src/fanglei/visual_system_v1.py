"""Deterministic V1.0a semantic visual system contracts.

The module is deliberately downstream-only: it consumes an approved storyboard and
real timeline, and never changes content or timing authority.
"""
from __future__ import annotations

from enum import Enum
import math
from dataclasses import dataclass, field
from html import escape
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PrimitiveType(str, Enum):
    HOOK = "hook"
    COMPARISON = "comparison"
    NUMBER_TRANSFORM = "number_transform"
    PROCESS_FLOW = "process_flow"
    CONCLUSION = "conclusion"


class Rect(StrictModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class TypographyTokens(StrictModel):
    display: int = 132
    number: int = 112
    heading: int = 64
    label: int = 44
    context: int = 32
    minimum: int = 28


class ColorTokens(StrictModel):
    canvas: str = "#F7F2E8"
    ink_primary: str = "#1E1E1E"
    ink_secondary: str = "#6B665E"
    emphasis_primary: str = "#D94B3D"
    emphasis_secondary: str = "#E69A32"
    confirmation: str = "#3E8E68"
    muted: str = "#B9B2A7"
    source_badge: str = "#E8E1D5"


class ShapeTokens(StrictModel):
    stroke_thin: int = 2
    stroke_regular: int = 4
    stroke_emphasis: int = 7
    radius_small: int = 12
    radius_card: int = 24
    badge_padding_x: int = 20
    badge_padding_y: int = 10
    arrow_width: int = 4
    arrow_head_size: int = 14


class MotionTokens(StrictModel):
    fast_ms: int = 240
    standard_ms: int = 480
    emphasis_ms: int = 760
    transform_ms: int = 1100
    easing_enter: str = "power2.out"
    easing_move: str = "power2.inOut"
    easing_transform: str = "expo.inOut"
    easing_exit: str = "power1.in"


class VisualTheme(StrictModel):
    theme_id: str = "fanglei-economy-default"
    canvas_width: int = 1080
    canvas_height: int = 1920
    safe_margin_x: int = 96
    top_safe_area: Rect = Field(default_factory=lambda: Rect(x=0, y=0, width=1080, height=120))
    content_safe_area: Rect = Field(default_factory=lambda: Rect(x=96, y=120, width=888, height=1360))
    subtitle_reserved_zone: Rect = Field(default_factory=lambda: Rect(x=96, y=1480, width=888, height=260))
    bottom_safe_area: Rect = Field(default_factory=lambda: Rect(x=0, y=1740, width=1080, height=180))
    typography: TypographyTokens = Field(default_factory=TypographyTokens)
    colors: ColorTokens = Field(default_factory=ColorTokens)
    shapes: ShapeTokens = Field(default_factory=ShapeTokens)
    motion: MotionTokens = Field(default_factory=MotionTokens)


ChangeType = Literal["introduce", "focus", "transform", "confirm", "connect", "remove", "hold"]


class StateSpec(StrictModel):
    state_id: str
    relative_position: float = Field(ge=0, le=1)
    change_type: ChangeType
    target_object_ids: list[str] = Field(default_factory=list)
    primary_focal_object_ids: list[str] = Field(default_factory=list)
    meaningful_change: bool = True
    minimum_hold_ms: int = Field(default=0, ge=0)
    hold_reason: str | None = None

    @model_validator(mode="after")
    def one_primary_focal_object(self) -> "StateSpec":
        if len(self.primary_focal_object_ids) > 1:
            raise ValueError("one primary focal object is allowed per state")
        return self


class PrimitiveSpec(StrictModel):
    primitive_id: str
    type: PrimitiveType
    variant: str
    sentence_ids: list[str] = Field(min_length=1)
    claim_ids: list[str] = Field(default_factory=list)
    key_message: str
    object_ids: list[str] = Field(default_factory=list)
    state_sequence: list[StateSpec] = Field(min_length=1)
    inherited_objects: list[str] = Field(default_factory=list)
    introduced_objects: list[str] = Field(default_factory=list)
    persistent_objects: list[str] = Field(default_factory=list)
    removed_objects: list[str] = Field(default_factory=list)
    recommended_duration_ms: tuple[int, int] = (4000, 12000)

    @model_validator(mode="after")
    def states_are_monotonic(self) -> "PrimitiveSpec":
        positions = [state.relative_position for state in self.state_sequence]
        if positions != sorted(positions):
            raise ValueError("state positions must be monotonic")
        return self


class VisualIssue(StrictModel):
    code: str
    severity: Literal["warning", "error"]
    message: str
    scene_id: str | None = None
    state_id: str | None = None


class VisualBudget(StrictModel):
    maximum_active_semantic_objects: int = Field(default=6, ge=1, le=8)
    hard_maximum_active_semantic_objects: int = 8
    maximum_highlighted_objects: int = 2
    maximum_large_numbers: int = 2
    maximum_full_sentence_blocks: int = 1

    def validate_primitive(self, primitive: PrimitiveSpec) -> list[VisualIssue]:
        issues: list[VisualIssue] = []
        largest_state = max((len(state.target_object_ids) for state in primitive.state_sequence), default=0)
        if max(len(primitive.object_ids), largest_state) > self.maximum_active_semantic_objects:
            issues.append(VisualIssue(
                code="VISUAL_ACTIVE_OBJECT_BUDGET_EXCEEDED",
                severity="error",
                message="active semantic object budget exceeded",
            ))
        return issues


class VisualObject(StrictModel):
    object_id: str
    semantic_role: str
    content: str
    factual: bool = False
    sentence_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def factual_content_has_provenance(self) -> "VisualObject":
        if self.factual and (not self.sentence_ids or not self.claim_ids):
            raise ValueError("factual visual object requires provenance")
        return self


class SceneSpec(StrictModel):
    scene_id: str
    order: int = Field(ge=1)
    primitive: PrimitiveSpec
    objects: list[VisualObject] = Field(default_factory=list)

    @model_validator(mode="after")
    def object_catalog_matches_primitive(self) -> "SceneSpec":
        if self.objects and {obj.object_id for obj in self.objects} != set(self.primitive.object_ids):
            raise ValueError("scene objects must match primitive object IDs")
        return self


class StoryboardV1(StrictModel):
    schema_version: Literal["storyboard.v1"] = "storyboard.v1"
    visual_system_version: Literal["1.0a"] = "1.0a"
    run_id: str
    script_id: str
    theme: VisualTheme = Field(default_factory=VisualTheme)
    budget: VisualBudget = Field(default_factory=VisualBudget)
    scenes: list[SceneSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def scene_order_is_contiguous(self) -> "StoryboardV1":
        if [scene.order for scene in self.scenes] != list(range(1, len(self.scenes) + 1)):
            raise ValueError("scene order must be contiguous")
        return self


class PrimitiveRenderer(Protocol):
    primitive_type: PrimitiveType

    def validate(self, primitive: PrimitiveSpec) -> list[VisualIssue]: ...

    def render(self, scene: SceneSpec, theme: VisualTheme) -> str: ...


@dataclass(frozen=True)
class SemanticPrimitiveRenderer:
    primitive_type: PrimitiveType
    minimum_objects: int

    def validate(self, primitive: PrimitiveSpec) -> list[VisualIssue]:
        issues: list[VisualIssue] = []
        if len(primitive.object_ids) < self.minimum_objects:
            issues.append(VisualIssue(
                code=f"{self.primitive_type.value.upper()}_REQUIRES_TWO_OBJECTS"
                if self.minimum_objects == 2 else f"{self.primitive_type.value.upper()}_INPUT_INVALID",
                severity="error",
                message=f"{self.primitive_type.value} requires at least {self.minimum_objects} objects",
            ))
        if primitive.type is not self.primitive_type:
            issues.append(VisualIssue(
                code="VISUAL_PRIMITIVE_TYPE_MISMATCH", severity="error",
                message="primitive renderer type mismatch",
            ))
        return issues

    def render(self, scene: SceneSpec, theme: VisualTheme) -> str:
        raise NotImplementedError

    def _attrs(self, scene: SceneSpec) -> str:
        focal = next((state.primary_focal_object_ids[0]
                      for state in scene.primitive.state_sequence
                      if state.primary_focal_object_ids), "")
        return (
            f'data-primitive="{self.primitive_type.value}" '
            f'data-primary-focal="{escape(focal, quote=True)}"'
        )

    @staticmethod
    def _object(obj: VisualObject, class_name: str) -> str:
        return (
            f'<div id="{escape(obj.object_id, quote=True)}" class="{class_name}" '
            'data-semantic-object="true" '
            f'data-object-id="{escape(obj.object_id, quote=True)}" '
            f'data-semantic-role="{escape(obj.semantic_role, quote=True)}">'
            f'{escape(obj.content)}</div>'
        )


class HookRenderer(SemanticPrimitiveRenderer):
    def __init__(self) -> None:
        super().__init__(PrimitiveType.HOOK, 2)

    def render(self, scene: SceneSpec, theme: VisualTheme) -> str:
        items = "".join(self._object(obj, "hook-object") for obj in scene.objects)
        return f'<section class="hook-stage" {self._attrs(scene)}>{items}</section>'


class ComparisonRenderer(SemanticPrimitiveRenderer):
    def __init__(self) -> None:
        super().__init__(PrimitiveType.COMPARISON, 2)

    def render(self, scene: SceneSpec, theme: VisualTheme) -> str:
        items = "".join(self._object(obj, "comparison-item") for obj in scene.objects)
        return f'<section class="comparison-grid" {self._attrs(scene)}>{items}</section>'


class NumberTransformRenderer(SemanticPrimitiveRenderer):
    def __init__(self) -> None:
        super().__init__(PrimitiveType.NUMBER_TRANSFORM, 2)

    def render(self, scene: SceneSpec, theme: VisualTheme) -> str:
        items = "".join(self._object(obj, "transform-item") for obj in scene.objects)
        return f'<section class="number-transform" {self._attrs(scene)}>{items}</section>'


class ProcessFlowRenderer(SemanticPrimitiveRenderer):
    def __init__(self) -> None:
        super().__init__(PrimitiveType.PROCESS_FLOW, 3)

    def render(self, scene: SceneSpec, theme: VisualTheme) -> str:
        items = "".join(self._object(obj, "process-node") for obj in scene.objects)
        return f'<section class="process-flow" {self._attrs(scene)}>{items}</section>'


class ConclusionRenderer(SemanticPrimitiveRenderer):
    def __init__(self) -> None:
        super().__init__(PrimitiveType.CONCLUSION, 1)

    def render(self, scene: SceneSpec, theme: VisualTheme) -> str:
        items = "".join(self._object(obj, "conclusion-object") for obj in scene.objects)
        return (
            f'<section class="conclusion-lockup" data-final-state="complete" '
            f'{self._attrs(scene)}>{items}</section>'
        )


class PrimitiveRegistry:
    def __init__(self) -> None:
        self._renderers: dict[PrimitiveType, PrimitiveRenderer] = {}

    def register(self, renderer: PrimitiveRenderer) -> None:
        if renderer.primitive_type in self._renderers:
            raise ValueError("VISUAL_PRIMITIVE_ALREADY_REGISTERED")
        self._renderers[renderer.primitive_type] = renderer

    def resolve(self, primitive_type: PrimitiveType) -> PrimitiveRenderer:
        renderer = self._renderers.get(primitive_type)
        if renderer is None:
            raise ValueError("VISUAL_PRIMITIVE_UNREGISTERED:" + primitive_type.value)
        return renderer


def build_default_registry() -> PrimitiveRegistry:
    registry = PrimitiveRegistry()
    registry.register(HookRenderer())
    registry.register(ComparisonRenderer())
    registry.register(NumberTransformRenderer())
    registry.register(ProcessFlowRenderer())
    registry.register(ConclusionRenderer())
    return registry


class SharedObject(StrictModel):
    object_id: str
    semantic_role: str
    sentence_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)


@dataclass
class SharedObjectRecord:
    object: SharedObject
    introduced_in: str
    inherited_in: list[str] = field(default_factory=list)
    removed_in: str | None = None


class SharedObjectRegistry:
    def __init__(self) -> None:
        self._objects: dict[str, SharedObjectRecord] = {}

    def introduce(self, obj: SharedObject, *, scene_id: str) -> None:
        if obj.object_id in self._objects:
            raise ValueError("SHARED_OBJECT_ALREADY_EXISTS:" + obj.object_id)
        self._objects[obj.object_id] = SharedObjectRecord(object=obj, introduced_in=scene_id)

    def inherit(self, obj: SharedObject, *, scene_id: str) -> None:
        record = self._objects.get(obj.object_id)
        if record is None:
            raise ValueError("SHARED_OBJECT_NOT_INTRODUCED:" + obj.object_id)
        if record.removed_in is not None:
            raise ValueError("SHARED_OBJECT_REMOVED:" + obj.object_id)
        if record.object.semantic_role != obj.semantic_role:
            raise ValueError("SHARED_OBJECT_SEMANTIC_CONFLICT:" + obj.object_id)
        if record.object.sentence_ids != obj.sentence_ids or record.object.claim_ids != obj.claim_ids:
            raise ValueError("SHARED_OBJECT_PROVENANCE_CONFLICT:" + obj.object_id)
        record.inherited_in.append(scene_id)

    def remove(self, object_id: str, *, scene_id: str) -> None:
        record = self._objects.get(object_id)
        if record is None:
            raise ValueError("SHARED_OBJECT_NOT_INTRODUCED:" + object_id)
        record.removed_in = scene_id


class CompiledState(StrictModel):
    state_id: str
    at_ms: int
    at_frame: int
    change_type: ChangeType
    target_object_ids: list[str]
    primary_focal_object_id: str | None = None
    meaningful_change: bool
    hold_reason: str | None = None


class CompiledScene(StrictModel):
    scene_id: str
    primitive_type: PrimitiveType
    start_ms: int
    end_ms: int
    start_frame: int
    end_frame_exclusive: int
    states: list[CompiledState]


class CompiledGap(StrictModel):
    after_sentence_id: str | None = None
    start_ms: int
    end_ms: int
    duration_ms: int | None = None
    visual_policy: Literal["hold_previous_canvas"]


class VisualProgram(StrictModel):
    schema_version: Literal["visual-program.v1.0a"] = "visual-program.v1.0a"
    run_id: str
    fps: int = 30
    duration_ms: int
    frame_count: int
    timing_source: Literal["timeline.json"] = "timeline.json"
    theme: VisualTheme
    scenes: list[CompiledScene]
    gaps: list[CompiledGap] = Field(default_factory=list)
    density_issues: list[VisualIssue] = Field(default_factory=list)


def _frame_at_or_after(timestamp_ms: int, fps: int = 30) -> int:
    return math.ceil(timestamp_ms * fps / 1000)


ALLOWED_HOLD_REASONS = {
    "reading_need", "narration_explains_current_focus", "numeric_comprehension",
    "final_resolution_hold", "natural_audio_gap",
}


def validate_animation_density(*, scene_id: str, scene_start_ms: int, scene_end_ms: int,
                               states: list[StateSpec]) -> list[VisualIssue]:
    issues: list[VisualIssue] = []
    points = [scene_start_ms + round((scene_end_ms - scene_start_ms) * state.relative_position)
              for state in states]
    points.append(scene_end_ms)
    for index, start_ms in enumerate(points[:-1]):
        duration_ms = points[index + 1] - start_ms
        if duration_ms <= 3000:
            continue
        current = states[index]
        next_state = states[index + 1] if index + 1 < len(states) else None
        reason = current.hold_reason or (next_state.hold_reason if next_state else None)
        severity: Literal["warning", "error"] = (
            "warning" if reason in ALLOWED_HOLD_REASONS else "error"
        )
        issues.append(VisualIssue(
            code="VISUAL_STATIC_DURATION_EXCEEDED",
            severity=severity,
            message=f"semantic state is unchanged for {duration_ms} ms"
                    + (f" ({reason})" if reason else ""),
            scene_id=scene_id,
            state_id=current.state_id,
        ))
    return issues


class VisualProgramCompiler:
    def __init__(self, registry: PrimitiveRegistry, *, fps: int = 30) -> None:
        self.registry = registry
        self.fps = fps

    def compile(self, storyboard: StoryboardV1, timeline: dict) -> VisualProgram:
        duration_ms = int(timeline["audio"]["duration_ms"])
        frame_count = _frame_at_or_after(duration_ms, self.fps)
        timings = {row["scene_id"]: row for row in timeline.get("scenes", [])}
        scenes: list[CompiledScene] = []
        density_issues: list[VisualIssue] = []
        shared_objects = SharedObjectRegistry()
        for scene_index, scene in enumerate(storyboard.scenes):
            timing = timings.get(scene.scene_id)
            if timing is None:
                raise ValueError("VISUAL_TIMELINE_SCENE_MISSING:" + scene.scene_id)
            renderer = self.registry.resolve(scene.primitive.type)
            issues = renderer.validate(scene.primitive) + storyboard.budget.validate_primitive(scene.primitive)
            errors = [issue for issue in issues if issue.severity == "error"]
            if errors:
                raise ValueError(errors[0].code)
            if scene.primitive.inherited_objects or scene.primitive.introduced_objects:
                declared = set(scene.primitive.inherited_objects + scene.primitive.introduced_objects)
                if declared != set(scene.primitive.object_ids):
                    raise ValueError("VISUAL_OBJECT_LIFECYCLE_INCOMPLETE:" + scene.scene_id)
                for obj in scene.objects:
                    shared = SharedObject(
                        object_id=obj.object_id, semantic_role=obj.semantic_role,
                        sentence_ids=obj.sentence_ids, claim_ids=obj.claim_ids,
                    )
                    if obj.object_id in scene.primitive.inherited_objects:
                        shared_objects.inherit(shared, scene_id=scene.scene_id)
                    else:
                        shared_objects.introduce(shared, scene_id=scene.scene_id)
            start_ms, end_ms = int(timing["start_ms"]), int(timing["end_ms"])
            states = [CompiledState(
                state_id=state.state_id,
                at_ms=start_ms + round((end_ms - start_ms) * state.relative_position),
                at_frame=_frame_at_or_after(
                    start_ms + round((end_ms - start_ms) * state.relative_position), self.fps
                ),
                change_type=state.change_type,
                target_object_ids=state.target_object_ids,
                primary_focal_object_id=(state.primary_focal_object_ids or [None])[0],
                meaningful_change=state.meaningful_change,
                hold_reason=state.hold_reason,
            ) for state in scene.primitive.state_sequence]
            density_issues.extend(validate_animation_density(
                scene_id=scene.scene_id, scene_start_ms=start_ms, scene_end_ms=end_ms,
                states=scene.primitive.state_sequence,
            ))
            scenes.append(CompiledScene(
                scene_id=scene.scene_id, primitive_type=scene.primitive.type,
                start_ms=start_ms, end_ms=end_ms,
                start_frame=_frame_at_or_after(start_ms, self.fps),
                end_frame_exclusive=(
                    frame_count if scene_index == len(storyboard.scenes) - 1
                    else _frame_at_or_after(end_ms, self.fps)
                ),
                states=states,
            ))
            for object_id in scene.primitive.removed_objects:
                shared_objects.remove(object_id, scene_id=scene.scene_id)
        return VisualProgram(
            run_id=storyboard.run_id, duration_ms=duration_ms,
            frame_count=frame_count, theme=storyboard.theme,
            scenes=scenes,
            gaps=[CompiledGap.model_validate(row) for row in timeline.get("gaps", [])],
            density_issues=density_issues,
        )
