from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import datetime

import pytest
from pydantic import ValidationError

from fanglei.human_storyboard_recovery import canonical_json_sha256
from fanglei.human_visual_asset_recovery import (
    HumanVisualAssetReviewV1,
    VisualAssetRecoveryPlanV1,
    validate_visual_asset_recovery_plan,
)
from fanglei.artifact_registry import _human_visual_asset_recovery_graph
from fanglei.pipeline import STAGE_ARTIFACT, STAGE_ARTIFACTS
from fanglei.visual_assets import build_visual_asset_bundle
from fanglei.visual_pipeline import _now
from fanglei.visual_models import (
    Placement,
    RendererDirectives,
    Storyboard,
    StoryboardObject,
    StoryboardScene,
    StoryboardTimingProvenance,
)


RUN_ID = "2026-09-29-001-synthetic-retail-run"
CASE_ID = "synthetic-retail-case"
HASHES = {
    "visual_assets": "1" * 64,
    "human_visual_asset_review_candidate_1.json": "b" * 64,
    "visual_asset_recovery.json": "c" * 64,
    "visual_assets_candidate_2": "d" * 64,
    "human_visual_asset_review_candidate_2.json": "e" * 64,
    "visual_asset_recovery_candidate_3.json": "f" * 64,
    "visual_assets_candidate_3": "a" * 64,
    "human_storyboard_approval.json": "2" * 64,
    "human_storyboard_candidate.json": "3" * 64,
    "human_script_approval.json": "c" * 64,
    "storyboard.json": "d" * 64,
    "script.json": "4" * 64,
    "facts.json": "5" * 64,
    "angle_selection.json": "6" * 64,
    "audio/narration.wav": "7" * 64,
    "audio/review.json": "8" * 64,
    "alignment.json": "9" * 64,
    "subtitle_track.json": "a" * 64,
}


def test_visual_review_owner_timestamp_is_timezone_aware() -> None:
    timestamp = datetime.fromisoformat(_now())
    assert timestamp.tzinfo is not None
    assert timestamp.utcoffset() is not None


def _storyboard() -> Storyboard:
    headline = StoryboardObject(
        object_id="headline", object_type="text", content="A measured retail change",
        placement=Placement(x=0.1, y=0.2, width=0.8, height=0.3),
        appearance_order=1, emphasis="primary", sentence_ids=["sentence_001"],
    )
    scene_one = StoryboardScene(
        scene_id="scene_open", order=1, beat_ids=["beat_001"],
        sentence_ids=["sentence_001"], narrative_role="hook", estimated_duration_seconds=1.5,
        relative_start=0, relative_end=0.5, start_ms=0, end_ms=1500, layout="single",
        objects=[headline], renderer_directives=RendererDirectives(
            primary_route="program_animation", structure="single_scene", draw_order=["headline"],
        ),
    )
    label_a = StoryboardObject(
        object_id="label_positive", object_type="text", content="Retail category A",
        placement=Placement(x=0.1, y=0.2, width=0.4, height=0.1),
        appearance_order=1, emphasis="secondary", sentence_ids=["sentence_002"],
        claim_ids=["claim_a"], factual=True,
    )
    value_a = StoryboardObject(
        object_id="value_positive", object_type="number", content="+120 points",
        placement=Placement(x=0.1, y=0.4, width=0.4, height=0.2),
        appearance_order=2, emphasis="primary", sentence_ids=["sentence_002"],
        claim_ids=["claim_a"], factual=True,
    )
    label_b = StoryboardObject(
        object_id="label_negative", object_type="text", content="Retail category B",
        placement=Placement(x=0.55, y=0.2, width=0.35, height=0.1),
        appearance_order=3, emphasis="secondary", sentence_ids=["sentence_003"],
        claim_ids=["claim_b"], factual=True,
    )
    value_b = StoryboardObject(
        object_id="value_negative", object_type="number", content="−60 points",
        placement=Placement(x=0.55, y=0.4, width=0.35, height=0.2),
        appearance_order=4, emphasis="primary", sentence_ids=["sentence_003"],
        claim_ids=["claim_b"], factual=True,
    )
    scene_two = StoryboardScene(
        scene_id="scene_compare", order=2, beat_ids=["beat_002"],
        sentence_ids=["sentence_002", "sentence_003"], narrative_role="phenomenon",
        estimated_duration_seconds=1.5, relative_start=0.5, relative_end=1,
        start_ms=1500, end_ms=3000, layout="comparison",
        objects=[label_a, value_a, label_b, value_b],
        renderer_directives=RendererDirectives(
            primary_route="program_animation", structure="comparison",
            draw_order=["label_positive", "value_positive", "label_negative", "value_negative"],
        ),
    )
    return Storyboard(
        schema_version="5.0", run_id=RUN_ID, script_id="script_synthetic",
        timing_basis="alignment_derived", total_estimated_duration_seconds=3.0,
        renderer_selection={"route": "program_animation"}, scenes=[scene_one, scene_two],
        timing_provenance=StoryboardTimingProvenance(
            audio_sha256="7" * 64, audio_duration_ms=3000, voice_review_sha256="8" * 64,
            alignment_sha256="9" * 64, alignment_method="synthetic_sentence_timing",
            subtitle_sha256="a" * 64, timing_quality="estimated",
        ),
    )


