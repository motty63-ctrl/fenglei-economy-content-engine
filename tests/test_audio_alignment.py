import pytest

from fanglei.audio_alignment import align_audio, validate_alignment, validate_real_alignment
from fanglei.narration_normalization import normalize_script
from fanglei.providers.alignment import AlignmentResult, FakeAlignmentProvider
from fanglei.v05_models import AlignedSentence, AlignmentCandidateDocument, AudioMetadata


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


def _real_candidate() -> AlignmentCandidateDocument:
    return AlignmentCandidateDocument(
        run_id="run", audio_sha256="a" * 64, audio_duration_ms=7000,
        provider="local_whisperx", method="forced_alignment",
        model_id="zh-ctc", model_revision="r1", confidence_source="ctc_acoustic_score",
        voice_review_hash="c" * 64,
        recognized_text="第一句。第二句稍微长一点。", normalized_ref="第一句第二句稍微长一点",
        normalized_asr="第一句第二句稍微长一点", text_match_cer=0,
        coverage_ratio=1, confidence=.31,
        sentences=[
            AlignedSentence(
                sentence_id="sentence_001", start_ms=120, end_ms=2500, confidence=.31,
                timing_source="forced_alignment", text="第一句。",
                confidence_source="ctc_acoustic_score", provider="local_whisperx",
                method="forced_alignment", audio_sha256="a" * 64,
                normalized_ref="第一句", normalized_asr="第一句", measured=True,
                interpolated=False,
            ),
            AlignedSentence(
                sentence_id="sentence_002", start_ms=2700, end_ms=6800, confidence=.42,
                timing_source="forced_alignment", text="第二句稍微长一点。",
                confidence_source="ctc_acoustic_score", provider="local_whisperx",
                method="forced_alignment", audio_sha256="a" * 64,
                normalized_ref="第二句稍微长一点", normalized_asr="第二句稍微长一点",
                measured=True, interpolated=False,
            ),
        ],
    )


def test_real_gate_accepts_measured_low_uncalibrated_score_and_trailing_silence() -> None:
    candidate = _real_candidate()
    result = validate_real_alignment(
        candidate, ["sentence_001", "sentence_002"], 7000, "a" * 64,
        expected_texts={"sentence_001": "第一句。", "sentence_002": "第二句稍微长一点。"},
    )
    assert result.passed
    assert candidate.sentences[-1].end_ms == 6800


@pytest.mark.parametrize("mutator,code", [
    (lambda c: setattr(c, "audio_sha256", "b" * 64), "ALIGNMENT_AUDIO_SHA_MISMATCH"),
    (lambda c: setattr(c, "method", "deterministic_fake"), "PRODUCTION_ALIGNMENT_PROVIDER_REQUIRED"),
    (lambda c: setattr(c.sentences[1], "start_ms", 2400), "ALIGNMENT_OVERLAP"),
    (lambda c: setattr(c.sentences[1], "end_ms", 7100), "ALIGNMENT_OUT_OF_BOUNDS"),
    (lambda c: setattr(c.sentences[0], "confidence_source", None), "ALIGNMENT_SCORE_MISSING"),
    (lambda c: setattr(c.sentences[0], "interpolated", True), "ALIGNMENT_INTERPOLATION_FORBIDDEN"),
    (lambda c: setattr(c.sentences[0], "text", "改写文本"), "ALIGNMENT_TEXT_CHANGED"),
    (lambda c: setattr(c.sentences[0], "normalized_asr", "另一句"), "ALIGNMENT_TEXT_MISMATCH"),
    (lambda c: setattr(c, "normalized_asr", "整体不一致"), "ALIGNMENT_TEXT_MISMATCH"),
])
def test_real_gate_fails_closed_on_structural_or_provenance_error(mutator, code) -> None:
    candidate = _real_candidate()
    mutator(candidate)
    result = validate_real_alignment(
        candidate, ["sentence_001", "sentence_002"], 7000, "a" * 64,
        expected_texts={"sentence_001": "第一句。", "sentence_002": "第二句稍微长一点。"},
    )
    assert not result.passed
    assert code in result.issues


def test_real_gate_rejects_duplicate_or_missing_sentence_coverage() -> None:
    candidate = _real_candidate()
    candidate.sentences[1].sentence_id = "sentence_001"
    result = validate_real_alignment(
        candidate, ["sentence_001", "sentence_002"], 7000, "a" * 64
    )
    assert "ALIGNMENT_COVERAGE_INVALID" in result.issues
