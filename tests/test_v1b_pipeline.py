from __future__ import annotations

from array import array
import hashlib
import io
import json
from pathlib import Path
import wave

from fanglei.artifact_registry import ArtifactRegistry
from fanglei.models import RunManifest
from fanglei.pipeline import _load
from fanglei.providers.alignment import FakeAlignmentProvider
from fanglei.providers.mastering import EngineMasteringResult
from fanglei.providers.narration import FakeNarrationProvider
from fanglei.render_preflight import FakeRendererProbe
from fanglei.v05_models import AudioMetadata, VoiceReviewDocument
from fanglei.v05_pipeline import (
    run_nikola_adaptation, run_timeline_compilation, run_v05_pipeline,
)
from fanglei.v1b_pipeline import (
    run_audio_mastering, run_subtitle_generation, run_v1b_render_adaptation,
)
from tests.test_v05_pipeline import _ready


def _manifest(run):
    return json.loads((run / "run.json").read_text(encoding="utf-8"))


def _v05_run(tmp_path: Path):
    run = _ready(tmp_path)
    run_v05_pipeline(run.name, tmp_path, FakeNarrationProvider(), FakeAlignmentProvider(),
                     FakeRendererProbe())
    # Synthetic, explicitly non-production timing fixture; the production compiler
    # still rejects the deterministic_fake timing source.
    manifest, registry = _load(run)
    alignment = registry.read_json("alignment.json")
    alignment["method"] = "test_authored_timing"
    alignment["provider"] = "test_fixture"
    for sentence in alignment["sentences"]:
        sentence["timing_source"] = "native_timestamp"
    registry.write_json("alignment.json", alignment, "audio_alignment", force=True)
    registry.save_manifest()
    return run


def _real_wav() -> bytes:
    samples = array("h", [7000 if i % 60 < 30 else -7000 for i in range(48000)])
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(24000)
        stream.writeframes(samples.tobytes())
    return output.getvalue()


def _replace_with_approved_real_audio(run: Path):
    manifest, registry = _load(run)
    audio = _real_wav(); sha = hashlib.sha256(audio).hexdigest()
    registry.write_bytes("audio/narration.wav", audio, "audio_generation", force=True)
    metadata = AudioMetadata(schema_version="5.1", sample_rate_hz=24000, duration_ms=2000,
                             sha256=sha, provider="real-test", provider_type="real",
                             voice_id="voice")
    registry.write_json("audio/metadata.json", metadata.model_dump(mode="json"),
                        "audio_generation", force=True)
    from fanglei.audio_quality import analyze_audio_quality
    quality = analyze_audio_quality(audio, sha, "real-test", "real")
    registry.write_json("audio/quality.json", quality.model_dump(mode="json"),
                        "audio_generation", force=True)
    review = VoiceReviewDocument(run_id=run.name, audio_sha256=sha, status="approved",
                                 reviewer="human", reviewed_at="2026-09-21T00:00:00Z",
                                 voice_approved=True, rate_approved=True, pauses_approved=True,
                                 number_pronunciation_approved=True)
    registry.write_json("audio/review.json", review.model_dump(mode="json"), "voice_review", force=True)
    registry.save_manifest()


class SameAudioEngine:
    name = "same-audio-test"
    def master(self, source_path, config):
        return EngineMasteringResult(
            audio_bytes=source_path.read_bytes(), engine=self.name, method="ebu_r128_two_pass",
            input_integrated_lufs=-20, input_true_peak_dbtp=-7,
            output_integrated_lufs=-16, output_true_peak_dbtp=-1.2,
            output_codec="pcm_s16le", output_format="wav", output_sample_rate_hz=24000,
            output_channels=1)