def _review(storyboard: Storyboard, *, candidate_id: int = 1, **changes) -> HumanVisualAssetReviewV1:
    bundle_name = "visual_assets" if candidate_id == 1 else f"visual_assets_candidate_{candidate_id}"
    payload = {
        "schema_version": "human-visual-asset-review/1.0",
        "candidate_id": candidate_id,
        "decision": "changes_required",
        "run_id": RUN_ID,
        "case_id": CASE_ID,
        "reviewer": "reviewer",
        "reviewed_at": "2026-09-29T18:00:00+08:00",
        "reason_code": "VISUAL_HIERARCHY",
        "rationale": "Improve mobile hierarchy while preserving approved content.",
        "findings": ["Primary values need more prominence."],
        "storyboard_sha256": canonical_json_sha256(storyboard),
        "storyboard_artifact_sha256": HASHES["human_storyboard_candidate.json"],
        "storyboard_approval_sha256": HASHES["human_storyboard_approval.json"],
        "visual_bundle_sha256": HASHES[bundle_name],
        "dependency_hashes": dict(HASHES),
    }
    payload.update(changes)
    return HumanVisualAssetReviewV1.model_validate(payload)


def _recovery_plan(
    storyboard: Storyboard,
    review: HumanVisualAssetReviewV1,
    *,
    source_candidate_id: int = 1,
    candidate_id: int = 2,
    **changes,
) -> VisualAssetRecoveryPlanV1:
    scene_layouts = [
        {
            "scene_id": "scene_open", "order": 1, "profile": "hero_topics",
            "object_styles": [{
                "object_id": "headline", "placement": {"x": 0.08, "y": 0.16, "width": 0.84, "height": 0.30},
                "target_font_size": 120, "tone": "primary", "show_card": False,
            }],
            "decorations": [], "diverging_bars": [],
        },
        {
            "scene_id": "scene_compare", "order": 2, "profile": "diverging_comparison",
            "object_styles": [
                {"object_id": "label_positive", "placement": {"x": 0.08, "y": 0.22, "width": 0.62, "height": 0.08}, "target_font_size": 44, "tone": "muted", "show_card": False},
                {"object_id": "value_positive", "placement": {"x": 0.72, "y": 0.22, "width": 0.20, "height": 0.08}, "target_font_size": 48, "tone": "positive", "show_card": False},
                {"object_id": "label_negative", "placement": {"x": 0.08, "y": 0.54, "width": 0.62, "height": 0.08}, "target_font_size": 44, "tone": "muted", "show_card": False},
                {"object_id": "value_negative", "placement": {"x": 0.72, "y": 0.54, "width": 0.20, "height": 0.08}, "target_font_size": 48, "tone": "negative", "show_card": False},
            ],
            "decorations": [],
            "diverging_bars": [
                {"label_object_id": "label_positive", "value_object_id": "value_positive", "center_x": 0.5, "y": 0.38, "max_half_width": 0.34, "height": 0.035},
                {"label_object_id": "label_negative", "value_object_id": "value_negative", "center_x": 0.5, "y": 0.70, "max_half_width": 0.34, "height": 0.035},
            ],
        },
    ]
    payload = {
        "schema_version": "visual-asset-recovery/1.0",
        "run_id": RUN_ID,
        "case_id": CASE_ID,
        "source_candidate_id": source_candidate_id,
        "candidate_id": candidate_id,
        "recovery_rationale": "Rebalance layout and typography without changing approved copy.",
        "storyboard_sha256": canonical_json_sha256(storyboard),
        "storyboard_artifact_sha256": HASHES["human_storyboard_candidate.json"],
        "storyboard_approval_sha256": HASHES["human_storyboard_approval.json"],
        "source_visual_bundle_sha256": HASHES[
            "visual_assets" if source_candidate_id == 1 else f"visual_assets_candidate_{source_candidate_id}"
        ],
        "source_review_sha256": HASHES[f"human_visual_asset_review_candidate_{source_candidate_id}.json"],
        "dependency_hashes": dict(HASHES),
        "source_footer": {"label": "Source: Example Data Office", "source_ids": ["src_synthetic"]},
        "scene_layouts": scene_layouts,
    }
    payload.update(changes)
    return VisualAssetRecoveryPlanV1.model_validate(payload)


