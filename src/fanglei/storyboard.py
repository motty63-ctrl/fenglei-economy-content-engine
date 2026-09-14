"""Convert semantic visual beats into an explicit, renderer-ready storyboard."""
from __future__ import annotations

from typing import Any

from fanglei.visual_models import (
    MicroAnimationStep,
    Placement,
    RendererDirectives,
    Storyboard,
    StoryboardObject,
    StoryboardScene,
    VisualBeatPlan,
)


PLACEMENTS = {
    "center": Placement(x=.10, y=.18, width=.80, height=.18),
    "left": Placement(x=.08, y=.32, width=.38, height=.20),
    "right": Placement(x=.54, y=.32, width=.38, height=.20),
    "middle": Placement(x=.35, y=.55, width=.30, height=.12),
    "bottom": Placement(x=.12, y=.65, width=.76, height=.14),
    "badge_left": Placement(x=.12, y=.25, width=.22, height=.08),
    "badge_right": Placement(x=.66, y=.25, width=.22, height=.08),
}


def _object(object_id: str, object_type: str, content: str, placement: str, order: int, *,
            factual: bool = False, sentence_ids: list[str] | None = None,
            claim_ids: list[str] | None = None, emphasis: str = "none") -> StoryboardObject:
    return StoryboardObject(
        object_id=object_id, object_type=object_type, content=content,
        factual=factual, sentence_ids=sentence_ids or [], claim_ids=claim_ids or [],
        deterministic_render=factual or object_type in {"text", "number"},
        placement=PLACEMENTS[placement], appearance_order=order, emphasis=emphasis,
    )


def _fact_object(object_id: str, content: str, sentence: dict[str, Any], placement: str,
                 order: int, object_type: str = "text") -> StoryboardObject:
    return _object(object_id, object_type, content, placement, order, factual=True,
                   sentence_ids=[sentence["sentence_id"]], claim_ids=sentence.get("claim_ids", []),
                   emphasis="primary" if object_type == "number" else "secondary")


def _derived_fact_object(object_id: str, content: str, source: StoryboardObject,
                         placement: str, order: int, object_type: str = "text") -> StoryboardObject:
    return _object(object_id, object_type, content, placement, order, factual=True,
                   sentence_ids=source.sentence_ids, claim_ids=source.claim_ids,
                   emphasis="primary" if object_type == "number" else "secondary")


def build_storyboard(plan: VisualBeatPlan, script: dict[str, Any], facts: dict[str, Any]) -> Storyboard:
    allowed = {row["claim_id"] for row in facts.get("claims", [])
               if row.get("verification_status") == "verified" and row.get("allowed_downstream") is True}
    by_id = {row["sentence_id"]: row for row in script.get("sentences", [])}
    verified = [row for row in script.get("sentences", []) if row.get("sentence_type") == "verified_fact"]
    if not verified:
        raise ValueError("STORYBOARD_REQUIRES_VERIFIED_SENTENCE")
    bea_sentence = verified[0]
    wb_sentence = verified[1] if len(verified) > 1 else verified[0]
    rounding_sentence = verified[2] if len(verified) > 2 else verified[-1]
    for row in verified:
        if not row.get("claim_ids") or not set(row["claim_ids"]).issubset(allowed):
            raise ValueError("STORYBOARD_FACT_NOT_ALLOWED:" + row["sentence_id"])
    normalized_text = "".join(row["text"] for row in script.get("sentences", []))
    normalized_text = normalized_text.replace("百分之二点七九三二", "2.7932%").replace("百分之二点八", "2.8%")
    is_gdp_precision = all(token in normalized_text for token in ("2.8%", "2.7932%")) and (
        "BEA" in normalized_text and ("世界银行" in normalized_text or "World Bank" in normalized_text)
    )
    if not is_gdp_precision:
        return _build_generic_storyboard(plan, verified[0])

    fact_objects = {
        "bea_label": _fact_object("bea_label", "BEA", bea_sentence, "left", 1),
        "world_bank_label": _fact_object("world_bank_label", "World Bank", wb_sentence, "right", 1),
        "bea_value": _fact_object("bea_value", "2.8%", bea_sentence, "left", 2, "number"),
        "world_bank_value": _fact_object("world_bank_value", "2.7932%", wb_sentence, "right", 2, "number"),
        "year_2024": _fact_object("year_2024", "2024年", bea_sentence, "center", 1),
        "gdp_indicator": _fact_object("gdp_indicator", "美国实际GDP增长率", bea_sentence, "center", 2),
        "rounding_rule": _fact_object("rounding_rule", "四舍五入到一位小数", rounding_sentence,
                                      "middle", 3),
    }

    total = sum(beat.estimated_duration_seconds for beat in plan.beats)
    elapsed = 0.0
    scenes: list[StoryboardScene] = []
    active: set[str] = set()
    for beat in plan.beats:
        start = elapsed / total
        elapsed += beat.estimated_duration_seconds
        end = elapsed / total
        scene_objects, _, structure, layout, primitives, micro_steps = _scene_spec(
            beat, fact_objects, by_id
        )
        desired_ids = [obj.object_id for obj in scene_objects]
        inherited = [oid for oid in desired_ids if oid in active]
        introduced = [oid for oid in desired_ids if oid not in active]
        removed = sorted(active - set(desired_ids))
        persistent = list(inherited)
        scenes.append(StoryboardScene(
            scene_id=f"scene_{beat.order:03d}", order=beat.order, beat_ids=[beat.beat_id],
            sentence_ids=beat.sentence_ids, narrative_role=beat.narrative_role,
            estimated_duration_seconds=beat.estimated_duration_seconds,
            relative_start=round(start, 6), relative_end=round(end, 6), layout=layout,
            objects=scene_objects, persistent_objects=persistent, inherited_objects=inherited,
            introduced_objects=introduced, removed_objects=removed,
            appearance_sequence=desired_ids,
            transition_in="draw_or_reveal" if beat.order == 1 else "continue_canvas",
            transition_out="hold" if beat.order == len(plan.beats) else "semantic_morph",
            renderer_directives=RendererDirectives(
                primary_route=beat.recommended_renderer, structure=structure,
                    animation_primitives=primitives, draw_order=desired_ids,
                deterministic_overlay_object_ids=[obj.object_id for obj in scene_objects
                                                  if obj.deterministic_render],
                micro_animation_sequence=micro_steps,
            ),
        ))
        active = set(desired_ids)

    routes = [scene.renderer_directives.primary_route for scene in scenes]
    primary = max(set(routes), key=routes.count)
    return Storyboard(
        run_id=plan.run_id, script_id=plan.script_id,
        total_estimated_duration_seconds=round(total, 2),
        renderer_selection={
            "primary_route": primary,
            "scene_routes": {scene.scene_id: scene.renderer_directives.primary_route for scene in scenes},
            "reason": "精确数字、机构标签、四舍五入和顺序检查需要可控的 SVG/HTML 元素；不冒充逐笔落墨。",
            "renderer_invoked": False,
        },
        scenes=scenes,
    )


