"""Human voice approval bound to an immutable audio hash."""
from __future__ import annotations

from datetime import datetime

from fanglei.v05_models import VoiceReviewDocument


def approve_voice(run_id: str, audio_sha256: str, *, reviewer: str,
                  voice: bool = True, rate: bool = True, pauses: bool = True,
                  number_pronunciation: bool = True) -> VoiceReviewDocument:
    if not all((voice, rate, pauses, number_pronunciation)):
        raise ValueError("VOICE_REVIEW_CHECKS_INCOMPLETE")
    return VoiceReviewDocument(
        run_id=run_id, audio_sha256=audio_sha256, status="approved", reviewer=reviewer,
        reviewed_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        voice_approved=voice, rate_approved=rate, pauses_approved=pauses,
        number_pronunciation_approved=number_pronunciation,
    )


def validate_voice_approval(review: VoiceReviewDocument, audio_sha256: str) -> None:
    if review.status != "approved" or review.audio_sha256 != audio_sha256 or not all((
        review.voice_approved, review.rate_approved, review.pauses_approved,
        review.number_pronunciation_approved,
    )):
        raise ValueError("VOICE_APPROVAL_STALE")
