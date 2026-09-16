import json

import pytest

from fanglei.artifact_registry import ARTIFACT_GRAPH, ArtifactRegistry
from fanglei.artifacts import sha256_text
from fanglei.errors import ArtifactConflictError
from fanglei.models import RunManifest


def _registry(tmp_path):
    manifest = RunManifest(
        run_id="2026-09-14-001-voice",
        created_at="2026-09-14T00:00:00+08:00",
        updated_at="2026-09-14T00:00:00+08:00",
    )
    return ArtifactRegistry(tmp_path, manifest)


def _mark_text_valid(registry, name, value="{}\n"):
    path = registry.run_dir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    registry.manifest.artifacts[name].status = "valid"
    registry.manifest.artifacts[name].content_hash = sha256_text(value)
    registry.manifest.artifacts[name].dependencies = {}


def test_v05_artifacts_have_unique_owners_and_dependencies() -> None:
    assert ARTIFACT_GRAPH["narration.json"] == ("narration_generation", ("script.json",))
    assert ARTIFACT_GRAPH["audio/narration.wav"][0] == "audio_generation"
    assert ARTIFACT_GRAPH["audio/quality.json"] == (
        "audio_generation", ("audio/narration.wav", "audio/metadata.json")
    )
    assert ARTIFACT_GRAPH["audio/review.json"] == (
        "voice_review", ("audio/narration.wav", "audio/quality.json")
    )
    assert ARTIFACT_GRAPH["alignment.json"] == (
        "audio_alignment", (
            "narration.json", "audio/narration.wav", "audio/metadata.json",
            "audio/quality.json", "audio/review.json",
        )
    )
    assert ARTIFACT_GRAPH["timeline.json"] == (
        "timeline_compilation",
        ("alignment.json", "storyboard.json", "visual_beats.json", "audio/metadata.json"),
    )
    assert ARTIFACT_GRAPH["renderer_project"][0] == "nikola_adaptation"
    assert ARTIFACT_GRAPH["render_qa.json"][0] == "render_preflight"


def test_registry_validates_binary_audio_hash(tmp_path) -> None:
    registry = _registry(tmp_path)
    _mark_text_valid(registry, "narration.json")
    _mark_text_valid(registry, "narration.txt", "voice")
    registry.write_bytes("audio/narration.wav", b"RIFF-test", "audio_generation")
    registry.validate("audio/narration.wav")

    (tmp_path / "audio" / "narration.wav").write_bytes(b"changed")
    with pytest.raises(ArtifactConflictError, match="hash changed"):
        registry.validate("audio/narration.wav")


def test_registry_hashes_renderer_project_tree_and_detects_changes(tmp_path) -> None:
    registry = _registry(tmp_path)
    for dependency in ("storyboard.json", "timeline.json"):
        _mark_text_valid(registry, dependency)
    registry.write_directory(
        "renderer_project",
        {"index.html": "<main></main>", "data/timeline.json": json.dumps({"ok": True})},
        "nikola_adaptation",
    )
    registry.validate("renderer_project")

    (tmp_path / "renderer_project" / "index.html").write_text("changed", encoding="utf-8")
    with pytest.raises(ArtifactConflictError, match="hash changed"):
        registry.validate("renderer_project")


def test_directory_artifact_rewrite_replaces_files_without_replacing_root(tmp_path) -> None:
    registry = _registry(tmp_path)
    for dependency in ("storyboard.json", "timeline.json"):
        _mark_text_valid(registry, dependency)
    registry.write_directory(
        "renderer_project", {"old.txt": "old", "assets/audio.wav": b"old"},
        "nikola_adaptation",
    )
    root = tmp_path / "renderer_project"
    registry.write_directory(
        "renderer_project", {"index.html": "new", "assets/audio.wav": b"new"},
        "nikola_adaptation", force=True,
    )
    assert root.is_dir()
    assert not (root / "old.txt").exists()
    assert (root / "index.html").read_text(encoding="utf-8") == "new"
    assert (root / "assets" / "audio.wav").read_bytes() == b"new"
    registry.validate("renderer_project")
