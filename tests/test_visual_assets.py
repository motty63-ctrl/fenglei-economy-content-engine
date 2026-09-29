from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import pytest
from pydantic import ValidationError

from fanglei.artifact_registry import ArtifactRegistry
from fanglei.human_storyboard_approval import HumanStoryboardApprovalV1
from fanglei.human_storyboard_recovery import canonical_json_sha256
from fanglei.models import RunManifest
from fanglei.visual_assets import build_visual_asset_bundle
from fanglei.visual_pipeline import generate_storyboard_visual_assets
from fanglei.visual_models import (
    Placement, RendererDirectives, Storyboard, StoryboardObject, StoryboardScene,
    StoryboardTimingProvenance,
)


RUN_ID = "2026-09-29-001-synthetic-retail-run"
HASHES = {
    "human_storyboard_candidate.json": "1" * 64,
    "storyboard.json": "2" * 64,
    "human_storyboard_review.json": "3" * 64,
    "human_storyboard_edit.json": "4" * 64,
    "visual_beats.json": "5" * 64,
    "script.json": "6" * 64,
    "facts.json": "7" * 64,
    "angle_selection.json": "8" * 64,
    "human_script_approval.json": "9" * 64,
    "narration.json": "a" * 64,
    "audio/narration.wav": "b" * 64,
    "audio/metadata.json": "c" * 64,
    "audio/quality.json": "d" * 64,
    "audio/review.json": "e" * 64,
    "alignment.json": "f" * 64,
    "subtitle_track.json": "a" * 64,
}


def _approval(**changes) -> HumanStoryboardApprovalV1:
    payload = {
        "schema_version": "human-storyboard-approval/1.0",
        "decision": "approved_for_visual_generation",
        "run_id": RUN_ID,
        "case_id": "synthetic-retail-case",
        "reviewer": "reviewer",
        "approved_at": "2026-09-29T18:00:00+08:00",
        "rationale": "The reviewed composition preserves the approved content and timing.",
        "original_storyboard_sha256": HASHES["storyboard.json"],
        "candidate_storyboard_sha256": "b" * 64,
        "candidate_artifact_sha256": HASHES["human_storyboard_candidate.json"],
        "script_sha256": HASHES["script.json"],
        "facts_sha256": HASHES["facts.json"],
        "angle_selection_sha256": HASHES["angle_selection.json"],
        "selected_angle_id": "angle_synthetic",
        "eligible_claim_ids": ["claim_retail"],
        "audio_sha256": HASHES["audio/narration.wav"],
        "voice_review_sha256": HASHES["audio/review.json"],
        "alignment_sha256": HASHES["alignment.json"],
        "subtitle_sha256": HASHES["subtitle_track.json"],
        "dependency_hashes": dict(HASHES),
    }
    payload.update(changes)
    return HumanStoryboardApprovalV1.model_validate(payload)


def _storyboard() -> Storyboard:
    scenes = []
    for index, (scene_id, text, start, end, claims) in enumerate((
        ("scene_alpha", "Retail index <stable> & measured", 0, 1400, []),
        ("scene_beta", "120 → 135 points", 1400, 3000, ["claim_retail"]),
    ), start=1):
        obj = StoryboardObject(
            object_id=f"object_{index}", object_type="text" if index == 1 else "number",
            content=text, factual=bool(claims), sentence_ids=[f"retail_{index:03}"],
            claim_ids=claims, deterministic_render=True,
            placement=Placement(x=0.1, y=0.2, width=0.8, height=0.3),
            appearance_order=1, emphasis="primary",
        )
        scenes.append(StoryboardScene(
            scene_id=scene_id, order=index, beat_ids=[f"beat_{index:03}"],
            sentence_ids=[f"retail_{index:03}"], narrative_role="phenomenon",
            estimated_duration_seconds=(end-start)/1000, relative_start=(index-1)/2,
            relative_end=index/2, start_ms=start, end_ms=end, layout="single",
            objects=[obj], renderer_directives=RendererDirectives(
                primary_route="program_animation", structure="single_scene",
                draw_order=[obj.object_id],
            ),
        ))
    return Storyboard(
        schema_version="5.0", run_id=RUN_ID, script_id="script_synthetic",
        timing_basis="alignment_derived", total_estimated_duration_seconds=3.0,
        renderer_selection={"route": "program_animation"}, scenes=scenes,
        timing_provenance=StoryboardTimingProvenance(
            audio_sha256="b" * 64, audio_duration_ms=3000, voice_review_sha256="e" * 64,
            alignment_sha256="f" * 64, alignment_method="synthetic_sentence_timing",
            subtitle_sha256="a" * 64, timing_quality="estimated",
        ),
    )


