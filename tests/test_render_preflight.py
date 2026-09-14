from pathlib import Path

from fanglei.artifacts import sha256_bytes
from fanglei.nikola_adapter import build_nikola_project
from fanglei.render_preflight import FakeRendererProbe, run_render_preflight
from fanglei.timeline import compile_timeline
from tests.test_timeline import _inputs


def _project(tmp_path: Path):
    alignment, board, beats, audio = _inputs()
    timeline = compile_timeline(alignment, board, beats, audio)
    narration_audio = b"audio"
    timeline.audio["sha256"] = sha256_bytes(narration_audio)
    files, manifest = build_nikola_project(board, timeline, narration_audio)
    project = tmp_path / "renderer_project"
    for relative, value in files.items():
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(value, bytes):
            path.write_bytes(value)
        else:
            path.write_text(value, encoding="utf-8")
    return project, manifest


def test_dry_run_checks_dependencies_and_keeps_probe_media_temporary(tmp_path) -> None:
    project, manifest = _project(tmp_path)
    probe_root = tmp_path / "probe-root"
    preflight, qa = run_render_preflight(
        project, manifest, FakeRendererProbe(), probe_root=probe_root,
    )
    assert preflight["passed"] is True
    assert all(preflight["capabilities"].values())
    assert qa["passed"] is True
    assert qa["temporary_outputs_registered"] is False
    assert not probe_root.exists() or not any(probe_root.rglob("*.mp4"))
    assert not any(project.rglob("*.mp4"))


def test_preflight_fails_when_runtime_capability_is_missing(tmp_path) -> None:
    project, manifest = _project(tmp_path)
    preflight, qa = run_render_preflight(
        project, manifest, FakeRendererProbe(missing="ffmpeg"), probe_root=tmp_path / "probe",
    )
    assert preflight["passed"] is False
    assert "PREFLIGHT_FFMPEG_UNAVAILABLE" in preflight["issues"]
    assert qa["passed"] is False


def test_preflight_requires_hyperframes_configuration(tmp_path) -> None:
    project, manifest = _project(tmp_path)
    (project / "hyperframes.json").unlink(missing_ok=True)
    preflight, qa = run_render_preflight(
        project, manifest, FakeRendererProbe(), probe_root=tmp_path / "probe",
    )
    assert preflight["passed"] is False
    assert "PROJECT_FILE_MISSING:hyperframes.json" in preflight["issues"]
    assert qa["passed"] is False
