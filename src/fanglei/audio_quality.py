"""Deterministic PCM signal analysis and production non-silence gate."""
from __future__ import annotations

from dataclasses import dataclass
from array import array
import io
import math
import sys
import wave

from fanglei.v05_models import AudioQualityDocument, AudioQualityThresholdsModel


@dataclass(frozen=True)
class AudioQualityThresholds:
    min_peak: float = .0001
    min_rms_dbfs: float = -50.0
    voiced_frame_rms_dbfs: float = -45.0
    min_voiced_duration_ms: int = 1000
    min_voiced_ratio: float = .15
    frame_duration_ms: int = 20


def _dbfs(value: float) -> float | None:
    return 20 * math.log10(value) if value > 0 else None


def analyze_audio_quality(audio_bytes: bytes, audio_sha256: str, provider: str,
                          provider_type: str,
                          thresholds: AudioQualityThresholds | None = None) -> AudioQualityDocument:
    threshold = thresholds or AudioQualityThresholds()
    with wave.open(io.BytesIO(audio_bytes), "rb") as stream:
        rate = stream.getframerate()
        width = stream.getsampwidth()
        channels = stream.getnchannels()
        frame_count = stream.getnframes()
        frames = stream.readframes(frame_count)
    if width != 2 or channels != 1 or rate != 24000:
        raise ValueError("AUDIO_SIGNAL_ANALYSIS_FAILED")
    duration_ms = round(frame_count * 1000 / rate)
    samples = array("h")
    samples.frombytes(frames)
    if sys.byteorder != "little":
        samples.byteswap()
    peak = max((abs(sample) for sample in samples), default=0) / 32768
    rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples)) / 32768 if samples else 0.0
    frame_samples = max(1, rate * threshold.frame_duration_ms // 1000)
    voiced = 0
    for offset in range(0, len(samples), frame_samples):
        block = samples[offset:offset + frame_samples]
        if not block:
            continue
        block_rms = math.sqrt(sum(sample * sample for sample in block) / len(block)) / 32768
        block_db = _dbfs(block_rms)
        if block_db is not None and block_db >= threshold.voiced_frame_rms_dbfs:
            voiced += round(len(block) * 1000 / rate)
    ratio = min(1.0, voiced / duration_ms) if duration_ms else 0.0
    reasons: list[str] = []
    if provider_type != "real": reasons.append("AUDIO_PROVIDER_NOT_REAL")
    if peak == 0 and rms == 0: reasons.append("AUDIO_SILENT")
    if peak < threshold.min_peak: reasons.append("AUDIO_PEAK_TOO_LOW")
    rms_db = _dbfs(rms)
    if rms_db is None or rms_db < threshold.min_rms_dbfs: reasons.append("AUDIO_RMS_TOO_LOW")
    if voiced < threshold.min_voiced_duration_ms: reasons.append("AUDIO_VOICED_DURATION_TOO_SHORT")
    if ratio < threshold.min_voiced_ratio: reasons.append("AUDIO_VOICED_RATIO_TOO_LOW")
    passed = not reasons
    return AudioQualityDocument(
        audio_sha256=audio_sha256, provider=provider, provider_type=provider_type,
        duration_ms=duration_ms, peak=peak, peak_dbfs=_dbfs(peak), rms=rms,
        rms_dbfs=rms_db, voiced_duration_ms=voiced, voiced_ratio=ratio,
        frame_duration_ms=threshold.frame_duration_ms,
        thresholds=AudioQualityThresholdsModel(**{
            key: getattr(threshold, key) for key in (
                "min_peak", "min_rms_dbfs", "voiced_frame_rms_dbfs",
                "min_voiced_duration_ms", "min_voiced_ratio")}),
        passed=passed, gate_reasons=reasons,
        production_eligible=passed and provider_type == "real",
    )
