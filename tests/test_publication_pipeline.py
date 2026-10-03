"""Synthetic publication lifecycle contracts; no release media is rendered."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from fanglei.artifacts import sha256_bytes
from fanglei.errors import ArtifactConflictError
from test_final_render import _snapshot
from test_final_render import source_run as source_run_fixture
from test_qa_implementation_identity import ready_history
from test_publication_package import OVERLAYS, prepare as prepare_package


@pytest.fixture(scope="module")
def approved_run_template(tmp_path_factory):
    root = source_run_fixture.__wrapped__(tmp_path_factory.mktemp("publication-approved-template"))
    package = root / "renderer_project_candidate_3"
    html = ('<html><body><section id="scene_001" data-source-ids="source">Source footer</section>'
            + OVERLAYS + '<div id="subtitle-layer"><span id="subtitle-text"></span></div>'
            + '<script>{"motion":[],"duration_ms":1000}</script></body></html>')
    (package / "review-preview.html").write_text(html, encoding="utf-8", newline="\n")
    from fanglei.artifact_registry import _directory_hash
    from fanglei.final_render import _registry
    registry = _registry(root, 3)
    registry.manifest.artifacts["renderer_project_candidate_3"].content_hash = _directory_hash(package)
    for state in registry.manifest.artifacts.values():
        if "renderer_project_candidate_3" in state.dependencies:
            state.dependencies["renderer_project_candidate_3"] = registry.manifest.artifacts[
                "renderer_project_candidate_3"
            ].content_hash
    registry.save_manifest()
    ready_history(root, approved=True)
    prepare_package(root)
    return root


@pytest.fixture
def approved_run(tmp_path, approved_run_template):
    root = tmp_path / "approved-run"
    shutil.copytree(approved_run_template, root)
    return root


def _create_request(root: Path, *, output_path="release/v-test/demo.mp4"):
    from fanglei.publication_render import create_publication_render_request

    package_sha = sha256_bytes((root / "publication_renderer_package.json").read_bytes())
    candidate_sha = sha256_bytes((root / "final_video_candidate.json").read_bytes())
    media_sha = sha256_bytes((root / "final.mp4").read_bytes())
    approval_sha = sha256_bytes((root / "human_final_video_review.json").read_bytes())
    return create_publication_render_request(
        root, release_version="v-test", asset_filename=Path(output_path).name,
        expected_package_sha256=package_sha, expected_candidate_sha256=candidate_sha,
        expected_final_media_sha256=media_sha, expected_approval_sha256=approval_sha,
    )


def _fake_toolchain(root, monkeypatch):
    import fanglei.publication_render as owner

    tool_dir = root / "synthetic-toolchain"
    tool_dir.mkdir(exist_ok=True)
    ffmpeg = tool_dir / "ffmpeg.exe"
    ffprobe = tool_dir / "ffprobe.exe"
    ffmpeg.write_bytes(b"synthetic-tool-identity-ffmpeg")
    ffprobe.write_bytes(b"synthetic-tool-identity-ffprobe")
    environment = SimpleNamespace(
        hyperframes_command=("synthetic-hyperframes",), node="synthetic-node",
        ffmpeg=str(ffmpeg), ffprobe=str(ffprobe),
    )
    monkeypatch.setattr(owner, "_render_toolchain", lambda: (environment, str(ffmpeg), str(ffprobe)))
    return environment


def _passing_probe():
    checks = {
        key: True for key in (
            "media_exists", "container_decode", "full_video_decode", "full_audio_decode", "video_stream", "audio_stream",
            "video_dimensions", "frame_rate", "frame_count", "video_codec", "audio_codec", "duration",
            "scene_coverage", "subtitle_coverage", "subtitle_text_unchanged", "subtitle_timing",
            "audio_equivalence", "source_footer",
            "opening", "ending", "subtitle_geometry", "subtitle_clipping", "subtitle_overflow",
            "black_frame_regression", "overlay_absence",
            "final_publication_comparison",
        )
    }
    return {"comparison": {"checks": checks}, "full_decode": {"video": True, "audio": True}}


def test_render_request_is_hash_bound_and_separate_from_final(approved_run):
    from fanglei.publication_render import validate_publication_render_request

    root = approved_run
    before = _snapshot(root)
    request_path = _create_request(root)
    request = validate_publication_render_request(root)
    assert request_path.name == "publication_render_request.json"
    assert request.schema_version == "publication-render-request/1.0"
    assert request.output_path == "release/v-test/demo.mp4"
    assert request.presentation_mode == "publication"
    assert request.accepted_final_media.path == "final.mp4"
    assert request.accepted_final_candidate.path == "final_video_candidate.json"
    assert request.human_final_approval.path == "human_final_video_review.json"
    assert request.authorized_visual_differences == ["review_overlay_removal"]
    for name in ("final.mp4", "final_video_candidate.json", "final_video_qa.json", "human_final_video_review.json"):
        assert (root / name).read_bytes() == before[name]


@pytest.mark.parametrize("path", [
    "final.mp4", "review-preview-candidate-3.mp4", "release/../final.mp4",
    "release/v-test/../../final.mp4", "release/v-test/not-an-mp4.txt",
    "release/v-test/final.mp4", "release/v-test/review-preview-candidate-2.mp4",
])
def test_request_rejects_final_preview_or_unsafe_publication_paths(approved_run, path):
    from fanglei.publication_render import PublicationRenderRequestV1

    with pytest.raises(ValueError):
        PublicationRenderRequestV1(
            run_id="synthetic-run", case_id="synthetic-case", release_version="v-test",
            asset_filename=Path(path).name, output_path=path,
            publication_package={"path": "publication_renderer_package.json", "sha256": "a" * 64},
            publication_renderer_package={"path": "renderer_project_publication", "sha256": "b" * 64},
            accepted_final_candidate={"path": "final_video_candidate.json", "sha256": "c" * 64},
            accepted_final_media={"path": "final.mp4", "sha256": "d" * 64},
            human_final_approval={"path": "human_final_video_review.json", "sha256": "e" * 64},
            final_render_request={"path": "final_render_request.json", "sha256": "f" * 64},
            presentation_mode="publication", authorized_visual_differences=["review_overlay_removal"],
            render_configuration={"engine": "hyperframes", "renderer_version": "0.8.20", "entry": "review-preview.html",
                "width": 1080, "height": 1920, "fps": 30, "duration_ms": 1000, "frame_count": 30,
                "package_configuration_sha256": "0" * 64},
            render_configuration_sha256="0" * 64, dependency_hashes={},
            created_at=datetime.now(timezone.utc),
        )


def test_existing_output_collision_fails_before_render_manifest(approved_run, monkeypatch):
    from fanglei.publication_render import run_publication_render

    root = approved_run
    _fake_toolchain(root, monkeypatch)
    _create_request(root)
    output = root / "release/v-test/demo.mp4"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"preexisting")
    with pytest.raises(ArtifactConflictError, match="MEDIA_ALREADY_EXISTS"):
        run_publication_render(root, renderer_runner=lambda *args: pytest.fail("renderer must not run"))
    assert not (root / "publication_render_manifest.json").exists()


def test_human_publication_review_requires_publication_qa(approved_run, monkeypatch):
    from fanglei.publication_render import run_publication_render
    from fanglei.publication_video_qa import validate_human_publication_review_entry

    root = approved_run
    _fake_toolchain(root, monkeypatch)
    _create_request(root)
    run_publication_render(root, renderer_runner=lambda package, output, command, env: output.write_bytes(b"\x00\x00\x00\x18ftypmp42synthetic"))
    with pytest.raises((ValueError, ArtifactConflictError)):
        validate_human_publication_review_entry(root)
    assert not (root / "human_publication_review.json").exists()


def test_synthetic_render_registration_and_qa_preserve_accepted_final(approved_run, monkeypatch):
    import fanglei.publication_video_qa as qa_owner
    from fanglei.publication_render import run_publication_render
    from fanglei.publication_video_qa import run_publication_video_qa, validate_human_publication_review_entry

    root = approved_run
    _fake_toolchain(root, monkeypatch)
    _create_request(root)
    before = {
        name: (root / name).read_bytes()
        for name in ("final.mp4", "final_video_candidate.json", "final_video_qa.json", "human_final_video_review.json")
    }

    def fake_renderer(package_path, temporary_output, command, environment):
        temporary_output.write_bytes(b"\x00\x00\x00\x18ftypmp42synthetic-publication-media")

    media_artifact_path = run_publication_render(root, renderer_runner=fake_renderer)
    media = json.loads(media_artifact_path.read_text(encoding="utf-8"))
    media_path = root / media["path"]
    media_sha = sha256_bytes(media_path.read_bytes())
    assert media_path.relative_to(root).as_posix() == "release/v-test/demo.mp4"
    assert media["schema_version"] == "publication-video/1.0"
    assert media["media_sha256"] == media_sha

    monkeypatch.setattr(qa_owner, "_measure_media", lambda *args, **kwargs: {
        "metadata": {"container": "mp4", "container_duration_seconds": 1.0,
                     "video": {"codec": "h264", "width": 1080, "height": 1920, "fps": 30, "frame_count": 30},
                     "audio": {"codec": "aac", "duration_seconds": 1.0, "sample_rate": 48000, "channels": 2}},
        "full_decode": {"video": True, "audio": True},
        **_passing_probe(),
    })
    qa_path = run_publication_video_qa(root)
    qa = json.loads(qa_path.read_text(encoding="utf-8"))
    assert qa["result"] == "passed"
    assert qa["schema_version"] == "publication-video-qa/1.0"
    assert qa["authorized_visual_differences"] == ["review_overlay_removal"]
    assert qa["publication_media_file"]["sha256"] == media_sha
    entry = validate_human_publication_review_entry(root)
    assert entry.status == "ready_for_human_publication_review"
    for name, content in before.items():
        assert (root / name).read_bytes() == content
    assert not (root / "human_publication_review.json").exists()


@pytest.mark.parametrize("field", [
    "media_exists", "container_decode", "full_video_decode", "full_audio_decode", "video_stream", "audio_stream",
    "video_dimensions", "frame_rate", "frame_count", "video_codec", "audio_codec", "duration",
    "scene_coverage", "subtitle_coverage", "subtitle_text_unchanged", "subtitle_timing",
    "audio_equivalence", "source_footer",
    "opening", "ending", "subtitle_geometry", "subtitle_clipping", "subtitle_overflow",
    "black_frame_regression", "overlay_absence",
    "final_publication_comparison",
])
def test_any_publication_qa_blocker_closes_review_gate(approved_run, monkeypatch, field):
    import fanglei.publication_video_qa as qa_owner
    from fanglei.publication_video_qa import run_publication_video_qa, validate_human_publication_review_entry
    from fanglei.publication_render import run_publication_render

    root = approved_run
    _fake_toolchain(root, monkeypatch)
    _create_request(root)
    run_publication_render(root, renderer_runner=lambda package, output, command, env: output.write_bytes(b"\x00\x00\x00\x18ftypmp42synthetic"))
    synthetic = _passing_probe()
    synthetic["comparison"]["checks"][field] = False
    monkeypatch.setattr(qa_owner, "_measure_media", lambda *args, **kwargs: synthetic)
    qa = json.loads(run_publication_video_qa(root).read_text(encoding="utf-8"))
    assert qa["result"] == "failed"
    assert any(check["check_id"] == field and check["status"] == "fail" for check in qa["checks"])
    with pytest.raises(ValueError, match="NOT_PASSED"):
        validate_human_publication_review_entry(root)


def test_publication_qa_attempts_are_immutable_and_human_decision_is_explicit(approved_run, monkeypatch):
    import fanglei.publication_video_qa as qa_owner
    from fanglei.publication_render import run_publication_render
    from fanglei.publication_video_qa import (
        record_human_publication_review, run_publication_video_qa, validate_human_publication_review_entry,
    )
    from fanglei.final_render import _registry

    root = approved_run
    _fake_toolchain(root, monkeypatch)
    _create_request(root)
    media_path = run_publication_render(root, renderer_runner=lambda package, output, command, env: output.write_bytes(b"\x00\x00\x00\x18ftypmp42synthetic"))
    fake = _passing_probe()
    fake["comparison"]["checks"]["media_exists"] = False
    monkeypatch.setattr(qa_owner, "_measure_media", lambda *args, **kwargs: fake)
    first = run_publication_video_qa(root)
    first_bytes = first.read_bytes()
    first_sha = sha256_bytes(first_bytes)
    with pytest.raises(ArtifactConflictError, match="ALREADY_EXISTS"):
        run_publication_video_qa(root)
    # Failed history may be superseded only with an expected exact prior hash.
    with pytest.raises(ArtifactConflictError, match="EXPECTED_PREVIOUS"):
        run_publication_video_qa(root, reevaluate=True, expected_previous_qa_sha256="0" * 64)
    monkeypatch.setattr(qa_owner, "_measure_media", lambda *args, **kwargs: _passing_probe())
    second = run_publication_video_qa(root, reevaluate=True, expected_previous_qa_sha256=first_sha)
    assert second.name == "publication_video_qa_attempt_2.json"
    assert first.read_bytes() == first_bytes
    assert media_path.is_file()
    entry = validate_human_publication_review_entry(root)
    review = record_human_publication_review(
        root, reviewer="synthetic-human", decision="changes_required", rationale="Synthetic review decision.",
        expected_media_sha256=entry.publication_media_sha256, expected_qa_sha256=entry.qa_sha256,
    )
    assert json.loads(review.read_text(encoding="utf-8"))["decision"] == "changes_required"


def test_registry_graph_is_acyclic_and_publication_is_downstream_only(approved_run):
    from fanglei.publication_video_qa import publication_qa_registry

    root = approved_run
    _create_request(root)
    graph = publication_qa_registry(root).graph
    visited = set()
    def visit(name, trail):
        assert name not in trail
        if name in visited:
            return
        for dependency in graph[name][1]:
            visit(dependency, trail | {name})
        visited.add(name)
    for name in graph:
        visit(name, set())
    for name in ("final.mp4", "final_video_candidate.json", "final_video_qa.json", "human_final_video_review.json"):
        assert not any("publication" in dependency for dependency in graph[name][1])
    package = json.loads((root / "publication_renderer_package.json").read_text(encoding="utf-8"))
    assert package["timeline"]["path"] in graph["publication_video_qa.json"][1]
    assert package["subtitle"]["path"] in graph["publication_video_qa.json"][1]
    assert package["audio"]["path"] in graph["publication_video_qa.json"][1]
    assert all(graph[name][0] == expected for name, expected in {
        "publication_render_request.json": "publication_render",
        "publication_media.json": "publication_render",
        "publication_video_qa.json": "publication_video_qa",
        "human_publication_review.json": "human_publication_review",
    }.items())


def test_renderer_toolchain_must_match_prepared_manifest(approved_run, monkeypatch):
    from fanglei.publication_render import prepare_publication_render, run_publication_render

    root = approved_run
    _fake_toolchain(root, monkeypatch)
    _create_request(root)
    prepare_publication_render(root)
    tool = root / "synthetic-toolchain" / "ffmpeg.exe"
    tool.write_bytes(b"changed after render manifest")
    calls = []
    with pytest.raises(ValueError, match="TOOLCHAIN_CHANGED"):
        run_publication_render(root, renderer_runner=lambda *args: calls.append(args))
    assert calls == []
    assert not (root / "release/v-test/demo.mp4").exists()


def test_render_owner_rejects_non_mp4_output_before_media_registration(approved_run, monkeypatch):
    from fanglei.publication_render import run_publication_render

    root = approved_run
    _fake_toolchain(root, monkeypatch)
    _create_request(root)
    with pytest.raises(ValueError, match="OUTPUT_NOT_MP4"):
        run_publication_render(root, renderer_runner=lambda package, output, command, env: output.write_bytes(b"not an mp4"))
    assert not (root / "release/v-test/demo.mp4").exists()
    assert not (root / "publication_media.json").exists()


def test_source_final_change_closes_publication_review_gate(approved_run, monkeypatch):
    import fanglei.publication_video_qa as qa_owner
    from fanglei.publication_render import run_publication_render
    from fanglei.publication_video_qa import run_publication_video_qa, validate_human_publication_review_entry

    root = approved_run
    _fake_toolchain(root, monkeypatch)
    _create_request(root)
    run_publication_render(root, renderer_runner=lambda package, output, command, env: output.write_bytes(b"\x00\x00\x00\x18ftypmp42synthetic"))
    monkeypatch.setattr(qa_owner, "_measure_media", lambda *args, **kwargs: _passing_probe())
    assert json.loads(run_publication_video_qa(root).read_text(encoding="utf-8"))["result"] == "passed"
    candidate = root / "final_video_candidate.json"
    candidate.write_bytes(candidate.read_bytes() + b"stale-source-final")
    with pytest.raises((ValueError, ArtifactConflictError)):
        validate_human_publication_review_entry(root)
    assert not (root / "human_publication_review.json").exists()


def test_approved_for_release_is_an_explicit_human_decision_and_keeps_final_bytes(approved_run, monkeypatch):
    import fanglei.publication_video_qa as qa_owner
    from fanglei.publication_render import run_publication_render
    from fanglei.publication_video_qa import (
        record_human_publication_review, run_publication_video_qa, validate_human_publication_review_entry,
    )

    root = approved_run
    _fake_toolchain(root, monkeypatch)
    _create_request(root)
    frozen_names = ("final.mp4", "final_video_candidate.json", "final_video_qa.json", "human_final_video_review.json")
    frozen = {name: (root / name).read_bytes() for name in frozen_names}
    run_publication_render(root, renderer_runner=lambda package, output, command, env: output.write_bytes(b"\x00\x00\x00\x18ftypmp42synthetic"))
    monkeypatch.setattr(qa_owner, "_measure_media", lambda *args, **kwargs: _passing_probe())
    run_publication_video_qa(root)
    entry = validate_human_publication_review_entry(root)
    path = record_human_publication_review(
        root, reviewer="synthetic-human", decision="approved_for_release", rationale="Explicitly approved synthetic media.",
        expected_media_sha256=entry.publication_media_sha256, expected_qa_sha256=entry.qa_sha256,
    )
    review = json.loads(path.read_text(encoding="utf-8"))
    assert review["decision"] == "approved_for_release"
    assert "published" not in review and "released" not in review
    assert {name: (root / name).read_bytes() for name in frozen_names} == frozen
