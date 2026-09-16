import io
import wave

import pytest

from fanglei.audio_generation import generate_audio
from fanglei.narration_normalization import normalize_script
from fanglei.providers.narration import (
    FakeNarrationProvider,
    NarrationAudioResult,
)
from fanglei.v05_models import NativeTimingEvent, NarrationSynthesisConfig


def _document():
    return normalize_script({
        "script_id": "script_001",
        "sentences": [{"sentence_id": "sentence_001", "text": "美国GDP增长2.8%。"}],
    }, "2026-09-14-001-gdp")


def test_fake_provider_produces_canonical_audio_and_complete_metadata() -> None:
    audio, metadata = generate_audio(_document(), FakeNarrationProvider(), "fake-voice")
    with wave.open(io.BytesIO(audio), "rb") as stream:
        assert stream.getnchannels() == 1
        assert stream.getsampwidth() == 2
        assert stream.getframerate() == 24000
    assert metadata.format == "wav"
    assert metadata.codec == "pcm_s16le"
    assert metadata.sample_rate_hz == 24000
    assert metadata.channels == 1
    assert metadata.duration_ms > 0
    assert metadata.sha256
    assert metadata.provider == "fake"
    assert metadata.voice_id == "fake-voice"


class StereoProvider(FakeNarrationProvider):
    def synthesize(self, request, config=None):
        result = super().synthesize(request, config)
        source = wave.open(io.BytesIO(result.audio_bytes), "rb")
        frames = source.readframes(source.getnframes())
        output = io.BytesIO()
        with wave.open(output, "wb") as stream:
            stream.setnchannels(2)
            stream.setsampwidth(2)
            stream.setframerate(24000)
            stream.writeframes(b"".join(frames[i:i + 2] * 2 for i in range(0, len(frames), 2)))
        return NarrationAudioResult(audio_bytes=output.getvalue())


def test_audio_gate_rejects_noncanonical_channels() -> None:
    with pytest.raises(ValueError, match="AUDIO_CHANNELS_INVALID"):
        generate_audio(_document(), StereoProvider(), "fake-voice")


def test_production_generation_rejects_fake_provider() -> None:
    with pytest.raises(ValueError, match="AUDIO_PROVIDER_NOT_REAL"):
        generate_audio(_document(), FakeNarrationProvider(),
                       NarrationSynthesisConfig(voice_id="fake-voice"), production=True)


def test_native_timing_outside_text_is_rejected_before_audio_artifact() -> None:
    class InvalidTiming(FakeNarrationProvider):
        def synthesize(self, request, config=None):
            result = super().synthesize(request, config)
            return NarrationAudioResult(audio_bytes=result.audio_bytes, native_timestamps=(
                NativeTimingEvent(event_type="word", audio_offset_ms=0,
                                  text_offset=1000, text_length=2, text="unknown"),
            ))

    with pytest.raises(ValueError, match="NATIVE_TIMESTAMP_OUT_OF_BOUNDS"):
        generate_audio(_document(), InvalidTiming(), "fake-voice")
