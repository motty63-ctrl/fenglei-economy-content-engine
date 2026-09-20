from __future__ import annotations

import pytest
from pydantic import ValidationError

from fanglei.visual_system_v1 import (
    PrimitiveRegistry,
    PrimitiveSpec,
    PrimitiveType,
    SceneSpec,
    SharedObject,
    SharedObjectRegistry,
    StateSpec,
    VisualBudget,
    VisualProgramCompiler,
    StoryboardV1,
    VisualTheme,
    build_default_registry,
    validate_animation_density,
)


def test_default_theme_reserves_portrait_subtitle_zone() -> None:
    theme = VisualTheme()

    assert theme.canvas_width == 1080
    assert theme.canvas_height == 1920
    assert theme.subtitle_reserved_zone.y == 1480
    assert theme.subtitle_reserved_zone.height == 260
    assert theme.typography.minimum == 28


def test_budget_rejects_multiple_primary_focal_objects() -> None:
    with pytest.raises(ValidationError, match="one primary focal object"):
        StateSpec(
            state_id="state_001",
            relative_position=0.0,
            change_type="introduce",
            target_object_ids=["a", "b"],
            primary_focal_object_ids=["a", "b"],
        )


def test_budget_rejects_too_many_active_semantic_objects() -> None:
    budget = VisualBudget(maximum_active_semantic_objects=6)
    primitive = PrimitiveSpec(
        primitive_id="primitive_001",
        type=PrimitiveType.HOOK,
        variant="numeric_contrast",
        sentence_ids=["sentence_001"],
        key_message="数字反差",
        object_ids=[f"object_{index}" for index in range(7)],
        state_sequence=[
            StateSpec(
                state_id="state_001",
                relative_position=0.0,
                change_type="introduce",
                target_object_ids=[f"object_{index}" for index in range(7)],
                primary_focal_object_ids=["object_0"],
            )
        ],
    )

    issues = budget.validate_primitive(primitive)

    assert [issue.code for issue in issues] == ["VISUAL_ACTIVE_OBJECT_BUDGET_EXCEEDED"]


def test_primitive_state_positions_must_be_monotonic() -> None:
    with pytest.raises(ValidationError, match="state positions must be monotonic"):
        PrimitiveSpec(
            primitive_id="primitive_001",
            type=PrimitiveType.HOOK,
            variant="numeric_contrast",
            sentence_ids=["sentence_001"],
            key_message="数字反差",
            object_ids=["a"],
            state_sequence=[
                StateSpec(
                    state_id="state_001",
                    relative_position=0.8,
                    change_type="focus",
                    target_object_ids=["a"],
                    primary_focal_object_ids=["a"],
                ),
                StateSpec(
                    state_id="state_002",
                    relative_position=0.2,
                    change_type="confirm",
                    target_object_ids=["a"],
                    primary_focal_object_ids=["a"],
                ),
            ],
        )


def _primitive(primitive_type: PrimitiveType, *, objects: list[str] | None = None,
               states: list[StateSpec] | None = None) -> PrimitiveSpec:
    return PrimitiveSpec(
        primitive_id=f"primitive_{primitive_type.value}",
        type=primitive_type,
        variant="calibration",
        sentence_ids=["sentence_001"],
        key_message="校准信息",
        object_ids=objects or ["object_a", "object_b"],
        state_sequence=states or [
            StateSpec(
                state_id="state_001",
                relative_position=0.0,
                change_type="introduce",
                target_object_ids=["object_a"],
                primary_focal_object_ids=["object_a"],
            ),
            StateSpec(
                state_id="state_002",
                relative_position=0.5,
                change_type="focus",
                target_object_ids=["object_b"],
                primary_focal_object_ids=["object_b"],
            ),
        ],
    )


@pytest.mark.parametrize("primitive_type", list(PrimitiveType))
def test_default_registry_supports_all_five_primitives(primitive_type: PrimitiveType) -> None:
    registry = build_default_registry()

    renderer = registry.resolve(primitive_type)

    assert renderer.primitive_type is primitive_type