def test_visual_asset_review_is_hash_bound_and_requires_aware_time() -> None:
    storyboard = _storyboard()
    review = _review(storyboard)
    assert review.dependency_hashes["visual_assets"] == review.visual_bundle_sha256

    with pytest.raises(ValidationError):
        _review(storyboard, reviewed_at="2026-09-29T18:00:00")
    with pytest.raises(ValidationError):
        _review(storyboard, dependency_hashes={**HASHES, "visual_assets": "0" * 64})


def test_recovery_changes_presentation_but_keeps_storyboard_content_and_bindings() -> None:
    storyboard = _storyboard()
    review = _review(storyboard)
    plan = _recovery_plan(storyboard, review)
    original = storyboard.model_dump(mode="json")

    validate_visual_asset_recovery_plan(
        storyboard, review, plan,
        current_visual_bundle_sha256=HASHES["visual_assets"],
        current_dependency_hashes=HASHES,
        approved_source_ids={"src_synthetic"},
    )
    files = build_visual_asset_bundle(
        storyboard,
        _approval_for_candidate(storyboard),
        approval_artifact_sha256=HASHES["human_storyboard_approval.json"],
        recovery_plan=plan,
    )

    manifest = json.loads(files["manifest.json"])
    assert manifest["schema_version"] == "visual-assets/1.1"
    assert manifest["candidate_id"] == 2
    assert manifest["review_status"] == "pending_human_visual_review"
    assert manifest["source_visual_bundle_sha256"] == HASHES["visual_assets"]
    assert [(row["scene_id"], row["order"], row["start_ms"], row["end_ms"], row["sentence_ids"])
            for row in manifest["scenes"]] == [
        (scene.scene_id, scene.order, scene.start_ms, scene.end_ms, scene.sentence_ids)
        for scene in storyboard.scenes
    ]
    assert storyboard.model_dump(mode="json") == original
    for scene in storyboard.scenes:
        svg = ET.fromstring(files[f"scene_{scene.order:03d}.svg"])
        assert svg.attrib["width"] == "1080"
        assert svg.attrib["height"] == "1920"
        assert svg.attrib["viewBox"] == "0 0 1080 1920"
        groups = {
            group.attrib["data-object-id"]: "".join(
                node.text or "" for node in group.iter() if node.tag.endswith("tspan")
            )
            for group in svg.iter()
            if "data-object-id" in group.attrib
        }
        assert all(obj.content.replace("\n", "") == groups[obj.object_id] for obj in scene.objects)
        if scene.order > 1:
            footer = next(node for node in svg.iter() if "data-source-ids" in node.attrib)
            assert float(footer.attrib["y"]) + float(footer.attrib["font-size"]) <= 0.90 * 1920
        assert [obj.object_id for obj in scene.objects] == [
            row["object_id"] for row in manifest["scenes"][scene.order - 1]["objects"]
        ]
        manifest_objects = {
            row["object_id"]: row for row in manifest["scenes"][scene.order - 1]["objects"]
        }
        for obj in scene.objects:
            row = manifest_objects[obj.object_id]
            assert row["content"] == obj.content
            assert row["claim_ids"] == obj.claim_ids
            assert row["sentence_ids"] == obj.sentence_ids
            assert manifest["scenes"][scene.order - 1]["rendered_font_sizes"][obj.object_id] > 15
    assert "Source: Example Data Office" not in files["scene_001.svg"]
    assert "Source: Example Data Office" in files["scene_002.svg"]
    assert "Candidate 1 — CHANGES_REQUIRED" in files["index.html"]
    assert "Candidate 2 — PENDING HUMAN VISUAL REVIEW" in files["index.html"]
    assert "../visual_assets/index.html" in files["index.html"]
    assert "timeline" not in manifest
    assert files == build_visual_asset_bundle(
        storyboard,
        _approval_for_candidate(storyboard),
        approval_artifact_sha256=HASHES["human_storyboard_approval.json"],
        recovery_plan=plan,
    )


