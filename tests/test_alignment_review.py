import json

import pytest

from fanglei.alignment_calibration import promote_alignment
from fanglei.audio_alignment import run_alignment_candidate
from fanglei.providers.alignment import AlignmentResult
from tests.test_real_alignment_pipeline import MeasuredProvider, _production_ready_run


class MismatchedAsrProvider(MeasuredProvider):
    def align(self, request):
        result = super().align(request)
        return AlignmentResult(
            **{**result.__dict__, "recognized_text": "第二句。第一句。"}
        )


def _failed_candidate(tmp_path):
    run, audio_sha = _production_ready_run(tmp_path)
    with pytest.raises(ValueError, match="ALIGNMENT_ASR_REFERENCE_MISMATCH"):
        run_alignment_candidate(run.name, tmp_path, MismatchedAsrProvider())
    manifest = json.loads((run / "run.json").read_text(encoding="utf-8"))
    return run, audio_sha, manifest["artifacts"]["alignment_candidate.json"]["content_hash"]


def test_human_review_override_promotes_only_exact_candidate_and_audio(tmp_path) -> None:
    run, audio_sha, candidate_hash = _failed_candidate(tmp_path)
    candidate = json.loads((run / "alignment_candidate.json").read_text(encoding="utf-8"))

    output = promote_alignment(
        run.name, tmp_path, reviewer="human",
        reviewed_sentence_ids=["sentence_001", "sentence_002"],
        expected_candidate_hash=candidate_hash,
        expected_audio_sha256=audio_sha,
    )

    alignment = json.loads(output.read_text(encoding="utf-8"))
    review = json.loads((run / "alignment_review.json").read_text(encoding="utf-8"))
    manifest = json.loads((run / "run.json").read_text(encoding="utf-8"))
    assert alignment["sentences"] == candidate["sentences"]
    assert alignment["recognized_text"] == candidate["recognized_text"]
    assert alignment["model_id"] == candidate["model_id"]
    assert alignment["model_revision"] == candidate["model_revision"]
    assert review["reviewer_status"] == "approved"
    assert review["reviewed_sentences"] == 2
    assert review["total_sentences"] == 2
    assert review["candidate_hash"] == candidate_hash
    assert review["audio_sha256"] == audio_sha
    assert review["automatic_text_consistency_passed"] is False
    assert review["automatic_text_consistency_issue"] == "ALIGNMENT_TEXT_MISMATCH"
    assert review["override_scope"] == "candidate_and_audio_sha"
    assert review["global_gate_changed"] is False
    assert review["timestamps_modified"] is False
    assert alignment["review_hash"] == manifest["artifacts"]["alignment_review.json"]["content_hash"]
    assert alignment["human_review_override"]["candidate_hash"] == candidate_hash
    assert manifest["artifacts"]["alignment_candidate.json"]["status"] == "valid"
    assert manifest["artifacts"]["alignment_review.json"]["status"] == "valid"
    assert manifest["artifacts"]["alignment.json"]["status"] == "valid"


@pytest.mark.parametrize("field", ["candidate", "audio"])
def test_review_binding_mismatch_cannot_promote(tmp_path, field) -> None:
    run, audio_sha, candidate_hash = _failed_candidate(tmp_path)
    with pytest.raises(ValueError, match="REVIEW_BINDING_MISMATCH"):
        promote_alignment(
            run.name, tmp_path, reviewer="human",
            reviewed_sentence_ids=["sentence_001", "sentence_002"],
            expected_candidate_hash="f" * 64 if field == "candidate" else candidate_hash,
            expected_audio_sha256="e" * 64 if field == "audio" else audio_sha,
        )
    manifest = json.loads((run / "run.json").read_text(encoding="utf-8"))
    assert manifest["artifacts"]["alignment.json"]["status"] != "valid"


def test_all_sentence_ids_must_be_human_reviewed(tmp_path) -> None:
    run, audio_sha, candidate_hash = _failed_candidate(tmp_path)
    with pytest.raises(ValueError, match="ALIGNMENT_REVIEW_COVERAGE_INVALID"):
        promote_alignment(
            run.name, tmp_path, reviewer="human",
            reviewed_sentence_ids=["sentence_001"],
            expected_candidate_hash=candidate_hash,
            expected_audio_sha256=audio_sha,
        )
