from fanglei.providers.visual import DeterministicVisualPlanningProvider, VisualPlanningRequest
from fanglei.storyboard import build_storyboard
from tests.test_visual_planning import _script


def _facts():
    return {"claims": [{"claim_id": "claim_007", "verification_status": "verified",
                         "allowed_downstream": True}]}


def _board():
    script = _script()
    plan = DeterministicVisualPlanningProvider().plan(VisualPlanningRequest(
        run_id="gdp", script=script, allowed_claim_ids={"claim_007"}
    ))
    return build_storyboard(plan, script, _facts())


def test_storyboard_separates_layout_from_semantic_beats() -> None:
    board = _board()
    assert len(board.scenes) == 5
    assert all(scene.layout for scene in board.scenes)
    assert all(scene.renderer_directives.primary_route == "program_animation" for scene in board.scenes)
    assert board.renderer_selection["primary_route"] == "program_animation"
    assert board.renderer_selection["reason"]
    assert board.scenes[3].renderer_directives.structure == "process_flow"


def test_appearance_sequence_lists_every_active_object_in_order() -> None:
    board = _board()
    for scene in board.scenes:
        assert scene.appearance_sequence == [obj.object_id for obj in scene.objects]
        assert scene.appearance_sequence


def test_storyboard_keeps_stable_objects_across_beats() -> None:
    board = _board()
    assert "bea_value" in board.scenes[1].introduced_objects
    assert "bea_value" in board.scenes[2].inherited_objects
    assert "bea_value" in board.scenes[2].persistent_objects
    assert "world_bank_value" in board.scenes[4].inherited_objects
    assert "hidden_digits" in board.scenes[4].introduced_objects
    first_value = next(obj for obj in board.scenes[1].objects if obj.object_id == "bea_value")
    inherited_value = next(obj for obj in board.scenes[2].objects if obj.object_id == "bea_value")
    assert first_value.content == inherited_value.content == "2.8%"


def test_rounding_scene_keeps_source_badges_until_number_merge_finishes() -> None:
    board = _board()
    scene = board.scenes[2]

    assert {"bea_label", "world_bank_label"} <= set(scene.inherited_objects)
    assert {"bea_label", "world_bank_label"} <= set(scene.persistent_objects)
    labels = {obj.object_id: obj for obj in scene.objects}
    assert labels["bea_label"].emphasis == "secondary"
    assert labels["world_bank_label"].emphasis == "secondary"
    assert labels["bea_label"].placement.height < board.scenes[1].objects[2].placement.height

    steps = scene.renderer_directives.micro_animation_sequence
    merge_index = next(i for i, step in enumerate(steps) if "merge" in step.actions)
    fade_index = next(i for i, step in enumerate(steps) if "fade_out" in step.actions)
    assert fade_index > merge_index
    assert set(steps[fade_index].target_object_ids) == {"bea_label", "world_bank_label"}


def test_process_flow_declares_each_check_node_micro_animation() -> None:
    scene = _board().scenes[3]
    steps = scene.renderer_directives.micro_animation_sequence
    expected = ["source_check", "indicator_check", "year_check", "precision_check"]

    assert [step.target_object_ids[0] for step in steps[:4]] == expected
    assert all(step.actions[:3] == ["appear", "focus", "check"] for step in steps[:4])
    assert all("move_focus_next" in step.actions for step in steps[:3])
    assert steps[3].actions == ["appear", "focus", "check"]
    assert steps[4].target_object_ids == expected + ["check_flow"]
    assert steps[4].actions == ["connect_complete_flow"]


def test_factual_visible_objects_are_deterministic_and_traceable() -> None:
    board = _board()
    factual = [obj for scene in board.scenes for obj in scene.objects if obj.factual]
    assert factual
    assert all(obj.deterministic_render for obj in factual)
    assert all(obj.sentence_ids for obj in factual)
    assert all(obj.claim_ids == ["claim_007"] for obj in factual)
    contents = {obj.content for obj in factual}
    assert {"2.8%", "2.7932%", "2024年", "BEA", "World Bank", "美国实际GDP增长率"} <= contents


def test_instructional_and_metaphor_objects_keep_sentence_provenance() -> None:
    board = _board()
    expected = {
        "gdp_topic": ["sentence_001"],
        "source_check": ["sentence_009"],
        "indicator_check": ["sentence_010"],
        "year_check": ["sentence_010"],
        "precision_check": ["sentence_011"],
        "closing_metaphor": ["sentence_014"],
    }
    objects = {obj.object_id: obj for scene in board.scenes for obj in scene.objects}
    for object_id, sentence_ids in expected.items():
        assert objects[object_id].sentence_ids == sentence_ids


def test_storyboard_has_estimated_relative_timing_only() -> None:
    payload = _board().model_dump(mode="json")
    assert payload["timing_basis"] == "estimated_speech"
    assert payload["scenes"][0]["relative_start"] == 0
    assert payload["scenes"][-1]["relative_end"] == 1
    assert all("start_seconds" not in scene and "end_seconds" not in scene for scene in payload["scenes"])


def test_storyboard_never_adds_an_exact_fact_absent_from_script() -> None:
    script = _script()
    for row in script["sentences"]:
        row["text"] = "一个抽象指标需要按同一方法检查。"
        row["claim_ids"] = []
        row["sentence_type"] = "explanation"
    script["sentences"][1].update(text="这个抽象指标是1.2%。", sentence_type="verified_fact",
                                  claim_ids=["claim_generic"])
    plan = DeterministicVisualPlanningProvider().plan(VisualPlanningRequest(
        run_id="generic", script=script, allowed_claim_ids={"claim_generic"}
    ))
    board = build_storyboard(plan, script, {"claims": [{"claim_id": "claim_generic",
        "verification_status": "verified", "allowed_downstream": True}]})
    payload = board.model_dump_json()
    for forbidden in ("2.8%", "2.7932%", "BEA", "World Bank", "2024"):
        assert forbidden not in payload


def test_scene_structure_follows_semantic_role_not_fixed_beat_number() -> None:
    script = _script()
    script["sentences"][7]["text"] = "看到经济数据不一样先别急。"
    plan = DeterministicVisualPlanningProvider().plan(VisualPlanningRequest(
        run_id="gdp", script=script, allowed_claim_ids={"claim_007"}
    ))
    assert len(plan.beats) == 4
    board = build_storyboard(plan, script, _facts())
    assert board.scenes[-1].narrative_role == "judgment"
    assert board.scenes[-1].renderer_directives.structure == "numeric_animation"
    assert "closing_metaphor" in board.scenes[-1].introduced_objects
