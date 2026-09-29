from __future__ import annotations

from copy import deepcopy

import pytest

from fanglei.errors import ArtifactConflictError
from fanglei.models import RunManifest
from fanglei.visual_models import (
    Placement,
    RendererDirectives,
    Storyboard,
    StoryboardObject,
    StoryboardScene,
    StoryboardTimingProvenance,
)


RUN_ID = "synthetic-retail-storyboard-run"
CASE_ID = "synthetic-retail-case"
SCRIPT_SHA = "1" * 64
STORYBOARD_SHA = "2" * 64
AUDIO_SHA = "3" * 64
REVIEW_SHA = "4" * 64
ALIGNMENT_SHA = "5" * 64
SUBTITLE_SHA = "6" * 64
SELECTION_SHA = "7" * 64


def _script() -> dict:
    return {
        "run_id": RUN_ID,
        "script_id": "script_synthetic",
        "target_language": "en",
        "sentences": [
            {"sentence_id": "sentence_hook", "sentence_type": "interpretation",
             "text": "One report has several measures.", "claim_ids": []},
            {"sentence_id": "sentence_fact", "sentence_type": "verified_fact",
             "text": "Synthetic bureau reported the retail index rose 12.4 points during Month X.",
             "claim_ids": ["claim_retail"]},
        ],
    }


def _facts() -> dict:
    return {
        "run_id": RUN_ID,
        "schema_version": "2.2",
        "claims": [
            {"claim_id": "claim_retail", "claim_text": "Synthetic bureau reported a 12.4-point rise.",
             "verification_status": "verified", "verification_basis": "independent_corroboration",
             "allowed_downstream": True, "source_ids": ["source_synthetic"], "evidence": []},
        ],
    }


def _storyboard() -> Storyboard:
    return Storyboard(
        schema_version="5.0",
        run_id=RUN_ID,
        script_id="script_synthetic",
        timing_basis="alignment_derived",
        total_estimated_duration_seconds=2.0,
        renderer_selection={"primary_route": "program_animation", "reason": "synthetic", "renderer_invoked": False},
        timing_provenance=StoryboardTimingProvenance(
            audio_sha256=AUDIO_SHA, audio_duration_ms=2000,
            voice_review_sha256=REVIEW_SHA, alignment_sha256=ALIGNMENT_SHA,
            alignment_method="proportional_by_normalized_char_count",
            timing_quality="estimated", subtitle_sha256=SUBTITLE_SHA,
        ),
        scenes=[
            StoryboardScene(
                scene_id="scene_001", order=1, beat_ids=["beat_001"], sentence_ids=["sentence_hook"],
                narrative_role="hook", estimated_duration_seconds=1.0,
                relative_start=0.0, relative_end=0.5, start_ms=0, end_ms=1000,
                layout="one plain hook line",
                objects=[StoryboardObject(
                    object_id="hook_copy", object_type="text", content="One report has several measures.",
                    sentence_ids=["sentence_hook"], placement=Placement(x=.1, y=.4, width=.8, height=.2),
                    appearance_order=1,
                )],
                introduced_objects=["hook_copy"], appearance_sequence=["hook_copy"],
                transition_in="draw_or_reveal", transition_out="semantic_morph",
                renderer_directives=RendererDirectives(
                    primary_route="program_animation", structure="single_scene",
                    draw_order=["hook_copy"],
                ),
            ),
            StoryboardScene(
                scene_id="scene_002", order=2, beat_ids=["beat_002"], sentence_ids=["sentence_fact"],
                narrative_role="judgment", estimated_duration_seconds=1.0,
                relative_start=0.5, relative_end=1.0, start_ms=1000, end_ms=2000,
                layout="one sentence fills the scene",
                objects=[StoryboardObject(
                    object_id="fact_copy", object_type="text",
                    content="Synthetic bureau reported the retail index rose 12.4 points during Month X.",
                    factual=True, sentence_ids=["sentence_fact"], claim_ids=["claim_retail"],
                    deterministic_render=True,
                    placement=Placement(x=.1, y=.3, width=.8, height=.4),
                    appearance_order=1, emphasis="secondary",
                )],
                introduced_objects=["fact_copy"], appearance_sequence=["fact_copy"],
                transition_in="continue_canvas", transition_out="hold",
                renderer_directives=RendererDirectives(
                    primary_route="program_animation", structure="single_scene",
                    draw_order=["fact_copy"], deterministic_overlay_object_ids=["fact_copy"],
                ),
            ),
        ],
    )


