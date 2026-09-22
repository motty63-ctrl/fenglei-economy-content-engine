"""Provider-neutral narration mastering orchestration and fail-closed gates."""

from __future__ import annotations

from array import array
from dataclasses import dataclass
import hashlib
import io
import math
from pathlib import Path
import sys
import wave

from .audio_quality import analyze_audio_quality
from .providers.mastering import AudioMasteringEngine
from .v05_models import AudioMetadata, VoiceReviewDocument
from .v1b_models import (
    AudioMasteringConfig, AudioMasteringDocument, AudioMeasurement, MasteringGate,
)


@dataclass(frozen=True)
class AudioMasteringResult:
    audio_bytes: bytes
    document: AudioMasteringDocument


def _pcm_measurement(audio: bytes, *, threshold_dbfs: float,
                     edge_activity_below_95th_db: float = 18.0) -> tuple[int, int, int, int, int]:
    with wave.open(io.BytesIO(audio), "rb") as stream:
        channels, width, rate = stream.getnchannels(), stream.getsampwidth(), stream.getframerate()
        count = stream.getnframes(); frames = stream.readframes(count)
    if channels != 1 or width != 2 or rate != 24000:
        raise ValueError("MASTERING_AUDIO_FORMAT_INVALID")
    samples = array("h"); samples.frombytes(frames)
    if sys.byteorder != "little": samples.byteswap()
    frame_samples = max(1, rate * 20 // 1000)
    frame_levels: list[tuple[int, float]] = []
    for offset in range(0, len(samples), frame_samples):
        block = samples[offset:offset + frame_samples]
        if not block: continue
        rms = math.sqrt(sum(value * value for value in block) / len(block)) / 32768
        frame_levels.append((offset, 20 * math.log10(rms) if rms > 0 else float("-inf")))
    duration = round(count * 1000 / rate)
    finite = sorted(level for _, level in frame_levels if math.isfinite(level))
    if not finite:
        return duration, duration, duration, rate, channels
    reference = finite[round((len(finite) - 1) * 0.95)]
    # A relative, robust programme-level threshold measures the same acoustic edge
    # before and after gain. The absolute floor only guards degenerate low-level data.
    effective_threshold = max(reference - edge_activity_below_95th_db, threshold_dbfs - 20)
    voiced = [offset for offset, level in frame_levels if level >= effective_threshold]
    if not voiced:
        return duration, duration, duration, rate, channels
    leading = round(voiced[0] * 1000 / rate)
    last_end = min(count, voiced[-1] + frame_samples)
    trailing = round((count - last_end) * 1000 / rate)
    return duration, leading, trailing, rate, channels


def master_audio(source_path: Path, metadata: AudioMetadata, review: VoiceReviewDocument,
                 engine: AudioMasteringEngine, *, run_id: str,
                 config: AudioMasteringConfig | None = None) -> AudioMasteringResult:
    config = config or AudioMasteringConfig()
    if metadata.provider_type != "real":
        raise ValueError("MASTERING_INPUT_NOT_REAL")
    source_bytes = source_path.read_bytes()
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    approval_ok = (
        review.status == "approved" and review.audio_sha256 == metadata.sha256 == source_sha
        and all((review.voice_approved, review.rate_approved, review.pauses_approved,
                 review.number_pronunciation_approved))
    )
    if not approval_ok:
        raise ValueError("MASTERING_AUDIO_APPROVAL_MISMATCH")
    input_quality = analyze_audio_quality(source_bytes, source_sha, metadata.provider,
                                          metadata.provider_type)
    if not input_quality.production_eligible:
        raise ValueError("MASTERING_INPUT_QUALITY_FAILED")
    input_duration, input_leading, input_trailing, input_rate, input_channels = _pcm_measurement(
        source_bytes, threshold_dbfs=config.silence_threshold_dbfs,
        edge_activity_below_95th_db=config.edge_activity_below_95th_db)
    if input_duration != metadata.duration_ms:
        raise ValueError("MASTERING_INPUT_DURATION_MISMATCH")

    engine_result = engine.master(source_path, config)
    output_sha = hashlib.sha256(engine_result.audio_bytes).hexdigest()
    output_quality = analyze_audio_quality(engine_result.audio_bytes, output_sha, engine.name, "real")
    if not output_quality.production_eligible:
        raise ValueError("MASTERING_OUTPUT_QUALITY_FAILED")
    output_duration, output_leading, output_trailing, output_rate, output_channels = _pcm_measurement(
        engine_result.audio_bytes, threshold_dbfs=config.silence_threshold_dbfs,
        edge_activity_below_95th_db=config.edge_activity_below_95th_db)
    issues: list[str] = []
    if abs(engine_result.output_integrated_lufs - config.target_integrated_lufs) > config.loudness_tolerance_lu:
        issues.append("MASTERING_LOUDNESS_OUT_OF_RANGE")
    if engine_result.output_true_peak_dbtp > config.maximum_true_peak_dbtp:
        issues.append("MASTERING_TRUE_PEAK_EXCEEDED")
    if abs(output_duration - input_duration) > config.maximum_duration_delta_ms:
        issues.append("MASTERING_DURATION_CHANGED")
    if abs(output_leading - input_leading) > config.maximum_edge_silence_delta_ms:
        issues.append("MASTERING_LEADING_SILENCE_CHANGED")
    if abs(output_trailing - input_trailing) > config.maximum_edge_silence_delta_ms:
        issues.append("MASTERING_TRAILING_SILENCE_CHANGED")
    if (engine_result.output_format != "wav" or engine_result.output_codec != config.output_codec
            or output_rate != config.sample_rate_hz or output_channels != config.channels
            or engine_result.output_sample_rate_hz != config.sample_rate_hz
            or engine_result.output_channels != config.channels):
        issues.append("MASTERING_OUTPUT_FORMAT_INVALID")
    if issues:
        raise ValueError(";".join(issues))

    input_measurement = AudioMeasurement(
        path="audio/narration.wav", sha256=source_sha, duration_ms=input_duration,
        leading_silence_ms=input_leading, trailing_silence_ms=input_trailing,
        integrated_lufs=engine_result.input_integrated_lufs,
        true_peak_dbtp=engine_result.input_true_peak_dbtp,
        sample_rate_hz=input_rate, channels=input_channels,
    )
    output_measurement = AudioMeasurement(
        path="audio/mastered_narration.wav", sha256=output_sha, duration_ms=output_duration,
        leading_silence_ms=output_leading, trailing_silence_ms=output_trailing,
        integrated_lufs=engine_result.output_integrated_lufs,
        true_peak_dbtp=engine_result.output_true_peak_dbtp,
        sample_rate_hz=output_rate, channels=output_channels,
    )
    document = AudioMasteringDocument(
        run_id=run_id, engine=engine_result.engine, config=config,
        input=input_measurement, output=output_measurement,
        duration_delta_ms=output_duration - input_duration,
        leading_silence_delta_ms=output_leading - input_leading,
        trailing_silence_delta_ms=output_trailing - input_trailing,
        gate=MasteringGate(passed=True, issues=[]),
    )
    return AudioMasteringResult(audio_bytes=engine_result.audio_bytes, document=document)
