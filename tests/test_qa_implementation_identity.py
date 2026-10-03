"""Implementation upgrades preserve audit history without opening future gates."""
from datetime import datetime, timezone
import json

import pytest

from fanglei.artifacts import sha256_bytes
from fanglei.errors import ArtifactConflictError
from test_final_render import source_run, _approve, _request, _snapshot
from test_final_video_qa import _register_passed_qa_stub


def ready_history(root, *, approved=False):
    from fanglei.final_render import prepare_final_render, record_final_video_candidate, _registry
    _approve(root)
    request = _request(root)
    manifest = prepare_final_render(root)
    output = root / "synthetic-export.mp4"
    output.write_bytes(b"\x00\x00\x00\x18ftypmp42synthetic-export")
    record_final_video_candidate(root, output,
        expected_request_sha256=sha256_bytes(request.read_bytes()),
        expected_manifest_sha256=sha256_bytes(manifest.read_bytes()))
    qa_path = _register_passed_qa_stub(root)
    reg = _registry(root)
    raw = json.loads(qa_path.read_text())
    raw.update(schema_version="final-video-qa/1.1", qa_owner_version="1.1",
               attempt_number=1, previous_qa=None, implementation_sha256="a" * 64)
    reg.write_json(qa_path.name, raw, "final_video_qa", force=True)
    if approved:
        from fanglei.final_video_qa import HumanFinalVideoReviewV1
        review = HumanFinalVideoReviewV1(
            run_id=raw["run_id"], case_id=raw["case_id"],
            candidate_sha256=raw["candidate"]["sha256"],
            qa_sha256=reg.manifest.artifacts[qa_path.name].content_hash,
            request_sha256=raw["request"]["sha256"], reviewer="fixture-human",
            decision="approved", reviewed_at=datetime.now(timezone.utc), rationale="Historical explicit decision.")
        reg.write_json("human_final_video_review.json", review.model_dump(mode="json"), "human_final_video_review")
    reg.save_manifest()
    return qa_path


@pytest.mark.parametrize("newline", [b"\n", b"\r\n", b"\r"])
def test_v2_identity_normalizes_only_newlines(tmp_path, newline):
    import fanglei.final_video_qa as owner
    baseline = tmp_path / "baseline"
    variant = tmp_path / "variant"
    baseline.mkdir(); variant.mkdir()
    for name in ("final_video_qa.py", "final_video_probe.mjs"):
        text = b"# comment\n  value = 'text'\n"
        (baseline / name).write_bytes(text)
        (variant / name).write_bytes(text.replace(b"\n", newline))
    assert owner.qa_implementation_identity(baseline) == owner.qa_implementation_identity(variant)


@pytest.mark.parametrize("changed", [b"# comment\n  value = 'other'\n", b"# comment\n  value = 'text'", b"# comment\n value = 'text'\n"])
def test_v2_identity_keeps_content_whitespace_and_trailing_newline(tmp_path, changed):
    import fanglei.final_video_qa as owner
    for name in ("final_video_qa.py", "final_video_probe.mjs"):
        (tmp_path / name).write_bytes(b"# comment\n  value = 'text'\n")
    old = owner.qa_implementation_identity(tmp_path)
    (tmp_path / "final_video_qa.py").write_bytes(changed)
    assert owner.qa_implementation_identity(tmp_path).sha256 != old.sha256


def test_legacy_passed_qa_is_superseded_not_stale(source_run):
    import fanglei.final_video_qa as owner
    qa = ready_history(source_run)
    before = _snapshot(source_run)
    assert owner.derive_final_video_qa_status(source_run) == "passed"
    assert owner.derive_final_video_qa_implementation_status(source_run) == "superseded"
    assert owner.qa_execution_identity(qa)["implementation_contract_version"] == "final-video-qa-implementation/1.0"
    assert _snapshot(source_run) == before


def test_legacy_passed_qa_cannot_open_new_human_approval(source_run):
    import fanglei.final_video_qa as owner
    ready_history(source_run)
    before = _snapshot(source_run)
    with pytest.raises(ValueError, match="IMPLEMENTATION_NOT_CURRENT"):
        owner.validate_human_final_video_review_entry(source_run)
    with pytest.raises(ValueError, match="IMPLEMENTATION_NOT_CURRENT"):
        owner.record_human_final_video_review(source_run, reviewer="human", decision="approved", rationale="Review",
            expected_candidate_sha256="0" * 64, expected_qa_sha256="0" * 64)
    assert _snapshot(source_run) == before


def test_existing_approval_survives_implementation_upgrade(source_run):
    import fanglei.final_video_qa as owner
    ready_history(source_run, approved=True)
    before = _snapshot(source_run)
    review = owner.validate_existing_human_final_video_approval(source_run)
    assert review.decision == "approved"
    assert owner.derive_final_video_qa_implementation_status(source_run) == "superseded"
    assert _snapshot(source_run) == before