def _build_generic_storyboard(plan: VisualBeatPlan, verified_sentence: dict[str, Any]) -> Storyboard:
    total = sum(beat.estimated_duration_seconds for beat in plan.beats)
    fact = _fact_object("verified_fact_primary", verified_sentence["text"], verified_sentence,
                        "center", 1)
    elapsed = 0.0
    active: set[str] = set()
    scenes: list[StoryboardScene] = []
    labels = ["核心问题", "已验证事实", "解释机制", "检查方法", "核心判断"]
    for beat in plan.beats:
        start = elapsed / total
        elapsed += beat.estimated_duration_seconds
        marker = _object(f"semantic_marker_{beat.order:03d}", "shape", labels[min(beat.order - 1, 4)],
                         "bottom", 2, emphasis="primary")
        objects = [marker] if beat.order == 1 else [fact, marker]
        ids = [obj.object_id for obj in objects]
        inherited = [oid for oid in ids if oid in active]
        scenes.append(StoryboardScene(
            scene_id=f"scene_{beat.order:03d}", order=beat.order, beat_ids=[beat.beat_id],
            sentence_ids=beat.sentence_ids, narrative_role=beat.narrative_role,
            estimated_duration_seconds=beat.estimated_duration_seconds,
            relative_start=round(start, 6), relative_end=round(elapsed / total, 6),
            layout="同一画布保留已验证事实，并逐步增加当前语义标记",
            objects=objects, persistent_objects=inherited, inherited_objects=inherited,
            introduced_objects=[oid for oid in ids if oid not in active],
            removed_objects=sorted(active - set(ids)), appearance_sequence=ids,
            transition_in="draw_or_reveal" if beat.order == 1 else "continue_canvas",
            transition_out="hold" if beat.order == len(plan.beats) else "semantic_morph",
            renderer_directives=RendererDirectives(
                primary_route=beat.recommended_renderer, structure="single_scene",
                animation_primitives=["hold", "reveal"], draw_order=ids,
                deterministic_overlay_object_ids=[obj.object_id for obj in objects if obj.deterministic_render],
            ),
        ))
        active = set(ids)
    return Storyboard(
        run_id=plan.run_id, script_id=plan.script_id,
        total_estimated_duration_seconds=round(total, 2),
        renderer_selection={
            "primary_route": "program_animation",
            "scene_routes": {scene.scene_id: scene.renderer_directives.primary_route for scene in scenes},
            "reason": "脚本包含需要确定性呈现的已验证文字，使用可控元素并保持同一画布连续演化。",
            "renderer_invoked": False,
        }, scenes=scenes,
    )