def test_registry_fails_closed_for_unregistered_primitive() -> None:
    registry = PrimitiveRegistry()

    with pytest.raises(ValueError, match="VISUAL_PRIMITIVE_UNREGISTERED"):
        registry.resolve(PrimitiveType.HOOK)


def test_comparison_requires_two_semantic_objects() -> None:
    primitive = _primitive(PrimitiveType.COMPARISON, objects=["only_one"])

    issues = build_default_registry().resolve(PrimitiveType.COMPARISON).validate(primitive)

    assert "COMPARISON_REQUIRES_TWO_OBJECTS" in [issue.code for issue in issues]


def test_shared_object_registry_rejects_semantic_role_change() -> None:
    registry = SharedObjectRegistry()
    registry.introduce(SharedObject(
        object_id="bea_value", semantic_role="numeric_value",
        sentence_ids=["sentence_002"], claim_ids=["claim_007"],
    ), scene_id="scene_002")

    with pytest.raises(ValueError, match="SHARED_OBJECT_SEMANTIC_CONFLICT"):
        registry.inherit(SharedObject(
            object_id="bea_value", semantic_role="source_badge",
            sentence_ids=["sentence_002"], claim_ids=["claim_007"],
        ), scene_id="scene_003")


def test_removed_shared_object_cannot_be_implicitly_restored() -> None:
    registry = SharedObjectRegistry()
    obj = SharedObject(object_id="badge", semantic_role="source_badge")
    registry.introduce(obj, scene_id="scene_001")
    registry.remove("badge", scene_id="scene_002")

    with pytest.raises(ValueError, match="SHARED_OBJECT_REMOVED"):
        registry.inherit(obj, scene_id="scene_003")


def test_compiler_uses_real_timeline_and_preserves_gaps() -> None:
    storyboard = StoryboardV1(
        run_id="gdp-run",
        script_id="script-gdp",
        scenes=[
            SceneSpec(scene_id="scene_001", order=1, primitive=_primitive(PrimitiveType.HOOK)),
            SceneSpec(scene_id="scene_002", order=2, primitive=_primitive(PrimitiveType.COMPARISON)),
        ],
    )
    timeline = {
        "audio": {"duration_ms": 60611, "sha256": "audio-sha"},
        "scenes": [
            {"scene_id": "scene_001", "start_ms": 500, "end_ms": 3521},
            {"scene_id": "scene_002", "start_ms": 4021, "end_ms": 14943},
        ],
        "gaps": [{
            "after_sentence_id": "sentence_001",
            "start_ms": 3521,
            "end_ms": 4021,
            "duration_ms": 500,
            "visual_policy": "hold_previous_canvas",
        }],
    }

    program = VisualProgramCompiler(build_default_registry()).compile(storyboard, timeline)

    assert program.duration_ms == 60611
    assert program.frame_count == 1819
    assert program.scenes[0].start_frame == 15
    assert program.scenes[0].end_frame_exclusive == 106
    assert program.gaps[0].visual_policy == "hold_previous_canvas"
    assert program.scenes[1].states[1].at_ms == 9482


def test_density_over_three_seconds_with_valid_hold_is_warning() -> None:
    issues = validate_animation_density(
        scene_id="scene_001",
        scene_start_ms=0,
        scene_end_ms=7000,
        states=[
            StateSpec(
                state_id="state_001", relative_position=0.0, change_type="introduce",
                target_object_ids=["a"], primary_focal_object_ids=["a"],
            ),
            StateSpec(
                state_id="state_002", relative_position=0.6, change_type="hold",
                target_object_ids=["a"], primary_focal_object_ids=["a"],
                meaningful_change=False, hold_reason="narration_explains_current_focus",
            ),
        ],
    )

    assert issues[0].code == "VISUAL_STATIC_DURATION_EXCEEDED"
    assert issues[0].severity == "warning"


def test_density_over_three_seconds_without_reason_is_error() -> None:
    issues = validate_animation_density(
        scene_id="scene_001", scene_start_ms=0, scene_end_ms=7000,
        states=[StateSpec(
            state_id="state_001", relative_position=0.0, change_type="introduce",
            target_object_ids=["a"], primary_focal_object_ids=["a"],
        )],
    )

    assert issues[0].severity == "error"
