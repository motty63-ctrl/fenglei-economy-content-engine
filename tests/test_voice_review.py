import pytest

from fanglei.voice_review import approve_voice, validate_voice_approval


def test_approval_is_bound_to_audio_hash() -> None:
    review = approve_voice("run", "a" * 64, reviewer="human")
    validate_voice_approval(review, "a" * 64)
    with pytest.raises(ValueError, match="VOICE_APPROVAL_STALE"):
        validate_voice_approval(review, "b" * 64)


def test_approval_requires_all_listening_checks() -> None:
    with pytest.raises(ValueError, match="VOICE_REVIEW_CHECKS_INCOMPLETE"):
        approve_voice("run", "a" * 64, reviewer="human", number_pronunciation=False)
