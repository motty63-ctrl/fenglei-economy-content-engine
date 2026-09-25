"""Alignment orchestration and deterministic local quality gate."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import wave

from fanglei.alignment_matching import compare_alignment_text
from fanglei.artifacts import sha256_bytes
from fanglei.models import StageError, StageState
from fanglei.paths import resolve_run_dir
from fanglei.pipeline import _execute, _load
from fanglei.providers.alignment import (
    AlignmentProvider, AlignmentRequest, ProportionalSentenceAlignmentProvider,
)
from fanglei.v05_models import (
    AlignmentCandidateDocument, AlignmentDocument, AudioMetadata, AudioQualityDocument,
    NarrationDocument,
    VoiceReviewDocument,
)
from fanglei.voice_review import validate_voice_approval
from fanglei.security import safe_error_message


MIN_ALIGNMENT_CONFIDENCE = .85


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


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


def validate_real_alignment(
    candidate: AlignmentCandidateDocument,
    expected_sentence_ids: list[str],
    actual_duration_ms: int,
    approved_sha: str,
    *,
    expected_texts: dict[str, str] | None = None,
) -> AlignmentGateResult:
    """Validate production structure and provenance without an uncalibrated score cutoff."""
    issues: list[str] = []
    actual_ids = [row.sentence_id for row in candidate.sentences]
    if actual_ids != expected_sentence_ids or len(actual_ids) != len(set(actual_ids)):
        issues.append("ALIGNMENT_COVERAGE_INVALID")
    if candidate.coverage_ratio != 1:
        issues.append("ALIGNMENT_COVERAGE_INVALID")
    if candidate.audio_sha256 != approved_sha:
        issues.append("ALIGNMENT_AUDIO_SHA_MISMATCH")
    if candidate.audio_duration_ms != actual_duration_ms:
        issues.append("ALIGNMENT_AUDIO_DURATION_MISMATCH")
    if candidate.method == "deterministic_fake" or candidate.provider == "fake" or candidate.fallback_used:
        issues.append("PRODUCTION_ALIGNMENT_PROVIDER_REQUIRED")
    if not candidate.model_id or not candidate.model_revision:
        issues.append("ALIGNMENT_MODEL_REVISION_MISSING")
    if not candidate.confidence_source:
        issues.append("ALIGNMENT_SCORE_MISSING")
    if candidate.normalized_ref != candidate.normalized_asr:
        issues.append("ALIGNMENT_TEXT_MISMATCH")

    previous_start = -1
    previous_end = -1
    for row in candidate.sentences:
        if row.start_ms < 0 or row.end_ms <= row.start_ms:
            issues.append("ALIGNMENT_BOUNDARY_INVALID")
        if row.start_ms < previous_start or row.end_ms < previous_end:
            issues.append("ALIGNMENT_NOT_MONOTONIC")
        if row.start_ms < previous_end:
            issues.append("ALIGNMENT_OVERLAP")
        if row.end_ms > actual_duration_ms:
            issues.append("ALIGNMENT_OUT_OF_BOUNDS")
        if row.audio_sha256 != approved_sha:
            issues.append("ALIGNMENT_AUDIO_SHA_MISMATCH")
        if not row.confidence_source or row.measured is not True:
            issues.append("ALIGNMENT_SCORE_MISSING")
        if row.interpolated is not False:
            issues.append("ALIGNMENT_INTERPOLATION_FORBIDDEN")
        if row.provider != candidate.provider or row.method != candidate.method:
            issues.append("ALIGNMENT_PROVENANCE_MISMATCH")
        if row.normalized_ref != row.normalized_asr:
            issues.append("ALIGNMENT_TEXT_MISMATCH")
        if expected_texts is not None and row.text != expected_texts.get(row.sentence_id):
            issues.append("ALIGNMENT_TEXT_CHANGED")
        previous_start, previous_end = row.start_ms, row.end_ms

    return AlignmentGateResult(passed=not issues, issues=tuple(dict.fromkeys(issues)))


def _wav_duration_ms(path: Path) -> int:
    with wave.open(str(path), "rb") as stream:
        return round(stream.getnframes() * 1000 / stream.getframerate())


def _build_alignment_candidate(run_id: str, run_dir: Path, manifest, registry,
                               provider: AlignmentProvider, force: bool) -> Path:
    for name in (
        "narration.json", "audio/narration.wav", "audio/metadata.json",
        "audio/quality.json", "audio/review.json",
    ):
        registry.validate(name)
    narration = NarrationDocument.model_validate(registry.read_json("narration.json"))
    audio = AudioMetadata.model_validate(registry.read_json("audio/metadata.json"))
    quality = AudioQualityDocument.model_validate(registry.read_json("audio/quality.json"))
    review = VoiceReviewDocument.model_validate(registry.read_json("audio/review.json"))
    audio_path = run_dir / audio.path
    actual_sha = sha256_bytes(audio_path.read_bytes())
    if actual_sha != audio.sha256:
        raise ValueError("AUDIO_METADATA_HASH_MISMATCH")
    if quality.audio_sha256 != actual_sha or not quality.production_eligible:
        raise ValueError("PRODUCTION_AUDIO_QUALITY_REQUIRED")
    validate_voice_approval(review, actual_sha)
    actual_duration_ms = _wav_duration_ms(audio_path)
    if actual_duration_ms != audio.duration_ms or quality.duration_ms != actual_duration_ms:
        raise ValueError("AUDIO_DURATION_MISMATCH")
    if audio.provider_type != "real":
        raise ValueError("PRODUCTION_AUDIO_REQUIRED")
    if provider.method == "deterministic_fake" or provider.name == "fake":
        raise ValueError("PRODUCTION_ALIGNMENT_PROVIDER_REQUIRED")

    result = provider.align(AlignmentRequest(
        narration=narration,
        audio=audio,
        audio_path=audio_path,
        audio_sha256=actual_sha,
        audio_duration_ms=actual_duration_ms,
        approved_review=review,
    ))
    reference_text = "".join(row.narration_text for row in narration.sentences)
    recognized_text = result.recognized_text or ""
    text_match = compare_alignment_text(reference_text, recognized_text)
    warnings = list(result.warnings)
    if not text_match.matched:
        warnings.append("ALIGNMENT_ASR_REFERENCE_MISMATCH")
    candidate = AlignmentCandidateDocument(
        run_id=run_id,
        audio_sha256=actual_sha,
        audio_duration_ms=actual_duration_ms,
        provider=result.provider or provider.name,
        method=result.method or provider.method,
        model_id=result.model_id or "",
        model_revision=result.model_revision or "",
        confidence_source=result.score_source or "",
        recognized_text=recognized_text,
        normalized_ref=text_match.normalized_ref,
        normalized_asr=text_match.normalized_asr,
        text_match_cer=text_match.cer,
        voice_review_hash=manifest.artifacts["audio/review.json"].content_hash or "",
        sentences=result.sentences,
        coverage_ratio=len(result.sentences) / len(narration.sentences),
        confidence=result.confidence,
        fallback_used=False,
        warnings=warnings,
    )
    output = registry.write_json(
        "alignment_candidate.json", candidate.model_dump(mode="json"),
        "audio_alignment", force=force,
    )
    expected_ids = [row.sentence_id for row in narration.sentences]
    expected_texts = {row.sentence_id: row.narration_text for row in narration.sentences}
    gate = validate_real_alignment(
        candidate, expected_ids, actual_duration_ms, actual_sha, expected_texts=expected_texts
    )
    if not gate.passed:
        if not text_match.matched:
            raise ValueError("ALIGNMENT_ASR_REFERENCE_MISMATCH")
        raise ValueError(",".join(gate.issues))
    registry.save_manifest()
    return output


def run_alignment_candidate(run_id: str, runs_dir: Path,
                            provider: AlignmentProvider, *, force: bool = False) -> Path:
    """Run only the production candidate stage; never promote final alignment."""
    run_dir = resolve_run_dir(Path(runs_dir), run_id)
    manifest, registry = _load(run_dir)
    candidate_state = manifest.artifacts["alignment_candidate.json"]
    if candidate_state.status == "valid" and not force:
        registry.validate("alignment_candidate.json")
        return run_dir / "alignment_candidate.json"
    previous = manifest.stages.get("audio_alignment", StageState())
    started = _now()
    manifest.stages["audio_alignment"] = StageState(
        status="running", attempts=previous.attempts + 1, started_at=started,
        provider=provider.name,
    )
    registry.save_manifest()
    try:
        output = _build_alignment_candidate(
            run_id, run_dir, manifest, registry, provider, force
        )
    except Exception as error:
        manifest.artifacts["alignment_candidate.json"].status = "failed"
        manifest.stages["audio_alignment"] = StageState(
            status="failed", attempts=previous.attempts + 1, started_at=started,
            finished_at=_now(), provider=provider.name,
            error=StageError(code="STAGE_FAILED", message=safe_error_message(error)),
        )
        registry.save_manifest()
        raise
    manifest.stages["audio_alignment"] = StageState(
        status="succeeded", attempts=previous.attempts + 1, started_at=started,
        finished_at=_now(), provider=provider.name,
    )
    registry.save_manifest()
    return output


def run_proportional_sentence_timing(run_id: str, runs_dir: Path) -> Path:
    """Write explicit estimated sentence windows for approved production narration.

    This is a timing estimate, not acoustic alignment. It is a bounded local fast path
    for downstream scene/caption pacing when no measured alignment subsystem is used.
    """
    run_dir = resolve_run_dir(Path(runs_dir), run_id)
    manifest, registry = _load(run_dir)
    existing = manifest.artifacts["alignment.json"]
    if existing.status == "valid":
        registry.validate("alignment.json")
        current = AlignmentDocument.model_validate(registry.read_json("alignment.json"))
        if (current.provider, current.method) == (
            ProportionalSentenceAlignmentProvider.name,
            ProportionalSentenceAlignmentProvider.method,
        ):
            return run_dir / "alignment.json"
        raise ValueError("ALIGNMENT_ALREADY_EXISTS_WITH_DIFFERENT_METHOD")

    def stage() -> None:
        for name in (
            "narration.json", "audio/narration.wav", "audio/metadata.json",
            "audio/quality.json", "audio/review.json",
        ):
            registry.validate(name)
        narration = NarrationDocument.model_validate(registry.read_json("narration.json"))
        audio = AudioMetadata.model_validate(registry.read_json("audio/metadata.json"))
        quality = AudioQualityDocument.model_validate(registry.read_json("audio/quality.json"))
        review = VoiceReviewDocument.model_validate(registry.read_json("audio/review.json"))
        audio_path = run_dir / audio.path
        actual_sha = sha256_bytes(audio_path.read_bytes())
        if actual_sha != audio.sha256:
            raise ValueError("AUDIO_METADATA_HASH_MISMATCH")
        if quality.audio_sha256 != actual_sha or not quality.production_eligible:
            raise ValueError("PRODUCTION_AUDIO_QUALITY_REQUIRED")
        if audio.provider_type != "real":
            raise ValueError("PRODUCTION_AUDIO_REQUIRED")
        validate_voice_approval(review, actual_sha)
        actual_duration_ms = _wav_duration_ms(audio_path)
        if actual_duration_ms != audio.duration_ms or quality.duration_ms != actual_duration_ms:
            raise ValueError("AUDIO_DURATION_MISMATCH")
        if narration.run_id != run_id or not narration.semantic_validation.passed:
            raise ValueError("NARRATION_IDENTITY_OR_SEMANTIC_VALIDATION_FAILED")

        provider = ProportionalSentenceAlignmentProvider()
        result = provider.align(AlignmentRequest(
            narration=narration, audio=audio, audio_path=audio_path,
            audio_sha256=actual_sha, audio_duration_ms=actual_duration_ms,
            approved_review=review,
        ))
        expected_ids = [row.sentence_id for row in narration.sentences]
        if [row.sentence_id for row in result.sentences] != expected_ids:
            raise ValueError("PROPORTIONAL_ALIGNMENT_COVERAGE_INVALID")
        if not result.sentences or result.sentences[0].start_ms != 0:
            raise ValueError("PROPORTIONAL_ALIGNMENT_START_INVALID")
        for index, row in enumerate(result.sentences):
            expected = narration.sentences[index]
            if (
                row.text != expected.narration_text
                or row.audio_sha256 != actual_sha
                or row.provider != provider.name
                or row.method != provider.method
                or row.measured is not False
                or row.interpolated is not True
                or (index > 0 and row.start_ms != result.sentences[index - 1].end_ms)
            ):
                raise ValueError("PROPORTIONAL_ALIGNMENT_PROVENANCE_INVALID")
        if result.sentences[-1].end_ms != actual_duration_ms:
            raise ValueError("PROPORTIONAL_ALIGNMENT_AUDIO_END_MISMATCH")
        document = AlignmentDocument(
            run_id=run_id, audio_sha256=actual_sha, audio_duration_ms=actual_duration_ms,
            provider=provider.name, method=provider.method, sentences=result.sentences,
            coverage_ratio=1.0, confidence=0.0, fallback_used=False,
            warnings=list(result.warnings),
            voice_review_hash=manifest.artifacts["audio/review.json"].content_hash or "",
        )
        registry.write_json("alignment.json", document.model_dump(mode="json"),
                            "audio_alignment")

    _execute(manifest, registry, "audio_alignment", stage)
    return run_dir / "alignment.json"


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
