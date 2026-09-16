import pytest

from fanglei.audio_alignment import align_audio, validate_alignment
from fanglei.narration_normalization import normalize_script
from fanglei.providers.alignment import AlignmentResult, FakeAlignmentProvider
from fanglei.v05_models import AlignedSentence, AudioMetadata


def _document():
    return normalize_script({
        "script_id": "script_001",
        "sentences": [
            {"sentence_id": "sentence_001", "text": "第一句。"},
            {"sentence_id": "sentence_002", "text": "第二句稍微长一点。"},
        ],
    }, "2026-09-14-001-gdp")


def _metadata(duration=3000):
    return AudioMetadata(
        sample_rate_hz=24000, duration_ms=duration, sha256="a" * 64,
        provider="fake", voice_id="fake-voice",
    )


def test_alignment_requires_complete_monotonic_audio_bounded_timing() -> None:
    result = align_audio(_document(), _metadata(), FakeAlignmentProvider())
    assert result.coverage_ratio == 1
    assert result.sentences[0].start_ms == 0
    assert result.sentences[-1].end_ms == 3000
    assert validate_alignment(result, ["sentence_001", "sentence_002"]).passed


@pytest.mark.parametrize("sentences,code", [
    ([AlignedSentence(sentence_id="sentence_001", start_ms=0, end_ms=1000,
                      confidence=.99, timing_source="deterministic_fake")],
     "ALIGNMENT_COVERAGE_INVALID"),
    ([AlignedSentence(sentence_id="sentence_001", start_ms=0, end_ms=1800,
                      confidence=.99, timing_source="deterministic_fake"),
      AlignedSentence(sentence_id="sentence_002", start_ms=1700, end_ms=3000,
                      confidence=.99, timing_source="deterministic_fake")],
     "ALIGNMENT_OVERLAP"),
    ([AlignedSentence(sentence_id="sentence_001", start_ms=0, end_ms=1200,
                      confidence=.99, timing_source="deterministic_fake"),
      AlignedSentence(sentence_id="sentence_002", start_ms=1200, end_ms=2999,
                      confidence=.99, timing_source="deterministic_fake")],
     "ALIGNMENT_AUDIO_END_MISMATCH"),
])
def test_alignment_gate_rejects_invalid_results(sentences, code) -> None:
    class Provider:
        name = "broken"
        method = "deterministic_fake"

        def align(self, request):
            return AlignmentResult(sentences=sentences, confidence=.99)

    with pytest.raises(ValueError, match=code):
        align_audio(_document(), _metadata(), Provider())


def test_low_confidence_uses_explicit_fallback() -> None:
    primary = FakeAlignmentProvider(confidence=.4)
    fallback = FakeAlignmentProvider(confidence=.98, name="fallback")
    result = align_audio(_document(), _metadata(), primary, fallback_provider=fallback)
    assert result.provider == "fallback"
    assert result.fallback_used is True


def test_low_confidence_without_fallback_fails() -> None:
    with pytest.raises(ValueError, match="ALIGNMENT_LOW_CONFIDENCE"):
        align_audio(_document(), _metadata(), FakeAlignmentProvider(confidence=.4))


def test_production_alignment_rejects_fake_provider() -> None:
    with pytest.raises(ValueError, match="PRODUCTION_ALIGNMENT_PROVIDER_REQUIRED"):
        align_audio(_document(), _metadata(), FakeAlignmentProvider(), production=True)
