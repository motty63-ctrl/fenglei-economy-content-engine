"""Fixed, non-LLM GDP calibration mapping for the V1.0a visual system."""
from __future__ import annotations

from copy import deepcopy

from fanglei.visual_system_v1 import (
    PrimitiveSpec,
    PrimitiveType,
    SceneSpec,
    StateSpec,
    StoryboardV1,
    VisualObject,
)


def _catalog(legacy_storyboard: dict) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for scene in legacy_storyboard.get("scenes", []):
        for obj in scene.get("objects", []):
            result.setdefault(obj["object_id"], deepcopy(obj))
    return result


def _legacy_fact(catalog: dict[str, dict], object_id: str, role: str, *,
                 content: str | None = None) -> VisualObject:
    try:
        row = catalog[object_id]
    except KeyError as exc:
        raise ValueError("GDP_CALIBRATION_OBJECT_MISSING:" + object_id) from exc
    return VisualObject(
        object_id=object_id,
        semantic_role=role,
        content=content or row["content"],
        factual=True,
        sentence_ids=row["sentence_ids"],
        claim_ids=row["claim_ids"],
    )


def _derived_fact(object_id: str, content: str, source: VisualObject, role: str) -> VisualObject:
    return VisualObject(
        object_id=object_id, semantic_role=role, content=content, factual=True,
        sentence_ids=source.sentence_ids, claim_ids=source.claim_ids,
    )


def _decorative(object_id: str, content: str, role: str) -> VisualObject:
    return VisualObject(object_id=object_id, semantic_role=role, content=content)


def _state(index: int, position: float, change: str, targets: list[str], primary: str,
           *, meaningful: bool = True, hold_reason: str | None = None) -> StateSpec:
    return StateSpec(
        state_id=f"state_{index:03d}", relative_position=position,
        change_type=change, target_object_ids=targets,
        primary_focal_object_ids=[primary], meaningful_change=meaningful,
        hold_reason=hold_reason,
    )


def _scene(order: int, primitive_type: PrimitiveType, sentence_ids: list[str],
           objects: list[VisualObject], states: list[StateSpec], *, key_message: str,
           inherited: list[str] | None = None, introduced: list[str] | None = None,
           removed: list[str] | None = None, variant: str) -> SceneSpec:
    object_ids = [obj.object_id for obj in objects]
    inherited = inherited or []
    introduced = introduced if introduced is not None else [
        object_id for object_id in object_ids if object_id not in inherited
    ]
    return SceneSpec(
        scene_id=f"scene_{order:03d}", order=order, objects=objects,
        primitive=PrimitiveSpec(
            primitive_id=f"primitive_{order:03d}", type=primitive_type, variant=variant,
            sentence_ids=sentence_ids,
            claim_ids=sorted({claim for obj in objects for claim in obj.claim_ids}),
            key_message=key_message, object_ids=object_ids, state_sequence=states,
            inherited_objects=inherited, introduced_objects=introduced,
            persistent_objects=inherited, removed_objects=removed or [],
        ),
    )


