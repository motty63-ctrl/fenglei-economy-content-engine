"""Offline final export contracts; all media and cases are synthetic."""
from __future__ import annotations

import json

import pytest

from fanglei.artifact_registry import ArtifactRegistry, _directory_hash
from fanglei.artifacts import sha256_bytes
from fanglei.models import RunManifest
from fanglei.errors import ArtifactConflictError
from fanglei.playback_preview import record_human_preview_review
from test_human_preview_review import _prime_review_registry


def _json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def _snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.fixture
def source_run(tmp_path):
    reg = _prime_review_registry(tmp_path)
    needed = set()
    queue = list(reg.graph["timeline_candidate_2.json"][1]) + [
        "timeline_candidate_2.json", "renderer_project_candidate_3",
        "render_manifest_candidate_3.json", "review-preview-candidate-3.mp4",
    ]
    while queue:
        name = queue.pop()
        if name in needed:
            continue
        needed.add(name)
        queue.extend(reg.graph[name][1])
    preview_bytes = b"\x00\x00\x00\x18ftypmp42synthetic-preview"
    (tmp_path / "review-preview.mp4").write_bytes(preview_bytes)
    for name in needed:
        p = tmp_path / name
        if name.startswith("renderer_project"):
            p.mkdir(exist_ok=True)
            (p / "review-preview.html").write_text("<main>frozen synthetic scenes</main>")
            _json(p / "package.json", {"scripts": {"render:full": "npx --yes hyperframes@0.8.20 render ."}})
            _json(p / "hyperframes.json", {"media": {"autoProxy": True}})
        elif not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(preview_bytes if name.endswith(".mp4") else b"{}\n")
    _json(tmp_path / "human_preview_review_candidate_1.json", {
        "preview_path": "review-preview.mp4", "preview_sha256": sha256_bytes(preview_bytes),
    })
    def refresh():
        for name in needed:
            p = tmp_path / name
            state = reg.manifest.artifacts[name]
            state.status = "valid"
            state.content_hash = _directory_hash(p) if p.is_dir() else sha256_bytes(p.read_bytes())
        for name in needed:
            reg.manifest.artifacts[name].dependencies = {
                dep: reg.manifest.artifacts[dep].content_hash for dep in reg.graph[name][1]
            }
    refresh()
    from test_playback_timeline import _base_timeline
    timeline = _base_timeline().model_dump(mode="json")
    timeline["run_id"] = reg.manifest.run_id
    comp = timeline["composition"]
    bindings = {
        "visual_bundle_sha256": "visual_assets_candidate_3",
        "visual_review_sha256": "human_visual_asset_review_candidate_3.json",
        "storyboard_artifact_sha256": "human_storyboard_candidate.json",
        "storyboard_approval_sha256": "human_storyboard_approval.json",
        "script_sha256": "script.json", "script_approval_sha256": "human_script_approval.json",
        "audio_sha256": "audio/narration.wav", "audio_review_sha256": "audio/review.json",
        "alignment_sha256": "alignment.json", "subtitle_sha256": "subtitle_track.json",
    }
    comp["dependency_hashes"] = {n: reg.manifest.artifacts[n].content_hash for n in bindings.values()}
    for field, name in bindings.items():
        comp[field] = reg.manifest.artifacts[name].content_hash
    from fanglei.human_storyboard_recovery import canonical_json_sha256
    comp["storyboard_sha256"] = canonical_json_sha256({})
    timeline["audio"]["sha256"] = comp["audio_sha256"]
    _json(tmp_path / "timeline_candidate_2.json", timeline)
    _json(tmp_path / "renderer_project_candidate_3/data/timeline.json", timeline)
    refresh()
    _json(tmp_path / "render_manifest_candidate_3.json", {
        "run_id": reg.manifest.run_id,
        "canvas": {"width": 1080, "height": 1920, "fps": 30},
        "audio": timeline["audio"],
        "inputs": {"timeline": {"path": "timeline_candidate_2.json", "sha256": reg.manifest.artifacts["timeline_candidate_2.json"].content_hash}},
        "renderer": {"candidate_id": 3, "engine": "hyperframes", "preview_entry": "review-preview.html",
            "preview_only": True, "full_render_requested": False,
            "preview_review_status": "pending_human_preview_review", "duration_ms": 1000,
            "fps": 30, "frame_count": 30},
    })
    refresh()
    reg.save_manifest()
    return tmp_path


