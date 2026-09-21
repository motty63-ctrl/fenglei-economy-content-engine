from __future__ import annotations

from datetime import datetime, timezone

from fanglei.artifact_registry import ARTIFACT_GRAPH, ArtifactRegistry
from fanglei.artifacts import sha256_bytes
from fanglei.models import RunManifest


def _manifest() -> RunManifest:
    now = datetime.now(timezone.utc).isoformat()
    return RunManifest(run_id="run-001", created_at=now, updated_at=now)


def test_v1b_artifact_ownership_and_dependencies() -> None:
    assert ARTIFACT_GRAPH["subtitle_track.json"] == (
        "subtitle_generation", ("script.json", "alignment.json")
    )
    assert ARTIFACT_GRAPH["audio/mastered_narration.wav"][0] == "audio_mastering"
    assert ARTIFACT_GRAPH["audio_mastering.json"][0] == "audio_mastering"
    assert ARTIFACT_GRAPH["renderer_project_v1b"][0] == "v1b_render_adaptation"
    assert "subtitle_track.json" in ARTIFACT_GRAPH["renderer_project_v1b"][1]
    assert "audio/mastered_narration.wav" in ARTIFACT_GRAPH["renderer_project_v1b"][1]


def test_mastered_wav_is_validated_as_binary(tmp_path) -> None:
    manifest = _manifest()
    registry = ArtifactRegistry(tmp_path, manifest)
    state = manifest.artifacts["audio/mastered_narration.wav"]
    payload = b"RIFF\x00binary-mastered-wave"
    path = tmp_path / "audio" / "mastered_narration.wav"
    path.parent.mkdir(parents=True)
    path.write_bytes(payload)
    state.status = "valid"
    state.content_hash = sha256_bytes(payload)
    state.dependencies = {}

    registry.validate("audio/mastered_narration.wav")
