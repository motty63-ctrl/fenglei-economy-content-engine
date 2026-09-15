import json
from pathlib import Path
import pytest

from fanglei.artifact_registry import ArtifactRegistry
from fanglei.models import RunManifest
from fanglei.providers.alignment import FakeAlignmentProvider
from fanglei.providers.narration import FakeNarrationProvider
from fanglei.render_preflight import FakeRendererProbe
from fanglei.v05_pipeline import run_v05_pipeline
from tests.test_visual_pipeline import _visual_ready_run
from fanglei.providers.visual import DeterministicVisualPlanningProvider
from fanglei.visual_pipeline import run_visual_pipeline


def _ready(tmp_path):
    run = _visual_ready_run(tmp_path)
    run_visual_pipeline(run.name, tmp_path, DeterministicVisualPlanningProvider())
    return run


def _manifest(run):
    return json.loads((run / "run.json").read_text(encoding="utf-8"))


def test_fake_pipeline_writes_every_v05_artifact_and_no_final_mp4(tmp_path) -> None:
    run = _ready(tmp_path)
    run_v05_pipeline(
        run.name, tmp_path, FakeNarrationProvider(), FakeAlignmentProvider(),
        FakeRendererProbe(), voice_id="fake-voice",
    )
    manifest = _manifest(run)
    expected = (
        "narration.json", "narration.txt", "audio/narration.wav", "audio/metadata.json",
        "alignment.json", "timeline.json", "renderer_project", "render_manifest.json",
        "preflight_report.json", "render_qa.json",
    )
    assert all(manifest["artifacts"][name]["status"] == "valid" for name in expected)
    assert manifest["status"] == "renderer_ready"
    assert not (run / "final.mp4").exists()
    assert not any(run.rglob("*.mp4"))
    timeline = json.loads((run / "timeline.json").read_text(encoding="utf-8"))
    audio = json.loads((run / "audio" / "metadata.json").read_text(encoding="utf-8"))
    assert timeline["audio"]["duration_ms"] == audio["duration_ms"]
    assert timeline["validation"]["forced_to_estimate"] is False


def test_pipeline_reuses_valid_stages_by_default(tmp_path) -> None:
    run = _ready(tmp_path)
    args = (run.name, tmp_path, FakeNarrationProvider(), FakeAlignmentProvider(), FakeRendererProbe())
    run_v05_pipeline(*args, voice_id="fake-voice")
    before = _manifest(run)
    run_v05_pipeline(*args, voice_id="fake-voice")
    after = _manifest(run)
    for stage in (
        "narration_generation", "audio_generation", "audio_alignment", "timeline_compilation",
        "nikola_adaptation", "render_preflight",
    ):
        assert after["stages"][stage]["attempts"] == before["stages"][stage]["attempts"]


def test_preflight_succeeds_when_windows_temporarily_locks_empty_probe_root(
    tmp_path, monkeypatch,
) -> None:
    run = _ready(tmp_path)
    original_rmdir = Path.rmdir

    def deny_probe_root_once(path: Path) -> None:
        if path.name == ".render-preflight-temp":
            raise PermissionError("probe root is temporarily locked")
        original_rmdir(path)

    monkeypatch.setattr(Path, "rmdir", deny_probe_root_once)
    run_v05_pipeline(
        run.name, tmp_path, FakeNarrationProvider(), FakeAlignmentProvider(),
        FakeRendererProbe(), voice_id="fake-voice",
    )

    manifest = _manifest(run)
    assert manifest["stages"]["render_preflight"]["status"] == "succeeded"
    assert manifest["artifacts"]["preflight_report.json"]["status"] == "valid"
    assert manifest["artifacts"]["render_qa.json"]["status"] == "valid"


def test_force_alignment_does_not_regenerate_audio(tmp_path) -> None:
    run = _ready(tmp_path)
    providers = (FakeNarrationProvider(), FakeAlignmentProvider(), FakeRendererProbe())
    run_v05_pipeline(run.name, tmp_path, *providers, voice_id="fake-voice")
    before = _manifest(run)
    run_v05_pipeline(run.name, tmp_path, *providers, voice_id="fake-voice",
                     force_stage="audio_alignment")
    after = _manifest(run)
    assert after["stages"]["audio_generation"]["attempts"] == before["stages"]["audio_generation"]["attempts"]
    assert after["stages"]["audio_alignment"]["attempts"] == before["stages"]["audio_alignment"]["attempts"] + 1


def test_narration_change_marks_audio_and_renderer_outputs_stale(tmp_path) -> None:
    run = _ready(tmp_path)
    run_v05_pipeline(run.name, tmp_path, FakeNarrationProvider(), FakeAlignmentProvider(),
                     FakeRendererProbe(), voice_id="fake-voice")
    manifest = RunManifest.model_validate(_manifest(run))
    registry = ArtifactRegistry(run, manifest)
    narration = registry.read_json("narration.json")
    narration["language"] = "zh-CN-x-test"
    registry.write_json("narration.json", narration, "narration_generation", force=True)
    registry.save_manifest()
    after = _manifest(run)
    for artifact in (
        "narration.txt", "audio/narration.wav", "alignment.json", "timeline.json",
        "renderer_project", "render_manifest.json", "preflight_report.json", "render_qa.json",
    ):
        assert after["artifacts"][artifact]["status"] == "stale"


def test_alignment_failure_preserves_valid_audio_for_resume(tmp_path) -> None:
    run = _ready(tmp_path)
    run_v05_pipeline(run.name, tmp_path, FakeNarrationProvider(), FakeAlignmentProvider(),
                     FakeRendererProbe(), voice_id="fake-voice", stop_after="audio_generation")
    with pytest.raises(ValueError, match="ALIGNMENT_LOW_CONFIDENCE"):
        run_v05_pipeline(run.name, tmp_path, FakeNarrationProvider(),
                         FakeAlignmentProvider(confidence=.2), FakeRendererProbe(),
                         voice_id="fake-voice")
    manifest = _manifest(run)
    assert manifest["artifacts"]["audio/narration.wav"]["status"] == "valid"
    assert manifest["artifacts"]["audio/metadata.json"]["status"] == "valid"
    assert manifest["stages"]["audio_alignment"]["status"] == "failed"


def test_voice_change_regenerates_audio_and_downstream_timeline(tmp_path) -> None:
    run = _ready(tmp_path)
    providers = (FakeNarrationProvider(), FakeAlignmentProvider(), FakeRendererProbe())
    run_v05_pipeline(run.name, tmp_path, *providers, voice_id="voice-a")
    before = _manifest(run)
    run_v05_pipeline(run.name, tmp_path, *providers, voice_id="voice-b")
    after = _manifest(run)
    metadata = json.loads((run / "audio" / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["voice_id"] == "voice-b"
    assert after["stages"]["audio_generation"]["attempts"] == before["stages"]["audio_generation"]["attempts"] + 1
    assert after["stages"]["timeline_compilation"]["attempts"] == before["stages"]["timeline_compilation"]["attempts"] + 1
