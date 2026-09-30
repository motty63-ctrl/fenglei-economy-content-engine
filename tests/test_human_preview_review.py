from __future__ import annotations

import json
from datetime import datetime

import pytest

from fanglei.artifact_registry import ArtifactRegistry
from fanglei.artifact_registry import _directory_hash
from fanglei.artifacts import sha256_bytes, sha256_text
from fanglei.errors import ArtifactConflictError
from fanglei.models import RunManifest
from fanglei.playback_preview import (
    HumanPreviewReviewV1,
    record_human_preview_review,
)


def _valid_review_payload() -> dict:
    return {
        "schema_version": "human-preview-review/1.0",
        "artifact_type": "human_preview_review",
        "candidate_id": 1,
        "run_id": "synthetic-preview-run",
        "case_id": "synthetic-case",
        "reviewer": "reviewer-id",
        "reviewed_at": "2026-09-30T12:00:00+08:00",
        "decision": "changes_required",
        "reason_code": "SUBTITLE_OCCLUSION_AND_TIMING_SYNC",
        "findings": [{"code": "subtitle_layout", "observation": "Panel competes with content."}],
        "preview_path": "review-preview.mp4",
        "preview_sha256": "a" * 64,
        "timeline_path": "timeline.json",
        "timeline_sha256": "b" * 64,
        "dependency_hashes": {"timeline.json": "b" * 64, "renderer_project": "c" * 64},
        "final_render_approved": False,
    }


def test_renderer_recovery_candidate_has_independent_owner_and_same_timeline(tmp_path):
    registry = _prime_review_registry(tmp_path)
    assert registry.graph["renderer_project_candidate_3"][1] == registry.graph["renderer_project_candidate_2"][1]
    assert "renderer_project_candidate_3" in registry.graph["review-preview-candidate-3.mp4"][1]
    assert "review-preview-candidate-3.mp4" in registry.graph["human_preview_review_candidate_3.json"][1]
    payload = _valid_review_payload()
    payload.update(candidate_id=3, preview_path="review-preview-candidate-3.mp4", timeline_path="timeline_candidate_2.json")
    review = HumanPreviewReviewV1.model_validate(payload)
    assert not review.final_render_approved


def _prime_review_registry(run_dir):
    run_dir.mkdir(parents=True, exist_ok=True)
    bundle = run_dir / "visual_assets_candidate_3"
    bundle.mkdir()
    (bundle / "index.html").write_text("<main>preview</main>", encoding="utf-8")
    storyboard_sha = sha256_text("{}\n")
    for name in ("human_storyboard_candidate.json", "human_storyboard_approval.json"):
        (run_dir / name).write_text("{}\n", encoding="utf-8")
    bundle_sha = _directory_hash(bundle)
    visual_review = {
        "schema_version": "human-visual-asset-review/1.0",
        "candidate_id": 3,
        "decision": "approved_for_timeline",
        "run_id": "synthetic-preview-run",
        "case_id": "synthetic-case",
        "reviewer": "reviewer-id",
        "reviewed_at": "2026-09-30T12:00:00+08:00",
        "reason_code": "APPROVED_FOR_TIMELINE",
        "rationale": "Synthetic approved visual fixture.",
        "findings": ["Visual binding fixture."],
        "storyboard_sha256": "a" * 64,
        "storyboard_artifact_sha256": storyboard_sha,
        "storyboard_approval_sha256": storyboard_sha,
        "visual_bundle_sha256": bundle_sha,
        "dependency_hashes": {
            "human_storyboard_candidate.json": storyboard_sha,
            "human_storyboard_approval.json": storyboard_sha,
            "visual_assets_candidate_3": bundle_sha,
        },
    }
    (run_dir / "human_visual_asset_review_candidate_3.json").write_text(
        json.dumps(visual_review), encoding="utf-8",
    )
    manifest = RunManifest(
        run_id="synthetic-preview-run",
        created_at="2026-09-30T12:00:00+08:00",
        updated_at="2026-09-30T12:00:00+08:00",
    )
    registry = ArtifactRegistry(run_dir, manifest, playback_preview_mode=True)
    root_name = "human_preview_review_candidate_1.json"
    needed: set[str] = set()
    queue = list(registry.graph[root_name][1])
    while queue:
        name = queue.pop()
        if name in needed:
            continue
        needed.add(name)
        queue.extend(registry.graph[name][1])
    directory_names = {
        name for name in needed
        if name in {"renderer_project", "visual_assets_candidate_3", "visual_assets", "renderer_project_v1b"}
    }
    for name in needed:
        path = run_dir / name
        if name == "timeline.json":
            payload = {
                "run_id": manifest.run_id,
                "audio": {"duration_ms": 1000},
                "composition": {
                    "visual_candidate_id": 3,
                    "visual_bundle_artifact": "visual_assets_candidate_3",
                    "visual_review_artifact": "human_visual_asset_review_candidate_3.json",
                    "preview_only": True,
                },
            }
            data = (json.dumps(payload) + "\n").encode("utf-8")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            actual_hash = sha256_bytes(data)
        elif name == "render_manifest.json":
            payload = {
                "run_id": manifest.run_id,
                "renderer": {
                    "preview_only": True, "full_render_requested": False,
                    "preview_review_status": "pending_human_preview_review",
                },
            }
            data = (json.dumps(payload) + "\n").encode("utf-8")
            path.write_bytes(data)
            actual_hash = sha256_bytes(data)
        elif name in directory_names:
            path.mkdir(parents=True, exist_ok=True)
            if not any(path.iterdir()):
                (path / "index.html").write_text("<main>preview</main>", encoding="utf-8")
            actual_hash = _directory_hash(path)
            registry.manifest.artifacts[name].content_hash = actual_hash
            registry.manifest.artifacts[name].status = "valid"
            registry.manifest.artifacts[name].dependencies = {}
            continue
        elif name == "human_visual_asset_review_candidate_3.json":
            data = path.read_bytes()
            actual_hash = sha256_bytes(data)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = b"{}\n"
            path.write_bytes(data)
            actual_hash = sha256_bytes(data)
        state = registry.manifest.artifacts[name]
        state.status = "valid"
        state.content_hash = actual_hash
        state.dependencies = {}
    for name in needed:
        state = registry.manifest.artifacts[name]
        state.dependencies = {
            dep: registry.manifest.artifacts[dep].content_hash or ""
            for dep in registry.graph[name][1]
        }
    registry.save_manifest()
    return registry


