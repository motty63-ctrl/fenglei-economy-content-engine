import pytest

from fanglei.v05_models import AudioMetadata, NarrationSynthesisConfig, NativeTimingEvent


def test_v051_audio_requires_explicit_provider_type() -> None:
    with pytest.raises(ValueError):
        AudioMetadata(schema_version="5.1", sample_rate_hz=24000, duration_ms=1000,
                      sha256="a" * 64, provider="azure_speech", voice_id="voice")


def test_legacy_fake_audio_is_classified_but_never_real() -> None:
    item = AudioMetadata(sample_rate_hz=24000, duration_ms=1000, sha256="a" * 64,
                         provider="fake", voice_id="fake-voice")
    assert item.provider_type == "fake"


def test_synthesis_config_and_native_timing_are_provider_neutral() -> None:
    config = NarrationSynthesisConfig(language="zh-CN", voice_id="voice", speaking_rate=0.9,
                                      pitch_semitones=-1, volume_gain_db=0)
    event = NativeTimingEvent(event_type="word", audio_offset_ms=120, text_offset=0,
                              text_length=2, text="美国")
    assert config.voice_id == "voice"
    assert event.source == "provider_native"
