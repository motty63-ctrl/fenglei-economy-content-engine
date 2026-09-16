import io
import math
import struct
import wave

from fanglei.audio_quality import AudioQualityThresholds, analyze_audio_quality


def _wav(amplitude: float, duration_ms: int = 1200) -> bytes:
    rate = 24000
    frames = []
    for index in range(rate * duration_ms // 1000):
        sample = int(32767 * amplitude * math.sin(2 * math.pi * 440 * index / rate))
        frames.append(struct.pack("<h", sample))
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(rate)
        stream.writeframes(b"".join(frames))
    return output.getvalue()


def test_silence_is_rejected() -> None:
    quality = analyze_audio_quality(_wav(0), "a" * 64, "fake", "fake")
    assert not quality.passed
    assert "AUDIO_PROVIDER_NOT_REAL" in quality.gate_reasons
    assert "AUDIO_SILENT" in quality.gate_reasons


def test_real_voiced_audio_passes_non_silence_gate() -> None:
    quality = analyze_audio_quality(_wav(.2), "b" * 64, "azure_speech", "real",
                                    AudioQualityThresholds(min_voiced_duration_ms=500))
    assert quality.passed
    assert quality.production_eligible
    assert quality.peak > .19
    assert quality.rms_dbfs is not None
    assert quality.voiced_duration_ms >= 1000
