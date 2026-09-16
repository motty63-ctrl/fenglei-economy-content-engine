"""Alignment orchestration and deterministic local quality gate."""
from __future__ import annotations

from dataclasses import dataclass

from fanglei.providers.alignment import AlignmentProvider, AlignmentRequest
from fanglei.v05_models import (
    AlignmentDocument, AudioMetadata, AudioQualityDocument, NarrationDocument,
    VoiceReviewDocument,
)
from fanglei.voice_review import validate_voice_approval


MIN_ALIGNMENT_CONFIDENCE = .85


@dataclass(frozen=True)
class AlignmentGateResult:
    passed: bool
    issues: tuple[str, ...]


def validate_alignment(document: AlignmentDocument,
                       expected_sentence_ids: list[str]) -> AlignmentGateResult:
    issues: list[str] = []
    actual_ids = [row.sentence_id for row in document.sentences]
    if actual_ids != expected_sentence_ids or len(actual_ids) != len(set(actual_ids)):
        issues.append("ALIGNMENT_COVERAGE_INVALID")
    for previous, current in zip(document.sentences, document.sentences[1:]):
        if current.start_ms < previous.end_ms:
            issues.append("ALIGNMENT_OVERLAP")
        if current.start_ms < previous.start_ms:
            issues.append("ALIGNMENT_NOT_MONOTONIC")
    if any(row.end_ms > document.audio_duration_ms for row in document.sentences):
        issues.append("ALIGNMENT_OUT_OF_BOUNDS")
    if not document.sentences or document.sentences[-1].end_ms != document.audio_duration_ms:
        issues.append("ALIGNMENT_AUDIO_END_MISMATCH")
    if document.coverage_ratio != 1:
        issues.append("ALIGNMENT_COVERAGE_INVALID")
    if document.confidence < MIN_ALIGNMENT_CONFIDENCE or any(
        row.confidence < MIN_ALIGNMENT_CONFIDENCE for row in document.sentences
    ):
        issues.append("ALIGNMENT_LOW_CONFIDENCE")
    return AlignmentGateResult(passed=not issues, issues=tuple(dict.fromkeys(issues)))


def _run(document: NarrationDocument, audio: AudioMetadata,
         provider: AlignmentProvider, fallback_used: bool) -> AlignmentDocument:
    result = provider.align(AlignmentRequest(narration=document, audio=audio))
    expected = [row.sentence_id for row in document.sentences]
    coverage = len({row.sentence_id for row in result.sentences} & set(expected)) / len(expected)
    return AlignmentDocument(
        run_id=document.run_id,
        audio_sha256=audio.sha256,
        audio_duration_ms=audio.duration_ms,
        provider=provider.name,
        method=provider.method,
        sentences=result.sentences,
        coverage_ratio=coverage,
        confidence=result.confidence,
        fallback_used=fallback_used,
        warnings=list(result.warnings),
    )


def align_audio(document: NarrationDocument, audio: AudioMetadata,
                provider: AlignmentProvider, *,
                fallback_provider: AlignmentProvider | None = None,
                production: bool = False,
                quality: AudioQualityDocument | None = None,
                review: VoiceReviewDocument | None = None) -> AlignmentDocument:
    if production:
        if provider.method == "deterministic_fake" or (
            fallback_provider is not None and fallback_provider.method == "deterministic_fake"
        ):
            raise ValueError("PRODUCTION_ALIGNMENT_PROVIDER_REQUIRED")
        if audio.provider_type != "real" or quality is None or not quality.production_eligible:
            raise ValueError("PRODUCTION_AUDIO_QUALITY_REQUIRED")
        if quality.audio_sha256 != audio.sha256:
            raise ValueError("AUDIO_QUALITY_HASH_MISMATCH")
        if review is None:
            raise ValueError("VOICE_REVIEW_REQUIRED")
        validate_voice_approval(review, audio.sha256)
    expected = [row.sentence_id for row in document.sentences]
    result = _run(document, audio, provider, False)
    gate = validate_alignment(result, expected)
    if gate.passed:
        return result
    if "ALIGNMENT_LOW_CONFIDENCE" in gate.issues and fallback_provider is not None:
        fallback = _run(document, audio, fallback_provider, True)
        fallback_gate = validate_alignment(fallback, expected)
        if fallback_gate.passed:
            return fallback
        gate = fallback_gate
    raise ValueError(",".join(gate.issues))