def _approval_for_candidate(storyboard: Storyboard):
    from fanglei.human_storyboard_approval import HumanStoryboardApprovalV1

    hashes = dict(HASHES)
    return HumanStoryboardApprovalV1.model_validate({
        "schema_version": "human-storyboard-approval/1.0",
        "decision": "approved_for_visual_generation",
        "run_id": RUN_ID,
        "case_id": CASE_ID,
        "reviewer": "reviewer",
        "approved_at": "2026-09-29T18:00:00+08:00",
        "rationale": "Approved for visual generation.",
        "original_storyboard_sha256": hashes["storyboard.json"],
        "candidate_storyboard_sha256": canonical_json_sha256(storyboard),
        "candidate_artifact_sha256": hashes["human_storyboard_candidate.json"],
        "script_sha256": hashes["script.json"],
        "facts_sha256": hashes["facts.json"],
        "angle_selection_sha256": hashes["angle_selection.json"],
        "selected_angle_id": "angle_synthetic",
        "eligible_claim_ids": ["claim_a", "claim_b"],
        "audio_sha256": hashes["audio/narration.wav"],
        "voice_review_sha256": hashes["audio/review.json"],
        "alignment_sha256": hashes["alignment.json"],
        "subtitle_sha256": hashes["subtitle_track.json"],
        "dependency_hashes": hashes,
    })


def test_recovery_plan_rejects_copy_edits_unknown_objects_and_stale_dependencies() -> None:
    storyboard = _storyboard()
    review = _review(storyboard)
    plan = _recovery_plan(storyboard, review)
    bad_scene = plan.scene_layouts[0].model_dump(mode="json")
    bad_scene["object_styles"][0]["content"] = "New factual copy"
    with pytest.raises(ValidationError):
        _recovery_plan(storyboard, review, scene_layouts=[bad_scene, plan.scene_layouts[1].model_dump(mode="json")])

    changed = storyboard.model_copy(deep=True)
    changed.scenes[0].objects[0].content = "Changed"
    with pytest.raises(Exception, match="VISUAL_ASSET_RECOVERY_STORYBOARD_MISMATCH"):
        validate_visual_asset_recovery_plan(
            changed, review, plan,
            current_visual_bundle_sha256=HASHES["visual_assets"],
            current_dependency_hashes=HASHES,
            approved_source_ids={"src_synthetic"},
        )
    with pytest.raises(Exception, match="VISUAL_ASSET_RECOVERY_SOURCE_BUNDLE_MISMATCH"):
        validate_visual_asset_recovery_plan(
            storyboard, review, plan,
            current_visual_bundle_sha256="0" * 64,
            current_dependency_hashes=HASHES,
            approved_source_ids={"src_synthetic"},
        )


