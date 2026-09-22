from __future__ import annotations

from array import array
import hashlib
import io
from pathlib import Path
import wave

import pytest

from fanglei.audio_mastering import _pcm_measurement, master_audio
from fanglei.providers.mastering import EngineMasteringResult
from fanglei.v05_models import AudioMetadata, VoiceReviewDocument


def _wav() -> bytes:
    rate = 24000
    samples = array("h")
    for index in range(rate * 2):
        value = 0 if index < 12000 or index >= 46800 else (7000 if index % 80 < 40 else -7000)
        samples.append(value)
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(rate)
        stream.writeframes(samples.tobytes())
    return output.getvalue()


def _metadata(data: bytes) -> AudioMetadata:
    return AudioMetadata(schema_version="5.1", sample_rate_hz=24000, channels=1,
                         duration_ms=2000, sha256=hashlib.sha256(data).hexdigest(),
                         provider="volcengine", provider_type="real", voice_id="voice")


def _review(sha: str) -> VoiceReviewDocument:
    return VoiceReviewDocument(run_id="run-1", audio_sha256=sha, status="approved",
                               reviewer="human", reviewed_at="2026-09-21T00:00:00Z",
                               voice_approved=True, rate_approved=True, pauses_approved=True,
                               number_pronunciation_approved=True)


class FakeMasteringEngine:
    name = "fake_mastering_engine"
    calls = 0

    def __init__(self, output: bytes | None = None, **metrics):
        self.output = output or _wav()
        self.metrics = metrics
        self.calls = 0

    def master(self, source_path, config):
        self.calls += 1
        return EngineMasteringResult(
            audio_bytes=self.output, engine=self.name, method="ebu_r128_two_pass",
            input_integrated_lufs=self.metrics.get("input_lufs", -22.0),
            input_true_peak_dbtp=self.metrics.get("input_tp", -7.0),
            output_integrated_lufs=self.metrics.get("output_lufs", -16.0),
            output_true_peak_dbtp=self.metrics.get("output_tp", -1.2),
            output_codec="pcm_s16le", output_format="wav", output_sample_rate_hz=24000,
            output_channels=1,
        )


def test_mastering_binds_current_approved_audio_sha(tmp_path: Path):
    data = _wav(); source = tmp_path / "narration.wav"; source.write_bytes(data)
    metadata = _metadata(data)
    result = master_audio(source, metadata, _review(metadata.sha256), FakeMasteringEngine(),
                          run_id="run-1")
    assert result.document.input.sha256 == metadata.sha256
    assert result.document.output.sha256 == hashlib.sha256(result.audio_bytes).hexdigest()
    assert result.document.gate.passed


def test_unapproved_or_hash_mismatched_audio_fails_before_engine_call(tmp_path: Path):
    data = _wav(); source = tmp_path / "narration.wav"; source.write_bytes(data)
    metadata = _metadata(data); engine = FakeMasteringEngine()
    with pytest.raises(ValueError, match="MASTERING_AUDIO_APPROVAL_MISMATCH"):
        master_audio(source, metadata, _review("f" * 64), engine, run_id="run-1")
    assert engine.calls == 0


def test_fake_narration_is_not_production_eligible(tmp_path: Path):
    data = _wav(); source = tmp_path / "narration.wav"; source.write_bytes(data)
    metadata = _metadata(data).model_copy(update={"provider_type": "fake"})
    with pytest.raises(ValueError, match="MASTERING_INPUT_NOT_REAL"):
        master_audio(source, metadata, _review(metadata.sha256), FakeMasteringEngine(),
                     run_id="run-1")


@pytest.mark.parametrize("metrics,code", [
    ({"output_lufs": -15.0}, "MASTERING_LOUDNESS_OUT_OF_RANGE"),
    ({"output_tp": -0.5}, "MASTERING_TRUE_PEAK_EXCEEDED"),
])
def test_loudness_and_true_peak_fail_closed(tmp_path: Path, metrics, code):
    data = _wav(); source = tmp_path / "narration.wav"; source.write_bytes(data)
    metadata = _metadata(data)
    with pytest.raises(ValueError, match=code):
        master_audio(source, metadata, _review(metadata.sha256),
                     FakeMasteringEngine(**metrics), run_id="run-1")


def test_temporal_edges_and_canonical_contract_are_recorded(tmp_path: Path):
    data = _wav(); source = tmp_path / "narration.wav"; source.write_bytes(data)
    metadata = _metadata(data)
    result = master_audio(source, metadata, _review(metadata.sha256), FakeMasteringEngine(),
                          run_id="run-1")
    assert result.document.input.leading_silence_ms == result.document.output.leading_silence_ms
    assert result.document.input.trailing_silence_ms == result.document.output.trailing_silence_ms
    assert result.document.duration_delta_ms == 0
    assert result.document.output.sample_rate_hz == 24000
    assert result.document.output.channels == 1


def test_leading_silence_measurement_is_level_invariant_under_gain():
    def signal(gain):
        values = array("h", [100 * gain] * 3360 + [5000 * gain] * 20640)
        out = io.BytesIO()
        with wave.open(out, "wb") as stream:
            stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(24000)
            stream.writeframes(values.tobytes())
        return out.getvalue()
    original = _pcm_measurement(signal(1), threshold_dbfs=-45)
    amplified = _pcm_measurement(signal(2), threshold_dbfs=-45)
    assert original[1] == amplified[1] == 140


def test_edge_detector_ignores_gain_lifted_low_level_background():
    def signal(gain):
        values = array("h", [50 * gain] * 3360 + [500 * gain] * 20640)
        out = io.BytesIO()
        with wave.open(out, "wb") as stream:
            stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(24000)
            stream.writeframes(values.tobytes())
        return out.getvalue()
    original = _pcm_measurement(signal(1), threshold_dbfs=-45)
    amplified = _pcm_measurement(signal(4), threshold_dbfs=-45)
    assert original[1] == amplified[1] == 140