def _approve(root, decision="approved_for_final_render"):
    return record_human_preview_review(
        root, candidate_id=3, reviewer="synthetic-human", decision=decision,
        reason_code="APPROVED_FOR_FINAL_RENDER", rationale="Explicit synthetic approval.",
        findings=[{"code": "playback", "observation": "Synthetic review complete."}],
        expected_preview_sha256=sha256_bytes((root / "review-preview-candidate-3.mp4").read_bytes()),
    )


def _request(root):
    from fanglei.final_render import create_final_render_request
    review = root / "human_preview_review_candidate_3.json"
    return create_final_render_request(root, candidate_id=3, expected_approval_sha256=sha256_bytes(review.read_bytes()))


def test_offline_final_owner_preserves_preview_and_separates_intent(source_run):
    from fanglei.final_render import prepare_final_render, validate_final_render_request
    _approve(source_run)
    before = _snapshot(source_run)
    request_path = _request(source_run)
    request = validate_final_render_request(source_run)
    manifest_path = prepare_final_render(source_run)
    manifest = json.loads(manifest_path.read_text())
    assert request.output_path == "final.mp4"
    assert request.output_intent == "final_candidate"
    assert request.render_configuration.width == 1080
    assert request.render_configuration.renderer_version == "0.8.20"
    assert manifest["renderer"]["preview_only"] is False
    assert manifest["renderer"]["full_render_requested"] is True
    assert request_path.name == "final_render_request.json"
    for name, value in before.items():
        if name != "run.json":
            assert (source_run / name).read_bytes() == value
    assert not (source_run / "final.mp4").exists()
    assert not (source_run / "final_video_candidate.json").exists()
    assert (source_run / "renderer_project_final/review-preview.html").read_bytes() == (source_run / "renderer_project_candidate_3/review-preview.html").read_bytes()


@pytest.mark.parametrize("decision", [None, "approved_for_review", "changes_required"])
def test_final_request_needs_explicit_final_approval(source_run, decision):
    from fanglei.final_render import create_final_render_request
    if decision is not None:
        _approve(source_run, decision)
    before = _snapshot(source_run)
    with pytest.raises((ValueError, ArtifactConflictError)):
        create_final_render_request(source_run, candidate_id=3, expected_approval_sha256="0" * 64)
    assert _snapshot(source_run) == before


@pytest.mark.parametrize("name", [
    "review-preview-candidate-3.mp4", "timeline_candidate_2.json", "visual_assets_candidate_3/index.html",
    "audio/narration.wav", "script.json", "human_storyboard_candidate.json",
    "renderer_project_candidate_3/review-preview.html", "subtitle_track.json",
    "preview_subtitle_track_candidate_2.json", "human_preview_review_candidate_3.json",
])
def test_changed_approved_input_blocks_final_owner_without_writes(source_run, name):
    from fanglei.final_render import prepare_final_render, validate_final_render_request
    _approve(source_run)
    _request(source_run)
    p = source_run / name
    p.write_bytes(p.read_bytes() + b"changed")
    before = _snapshot(source_run)
    with pytest.raises((ValueError, ArtifactConflictError)):
        validate_final_render_request(source_run)
    with pytest.raises((ValueError, ArtifactConflictError)):
        prepare_final_render(source_run)
    assert _snapshot(source_run) == before


def test_current_request_cannot_transfer_to_another_candidate(source_run):
    from fanglei.final_render import create_final_render_request
    _approve(source_run)
    before = _snapshot(source_run)
    with pytest.raises((ValueError, ArtifactConflictError)):
        create_final_render_request(source_run, candidate_id=2, expected_approval_sha256=sha256_bytes((source_run / "human_preview_review_candidate_3.json").read_bytes()))
    assert _snapshot(source_run) == before


