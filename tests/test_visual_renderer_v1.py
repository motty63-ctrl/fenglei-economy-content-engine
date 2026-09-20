from __future__ import annotations

import pytest
from pydantic import ValidationError

from fanglei.visual_system_v1 import (
    PrimitiveSpec,
    PrimitiveType,
    SceneSpec,
    StateSpec,
    VisualObject,
    VisualTheme,
    build_default_registry,
)


def _object(object_id: str, content: str, role: str = "label", *, factual: bool = False) -> VisualObject:
    return VisualObject(
        object_id=object_id,
        semantic_role=role,
        content=content,
        factual=factual,
        sentence_ids=["sentence_001"] if factual else [],
        claim_ids=["claim_001"] if factual else [],
    )


def _scene(primitive_type: PrimitiveType) -> SceneSpec:
    if primitive_type is PrimitiveType.PROCESS_FLOW:
        objects = [_object(f"step_{index}", name, "process_step") for index, name in enumerate(
            ["来源", "指标", "年份", "精度"], start=1
        )]
    elif primitive_type is PrimitiveType.CONCLUSION:
        objects = [_object("conclusion", "同一数字，不同精度", "conclusion")]
    else:
        objects = [
            _object("value_a", "2.8%", "numeric_value", factual=True),
            _object("value_b", "2.7932%", "numeric_value", factual=True),
        ]
    states = [
        StateSpec(
            state_id=f"state_{index:03d}", relative_position=(index - 1) / len(objects),
            change_type="introduce" if index == 1 else "focus",
            target_object_ids=[obj.object_id], primary_focal_object_ids=[obj.object_id],
        )
        for index, obj in enumerate(objects, start=1)
    ]
    primitive = PrimitiveSpec(
        primitive_id=f"primitive_{primitive_type.value}", type=primitive_type,
        variant="calibration", sentence_ids=["sentence_001"], key_message="校准",
        object_ids=[obj.object_id for obj in objects], state_sequence=states,
    )
    return SceneSpec(scene_id="scene_001", order=1, primitive=primitive, objects=objects)


def test_factual_visual_object_requires_sentence_and_claim_provenance() -> None:
    with pytest.raises(ValidationError, match="factual visual object requires provenance"):
        VisualObject(
            object_id="value", semantic_role="numeric_value", content="2.8%", factual=True,
        )


@pytest.mark.parametrize(
    ("primitive_type", "marker"),
    [
        (PrimitiveType.HOOK, 'class="hook-stage"'),
        (PrimitiveType.COMPARISON, 'class="comparison-grid"'),
        (PrimitiveType.NUMBER_TRANSFORM, 'class="number-transform"'),
        (PrimitiveType.PROCESS_FLOW, 'class="process-flow"'),
        (PrimitiveType.CONCLUSION, 'class="conclusion-lockup"'),
    ],
)
def test_each_primitive_renders_distinct_semantic_component(
    primitive_type: PrimitiveType, marker: str,
) -> None:
    scene = _scene(primitive_type)
    renderer = build_default_registry().resolve(primitive_type)

    markup = renderer.render(scene, VisualTheme())

    assert marker in markup
    assert f'data-primitive="{primitive_type.value}"' in markup
    assert 'data-primary-focal="' in markup
    assert 'subtitle-reserved' not in markup


def test_process_flow_renders_ordered_four_node_sequence() -> None:
    markup = build_default_registry().resolve(PrimitiveType.PROCESS_FLOW).render(
        _scene(PrimitiveType.PROCESS_FLOW), VisualTheme()
    )

    assert markup.count('class="process-node"') == 4
    assert markup.index("来源") < markup.index("指标") < markup.index("年份") < markup.index("精度")


def test_conclusion_has_non_blank_final_lockup() -> None:
    markup = build_default_registry().resolve(PrimitiveType.CONCLUSION).render(
        _scene(PrimitiveType.CONCLUSION), VisualTheme()
    )

    assert "同一数字，不同精度" in markup
    assert 'data-final-state="complete"' in markup
