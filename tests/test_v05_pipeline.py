import json
from pathlib import Path
import pytest

from fanglei.artifact_registry import ArtifactRegistry
from fanglei.models import RunManifest
from fanglei.providers.alignment import FakeAlignmentProvider
from fanglei.providers.narration import FakeNarrationProvider
from fanglei.render_preflight import FakeRendererProbe
from fanglei.v05_pipeline import run_v05_pipeline
from fanglei.v05_pipeline import run_voice_generation, approve_voice_run
from fanglei.v05_models import NarrationSynthesisConfig
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


def test_real_audio_replaces_fake_and_stops_before_alignment(tmp_path) -> None:
    import io
    import struct
    import wave
    from fanglei.providers.narration import NarrationAudioResult

    class RealProvider:
        name = "mock_real"
        model = "test-sine"
        provider_type = "real"

        def synthesize(self, request, config):
            output = io.BytesIO()
            with wave.open(output, "wb") as stream:
                stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(24000)
                stream.writeframes(struct.pack("<h", 7000) * 24000 * 2)
            return NarrationAudioResult(audio_bytes=output.getvalue())

    run = _ready(tmp_path)
    run_v05_pipeline(run.name, tmp_path, FakeNarrationProvider(), FakeAlignmentProvider(),
                     FakeRendererProbe())
    narration_before = (run / "narration.json").read_bytes()
    text_before = (run / "narration.txt").read_bytes()
    before = _manifest(run)
    run_voice_generation(run.name, tmp_path, RealProvider(),
                         NarrationSynthesisConfig(voice_id="configured"), force=True)
    after = _manifest(run)
    assert (run / "narration.json").read_bytes() == narration_before
    assert (run / "narration.txt").read_bytes() == text_before
    assert after["status"] == "voice_review_pending"
    assert after["artifacts"]["audio/quality.json"]["status"] == "valid"
    for name in ("audio/review.json", "alignment.json", "timeline.json", "renderer_project",
                 "render_manifest.json", "preflight_report.json", "render_qa.json"):
        assert after["artifacts"][name]["status"] in {"missing", "stale"}
    assert after["stages"]["audio_alignment"]["attempts"] == before["stages"]["audio_alignment"]["attempts"]


def test_failed_real_silent_replacement_never_leaves_fake_audio_valid(tmp_path) -> None:
    class SilentReal(FakeNarrationProvider):
        name = "silent_real_mock"
        provider_type = "real"

    run = _ready(tmp_path)
    run_v05_pipeline(run.name, tmp_path, FakeNarrationProvider(), FakeAlignmentProvider(),
                     FakeRendererProbe(), stop_after="audio_generation")
    with pytest.raises(ValueError, match="AUDIO_SILENT"):
        run_voice_generation(run.name, tmp_path, SilentReal(),
                             NarrationSynthesisConfig(voice_id="configured"), force=True)
    manifest = _manifest(run)
    for name in ("audio/narration.wav", "audio/metadata.json", "audio/quality.json"):
        assert manifest["artifacts"][name]["status"] != "valid"
    assert manifest["stages"]["audio_generation"]["status"] == "failed"


def test_real_generation_requires_force_when_audio_already_valid(tmp_path) -> None:
    class RealMock(FakeNarrationProvider):
        provider_type = "real"
    run = _ready(tmp_path)
    run_v05_pipeline(run.name, tmp_path, FakeNarrationProvider(), FakeAlignmentProvider(),
                     FakeRendererProbe(), stop_after="audio_generation")
    with pytest.raises(ValueError, match="AUDIO_ALREADY_VALID_USE_FORCE"):
        run_voice_generation(run.name, tmp_path, RealMock(),
                             NarrationSynthesisConfig(voice_id="voice"))


def test_legacy_full_pipeline_cannot_run_real_voice_without_manual_approval(tmp_path) -> None:
    class RealMock(FakeNarrationProvider):
        provider_type = "real"
    run = _ready(tmp_path)
    with pytest.raises(ValueError, match="PRODUCTION_VOICE_REQUIRES_AUDIO_ONLY"):
        run_v05_pipeline(run.name, tmp_path, RealMock(), FakeAlignmentProvider(),
                         FakeRendererProbe())


def test_audio_regeneration_invalidates_approved_hash(tmp_path) -> None:
    import io
    import struct
    import wave
    from fanglei.providers.narration import NarrationAudioResult

    class RealProvider:
        name = "mock_real"
        model = "test"
        provider_type = "real"

        def __init__(self, amplitude):
            self.amplitude = amplitude

        def synthesize(self, request, config):
            output = io.BytesIO()
            with wave.open(output, "wb") as stream:
                stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(24000)
                stream.writeframes(struct.pack("<h", self.amplitude) * 24000 * 2)
            return NarrationAudioResult(audio_bytes=output.getvalue())

    run = _ready(tmp_path)
    run_v05_pipeline(run.name, tmp_path, FakeNarrationProvider(), FakeAlignmentProvider(),
                     FakeRendererProbe(), stop_after="narration_generation")
    config = NarrationSynthesisConfig(voice_id="real-voice")
    run_voice_generation(run.name, tmp_path, RealProvider(7000), config)
    approve_voice_run(run.name, tmp_path, reviewer="human", voice=True, rate=True,
                      pauses=True, number_pronunciation=True)
    before = _manifest(run)
    assert before["artifacts"]["audio/review.json"]["status"] == "valid"
    run_voice_generation(run.name, tmp_path, RealProvider(8000), config, force=True)
    after = _manifest(run)
    assert after["artifacts"]["audio/review.json"]["status"] == "stale"
    assert after["status"] == "voice_review_pending"