def _edited_storyboard(*, fact_text: str = "12.4", sentence_ids: list[str] | None = None) -> Storyboard:
    board = _storyboard()
    source = board.scenes[1].objects[0]
    objects = [
        StoryboardObject(
            object_id="metric_label", object_type="text", content="retail index", factual=True,
            sentence_ids=["sentence_fact"], claim_ids=["claim_retail"], deterministic_render=True,
            placement=Placement(x=.1, y=.2, width=.8, height=.14), appearance_order=1,
            emphasis="secondary",
        ),
        StoryboardObject(
            object_id="metric_value", object_type="number", content=fact_text, factual=True,
            sentence_ids=sentence_ids or ["sentence_fact"], claim_ids=["claim_retail"],
            deterministic_render=True, placement=Placement(x=.1, y=.4, width=.8, height=.3),
            appearance_order=2, emphasis="primary",
        ),
        StoryboardObject(
            object_id="metric_unit", object_type="text", content="points", factual=True,
            sentence_ids=["sentence_fact"], claim_ids=["claim_retail"], deterministic_render=True,
            placement=Placement(x=.1, y=.75, width=.8, height=.1), appearance_order=3,
            emphasis="secondary",
        ),
    ]
    second = board.scenes[1].model_copy(update={
        "layout": "metric data card: label, large number, unit",
        "objects": objects,
        "introduced_objects": [obj.object_id for obj in objects],
        "removed_objects": [],
        "appearance_sequence": [obj.object_id for obj in objects],
        "renderer_directives": RendererDirectives(
            primary_route="program_animation", structure="comparison",
            animation_primitives=["reveal", "highlight", "hold"],
            draw_order=[obj.object_id for obj in objects],
            deterministic_overlay_object_ids=[obj.object_id for obj in objects],
        ),
    })
    board.scenes[1] = second
    return board


def _review_payload(**overrides) -> dict:
    from fanglei.human_storyboard_recovery import HumanStoryboardReviewV1

    payload = {
        "schema_version": "human-storyboard-review/1.0",
        "run_id": RUN_ID,
        "case_id": CASE_ID,
        "reviewer": "reviewer-synthetic",
        "reviewed_at": "2026-09-29T12:00:00+08:00",
        "decision": "changes_required",
        "reason_code": "VISUAL_DIFFERENTIATION_AND_HIERARCHY",
        "rationale": "The candidate needs clearer visual hierarchy.",
        "original_storyboard_sha256": STORYBOARD_SHA,
        "script_sha256": SCRIPT_SHA,
        "audio_sha256": AUDIO_SHA,
        "voice_review_sha256": REVIEW_SHA,
        "alignment_sha256": ALIGNMENT_SHA,
        "subtitle_sha256": SUBTITLE_SHA,
        "angle_selection_sha256": SELECTION_SHA,
        "selected_angle_id": "angle_synthetic",
        "target_language": "en",
        "dependency_hashes": {"storyboard.json": STORYBOARD_SHA, "script.json": SCRIPT_SHA},
    }
    payload.update(overrides)
    return payload


def test_visual_only_storyboard_edit_is_accepted_and_does_not_mutate_original() -> None:
    from fanglei.human_storyboard_recovery import validate_human_storyboard_candidate

    original = _storyboard()
    before = deepcopy(original.model_dump(mode="json"))
    candidate = _edited_storyboard()

    checked = validate_human_storyboard_candidate(original, candidate, _script(), _facts())

    assert checked.quality_gate is not None and checked.quality_gate.passed
    assert checked.scenes[1].layout == "metric data card: label, large number, unit"
    assert original.model_dump(mode="json") == before