def test_diverging_bars_derive_direction_and_relative_magnitude_without_new_copy() -> None:
    storyboard = _storyboard()
    review = _review(storyboard)
    plan = _recovery_plan(storyboard, review)
    files = build_visual_asset_bundle(
        storyboard,
        _approval_for_candidate(storyboard),
        approval_artifact_sha256=HASHES["human_storyboard_approval.json"],
        recovery_plan=plan,
    )
    root = ET.fromstring(files["scene_002.svg"])
    bars = [element for element in root.iter() if "data-value-object-id" in element.attrib]
    by_id = {element.attrib["data-value-object-id"]: element.attrib for element in bars}
    positive = by_id["value_positive"]
    negative = by_id["value_negative"]
    assert positive["data-sign"] == "positive"
    assert negative["data-sign"] == "negative"
    assert float(positive["data-normalized-length"]) == pytest.approx(1.0)
    assert float(negative["data-normalized-length"]) == pytest.approx(0.5)
    positive_rect = next(child for child in root.iter() if child.tag.endswith("rect") and child.attrib.get("width") == "367.2")
    negative_rect = next(child for child in root.iter() if child.tag.endswith("rect") and child.attrib.get("width") == "183.6")
    assert float(positive_rect.attrib["x"]) == pytest.approx(540)
    assert float(negative_rect.attrib["x"]) < 540
    visible_text = "".join(node.text or "" for node in root.iter() if node.tag.endswith("tspan"))
    assert "+120 points" in visible_text
    assert "−60 points" in visible_text


def test_visual_asset_recovery_contract_rejects_missing_scene_or_source_footer_identity() -> None:
    storyboard = _storyboard()
    review = _review(storyboard)
    plan = _recovery_plan(storyboard, review)
    with pytest.raises(Exception, match="VISUAL_ASSET_RECOVERY_SCENE_COVERAGE_INVALID"):
        validate_visual_asset_recovery_plan(
            storyboard, review,
            plan.model_copy(update={"scene_layouts": plan.scene_layouts[:1]}),
            current_visual_bundle_sha256=HASHES["visual_assets"],
            current_dependency_hashes=HASHES,
            approved_source_ids={"src_synthetic"},
        )
    with pytest.raises(Exception, match="VISUAL_ASSET_RECOVERY_SOURCE_FOOTER_NOT_APPROVED"):
        validate_visual_asset_recovery_plan(
            storyboard, review,
            plan.model_copy(update={"source_footer": plan.source_footer.model_copy(update={"source_ids": ["src_other"]})}),
            current_visual_bundle_sha256=HASHES["visual_assets"],
            current_dependency_hashes=HASHES,
            approved_source_ids={"src_synthetic"},
        )


def test_recovery_registers_new_candidate_without_approving_timeline() -> None:
    base_graph = {
        "visual_assets": ("visual_asset_generation", ("human_storyboard_approval.json", "human_storyboard_candidate.json")),
        "timeline.json": ("timeline_compilation", ("storyboard.json", "subtitle_track.json")),
    }
    graph = _human_visual_asset_recovery_graph(base_graph)
    assert graph["visual_assets"] == base_graph["visual_assets"]
    assert graph["timeline.json"] == base_graph["timeline.json"]
    assert graph["human_visual_asset_review_candidate_1.json"][1] == (
        "visual_assets", "human_storyboard_approval.json", "human_storyboard_candidate.json",
    )
    assert graph["visual_assets_candidate_2"] == (
        "visual_asset_recovery",
        ("visual_asset_recovery.json", "human_visual_asset_review_candidate_1.json", "visual_assets"),
    )
    assert graph["human_visual_asset_review_candidate_2.json"][1] == (
        "visual_assets_candidate_2", "visual_asset_recovery.json",
        "human_visual_asset_review_candidate_1.json", "human_storyboard_approval.json",
        "human_storyboard_candidate.json",
    )
    assert graph["human_visual_asset_review_candidate_2.json"][0] == "human_visual_asset_review_candidate_2"
    assert STAGE_ARTIFACT["human_visual_asset_review_candidate_2"] == "human_visual_asset_review_candidate_2.json"
    assert graph["visual_assets_candidate_3"] == (
        "visual_asset_recovery_candidate_3",
        ("visual_asset_recovery_candidate_3.json", "human_visual_asset_review_candidate_2.json",
         "visual_assets_candidate_2"),
    )
    assert STAGE_ARTIFACTS["visual_asset_recovery"] == (
        "visual_asset_recovery.json", "visual_assets_candidate_2",
    )
    assert STAGE_ARTIFACTS["visual_asset_recovery_candidate_3"] == (
        "visual_asset_recovery_candidate_3.json", "visual_assets_candidate_3",
    )