def _scene_spec(beat, facts: dict[str, StoryboardObject],
                by_id: dict[str, dict[str, Any]]) -> tuple[
                    list[StoryboardObject], list[str], str, str, list[str], list[MicroAnimationStep]
                ]:
    def sentence_for(token: str, fallback: str | None = None) -> list[str]:
        for sentence_id in beat.sentence_ids:
            if token in by_id[sentence_id]["text"]:
                return [sentence_id]
        return [fallback or beat.sentence_ids[0]]

    if beat.narrative_role == "hook":
        hook_ids = [beat.sentence_ids[0]]
        objects = [
            _object("gdp_topic", "text", "同一个美国GDP", "center", 1, sentence_ids=hook_ids),
            _object("left_number_placeholder", "shape", "数字A", "left", 2, sentence_ids=hook_ids),
            _object("right_number_placeholder", "shape", "数字B", "right", 2, sentence_ids=hook_ids),
            _object("question_mark", "text", "？", "middle", 3, sentence_ids=hook_ids,
                    emphasis="primary"),
        ]
        return objects, [], "comparison", "同一画布左右两栏，中间保留问题焦点", ["draw", "reveal", "pulse"], []
    if beat.narrative_role == "phenomenon":
        objects = [facts[name] for name in (
            "year_2024", "gdp_indicator", "bea_label", "world_bank_label", "bea_value", "world_bank_value"
        )]
        return objects, [], "comparison", "共享标题下的左右同尺度数字对比", ["replace", "count_in", "highlight"], []
    if beat.narrative_role == "mechanism" and "检查" not in beat.cognitive_purpose:
        bea_badge = facts["bea_label"].model_copy(update={"placement": PLACEMENTS["badge_left"]})
        world_bank_badge = facts["world_bank_label"].model_copy(
            update={"placement": PLACEMENTS["badge_right"]}
        )
        objects = [bea_badge, world_bank_badge, facts["bea_value"], facts["world_bank_value"], facts["rounding_rule"],
                   _derived_fact_object("rounding_arrow", "2.7932% → 2.8%", facts["rounding_rule"],
                                        "bottom", 4)]
        micro_steps = [
            MicroAnimationStep(
                step_id="source_badges_hold",
                target_object_ids=["bea_label", "world_bank_label"],
                actions=["scale_down", "deemphasize", "hold"],
            ),
            MicroAnimationStep(
                step_id="rounding_merge",
                target_object_ids=["world_bank_value", "rounding_arrow", "bea_value"],
                actions=["digit_highlight", "round", "merge"],
            ),
            MicroAnimationStep(
                step_id="source_badges_fade",
                target_object_ids=["bea_label", "world_bank_label"],
                actions=["fade_out"],
            ),
        ]
        return objects, [], "numeric_animation", "来源标签缩小为角标保留至数字合并完成，再淡出", ["hold", "digit_highlight", "round", "merge", "fade_out"], micro_steps
    if beat.narrative_role == "mechanism":
        source_ids = sentence_for("原始来源")
        indicator_ids = sentence_for("指标")
        precision_ids = sentence_for("小数")
        objects = [facts["bea_value"], facts["world_bank_value"],
                   _object("source_check", "text", "来源", "left", 3, sentence_ids=source_ids),
                   _object("indicator_check", "text", "指标", "right", 4, sentence_ids=indicator_ids),
                   _object("year_check", "text", "年份", "left", 5, sentence_ids=indicator_ids),
                   _object("precision_check", "text", "精度", "right", 6,
                           sentence_ids=precision_ids, emphasis="primary"),
                   _object("check_flow", "arrow", "来源 → 指标 → 年份 → 精度", "bottom", 7,
                           sentence_ids=list(dict.fromkeys(source_ids + indicator_ids + precision_ids)))]
        nodes = ["source_check", "indicator_check", "year_check", "precision_check"]
        micro_steps = [
            MicroAnimationStep(
                step_id=f"{object_id}_cycle",
                target_object_ids=[object_id],
                actions=["appear", "focus", "check"] + (
                    ["move_focus_next"] if object_id != nodes[-1] else []
                ),
            )
            for object_id in nodes
        ]
        micro_steps.append(MicroAnimationStep(
            step_id="connect_complete_flow",
            target_object_ids=nodes + ["check_flow"],
            actions=["connect_complete_flow"],
        ))
        return objects, [], "process_flow", "两个数值保留在上方；来源、指标、年份、精度依次出现、聚焦、确认并移交焦点，最后连接成完整路径", ["hold", "reveal_sequence", "focus", "check", "connect"], micro_steps
    judgment_ids = [beat.sentence_ids[0]]
    objects = [facts["bea_value"], facts["world_bank_value"],
               _object("decimal_point", "shape", "小数点", "middle", 3,
                       sentence_ids=judgment_ids, emphasis="primary"),
               _derived_fact_object("hidden_digits", "932", facts["world_bank_value"],
                                    "right", 4, "number"),
               _object("closing_metaphor", "metaphor", "小数点把部分数字藏到纸后", "bottom", 5,
                       sentence_ids=judgment_ids)]
    return objects, [], "numeric_animation", "延续数值位置，让多余小数位滑到纸后并收束", ["hold", "mask_digits", "merge", "final_hold"], []
