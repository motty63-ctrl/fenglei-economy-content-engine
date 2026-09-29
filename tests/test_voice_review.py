import pytest

from fanglei.voice_review import (
    approve_voice,
    record_voice_review,
    validate_voice_approval,
)


def test_approval_is_bound_to_audio_hash() -> None:
    review = approve_voice("run", "a" * 64, reviewer="human")
    validate_voice_approval(review, "a" * 64)
    with pytest.raises(ValueError, match="VOICE_APPROVAL_STALE"):
        validate_voice_approval(review, "b" * 64)


def test_approval_requires_all_listening_checks() -> None:
    with pytest.raises(ValueError, match="VOICE_REVIEW_CHECKS_INCOMPLETE"):
        approve_voice("run", "a" * 64, reviewer="human", number_pronunciation=False)


def test_changes_required_review_is_bound_and_cannot_unlock_alignment() -> None:
    review = record_voice_review(
        "run", "a" * 64, reviewer="human", status="changes_required",
        script_sha256="b" * 64,
        voice=True, rate=True, pauses=True, number_pronunciation=False,
        reason_code="numeric_pronunciation",
        findings=["16.2万 was spoken digit by digit"],
    )
    assert review.schema_version == "5.2"
    assert review.status == "changes_required"
    assert review.audio_sha256 == "a" * 64
    assert review.script_sha256 == "b" * 64
    with pytest.raises(ValueError, match="VOICE_APPROVAL_STALE"):
        validate_voice_approval(review, "a" * 64)


def test_changes_required_review_requires_auditable_finding() -> None:
    with pytest.raises(ValueError, match="VOICE_REVIEW_FINDINGS_REQUIRED"):
        record_voice_review(
            "run", "a" * 64, reviewer="human", status="changes_required",
            script_sha256="b" * 64,
            voice=True, rate=True, pauses=True, number_pronunciation=False,
            reason_code="numeric_pronunciation", findings=[],
        )


def test_schema_52_approval_is_bound_to_current_script_hash() -> None:
    review = approve_voice(
        "run", "a" * 64, reviewer="human", script_sha256="b" * 64,
    )
    validate_voice_approval(review, "a" * 64, script_sha256="b" * 64)
    with pytest.raises(ValueError, match="VOICE_APPROVAL_STALE"):
        validate_voice_approval(review, "a" * 64, script_sha256="c" * 64)
