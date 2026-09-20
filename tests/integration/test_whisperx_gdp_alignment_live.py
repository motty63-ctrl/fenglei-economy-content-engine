"""Opt-in real WhisperX canary for the approved GDP narration."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from fanglei.audio_alignment import run_alignment_candidate
from fanglei.artifacts import sha256_bytes
from fanglei.providers.whisperx_alignment import (
    LocalWhisperXAlignmentProvider,
    WhisperXLocalEngine,
)


RUN_ID = "2026-09-08-004-2024-us-real-gdp-growth"
APPROVED_SHA = "3bf65eec73b721f79de32980cbc9333752c137b1b1cb14559916a0a790af7330"


@pytest.mark.integration
def test_whisperx_gdp_alignment_live() -> None:
    if os.environ.get("RUN_WHISPERX_ALIGNMENT_INTEGRATION") != "1":
        pytest.skip("set RUN_WHISPERX_ALIGNMENT_INTEGRATION=1")

    runs_dir = Path(os.environ["WHISPERX_GDP_RUNS_DIR"])
    run_dir = runs_dir / RUN_ID
    audio_path = run_dir / "audio" / "narration.wav"
    assert sha256_bytes(audio_path.read_bytes()) == APPROVED_SHA
    narration = json.loads((run_dir / "narration.json").read_text(encoding="utf-8"))
    review = json.loads((run_dir / "audio" / "review.json").read_text(encoding="utf-8"))
    assert review["status"] == "approved"
    assert review["audio_sha256"] == APPROVED_SHA
    references = [
        {"sentence_id": row["sentence_id"], "text": row["narration_text"]}
        for row in narration["sentences"]
    ]
    assert len(references) == 14

    raw_path = Path(os.environ["WHISPERX_ALIGNMENT_CACHE_DIR"]) / "gdp-canary-payload.json"
    revision = os.environ["WHISPERX_MODEL_REVISION"]
    if os.environ.get("WHISPERX_REPLAY_PAYLOAD") == "1":
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        model_id = payload["model_id"]
    else:
        engine = WhisperXLocalEngine(
            asr_model_id=os.environ["WHISPERX_ASR_SNAPSHOT"],
            align_model_id=os.environ["WHISPERX_CTC_SNAPSHOT"],
            model_revision=revision,
            cache_dir=Path(os.environ["WHISPERX_ALIGNMENT_CACHE_DIR"]),
            device="cpu",
            compute_type="int8",
        )
        payload = engine.align(
            audio_path=audio_path,
            reference_sentences=references,
            language=narration["language"],
            diarize=False,
        )
        model_id = engine.model_id
        raw_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    class ReplayEngine:
        def align(self, **kwargs):
            return payload

    provider = LocalWhisperXAlignmentProvider(
        model_id=model_id,
        model_revision=revision,
        engine=ReplayEngine(),
    )
    try:
        candidate_path = run_alignment_candidate(RUN_ID, runs_dir, provider, force=True)
    except ValueError as error:
        if str(error) != "ALIGNMENT_ASR_REFERENCE_MISMATCH":
            raise
        candidate_path = run_dir / "alignment_candidate.json"
        manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        assert candidate_path.is_file()
        assert manifest["artifacts"]["alignment_candidate.json"]["status"] == "failed"
        assert manifest["artifacts"]["alignment.json"]["status"] != "valid"
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    assert len(candidate["sentences"]) == 14
    assert candidate["coverage_ratio"] == 1
    assert candidate["audio_sha256"] == APPROVED_SHA
    assert candidate["method"] == "forced_alignment"