def build_gdp_calibration_storyboard(legacy_storyboard: dict, *, run_id: str,
                                     script_id: str) -> StoryboardV1:
    """Create the approved five-scene mapping without model generation."""
    source = _catalog(legacy_storyboard)
    bea_value = _legacy_fact(source, "bea_value", "numeric_value")
    world_bank_value = _legacy_fact(source, "world_bank_value", "numeric_value")
    bea_label = _legacy_fact(source, "bea_label", "source_badge")
    world_bank_label = _legacy_fact(source, "world_bank_label", "source_badge")
    year = _legacy_fact(source, "year_2024", "year")
    indicator = _legacy_fact(source, "gdp_indicator", "indicator")
    rounding = _legacy_fact(source, "rounding_rule", "transform_rule")
    metric_context = _derived_fact(
        "metric_context", f"{year.content} · {indicator.content}", indicator, "metric_context"
    )
    rounding_arrow = _derived_fact(
        "rounding_arrow", "2.7932% → 2.8%", rounding, "numeric_relation"
    )

    scene_1_objects = [
        _decorative("gdp_topic", "同一个美国实际GDP", "topic"),
        bea_value, world_bank_value,
        _decorative("hook_question", "到底谁错了？", "question"),
    ]
    scene_1 = _scene(
        1, PrimitiveType.HOOK, ["sentence_001"], scene_1_objects,
        [
            _state(1, 0.00, "introduce", ["gdp_topic"], "gdp_topic"),
            _state(2, 0.34, "introduce", ["bea_value"], "bea_value"),
            _state(3, 0.67, "introduce", ["world_bank_value"], "world_bank_value"),
            _state(4, 0.88, "focus", ["hook_question"], "hook_question"),
        ],
        key_message="同一个美国实际GDP出现两个看似不同的数字",
        variant="numeric_contrast",
    )

    scene_2_objects = [
        metric_context, bea_label, bea_value, world_bank_label, world_bank_value,
        _decorative("comparison_relation", "看起来不一样", "comparison_relation"),
    ]
    scene_2 = _scene(
        2, PrimitiveType.COMPARISON, ["sentence_002", "sentence_003", "sentence_004"],
        scene_2_objects,
        [
            _state(1, 0.00, "introduce", ["metric_context"], "metric_context"),
            _state(2, 0.22, "introduce", ["bea_label", "bea_value"], "bea_value"),
            _state(3, 0.48, "introduce", ["world_bank_label", "world_bank_value"], "world_bank_value"),
            _state(4, 0.73, "connect", ["comparison_relation"], "comparison_relation"),
        ],
        key_message="BEA显示2.8%，World Bank保留2.7932%",
        inherited=["bea_value", "world_bank_value"],
        removed=["gdp_topic", "hook_question"], variant="two_source_numeric",
    )

    scene_3_objects = [
        bea_label, world_bank_label, world_bank_value, rounding, bea_value, rounding_arrow,
    ]
    scene_3 = _scene(
        3, PrimitiveType.NUMBER_TRANSFORM,
        ["sentence_005", "sentence_006", "sentence_007"], scene_3_objects,
        [
            _state(1, 0.00, "introduce", ["bea_label", "world_bank_label"], "world_bank_label"),
            _state(2, 0.15, "focus", ["world_bank_value"], "world_bank_value"),
            _state(3, 0.30, "focus", ["rounding_rule"], "rounding_rule"),
            _state(4, 0.45, "transform", ["world_bank_value"], "world_bank_value"),
            _state(5, 0.60, "introduce", ["bea_value"], "bea_value"),
            _state(6, 0.75, "connect", ["rounding_arrow"], "rounding_arrow"),
            _state(7, 0.90, "confirm", ["bea_value", "world_bank_value"], "rounding_arrow"),
        ],
        key_message="2.7932%四舍五入到一位小数就是2.8%",
        inherited=["bea_label", "world_bank_label", "bea_value", "world_bank_value"],
        removed=["metric_context", "comparison_relation"], variant="rounding_precision",
    )

    process_nodes = [
        _decorative("source_check", "来源", "process_step"),
        _decorative("indicator_check", "指标", "process_step"),
        _decorative("year_check", "年份", "process_step"),
        _decorative("precision_check", "精度", "process_step"),
    ]
    scene_4_objects = [bea_value, world_bank_value, *process_nodes]
    scene_4 = _scene(
        4, PrimitiveType.PROCESS_FLOW,
        [f"sentence_{index:03d}" for index in range(8, 14)], scene_4_objects,
        [
            _state(1, 0.00, "introduce", ["bea_value", "world_bank_value"], "bea_value"),
            _state(2, 0.11, "introduce", ["source_check"], "source_check"),
            _state(3, 0.22, "confirm", ["source_check"], "source_check"),
            _state(4, 0.33, "introduce", ["indicator_check"], "indicator_check"),
            _state(5, 0.44, "confirm", ["indicator_check"], "indicator_check"),
            _state(6, 0.55, "introduce", ["year_check"], "year_check"),
            _state(7, 0.66, "confirm", ["year_check"], "year_check"),
            _state(8, 0.77, "introduce", ["precision_check"], "precision_check"),
            _state(9, 0.88, "confirm", ["precision_check"], "precision_check"),
        ],
        key_message="先核对来源、指标、年份和精度，再判断数据是否冲突",
        inherited=["bea_value", "world_bank_value"],
        removed=["bea_label", "world_bank_label", "rounding_rule", "rounding_arrow"],
        variant="four_check_sequence",
    )

    scene_5_objects = [
        bea_value, world_bank_value,
        _decorative("conclusion", "同一数值，不同精度", "conclusion"),
        _decorative("decimal_metaphor", "有时数据没打架，只是小数点藏起来了", "metaphor"),
    ]
    scene_5 = _scene(
        5, PrimitiveType.CONCLUSION, ["sentence_014"], scene_5_objects,
        [
            _state(1, 0.00, "introduce", ["bea_value", "world_bank_value"], "bea_value"),
            _state(2, 0.32, "connect", ["conclusion"], "conclusion"),
            _state(3, 0.64, "transform", ["decimal_metaphor"], "decimal_metaphor"),
            _state(4, 0.86, "hold", ["decimal_metaphor"], "decimal_metaphor",
                   meaningful=False, hold_reason="final_resolution_hold"),
        ],
        key_message="数据看似冲突，可能只是展示精度不同",
        inherited=["bea_value", "world_bank_value"],
        removed=["source_check", "indicator_check", "year_check", "precision_check"],
        variant="decimal_point_resolution",
    )
    return StoryboardV1(
        run_id=run_id, script_id=script_id,
        scenes=[scene_1, scene_2, scene_3, scene_4, scene_5],
    )
