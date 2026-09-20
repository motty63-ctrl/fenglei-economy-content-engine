from __future__ import annotations

from fanglei.gdp_calibration_v1 import build_gdp_calibration_storyboard
from fanglei.visual_system_v1 import PrimitiveType, VisualProgramCompiler, build_default_registry


def _legacy_object(object_id: str, content: str, sentence_id: str, *, factual: bool) -> dict:
    return {
        "object_id": object_id,
        "content": content,
        "factual": factual,
        "sentence_ids": [sentence_id],
        "claim_ids": ["claim_007"] if factual else [],
    }


def _legacy_storyboard() -> dict:
    factual = [
        _legacy_object("year_2024", "2024年", "sentence_002", factual=True),
        _legacy_object("gdp_indicator", "美国实际GDP增长率", "sentence_002", factual=True),
        _legacy_object("bea_label", "BEA", "sentence_002", factual=True),
        _legacy_object("world_bank_label", "World Bank", "sentence_003", factual=True),
        _legacy_object("bea_value", "2.8%", "sentence_002", factual=True),
        _legacy_object("world_bank_value", "2.7932%", "sentence_003", factual=True),
        _legacy_object("rounding_rule", "四舍五入到一位小数", "sentence_005", factual=True),
    ]
    return {"scenes": [{"objects": factual}]}


def _timeline() -> dict:
    windows = [
        ("scene_001", 500, 3521),
        ("scene_002", 4021, 14943),
        ("scene_003", 15523, 32766),
        ("scene_004", 33326, 56511),
        ("scene_005", 57011, 60571),
    ]
    return {
        "audio": {"duration_ms": 60611, "sha256": "audio-sha"},
        "scenes": [
            {"scene_id": scene_id, "start_ms": start, "end_ms": end}
            for scene_id, start, end in windows
        ],
        "gaps": [],
    }


def test_gdp_mapping_is_fixed_to_five_approved_primitives() -> None:
    storyboard = build_gdp_calibration_storyboard(
        _legacy_storyboard(), run_id="gdp-run", script_id="script_001"
    )

    assert [scene.primitive.type for scene in storyboard.scenes] == [
        PrimitiveType.HOOK,
        PrimitiveType.COMPARISON,
        PrimitiveType.NUMBER_TRANSFORM,
        PrimitiveType.PROCESS_FLOW,
        PrimitiveType.CONCLUSION,
    ]
    assert [scene.scene_id for scene in storyboard.scenes] == [
        "scene_001", "scene_002", "scene_003", "scene_004", "scene_005",
    ]


def test_gdp_mapping_preserves_fact_provenance_and_shared_ids() -> None:
    storyboard = build_gdp_calibration_storyboard(
        _legacy_storyboard(), run_id="gdp-run", script_id="script_001"
    )

    value_occurrences = [
        obj for scene in storyboard.scenes for obj in scene.objects if obj.object_id == "bea_value"
    ]
    assert len(value_occurrences) == 5
    assert all(obj.sentence_ids == ["sentence_002"] for obj in value_occurrences)
    assert all(obj.claim_ids == ["claim_007"] for obj in value_occurrences)
    assert "bea_value" in storyboard.scenes[1].primitive.inherited_objects
    assert "world_bank_value" in storyboard.scenes[4].primitive.inherited_objects


def test_gdp_mapping_compiles_without_unjustified_static_errors() -> None:
    storyboard = build_gdp_calibration_storyboard(
        _legacy_storyboard(), run_id="gdp-run", script_id="script_001"
    )

    program = VisualProgramCompiler(build_default_registry()).compile(storyboard, _timeline())

    assert program.duration_ms == 60611
    assert program.frame_count == 1819
    assert not [issue for issue in program.density_issues if issue.severity == "error"]
    assert max(
        b.at_ms - a.at_ms
        for scene in program.scenes
        for a, b in zip(scene.states, scene.states[1:])
    ) <= 3000


def test_number_transform_states_target_real_scene_objects() -> None:
    storyboard = build_gdp_calibration_storyboard(
        _legacy_storyboard(), run_id="gdp-run", script_id="script_001"
    )
    scene = next(item for item in storyboard.scenes if item.scene_id == "scene_003")
    object_ids = {obj.object_id for obj in scene.objects}

    assert {
        object_id
        for state in scene.primitive.state_sequence
        for object_id in state.target_object_ids
    } <= object_ids