def test_preview_review_rejects_timezone_naive_timestamp() -> None:
    payload = _valid_review_payload()
    payload["reviewed_at"] = "2026-09-30T12:00:00"

    with pytest.raises(ValueError, match="timezone-aware"):
        HumanPreviewReviewV1.model_validate(payload)


def test_preview_review_record_binds_candidate_hash_and_never_approves_final_render(tmp_path) -> None:
    registry = _prime_review_registry(tmp_path)
    preview = tmp_path / "review-preview.mp4"
    preview_bytes = b"synthetic local preview candidate"
    preview.write_bytes(preview_bytes)
    timeline_bytes_before = (tmp_path / "timeline.json").read_bytes()
    alignment_path = tmp_path / "alignment.json"
    alignment_bytes_before = alignment_path.read_bytes()

    review_path = record_human_preview_review(
        tmp_path,
        candidate_id=1,
        reviewer="reviewer-id",
        decision="changes_required",
        reason_code="SUBTITLE_OCCLUSION_AND_TIMING_SYNC",
        findings=[
            {"code": "subtitle_layout", "observation": "The panel competes with approved visuals."},
        ],
        expected_preview_sha256=sha256_bytes(preview_bytes),
    )

    document = HumanPreviewReviewV1.model_validate_json(review_path.read_text(encoding="utf-8"))
    assert document.decision == "changes_required"
    assert document.preview_sha256 == sha256_bytes(preview_bytes)
    assert document.timeline_sha256 == registry.manifest.artifacts["timeline.json"].content_hash
    assert document.final_render_approved is False
    assert datetime.fromisoformat(document.reviewed_at).utcoffset() is not None
    assert (tmp_path / "timeline.json").read_bytes() == timeline_bytes_before
    assert alignment_path.read_bytes() == alignment_bytes_before
    saved_manifest = RunManifest.model_validate_json((tmp_path / "run.json").read_text(encoding="utf-8"))
    assert saved_manifest.artifacts["human_preview_review_candidate_1.json"].status == "valid"


def test_preview_review_rejects_changed_media_before_recording(tmp_path) -> None:
    _prime_review_registry(tmp_path)
    (tmp_path / "review-preview.mp4").write_bytes(b"different preview")

    with pytest.raises(ValueError, match="PREVIEW_MEDIA_HASH_MISMATCH"):
        record_human_preview_review(
            tmp_path,
            candidate_id=1,
            reviewer="reviewer-id",
            decision="changes_required",
            reason_code="SUBTITLE_OCCLUSION_AND_TIMING_SYNC",
            findings=[{"code": "timing", "observation": "Observed playback offset."}],
            expected_preview_sha256="a" * 64,
        )


def test_registry_marks_review_stale_when_reviewed_preview_bytes_change(tmp_path) -> None:
    registry = _prime_review_registry(tmp_path)
    preview = tmp_path / "review-preview.mp4"
    preview.write_bytes(b"reviewed bytes")
    review_path = record_human_preview_review(
        tmp_path,
        candidate_id=1,
        reviewer="reviewer-id",
        decision="changes_required",
        reason_code="SUBTITLE_OCCLUSION_AND_TIMING_SYNC",
        findings=[{"code": "timing", "observation": "Observed playback offset."}],
        expected_preview_sha256=sha256_bytes(b"reviewed bytes"),
    )
    (tmp_path / "review-preview.mp4").write_bytes(b"mutated bytes")

    fresh_manifest = RunManifest.model_validate_json((tmp_path / "run.json").read_text(encoding="utf-8"))
    fresh_registry = ArtifactRegistry(tmp_path, fresh_manifest)
    with pytest.raises(ArtifactConflictError, match="preview media binding is invalid"):
        fresh_registry.validate("human_preview_review_candidate_1.json")
    assert fresh_registry.manifest.artifacts["human_preview_review_candidate_1.json"].status == "stale"