def test_storyboard_edit_rejects_scene_timing_change() -> None:
    from fanglei.human_storyboard_recovery import validate_human_storyboard_candidate

    original = _storyboard()
    changed = _edited_storyboard()
    changed.scenes[1].start_ms = 999

    with pytest.raises(ArtifactConflictError, match="STORYBOARD_RECOVERY_TIMING_CHANGED"):
        validate_human_storyboard_candidate(original, changed, _script(), _facts())


def test_storyboard_edit_rejects_segment_ownership_change() -> None:
    from fanglei.human_storyboard_recovery import validate_human_storyboard_candidate

    original = _storyboard()
    changed = _edited_storyboard()
    changed.scenes[1].sentence_ids = ["sentence_hook"]

    with pytest.raises(ArtifactConflictError, match="STORYBOARD_RECOVERY_SEGMENT_OWNERSHIP_CHANGED"):
        validate_human_storyboard_candidate(original, changed, _script(), _facts())


def test_storyboard_edit_rejects_claim_outside_original_scene() -> None:
    from fanglei.human_storyboard_recovery import validate_human_storyboard_candidate

    original = _storyboard()
    facts = _facts()
    facts["claims"].append({
        "claim_id": "claim_other", "claim_text": "Another approved claim.",
        "verification_status": "verified", "verification_basis": "independent_corroboration",
        "allowed_downstream": True, "source_ids": ["source_synthetic"], "evidence": [],
    })
    changed = _edited_storyboard()
    changed.scenes[1].objects[0].claim_ids = ["claim_other"]

    with pytest.raises(ArtifactConflictError, match="STORYBOARD_RECOVERY_CLAIM_SET_CHANGED"):
        validate_human_storyboard_candidate(original, changed, _script(), facts)


@pytest.mark.parametrize("value", ["99.9", "11.4", "12.4.0"])
def test_storyboard_edit_rejects_numeric_fact_not_in_bound_script(value: str) -> None:
    from fanglei.human_storyboard_recovery import validate_human_storyboard_candidate

    with pytest.raises(ArtifactConflictError, match="STORYBOARD_RECOVERY_NUMERIC_VALUE_UNSUPPORTED"):
        validate_human_storyboard_candidate(_storyboard(), _edited_storyboard(fact_text=value), _script(), _facts())


def test_explicit_signs_follow_the_nearest_revision_direction_marker() -> None:
    from fanglei.human_storyboard_recovery import _validate_explicit_number_signs

    source = "Synthetic index was revised upward 4.4 points, from a decrease of 2.3 to an increase of 2.1 points."
    # English markers are intentionally supported by this generic helper.
    _validate_explicit_number_signs("+4.4", source)
    _validate_explicit_number_signs("−2.3", source)
    _validate_explicit_number_signs("+2.1", source)


def test_human_review_and_recovery_contracts_are_strict_and_remain_pending() -> None:
    from fanglei.human_storyboard_recovery import (
        HumanStoryboardEditV1,
        HumanStoryboardReviewV1,
        canonical_json_sha256,
    )

    review = HumanStoryboardReviewV1.model_validate(_review_payload())
    candidate = _edited_storyboard()
    edit = HumanStoryboardEditV1(
        schema_version="human-storyboard-edit/1.0", status="pending_human_review",
        run_id=RUN_ID, case_id=CASE_ID, reviewer=review.reviewer,
        submitted_at="2026-09-29T12:01:00+08:00", rationale="Differentiate the visual hierarchy.",
        review_sha256="8" * 64, original_storyboard_sha256=STORYBOARD_SHA,
        candidate_storyboard_sha256=canonical_json_sha256(candidate),
        dependency_hashes=review.dependency_hashes,
        candidate_storyboard=candidate,
    )

    assert review.decision == "changes_required"
    assert edit.status == "pending_human_review"
    assert "approval" not in edit.status
    with pytest.raises(ValueError):
        HumanStoryboardReviewV1.model_validate({**_review_payload(), "reviewed_at": "2026-09-29T12:00:00"})
    with pytest.raises(ValueError):
        HumanStoryboardEditV1.model_validate({**edit.model_dump(mode="json"), "status": "approved"})