def test_final_candidate_is_pending_and_stales_with_approved_chain(source_run):
    from fanglei.final_render import prepare_final_render, record_final_video_candidate
    _approve(source_run)
    _request(source_run)
    manifest_path = prepare_final_render(source_run)
    output = source_run / "synthetic-render-output.mp4"
    output.write_bytes(b"\x00\x00\x00\x18ftypmp42synthetic-export")
    candidate_path = record_final_video_candidate(
        source_run, output,
        expected_request_sha256=sha256_bytes((source_run / "final_render_request.json").read_bytes()),
        expected_manifest_sha256=sha256_bytes(manifest_path.read_bytes()),
    )
    candidate = json.loads(candidate_path.read_text())
    assert candidate["status"] == "pending_human_final_review"
    assert candidate["human_final_video_review"] == "pending"
    assert candidate["workflow_acceptance"] == "pending"
    from fanglei.final_video_qa import derive_final_video_qa_status
    assert derive_final_video_qa_status(source_run) == "pending"
    m = RunManifest.model_validate_json((source_run / "run.json").read_text())
    reg = ArtifactRegistry(source_run, m)
    assert reg.graph["final.mp4"][0] == "final_render"
    reg.validate("final_video_candidate.json")
    for name in ("review-preview-candidate-3.mp4", "timeline_candidate_2.json", "human_preview_review_candidate_3.json"):
        m2 = m.model_copy(deep=True)
        reg2 = ArtifactRegistry(source_run, m2)
        reg2.invalidate_descendants(name)
        assert reg2.manifest.artifacts["final_video_candidate.json"].status == "stale"


@pytest.mark.parametrize("field,value", [("case_id", "other-case"), ("run_id", "other-run"), ("output_path", "../final.mp4")])
def test_hash_current_but_forged_request_is_rejected(source_run, field, value):
    from fanglei.final_render import validate_final_render_request
    _approve(source_run)
    path = _request(source_run)
    payload = json.loads(path.read_text())
    payload[field] = value
    _json(path, payload)
    m = RunManifest.model_validate_json((source_run / "run.json").read_text())
    m.artifacts[path.name].content_hash = sha256_bytes(path.read_bytes())
    _json(source_run / "run.json", m.model_dump(mode="json"))
    with pytest.raises(ValueError):
        validate_final_render_request(source_run)


@pytest.mark.parametrize("field", ["rationale", "reviewer"])
def test_final_approval_missing_human_identity_or_reason_writes_nothing(source_run, field):
    before = _snapshot(source_run)
    arguments = dict(
        candidate_id=3, reviewer="synthetic-human", decision="approved_for_final_render",
        reason_code="APPROVED_FOR_FINAL_RENDER", rationale="Explicit human approval.",
        findings=[{"code": "playback", "observation": "Reviewed."}],
        expected_preview_sha256=sha256_bytes((source_run / "review-preview-candidate-3.mp4").read_bytes()),
    )
    arguments[field] = " "
    with pytest.raises(ValueError):
        record_human_preview_review(source_run, **arguments)
    assert _snapshot(source_run) == before


@pytest.mark.parametrize("field,value", [
    ("status", "accepted"), ("output_path", "other.mp4"),
    ("human_final_video_review", "approved"), ("workflow_acceptance", "accepted"),
])
def test_final_handoff_rejects_hash_current_but_forged_manifest(source_run, field, value):
    from fanglei.final_render import prepare_final_render, record_final_video_candidate
    _approve(source_run)
    request = _request(source_run)
    manifest = prepare_final_render(source_run)
    data = json.loads(manifest.read_text())
    data[field] = value
    _json(manifest, data)
    m = RunManifest.model_validate_json((source_run / "run.json").read_text())
    m.artifacts[manifest.name].content_hash = sha256_bytes(manifest.read_bytes())
    _json(source_run / "run.json", m.model_dump(mode="json"))
    output = source_run / "export.mp4"
    output.write_bytes(b"\x00\x00\x00\x18ftypmp42synthetic-export")
    before = _snapshot(source_run)
    with pytest.raises(ValueError):
        record_final_video_candidate(source_run, output,
            expected_request_sha256=sha256_bytes(request.read_bytes()),
            expected_manifest_sha256=sha256_bytes(manifest.read_bytes()))
    assert _snapshot(source_run) == before


def test_manifest_dependency_key_order_is_not_approval_identity(source_run):
    from fanglei.final_render import validate_final_render_request
    _approve(source_run)
    _request(source_run)
    path = source_run / "run.json"
    data = json.loads(path.read_text())
    for state in data["artifacts"].values():
        state["dependencies"] = dict(sorted(state["dependencies"].items()))
    _json(path, data)
    assert validate_final_render_request(source_run).preview_candidate_id == 3
