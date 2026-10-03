"""Synthetic local MP4 contract tests for immutable final candidate QA."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
from datetime import datetime, timezone

import pytest

from fanglei.artifact_registry import _directory_hash
from fanglei.artifacts import sha256_bytes
from fanglei.errors import ArtifactConflictError
from fanglei.models import RunManifest
from test_final_render import _approve, _json, _request, source_run


@pytest.fixture(scope="session")
def synthetic_media(tmp_path_factory):
    node = os.environ.get("FENGLEI_RENDER_NODE")
    puppeteer = os.environ.get("FENGLEI_PUPPETEER_MODULE")
    browser = os.environ.get("FENGLEI_RENDER_BROWSER")
    if not all((node, puppeteer, browser)):
        pytest.skip("Synthetic MP4 QA requires the installed local Node/Chromium toolchain")
    output = tmp_path_factory.mktemp("final-video-qa-media")
    subprocess.run([
        node, str(Path(__file__).with_name("synthetic_final_media.mjs")), puppeteer, browser, str(output),
    ], check=True, capture_output=True, text=True, timeout=90)
    matching = (output / "matching.mp4").read_bytes()
    preview = output / "approved-preview.mp4"
    preview.write_bytes(matching)
    return {
        "preview": preview,
        "matching": output / "matching.mp4",
        "divergent": output / "divergent.mp4",
        "no-captions": output / "no-captions.mp4",
        "no-audio": output / "no-audio.mp4",
        "wrong-size": output / "wrong-size.mp4",
        "corrupt": output / "corrupt.mp4",
    }


def _ready_candidate(root: Path, media: Path, approved_preview: Path):
    from fanglei.final_render import _registry, prepare_final_render, record_final_video_candidate
    from fanglei.final_video_qa import _mp4_metadata

    # Keep media fixtures small and fast while exercising the same generic QA contract.
    preview_metadata = _mp4_metadata(approved_preview.read_bytes())
    video_metadata = preview_metadata["video"]
    duration_ms = round(preview_metadata["container_duration_seconds"] * 1000)
    timeline_path = root / "timeline_candidate_2.json"
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    timeline["audio"]["duration_ms"] = duration_ms
    timeline["validation"]["actual_audio_duration_ms"] = duration_ms
    layout = timeline["composition"]["subtitle_layout"]
    layout.update({"canvas_width": 320, "canvas_height": 240})
    layout["reserved_zone"].update({"x": 10, "y": 170, "width": 300, "height": 60})
    cues = timeline["composition"]["subtitle_cues"]
    registry = _registry(root, 3)
    timeline["composition"]["subtitle_sha256"] = "0" * 64
    subtitles = {
        "schema_version": "subtitle_track.v1", "run_id": timeline["run_id"],
        "script_id": "synthetic-script", "timing_source": "approved_sentence_alignment",
        "source": {
            "script_path": "script.json", "script_sha256": registry.manifest.artifacts["script.json"].content_hash,
            "alignment_path": "alignment.json", "alignment_sha256": registry.manifest.artifacts["alignment.json"].content_hash,
            "alignment_audio_sha256": registry.manifest.artifacts["audio/narration.wav"].content_hash,
        },
        "layout": layout,
        "cues": [
            {
                "cue_id": cue["cue_id"], "sentence_id": cue["sentence_id"], "text": cue["text"],
                "start_ms": cue["start_ms"], "end_ms": cue["end_ms"],
                "font_size_px": cue["font_size_px"],
                "lines": [{
                    "line_id": "line_01", "text": cue["text"], "start_char": 0,
                    "end_char": len(cue["text"]),
                }],
                "emphasis_spans": [],
            }
            for cue in cues
        ],
        "validation": {
            "passed": True, "sentence_coverage": 1.0, "text_exact_match": True,
            "timing_exact_match": True, "issues": [],
        },
    }
    registry.write_json("subtitle_track.json", subtitles, "subtitle_generation", force=True)
    registry.save_manifest()
    subtitle_sha = registry.manifest.artifacts["subtitle_track.json"].content_hash
    timeline["composition"]["subtitle_sha256"] = subtitle_sha
    timeline["composition"]["dependency_hashes"]["subtitle_track.json"] = subtitle_sha
    package_timeline = root / "renderer_project_candidate_3/data/timeline.json"
    _json(timeline_path, timeline)
    _json(package_timeline, timeline)
    render_manifest_path = root / "render_manifest_candidate_3.json"
    render_manifest = json.loads(render_manifest_path.read_text(encoding="utf-8"))
    render_manifest["canvas"].update({"width": video_metadata["width"], "height": video_metadata["height"],
                                      "fps": round(video_metadata["fps"])})
    render_manifest["inputs"]["timeline"]["sha256"] = sha256_bytes(timeline_path.read_bytes())
    render_manifest["renderer"].update({
        "duration_ms": duration_ms, "fps": round(video_metadata["fps"]),
        "frame_count": video_metadata["frame_count"],
    })
    _json(render_manifest_path, render_manifest)
    manifest = registry.manifest
    needed = set()
    queue = list(registry.graph["timeline_candidate_2.json"][1]) + [
        "timeline_candidate_2.json", "renderer_project_candidate_3",
        "render_manifest_candidate_3.json", "review-preview-candidate-3.mp4",
    ]
    while queue:
        name = queue.pop()
        if name in needed:
            continue
        needed.add(name)
        queue.extend(registry.graph[name][1])
    for name in needed:
        state = manifest.artifacts[name]
        artifact_path = root / name
        state.status = "valid"
        state.content_hash = _directory_hash(artifact_path) if artifact_path.is_dir() else sha256_bytes(artifact_path.read_bytes())
    for name in needed:
        state = manifest.artifacts[name]
        state.dependencies = {dep: manifest.artifacts[dep].content_hash for dep in registry.graph[name][1]}
    registry.save_manifest()

    registry.write_bytes(
        "review-preview-candidate-3.mp4", approved_preview.read_bytes(), "review_preview_render", force=True,
    )
    registry.save_manifest()
    _approve(root)
    request_path = _request(root)
    manifest_path = prepare_final_render(root)
    rendered_output = root / "synthetic-render-output.mp4"
    rendered_output.write_bytes(media.read_bytes())
    candidate_path = record_final_video_candidate(
        root, rendered_output,
        expected_request_sha256=sha256_bytes(request_path.read_bytes()),
        expected_manifest_sha256=sha256_bytes(manifest_path.read_bytes()),
    )
    return candidate_path


def _register_passed_qa_stub(root: Path):
    from fanglei.final_render import FinalVideoCandidateV1, _registry, validate_final_render_request
    from fanglei.final_video_qa import FinalVideoQAReportV1

    registry = _registry(root, 3)
    registry.validate("final_video_candidate.json")
    registry.validate("final.mp4")
    request = validate_final_render_request(root)
    candidate_sha = registry.manifest.artifacts["final_video_candidate.json"].content_hash
    report = FinalVideoQAReportV1(
        run_id=request.run_id, case_id=request.case_id,
        media={"path": "final.mp4", "sha256": registry.manifest.artifacts["final.mp4"].content_hash},
        candidate={"path": "final_video_candidate.json", "sha256": candidate_sha},
        request={"path": "final_render_request.json", "sha256": registry.manifest.artifacts["final_render_request.json"].content_hash},
        human_preview_approval=request.human_preview_approval,
        preview=request.preview, timeline=request.timeline,
        executed_at=datetime.now(timezone.utc), result="passed", checks=[], measurements={},
    )
    path = registry.write_json("final_video_qa.json", report.model_dump(mode="json"), "final_video_qa")
    registry.save_manifest()
    return path


def test_real_synthetic_media_passes_qa_without_mutating_candidate(source_run, synthetic_media):
    from fanglei.final_video_qa import (
        derive_final_video_qa_status, run_final_video_qa, validate_human_final_video_review_entry,
    )

    candidate_path = _ready_candidate(source_run, synthetic_media["matching"], synthetic_media["preview"])
    candidate_bytes = candidate_path.read_bytes()
    candidate_sha = hashlib.sha256(candidate_bytes).hexdigest()
    assert derive_final_video_qa_status(source_run) == "pending"
    with pytest.raises((ValueError, ArtifactConflictError)):
        validate_human_final_video_review_entry(source_run)

    qa_path = run_final_video_qa(source_run)
    qa = json.loads(qa_path.read_text(encoding="utf-8"))
    assert qa["result"] == "passed"
    assert qa["schema_version"] == "final-video-qa/1.2"
    assert qa["implementation_identity"]["implementation_contract_version"] == "final-video-qa-implementation/2.0"
    assert qa["implementation_identity"]["sha256"] == qa["implementation_sha256"]
    assert qa["candidate"]["sha256"] == candidate_sha
    assert {row["check_id"] for row in qa["checks"]} >= {
        "full_media_decode", "video_stream", "audio_stream", "scene_coverage",
        "subtitle_coverage", "preview_final_comparison", "opening_completeness", "ending_completeness",
    }
    assert candidate_path.read_bytes() == candidate_bytes
    assert derive_final_video_qa_status(source_run) == "passed"
    entry = validate_human_final_video_review_entry(source_run)
    assert entry.candidate_sha256 == candidate_sha
    assert entry.qa_sha256 == hashlib.sha256(qa_path.read_bytes()).hexdigest()
    assert not (source_run / "human_final_video_review.json").exists()


@pytest.mark.parametrize(
    ("media_key", "expected_failed_check"),
    [("corrupt", "full_media_decode"), ("no-audio", "audio_stream"), ("wrong-size", "video_dimensions")],
)
def test_media_decode_and_format_failures_block_human_review(
    source_run, synthetic_media, media_key, expected_failed_check,
):
    from fanglei.final_video_qa import run_final_video_qa, validate_human_final_video_review_entry

    candidate = _ready_candidate(source_run, synthetic_media[media_key], synthetic_media["preview"])
    before_candidate = candidate.read_bytes()
    qa_path = run_final_video_qa(source_run)
    qa = json.loads(qa_path.read_text(encoding="utf-8"))
    assert qa["result"] == "failed"
    assert any(row["check_id"] == expected_failed_check and row["status"] == "fail" for row in qa["checks"])
    assert candidate.read_bytes() == before_candidate
    with pytest.raises((ValueError, ArtifactConflictError), match="FINAL_VIDEO_QA_NOT_PASSED"):
        validate_human_final_video_review_entry(source_run)


@pytest.mark.parametrize(
    ("media_key", "expected_failed_check"),
    [("divergent", "preview_final_comparison"), ("no-captions", "subtitle_coverage")],
)
def test_preview_visual_or_subtitle_divergence_is_blocking(
    source_run, synthetic_media, media_key, expected_failed_check,
):
    from fanglei.final_video_qa import run_final_video_qa

    _ready_candidate(source_run, synthetic_media[media_key], synthetic_media["preview"])
    qa = json.loads(run_final_video_qa(source_run).read_text(encoding="utf-8"))
    assert qa["result"] == "failed"
    assert any(row["check_id"] == expected_failed_check and row["status"] == "fail" for row in qa["checks"])


def test_qa_is_write_once_and_candidate_changes_stale_qa_and_review_gate(source_run, synthetic_media):
    from fanglei.final_render import _registry
    from fanglei.final_video_qa import run_final_video_qa, validate_human_final_video_review_entry

    candidate = _ready_candidate(source_run, synthetic_media["matching"], synthetic_media["preview"])
    candidate_sha = sha256_bytes(candidate.read_bytes())
    qa_path = run_final_video_qa(source_run)
    qa_before = qa_path.read_bytes()
    with pytest.raises(ArtifactConflictError, match="FINAL_VIDEO_QA_ALREADY_EXISTS"):
        run_final_video_qa(source_run)

    registry = _registry(source_run, 3)
    candidate_payload = json.loads(candidate.read_text(encoding="utf-8"))
    candidate_payload["run_id"] = "different-synthetic-run"
    registry.write_json("final_video_candidate.json", candidate_payload, "final_render", force=True)
    registry.save_manifest()
    assert registry.manifest.artifacts["final_video_qa.json"].status == "stale"
    with pytest.raises((ValueError, ArtifactConflictError)):
        validate_human_final_video_review_entry(source_run)
    assert candidate.read_bytes() and sha256_bytes(candidate.read_bytes()) != candidate_sha
    assert qa_path.read_bytes() == qa_before


def test_qa_binding_mismatch_is_derived_stale_and_cannot_open_review_gate(source_run, synthetic_media):
    from fanglei.final_render import _registry
    from fanglei.final_video_qa import (
        derive_final_video_qa_status, run_final_video_qa, validate_human_final_video_review_entry,
    )

    _ready_candidate(source_run, synthetic_media["matching"], synthetic_media["preview"])
    qa_path = run_final_video_qa(source_run)
    registry = _registry(source_run, 3)
    payload = json.loads(qa_path.read_text(encoding="utf-8"))
    payload["preview"]["sha256"] = "f" * 64
    registry.write_json("final_video_qa.json", payload, "final_video_qa", force=True)
    registry.save_manifest()

    assert derive_final_video_qa_status(source_run) == "stale"
    with pytest.raises((ValueError, ArtifactConflictError), match="FINAL_VIDEO_QA_APPROVED_INPUT_BINDING_MISMATCH"):
        validate_human_final_video_review_entry(source_run)


@pytest.mark.parametrize("changed_artifact", ["media", "request", "preview_approval"])
def test_upstream_change_stales_qa_and_blocks_final_review(source_run, synthetic_media, changed_artifact):
    from fanglei.final_render import _registry
    from fanglei.final_video_qa import derive_final_video_qa_status, validate_human_final_video_review_entry

    _ready_candidate(source_run, synthetic_media["matching"], synthetic_media["preview"])
    _register_passed_qa_stub(source_run)
    registry = _registry(source_run, 3)
    if changed_artifact == "media":
        registry.write_bytes("final.mp4", b"changed-media", "final_render", force=True)
    elif changed_artifact == "request":
        request = registry.read_json("final_render_request.json")
        request["case_id"] = "changed-case"
        registry.write_json("final_render_request.json", request, "final_render", force=True)
    else:
        name = "human_preview_review_candidate_3.json"
        approval = registry.read_json(name)
        approval["reviewer"] = "changed-reviewer"
        registry.write_json(name, approval, "human_preview_review", force=True)
    registry.save_manifest()

    assert derive_final_video_qa_status(source_run) == "stale"
    with pytest.raises((ValueError, ArtifactConflictError)):
        validate_human_final_video_review_entry(source_run)


def test_human_final_review_owner_records_only_explicit_qa_bound_decision(source_run, synthetic_media):
    from fanglei.final_video_qa import record_human_final_video_review, run_final_video_qa

    _ready_candidate(source_run, synthetic_media["matching"], synthetic_media["preview"])
    with pytest.raises((ValueError, ArtifactConflictError)):
        record_human_final_video_review(
            source_run, reviewer="reviewer", decision="approved", rationale="Reviewed.",
            expected_candidate_sha256="0" * 64, expected_qa_sha256="0" * 64,
        )
    run_final_video_qa(source_run)
    candidate_sha = sha256_bytes((source_run / "final_video_candidate.json").read_bytes())
    qa_sha = sha256_bytes((source_run / "final_video_qa.json").read_bytes())
    review_path = record_human_final_video_review(
        source_run, reviewer="synthetic-reviewer", decision="approved", rationale="Synthetic human decision.",
        expected_candidate_sha256=candidate_sha, expected_qa_sha256=qa_sha,
    )
    review = json.loads(review_path.read_text(encoding="utf-8"))
    assert review["decision"] == "approved"
    assert review["candidate_sha256"] == candidate_sha
    assert review["qa_sha256"] == qa_sha
    assert "v0_2_acceptance" not in review


def test_blocking_failure_cannot_be_labeled_overall_passed():
    from fanglei.final_video_qa import FinalVideoQAReportV1

    payload = {
        "run_id": "synthetic-run", "case_id": "synthetic-case",
        "media": {"path": "final.mp4", "sha256": "a" * 64},
        "candidate": {"path": "final_video_candidate.json", "sha256": "b" * 64},
        "request": {"path": "final_render_request.json", "sha256": "c" * 64},
        "human_preview_approval": {"path": "human_preview_review_candidate_3.json", "sha256": "f" * 64},
        "preview": {"path": "preview.mp4", "sha256": "d" * 64},
        "timeline": {"path": "timeline.json", "sha256": "e" * 64},
        "qa_owner_version": "1.0", "executed_at": datetime(2026, 9, 30, tzinfo=timezone.utc),
        "result": "passed",
        "checks": [{"check_id": "video_stream", "status": "fail", "blocking": True,
                    "summary": "Missing.", "evidence": {}}],
        "measurements": {},
    }
    with pytest.raises(ValueError, match="blocking"):
        FinalVideoQAReportV1.model_validate(payload)


def _historical_failed_qa(root):
    from fanglei.final_render import _registry
    path = _register_passed_qa_stub(root)
    raw = json.loads(path.read_text(encoding='utf-8'))
    raw['result'] = 'failed'
    raw['checks'] = [{'check_id': 'video_stream', 'status': 'fail', 'blocking': True,
                      'summary': 'Historical probe failure.', 'evidence': {'error': 'MP4_BOX_SIZE_INVALID'}}]
    registry = _registry(root, 3)
    registry.write_json('final_video_qa.json', raw, 'final_video_qa', force=True)
    registry.save_manifest()
    return path


def test_reassessment_preserves_failed_history_and_immutable_inputs(source_run, synthetic_media):
    from fanglei.final_video_qa import run_final_video_qa, validate_human_final_video_review_entry
    candidate = _ready_candidate(source_run, synthetic_media['matching'], synthetic_media['preview'])
    old = _historical_failed_qa(source_run)
    before = {path: path.read_bytes() for path in (old, candidate, source_run / 'final.mp4')}
    old_sha = sha256_bytes(before[old])
    with pytest.raises(ArtifactConflictError, match='ALREADY_EXISTS'):
        run_final_video_qa(source_run)
    with pytest.raises((ValueError, ArtifactConflictError), match='EXPECTED_PREVIOUS'):
        run_final_video_qa(source_run, reevaluate=True, expected_previous_qa_sha256='0' * 64)
    path = run_final_video_qa(source_run, reevaluate=True, expected_previous_qa_sha256=old_sha)
    raw = json.loads(path.read_text(encoding='utf-8'))
    assert path.name == 'final_video_qa_attempt_2.json'
    assert raw['result'] == 'passed'
    assert raw['attempt_number'] == 2
    assert raw['previous_qa'] == {'path': 'final_video_qa.json', 'sha256': old_sha}
    assert all(path.read_bytes() == content for path, content in before.items())
    assert validate_human_final_video_review_entry(source_run).qa_sha256 == sha256_bytes(path.read_bytes())
    with pytest.raises(ArtifactConflictError, match='ALREADY_EXISTS'):
        run_final_video_qa(source_run, reevaluate=True, expected_previous_qa_sha256=sha256_bytes(path.read_bytes()))


def test_failed_reassessment_cannot_fall_back_to_prior_passed_gate(source_run, synthetic_media):
    from fanglei.final_video_qa import run_final_video_qa, validate_human_final_video_review_entry
    _ready_candidate(source_run, synthetic_media['divergent'], synthetic_media['preview'])
    old = _historical_failed_qa(source_run)
    path = run_final_video_qa(source_run, reevaluate=True, expected_previous_qa_sha256=sha256_bytes(old.read_bytes()))
    assert json.loads(path.read_text(encoding='utf-8'))['result'] == 'failed'
    with pytest.raises(ValueError, match='NOT_PASSED'):
        validate_human_final_video_review_entry(source_run)
    with pytest.raises(ArtifactConflictError, match='ALREADY_EXISTS'):
        run_final_video_qa(source_run, reevaluate=True, expected_previous_qa_sha256=sha256_bytes(path.read_bytes()))


def test_changed_qa_implementation_closes_current_review_gate(source_run, synthetic_media, monkeypatch):
    import fanglei.final_video_qa as owner
    _ready_candidate(source_run, synthetic_media['matching'], synthetic_media['preview'])
    owner.run_final_video_qa(source_run)
    monkeypatch.setattr(owner, '_implementation_sha256', lambda: 'f' * 64)
    assert owner.derive_final_video_qa_status(source_run) == 'passed'
    assert owner.derive_final_video_qa_implementation_status(source_run) == 'superseded'
    with pytest.raises(ValueError, match='IMPLEMENTATION_NOT_CURRENT'):
        owner.validate_human_final_video_review_entry(source_run)