def test_storyboard_approval_binds_current_candidate_and_upstream_hashes() -> None:
    approval = _approval()

    assert approval.dependency_hashes["human_storyboard_candidate.json"] == approval.candidate_artifact_sha256
    assert approval.dependency_hashes["storyboard.json"] == approval.original_storyboard_sha256
    assert approval.dependency_hashes["script.json"] == approval.script_sha256
    assert approval.dependency_hashes["facts.json"] == approval.facts_sha256
    assert approval.eligible_claim_ids == ["claim_retail"]


@pytest.mark.parametrize("changes", [
    {"dependency_hashes": {**HASHES, "facts.json": "0" * 64}},
    {"approved_at": "2026-09-29T18:00:00"},
    {"eligible_claim_ids": ["claim_retail", "claim_retail"]},
    {"decision": "changes_required"},
])
def test_storyboard_approval_rejects_invalid_bindings(changes) -> None:
    with pytest.raises((ValidationError, ValueError)):
        _approval(**changes)


def test_visual_asset_bundle_preserves_scene_order_timing_claims_and_exact_copy() -> None:
    storyboard = _storyboard()
    approval = _approval(candidate_storyboard_sha256=canonical_json_sha256(storyboard))

    files = build_visual_asset_bundle(storyboard, approval, approval_artifact_sha256="c" * 64)

    assert set(files) == {"manifest.json", "index.html", "scene_001.svg", "scene_002.svg"}
    manifest = json.loads(files["manifest.json"])
    assert manifest["schema_version"] == "visual-assets/1.0"
    assert "layout_profile" not in manifest["scenes"][0]
    assert manifest["run_id"] == RUN_ID
    assert manifest["case_id"] == "synthetic-retail-case"
    assert manifest["scene_count"] == 2
    assert [(row["scene_id"], row["order"], row["start_ms"], row["end_ms"])
            for row in manifest["scenes"]] == [
        ("scene_alpha", 1, 0, 1400), ("scene_beta", 2, 1400, 3000),
    ]
    assert manifest["scenes"][1]["sentence_ids"] == ["retail_002"]
    assert manifest["scenes"][1]["claim_ids"] == ["claim_retail"]
    svg_root = ET.fromstring(files["scene_001.svg"])
    assert "data-visual-profile" not in svg_root.attrib
    rendered_text = "".join(
        node.text or "" for node in svg_root.iter()
        if node.tag.endswith("text") or node.tag.endswith("tspan")
    ).strip()
    assert rendered_text == "Retail index <stable> & measured"
    second_root = ET.fromstring(files["scene_002.svg"])
    second_text = "".join(
        node.text or "" for node in second_root.iter()
        if node.tag.endswith("text") or node.tag.endswith("tspan")
    ).strip()
    assert second_text == "120 → 135 points"
    assert "<script" not in files["index.html"]
    assert files == build_visual_asset_bundle(storyboard, approval, approval_artifact_sha256="c" * 64)


def test_visual_assets_registry_graph_requires_storyboard_approval(tmp_path) -> None:
    manifest = RunManifest(run_id=RUN_ID, created_at="2026-09-29T00:00:00+00:00",
                           updated_at="2026-09-29T00:00:00+00:00")
    registry = ArtifactRegistry(
        tmp_path, manifest, research_focus_mode=True, human_angle_selection_mode=True,
        human_script_approval_mode=True, timing_aware_storyboard_mode=True,
        human_storyboard_recovery_mode=True, human_storyboard_approval_mode=True,
    )

    assert registry.graph["human_storyboard_approval.json"][0] == "human_storyboard_approval"
    assert "human_storyboard_candidate.json" in registry.graph["human_storyboard_approval.json"][1]
    assert registry.graph["visual_assets"] == (
        "visual_asset_generation", ("human_storyboard_approval.json", "human_storyboard_candidate.json"),
    )


def test_visual_asset_owner_fails_closed_without_approval_or_output(tmp_path) -> None:
    from fanglei.errors import ArtifactConflictError
    from fanglei.artifacts import atomic_write_json

    run_dir = tmp_path / RUN_ID
    run_dir.mkdir()
    manifest = RunManifest(run_id=RUN_ID, created_at="2026-09-29T00:00:00+00:00",
                           updated_at="2026-09-29T00:00:00+00:00")
    atomic_write_json(run_dir / "run.json", manifest.model_dump(mode="json"))

    with pytest.raises(ArtifactConflictError, match="VISUAL_ASSET_APPROVAL_OR_INPUT_INVALID"):
        generate_storyboard_visual_assets(RUN_ID, tmp_path)

    assert not (run_dir / "visual_assets").exists()
