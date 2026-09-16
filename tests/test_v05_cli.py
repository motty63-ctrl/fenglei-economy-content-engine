from typer.testing import CliRunner
import io
import struct
import wave

from fanglei.cli import app
from fanglei.providers.alignment import FakeAlignmentProvider
from fanglei.providers.narration import FakeNarrationProvider, NarrationAudioResult
from fanglei.render_preflight import FakeRendererProbe
from fanglei.v05_pipeline import run_v05_pipeline
from tests.test_v05_pipeline import _ready


def test_prepare_renderer_cli_runs_fake_pipeline_without_mp4(tmp_path) -> None:
    run = _ready(tmp_path)
    result = CliRunner().invoke(app, [
        "--runs-dir", str(tmp_path), "prepare-renderer", run.name,
        "--narration-provider", "fake", "--alignment-provider", "fake", "--probe", "fake",
    ])
    assert result.exit_code == 0, result.output
    assert "renderer_ready" in result.output
    assert (run / "render_qa.json").is_file()
    assert not (run / "final.mp4").exists()


def test_generate_voice_cli_rejects_fake_provider(tmp_path) -> None:
    result = CliRunner().invoke(app, [
        "--runs-dir", str(tmp_path), "generate-voice", "run-id",
        "--provider", "fake", "--voice-id", "fake-voice",
    ])
    assert result.exit_code == 2
    assert "PRODUCTION_PROVIDER_REQUIRED" in result.output


def test_mocked_azure_cli_stops_at_listening_checkpoint_and_can_record_approval(
    tmp_path, monkeypatch,
) -> None:
    class MockAzure:
        name = "azure_speech"
        model = "mock-sdk"
        provider_type = "real"

        def synthesize(self, request, config):
            output = io.BytesIO()
            with wave.open(output, "wb") as stream:
                stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(24000)
                stream.writeframes(struct.pack("<h", 7000) * 24000 * 2)
            return NarrationAudioResult(audio_bytes=output.getvalue())

    run = _ready(tmp_path)
    run_v05_pipeline(run.name, tmp_path, FakeNarrationProvider(), FakeAlignmentProvider(),
                     FakeRendererProbe(), stop_after="narration_generation")
    monkeypatch.setattr("fanglei.cli.build_narration_provider",
                        lambda name: MockAzure())
    runner = CliRunner()
    generated = runner.invoke(app, [
        "--runs-dir", str(tmp_path), "generate-voice", run.name,
        "--provider", "azure", "--voice-id", "configured",
    ])
    assert generated.exit_code == 0, generated.output
    assert (run / "audio" / "quality.json").is_file()
    assert not (run / "alignment.json").is_file()
    approved = runner.invoke(app, [
        "--runs-dir", str(tmp_path), "approve-voice", run.name,
        "--confirm-voice", "--confirm-speaking-rate", "--confirm-pauses",
        "--confirm-number-pronunciation",
    ])
    assert approved.exit_code == 0, approved.output
    assert (run / "audio" / "review.json").is_file()
