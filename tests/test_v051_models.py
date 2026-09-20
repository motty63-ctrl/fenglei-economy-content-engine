import pytest
from pydantic import ValidationError

from fanglei.v05_models import (
    AlignedSentence, AlignmentDocument, AudioMetadata, NarrationSynthesisConfig,
    NativeTimingEvent,
)


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


def test_alignment_schema_52_requires_real_provenance_metadata() -> None:
    row = AlignedSentence(
        sentence_id="sentence_001", start_ms=0, end_ms=1000, confidence=.5,
        timing_source="forced_alignment",
    )
    with pytest.raises(ValidationError, match="schema 5.2 requires alignment provenance"):
        AlignmentDocument(
            schema_version="5.2", run_id="run", audio_sha256="a" * 64,
            audio_duration_ms=1000, provider="local_whisperx", method="forced_alignment",
            sentences=[row], coverage_ratio=1, confidence=.5,
        )
