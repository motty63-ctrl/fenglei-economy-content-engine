"""Human review and fail-closed promotion of measured alignment candidates."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fanglei.artifacts import sha256_bytes, sha256_text
from fanglei.audio_alignment import validate_real_alignment
from fanglei.models import StageState
from fanglei.paths import resolve_run_dir
from fanglei.pipeline import _load
from fanglei.v05_models import (
    AlignmentCandidateDocument,
    AlignmentDocument,
    AlignmentReviewDocument,
    AudioMetadata,
    NarrationDocument,
    VoiceReviewDocument,
)
from fanglei.voice_review import validate_voice_approval


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def promote_alignment(
    run_id: str,
    runs_dir: Path,
    *,
    reviewer: str,
    reviewed_sentence_ids: list[str],
    expected_candidate_hash: str,
    expected_audio_sha256: str,
) -> Path:
    """Promote one exact reviewed mismatch candidate without changing global gates."""
    run_dir = resolve_run_dir(Path(runs_dir), run_id)
    manifest, registry = _load(run_dir)
    for name in (
        "narration.json", "audio/narration.wav", "audio/metadata.json",
        "audio/quality.json", "audio/review.json",
    ):
        registry.validate(name)

    candidate_path = run_dir / "alignment_candidate.json"
    if not candidate_path.is_file():
        raise ValueError("ALIGNMENT_CANDIDATE_MISSING")
    candidate_text = candidate_path.read_text(encoding="utf-8")
    candidate_hash = sha256_text(candidate_text)
    candidate_state = manifest.artifacts["alignment_candidate.json"]
    audio = AudioMetadata.model_validate(registry.read_json("audio/metadata.json"))
    voice_review = VoiceReviewDocument.model_validate(registry.read_json("audio/review.json"))
    actual_audio_sha = sha256_bytes((run_dir / audio.path).read_bytes())
    if (
        candidate_hash != candidate_state.content_hash
        or candidate_hash != expected_candidate_hash
        or actual_audio_sha != expected_audio_sha256
        or audio.sha256 != expected_audio_sha256
    ):
        raise ValueError("REVIEW_BINDING_MISMATCH")
    validate_voice_approval(voice_review, actual_audio_sha)

    candidate = AlignmentCandidateDocument.model_validate_json(candidate_text)
    narration = NarrationDocument.model_validate(registry.read_json("narration.json"))
    expected_ids = [row.sentence_id for row in narration.sentences]
    if reviewed_sentence_ids != expected_ids:
        raise ValueError("ALIGNMENT_REVIEW_COVERAGE_INVALID")
    gate = validate_real_alignment(
        candidate, expected_ids, audio.duration_ms, actual_audio_sha,
        expected_texts={row.sentence_id: row.narration_text for row in narration.sentences},
    )
    if set(gate.issues) != {"ALIGNMENT_TEXT_MISMATCH"}:
        raise ValueError("ALIGNMENT_REVIEW_OVERRIDE_NOT_ALLOWED")
    if (
        candidate.normalized_ref == candidate.normalized_asr
        or "ALIGNMENT_ASR_REFERENCE_MISMATCH" not in candidate.warnings
    ):
        raise ValueError("ALIGNMENT_REVIEW_OVERRIDE_NOT_ALLOWED")

    candidate_state.status = "valid"
    candidate_state.updated_at = _now()
    reviewed_at = _now()
    review_document = AlignmentReviewDocument(
        run_id=run_id,
        reviewer=reviewer,
        reviewer_status="approved",
        reviewed_at=reviewed_at,
        reviewed_sentence_ids=reviewed_sentence_ids,
        reviewed_sentences=len(reviewed_sentence_ids),
        total_sentences=len(expected_ids),
        reviewed_coverage=f"{len(reviewed_sentence_ids)}/{len(expected_ids)}",
        candidate_hash=candidate_hash,
        audio_sha256=actual_audio_sha,
        voice_review_hash=manifest.artifacts["audio/review.json"].content_hash or "",
        model_id=candidate.model_id,
        model_revision=candidate.model_revision,
        automatic_text_consistency_passed=False,
        automatic_text_consistency_issue="ALIGNMENT_TEXT_MISMATCH",
        override_scope="candidate_and_audio_sha",
        global_gate_changed=False,
        timestamps_modified=False,
        raw_measurements_modified=False,
    )
    registry.write_json(
        "alignment_review.json", review_document.model_dump(mode="json"),
        "alignment_review", force=True,
    )
    review_hash = manifest.artifacts["alignment_review.json"].content_hash or ""

    alignment_payload = candidate.model_dump(mode="json")
    alignment_payload.pop("artifact_type", None)
    alignment_payload["review_hash"] = review_hash
    review_values = review_document.model_dump(mode="json")
    alignment_payload["human_review_override"] = {
        key: review_values[key] for key in (
            "reviewer_status", "reviewer", "reviewed_sentences", "total_sentences",
            "candidate_hash", "audio_sha256", "automatic_text_consistency_passed",
            "automatic_text_consistency_issue", "override_scope", "global_gate_changed",
        )
    }
    alignment = AlignmentDocument.model_validate(alignment_payload)
    output = registry.write_json(
        "alignment.json", alignment.model_dump(mode="json"),
        "audio_alignment", force=True,
    )
    manifest.stages["alignment_review"] = StageState(
        status="succeeded", attempts=1, started_at=reviewed_at,
        finished_at=reviewed_at, provider="human_review",
    )
    previous = manifest.stages.get("audio_alignment", StageState())
    manifest.stages["audio_alignment"] = StageState(
        status="succeeded", attempts=previous.attempts + 1,
        started_at=reviewed_at, finished_at=_now(), provider=candidate.provider,
    )
    registry.save_manifest()
    return output
