"""Human voice approval bound to an immutable audio hash."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from fanglei.v05_models import VoiceReviewDocument


def approve_voice(run_id: str, audio_sha256: str, *, reviewer: str,
                  voice: bool = True, rate: bool = True, pauses: bool = True,
                  number_pronunciation: bool = True,
                  script_sha256: str | None = None) -> VoiceReviewDocument:
    if not all((voice, rate, pauses, number_pronunciation)):
        raise ValueError("VOICE_REVIEW_CHECKS_INCOMPLETE")
    if script_sha256 is not None:
        return record_voice_review(
            run_id, audio_sha256, reviewer=reviewer, status="approved",
            script_sha256=script_sha256, voice=voice, rate=rate, pauses=pauses,
            number_pronunciation=number_pronunciation,
        )
    return VoiceReviewDocument(
        run_id=run_id, audio_sha256=audio_sha256, status="approved", reviewer=reviewer,
        reviewed_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        voice_approved=voice, rate_approved=rate, pauses_approved=pauses,
        number_pronunciation_approved=number_pronunciation,
    )


def record_voice_review(
    run_id: str,
    audio_sha256: str,
    *,
    reviewer: str,
    status: Literal["approved", "changes_required"],
    script_sha256: str,
    voice: bool,
    rate: bool,
    pauses: bool,
    number_pronunciation: bool,
    reason_code: str | None = None,
    findings: list[str] | None = None,
) -> VoiceReviewDocument:
    """Build a timestamped, script/audio-bound human decision for the voice-review owner."""
    findings = findings or []
    if status == "approved" and not all((voice, rate, pauses, number_pronunciation)):
        raise ValueError("VOICE_REVIEW_CHECKS_INCOMPLETE")
    return VoiceReviewDocument(
        schema_version="5.2", run_id=run_id, audio_sha256=audio_sha256,
        script_sha256=script_sha256, status=status, reviewer=reviewer,
        reviewed_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        voice_approved=voice, rate_approved=rate, pauses_approved=pauses,
        number_pronunciation_approved=number_pronunciation,
        reason_code=reason_code, findings=findings,
    )


def validate_voice_approval(
    review: VoiceReviewDocument,
    audio_sha256: str,
    *,
    script_sha256: str | None = None,
) -> None:
    if review.status != "approved" or review.audio_sha256 != audio_sha256 or not all((
        review.voice_approved, review.rate_approved, review.pauses_approved,
        review.number_pronunciation_approved,
    )):
        raise ValueError("VOICE_APPROVAL_STALE")
    if (script_sha256 is not None and review.schema_version == "5.2"
            and review.script_sha256 != script_sha256):
        raise ValueError("VOICE_APPROVAL_STALE")