def test_subtitle_stage_is_independently_rerunnable(tmp_path: Path):
    run = _v05_run(tmp_path)
    run_subtitle_generation(run.name, tmp_path)
    before = _manifest(run)
    run_subtitle_generation(run.name, tmp_path)
    after = _manifest(run)
    assert after["artifacts"]["subtitle_track.json"]["status"] == "valid"
    assert after["stages"]["subtitle_generation"]["attempts"] == before["stages"]["subtitle_generation"]["attempts"]


def test_audio_mastering_stage_writes_pair_without_touching_subtitles(tmp_path: Path):
    run = _v05_run(tmp_path)
    _replace_with_approved_real_audio(run)
    manifest, registry = _load(run)
    alignment = json.loads((run / "alignment.json").read_text(encoding="utf-8"))
    alignment["audio_sha256"] = registry.read_json("audio/metadata.json")["sha256"]
    alignment["audio_duration_ms"] = 2000
    for index, sentence in enumerate(alignment["sentences"]):
        sentence["start_ms"] = index * 150
        sentence["end_ms"] = index * 150 + 100
    # This test verifies stage independence, not alignment generation.
    registry.write_json("alignment.json", alignment, "audio_alignment", force=True)
    registry.save_manifest()
    run_subtitle_generation(run.name, tmp_path)
    run_audio_mastering(run.name, tmp_path, SameAudioEngine())
    manifest = _manifest(run)
    assert manifest["artifacts"]["subtitle_track.json"]["status"] == "valid"
    assert manifest["artifacts"]["audio/mastered_narration.wav"]["status"] == "valid"
    assert manifest["artifacts"]["audio_mastering.json"]["status"] == "valid"


def test_v1b_adaptation_layers_subtitles_on_generic_nikola_project(tmp_path: Path):
    run = _v05_run(tmp_path)
    _replace_with_approved_real_audio(run)
    manifest, registry = _load(run)
    alignment = json.loads((run / "alignment.json").read_text(encoding="utf-8"))
    audio = registry.read_json("audio/metadata.json")
    rows = alignment["sentences"]
    for index, row in enumerate(rows):
        row["start_ms"] = round(index * audio["duration_ms"] / len(rows))
        row["end_ms"] = (round((index + 1) * audio["duration_ms"] / len(rows)))
        row["timing_source"] = "native_timestamp"
    alignment["audio_sha256"] = audio["sha256"]
    alignment["audio_duration_ms"] = audio["duration_ms"]
    registry.write_json("alignment.json", alignment, "audio_alignment", force=True)
    registry.save_manifest()
    run_timeline_compilation(run.name, tmp_path, force=True)
    run_nikola_adaptation(run.name, tmp_path, force=True)
    run_subtitle_generation(run.name, tmp_path, force=True)
    run_audio_mastering(run.name, tmp_path, SameAudioEngine(), force=True)

    run_v1b_render_adaptation(run.name, tmp_path, force=True)

    adapted_html = run / "renderer_project_v1b" / "index.html"
    assert adapted_html.is_file()
    assert "installFangleiSubtitles" in adapted_html.read_text(encoding="utf-8")
    assert (run / "renderer_project_v1b" / "assets" / "mastered_narration.wav").is_file()
    assert not (run / "renderer_project_v1a").exists()


def test_alignment_change_stales_subtitle_and_v1b_renderer_only(tmp_path: Path):
    run = _v05_run(tmp_path); run_subtitle_generation(run.name, tmp_path)
    manifest, registry = _load(run)
    manifest.artifacts["renderer_project_v1b"].status = "valid"
    manifest.artifacts["audio/mastered_narration.wav"].status = "valid"
    registry.save_manifest()
    alignment = registry.read_json("alignment.json")
    alignment["confidence"] = .98
    registry.write_json("alignment.json", alignment, "audio_alignment", force=True)
    registry.save_manifest()
    after = _manifest(run)
    assert after["artifacts"]["subtitle_track.json"]["status"] == "stale"
    assert after["artifacts"]["renderer_project_v1b"]["status"] == "stale"
    assert after["artifacts"]["audio/mastered_narration.wav"]["status"] == "valid"