def test_current_qa_opens_new_gate_but_upgrade_preserves_existing_decision(source_run, monkeypatch):
    import fanglei.final_video_qa as owner
    from fanglei.final_render import _registry
    path = ready_history(source_run)
    payload = json.loads(path.read_text())
    identity = owner.qa_implementation_identity()
    payload.update(schema_version="final-video-qa/1.2", qa_owner_version="1.2",
                   implementation_identity=identity.model_dump(mode="json"), implementation_sha256=identity.sha256)
    reg = _registry(source_run)
    reg.write_json(path.name, payload, "final_video_qa", force=True)
    reg.save_manifest()
    entry = owner.validate_human_final_video_review_entry(source_run)
    assert owner.derive_final_video_qa_implementation_status(source_run) == "current"
    approval = owner.record_human_final_video_review(source_run, reviewer="fixture-human", decision="approved",
        rationale="Explicit review.", expected_candidate_sha256=entry.candidate_sha256,
        expected_qa_sha256=entry.qa_sha256)
    before = _snapshot(source_run)
    monkeypatch.setattr(owner, "_implementation_sha256", lambda: "f" * 64)
    assert owner.derive_final_video_qa_status(source_run) == "passed"
    assert owner.derive_final_video_qa_implementation_status(source_run) == "superseded"
    assert owner.validate_existing_human_final_video_approval(source_run).decision == "approved"
    assert approval.read_bytes() == before[str(approval.relative_to(source_run))]
    with pytest.raises(ValueError, match="IMPLEMENTATION_NOT_CURRENT"):
        owner.validate_human_final_video_review_entry(source_run)
    assert _snapshot(source_run) == before


def test_new_qa_execution_records_v2_identity_at_external_probe_boundary(source_run, monkeypatch, tmp_path):
    """Probe I/O is external; the real owner computes/writes its immutable failed report."""
    import fanglei.final_video_qa as owner
    from fanglei.final_render import _registry
    from types import SimpleNamespace
    ready_history(source_run)
    # An explicit re-evaluation of a historical failed report, not real case media.
    reg = _registry(source_run)
    raw = reg.read_json("final_video_qa.json")
    raw.update(result="failed", checks=[{"check_id":"decode", "status":"fail", "blocking":True,
        "summary":"Historical external decoder failure.", "evidence":{}}])
    reg.write_json("final_video_qa.json", raw, "final_video_qa", force=True)
    reg.save_manifest()
    old = (source_run / "final_video_qa.json").read_bytes()
    candidate = (source_run / "final_video_candidate.json").read_bytes()
    executable = tmp_path / "probe-tool"
    executable.write_bytes(b"synthetic external probe executable")
    monkeypatch.setattr(owner, "_node_tools", lambda *args: ("synthetic-node", "synthetic-module", "synthetic-browser"))
    monkeypatch.setattr(owner, "_ffprobe_tool", lambda *args: executable)
    def subprocess_boundary(command, **kwargs):
        if command[0] == "synthetic-node":
            return SimpleNamespace(returncode=0, stdout=json.dumps({"final":{}, "preview":{}, "full_decode":{}, "samples":[]}), stderr="")
        return SimpleNamespace(returncode=1, stdout="", stderr="Synthetic decode failure")
    monkeypatch.setattr(owner.subprocess, "run", subprocess_boundary)
    path = owner.run_final_video_qa(source_run, reevaluate=True, expected_previous_qa_sha256=sha256_bytes(old))
    report = json.loads(path.read_text())
    assert report["schema_version"] == "final-video-qa/1.2"
    assert report["implementation_identity"]["implementation_contract_version"] == "final-video-qa-implementation/2.0"
    assert report["implementation_sha256"] == owner.qa_implementation_identity().sha256
    assert report["result"] == "failed"
    assert owner.derive_final_video_qa_implementation_status(source_run) == "current"
    assert (source_run / "final_video_qa.json").read_bytes() == old
    assert (source_run / "final_video_candidate.json").read_bytes() == candidate


@pytest.mark.parametrize("name", ["final.mp4", "final_video_qa.json", "final_video_candidate.json", "human_final_video_review.json"])
def test_existing_approval_rejects_changed_bound_bytes(source_run, name):
    import fanglei.final_video_qa as owner
    ready_history(source_run, approved=True)
    path = source_run / name
    path.write_bytes(path.read_bytes() + b"changed")
    before = _snapshot(source_run)
    with pytest.raises((ValueError, ArtifactConflictError)):
        owner.validate_existing_human_final_video_approval(source_run)
    assert _snapshot(source_run) == before