def test_storyboard_recovery_graph_tracks_new_candidate_and_visual_plan(tmp_path) -> None:
    from fanglei.artifact_registry import ArtifactRegistry

    manifest = RunManifest(run_id=RUN_ID, created_at="2026-09-29T00:00:00+00:00",
                           updated_at="2026-09-29T00:00:00+00:00")
    registry = ArtifactRegistry(
        tmp_path, manifest, research_focus_mode=True, human_angle_selection_mode=True,
        human_script_approval_mode=True, timing_aware_storyboard_mode=True,
        human_storyboard_recovery_mode=True,
    )

    assert registry.graph["storyboard.json"][0] == "storyboard_generation"
    assert "storyboard.json" in registry.graph["storyboard_review.json"][1]
    assert "storyboard_review.json" in registry.graph["human_storyboard_edit.json"][1]
    assert "storyboard.json" in registry.graph["human_storyboard_candidate.json"][1]
    assert registry.graph["visual_plan.md"][1] == ("human_storyboard_candidate.json",)
    assert "storyboard.json" not in registry.graph["visual_plan.md"][1]


def test_run_identity_uses_registry_binding_for_script_without_inline_run_id() -> None:
    from fanglei.visual_pipeline import _validate_storyboard_run_identity

    _validate_storyboard_run_identity("script.json", {"script_id": "script_synthetic"}, RUN_ID,
                                      allow_missing=True)
    _validate_storyboard_run_identity("facts.json", {"run_id": RUN_ID}, RUN_ID)
    with pytest.raises(ArtifactConflictError, match="STORYBOARD_RECOVERY_RUN_ID_MISMATCH:script.json"):
        _validate_storyboard_run_identity("script.json", {"run_id": "another-run"}, RUN_ID,
                                          allow_missing=True)
    with pytest.raises(ArtifactConflictError, match="STORYBOARD_RECOVERY_RUN_ID_MISMATCH:facts.json"):
        _validate_storyboard_run_identity("facts.json", {}, RUN_ID)


def test_recovered_candidate_is_invalidated_when_original_dependency_changes(tmp_path) -> None:
    from fanglei.artifact_registry import ArtifactRegistry

    manifest = RunManifest(run_id=RUN_ID, created_at="2026-09-29T00:00:00+00:00",
                           updated_at="2026-09-29T00:00:00+00:00")
    registry = ArtifactRegistry(
        tmp_path, manifest, research_focus_mode=True, human_angle_selection_mode=True,
        human_script_approval_mode=True, timing_aware_storyboard_mode=True,
        human_storyboard_recovery_mode=True,
    )
    for name in ("human_storyboard_candidate.json", "visual_plan.md"):
        manifest.artifacts[name].status = "valid"

    registry.invalidate_descendants("script.json")

    assert manifest.artifacts["human_storyboard_candidate.json"].status == "stale"
    assert manifest.artifacts["visual_plan.md"].status == "stale"


def test_registry_validates_shared_dependencies_once_per_dag_walk(tmp_path) -> None:
    from fanglei.artifact_registry import ArtifactRegistry
    from fanglei.models import ArtifactState

    manifest = RunManifest(run_id=RUN_ID, created_at="2026-09-29T00:00:00+00:00",
                           updated_at="2026-09-29T00:00:00+00:00")
    registry = ArtifactRegistry(tmp_path, manifest)
    registry.graph = {
        "leaf.json": ("leaf", ()),
        "left.json": ("left", ("leaf.json",)),
        "right.json": ("right", ("leaf.json",)),
        "root.json": ("root", ("left.json", "right.json")),
    }
    manifest.artifacts = {
        name: ArtifactState(owner=owner, dependencies={dep: "" for dep in dependencies})
        for name, (owner, dependencies) in registry.graph.items()
    }
    registry.write_text("leaf.json", "leaf", "leaf")
    registry.write_text("left.json", "left", "left")
    registry.write_text("right.json", "right", "right")
    registry.write_text("root.json", "root", "root")

    calls: list[str] = []
    original_validate = registry._validate_recursive

    def count_visits(name: str, *, validated: set[str], visiting: set[str]) -> None:
        calls.append(name)
        original_validate(name, validated=validated, visiting=visiting)

    registry._validate_recursive = count_visits
    registry.validate("root.json")

    assert calls.count("leaf.json") == 1
    assert len(calls) == len(set(calls)) == 4