def test_candidate_three_binds_candidate_two_review_and_does_not_approve_timeline() -> None:
    storyboard = _storyboard()
    review = _review(storyboard, candidate_id=2)
    plan = _recovery_plan(
        storyboard, review, source_candidate_id=2, candidate_id=3,
        source_review_sha256=HASHES["human_visual_asset_review_candidate_2.json"],
        source_visual_bundle_sha256=HASHES["visual_assets_candidate_2"],
    )

    validate_visual_asset_recovery_plan(
        storyboard, review, plan,
        current_visual_bundle_sha256=HASHES["visual_assets_candidate_2"],
        current_dependency_hashes=HASHES,
        approved_source_ids={"src_synthetic"},
    )
    files = build_visual_asset_bundle(
        storyboard,
        _approval_for_candidate(storyboard),
        approval_artifact_sha256=HASHES["human_storyboard_approval.json"],
        recovery_plan=plan,
    )
    manifest = json.loads(files["manifest.json"])

    assert manifest["candidate_id"] == 3
    assert manifest["source_candidate_id"] == 2
    assert manifest["review_status"] == "pending_human_visual_review"
    assert "Candidate 2 — CHANGES_REQUIRED" in files["index.html"]
    assert "../visual_assets_candidate_2/index.html" in files["index.html"]
    assert "timeline" not in manifest


def test_recovery_plan_rejects_objects_outside_mobile_safe_region() -> None:
    storyboard = _storyboard()
    review = _review(storyboard)
    plan = _recovery_plan(storyboard, review)
    first_layout = plan.scene_layouts[0].model_copy(update={
        "object_styles": [plan.scene_layouts[0].object_styles[0].model_copy(update={
            "placement": Placement(x=0.01, y=0.16, width=0.84, height=0.30),
        })],
    })
    invalid_plan = plan.model_copy(update={
        "scene_layouts": [first_layout, plan.scene_layouts[1]],
    })

    with pytest.raises(Exception, match="VISUAL_ASSET_RECOVERY_OBJECT_OUTSIDE_SAFE_AREA"):
        validate_visual_asset_recovery_plan(
            storyboard, review, invalid_plan,
            current_visual_bundle_sha256=HASHES["visual_assets"],
            current_dependency_hashes=HASHES,
            approved_source_ids={"src_synthetic"},
        )


def test_recovery_plan_rejects_preferred_break_inside_value_unit_token() -> None:
    storyboard = _storyboard()
    review = _review(storyboard)
    payload = _recovery_plan(storyboard, review).model_dump(mode="json")
    value_style = next(
        style
        for scene in payload["scene_layouts"]
        for style in scene["object_styles"]
        if style["object_id"] == "value_positive"
    )
    value_style["preferred_line_breaks"] = [5]
    invalid_plan = VisualAssetRecoveryPlanV1.model_validate(payload)

    with pytest.raises(Exception, match="VISUAL_ASSET_RECOVERY_BREAK_SPLITS_VALUE_UNIT"):
        validate_visual_asset_recovery_plan(
            storyboard, review, invalid_plan,
            current_visual_bundle_sha256=HASHES["visual_assets"],
            current_dependency_hashes=HASHES,
            approved_source_ids={"src_synthetic"},
        )
