from __future__ import annotations

import pytest
from pydantic import ValidationError

from fanglei.artifact_registry import ArtifactRegistry
from fanglei.models import RunManifest
from fanglei.providers.visual import DeterministicVisualPlanningProvider, VisualPlanningRequest
from fanglei.storyboard import build_storyboard
from fanglei.visual_models import VisualBeat, VisualBeatPlan
from fanglei.visual_timing import (
    apply_alignment_derived_timing,
    build_timing_aware_context,
    validate_timed_scene_coverage,
)


RUN_ID = "synthetic-retail-run"
AUDIO_SHA = "a" * 64
SCRIPT_SHA = "b" * 64
FACTS_SHA = "c" * 64
ANGLES_SHA = "d" * 64
SELECTION_SHA = "e" * 64
APPROVAL_SHA = "f" * 64
REVIEW_SHA = "1" * 64
ALIGNMENT_SHA = "2" * 64
SUBTITLE_SHA = "3" * 64


def _inputs() -> dict:
    script = {
        "schema_version": "3.0",
        "script_id": "script_synthetic",
        "angle_id": "angle_synthetic",
        "target_language": "zh-CN",
        "title": "合成零售指数",
        "target_duration_seconds": 60,
        "sentences": [
            {"sentence_id": "retail_001", "section": "hook", "sentence_type": "interpretation",
             "text": "这项合成指标有什么变化？", "claim_ids": []},
            {"sentence_id": "retail_002", "section": "phenomenon", "sentence_type": "verified_fact",
             "text": "合成零售指数：120 → 135。", "claim_ids": ["claim_retail"]},
            {"sentence_id": "retail_003", "section": "core_judgment", "sentence_type": "interpretation",
             "text": "这里只描述记录，不推断原因。", "claim_ids": []},
        ],
    }
    facts = {"schema_version": "2.2", "claims": [
        {"claim_id": "claim_retail", "claim_text": "合成零售指数由120变为135。",
         "verification_status": "verified", "verification_basis": "independent_corroboration",
         "allowed_downstream": True, "source_ids": ["source_synthetic"], "evidence": [],
         "authority_attestation": None},
        {"claim_id": "claim_restricted", "claim_text": "已核验但不允许下游。",
         "verification_status": "verified", "verification_basis": "independent_corroboration",
         "allowed_downstream": False, "source_ids": ["source_synthetic"], "evidence": [],
         "authority_attestation": None},
        {"claim_id": "claim_unverified", "claim_text": "尚未核验。",
         "verification_status": "unverified", "verification_basis": "none",
         "allowed_downstream": False, "source_ids": [], "evidence": [],
         "authority_attestation": None},
    ]}
    selected_angle = {
        "angle_id": "angle_synthetic", "title": "观察指标变化", "hook": "先看变化本身。",
        "core_question": "合成指标如何变化？", "core_insight": "只描述记录变化。",
        "hook_mechanism": "contrast", "audience_takeaway": "记录变化",
        "narrative_framing": "comparison", "eligibility": "eligible",
        "supporting_claim_ids": ["claim_retail"], "audience_relevance": 3, "novelty": 3,
        "hook_strength": 3, "visual_potential": 3, "explainability": 4,
        "risk_notes": [], "evidence_strength": 4, "controversy_risk": 0,
        "total_score": 70, "rejection_codes": [], "originality": {},
    }
    selection = {"schema_version": "human-angle-selection/1.0", "run_id": RUN_ID,
                 "selected_angle_id": "angle_synthetic", "source": "human",
                 "selected_at": "2026-09-29T12:00:00+08:00", "angles_sha256": ANGLES_SHA,
                 "facts_sha256": FACTS_SHA, "reviewer": "reviewer", "rationale": "synthetic test"}
    approval = {
        "schema_version": "human-script-approval/1.0", "status": "approved_for_tts",
        "run_id": RUN_ID, "case_id": "synthetic-case", "angle_id": "angle_synthetic",
        "facts_sha256": FACTS_SHA, "angles_sha256": ANGLES_SHA,
        "angle_selection_sha256": SELECTION_SHA, "terminology_sha256": "4" * 64,
        "human_script_edit_sha256": "5" * 64, "script_sha256": SCRIPT_SHA,
        "target_language": "zh-CN", "reviewer": "reviewer",
        "approved_at": "2026-09-29T12:00:00+08:00", "rationale": "synthetic test",
    }
    narration = {
        "schema_version": "5.1", "run_id": RUN_ID, "script_id": "script_synthetic", "language": "zh-CN",
        "sentences": [
            {"sentence_id": "retail_001", "original_text": script["sentences"][0]["text"],
             "narration_text": script["sentences"][0]["text"], "tts_spoken_text": "这项合成指标有什么变化？",
             "normalization_reason": "unchanged", "normalizations": [], "pause_after_ms": 0},
            {"sentence_id": "retail_002", "original_text": script["sentences"][1]["text"],
             "narration_text": script["sentences"][1]["text"], "tts_spoken_text": "合成零售指数：一百二十到一百三十五。",
             "normalization_reason": "spoken form", "normalizations": [], "pause_after_ms": 0},
            {"sentence_id": "retail_003", "original_text": script["sentences"][2]["text"],
             "narration_text": script["sentences"][2]["text"], "tts_spoken_text": script["sentences"][2]["text"],
             "normalization_reason": "unchanged", "normalizations": [], "pause_after_ms": 0},
        ],
        "semantic_validation": {"passed": True, "canonical_original_hash": "6" * 64,
                                 "canonical_narration_hash": "7" * 64, "issues": []},
    }
    audio_metadata = {
        "schema_version": "5.1", "path": "audio/narration.wav", "format": "wav", "codec": "pcm_s16le",
        "sample_rate_hz": 24000, "channels": 1, "duration_ms": 3000, "sha256": AUDIO_SHA,
        "provider": "local_fixture", "provider_type": "real", "provider_model": "fixture",
        "voice_id": "fixture", "language": "zh-CN", "speaking_rate": 1.0, "pitch_semitones": 0.0,
        "volume_gain_db": 0.0, "native_timestamps": [],
    }
    review = {
        "schema_version": "5.2", "run_id": RUN_ID, "audio_sha256": AUDIO_SHA,
        "script_sha256": SCRIPT_SHA, "status": "approved", "reviewer": "reviewer",
        "reviewed_at": "2026-09-29T12:00:00+08:00", "voice_approved": True,
        "rate_approved": True, "pauses_approved": True, "number_pronunciation_approved": True,
        "reason_code": None, "findings": [],
    }
    alignment = {
        "schema_version": "5.0", "run_id": RUN_ID, "audio_path": "audio/narration.wav",
        "audio_sha256": AUDIO_SHA, "audio_duration_ms": 3000,
        "provider": "proportional_sentence_timing", "method": "proportional_by_normalized_char_count",
        "sentences": [
            {"sentence_id": "retail_001", "start_ms": 0, "end_ms": 1000, "confidence": 0.0,
             "timing_source": "proportional_sentence", "text": narration["sentences"][0]["tts_spoken_text"],
             "confidence_source": "proportional_char_count_estimate_not_measured",
             "provider": "proportional_sentence_timing", "method": "proportional_by_normalized_char_count",
             "audio_sha256": AUDIO_SHA, "measured": False, "interpolated": True},
            {"sentence_id": "retail_002", "start_ms": 1000, "end_ms": 2000, "confidence": 0.0,
             "timing_source": "proportional_sentence", "text": narration["sentences"][1]["tts_spoken_text"],
             "confidence_source": "proportional_char_count_estimate_not_measured",
             "provider": "proportional_sentence_timing", "method": "proportional_by_normalized_char_count",
             "audio_sha256": AUDIO_SHA, "measured": False, "interpolated": True},
            {"sentence_id": "retail_003", "start_ms": 2000, "end_ms": 3000, "confidence": 0.0,
             "timing_source": "proportional_sentence", "text": narration["sentences"][2]["tts_spoken_text"],
             "confidence_source": "proportional_char_count_estimate_not_measured",
             "provider": "proportional_sentence_timing", "method": "proportional_by_normalized_char_count",
             "audio_sha256": AUDIO_SHA, "measured": False, "interpolated": True},
        ],
        "coverage_ratio": 1.0, "confidence": 0.0, "fallback_used": False, "warnings": [],
        "model_id": None, "model_revision": None, "confidence_source": None, "recognized_text": None,
        "normalized_ref": None, "normalized_asr": None, "text_match_cer": None,
        "voice_review_hash": REVIEW_SHA, "review_hash": None, "human_review_override": None,
    }
    subtitle = {
        "schema_version": "subtitle_track.v1", "run_id": RUN_ID, "script_id": "script_synthetic",
        "timing_source": "approved_sentence_alignment",
        "source": {"script_path": "script.json", "script_sha256": SCRIPT_SHA,
                   "alignment_path": "alignment.json", "alignment_sha256": ALIGNMENT_SHA,
                   "alignment_audio_sha256": AUDIO_SHA},
        "cues": [],
        "validation": {"passed": True, "sentence_coverage": 1.0, "text_exact_match": True,
                       "timing_exact_match": True, "issues": []},
    }
    for sentence, aligned in zip(script["sentences"], alignment["sentences"], strict=True):
        text = sentence["text"]
        subtitle["cues"].append({
            "cue_id": f"subtitle_{sentence['sentence_id']}", "sentence_id": sentence["sentence_id"],
            "text": text, "start_ms": aligned["start_ms"], "end_ms": aligned["end_ms"],
            "font_size_px": 52, "lines": [{"line_id": "line_01", "text": text,
                                             "start_char": 0, "end_char": len(text)}],
            "emphasis_spans": [],
        })
    return {
        "run_id": RUN_ID, "script": script, "script_sha256": SCRIPT_SHA,
        "facts": facts, "facts_sha256": FACTS_SHA, "selected_angle": selected_angle,
        "angle_selection": selection, "angle_selection_sha256": SELECTION_SHA,
        "angles_sha256": ANGLES_SHA, "script_approval": approval,
        "narration": narration, "audio_metadata": audio_metadata,
        "actual_audio_sha256": AUDIO_SHA, "actual_audio_duration_ms": 3000,
        "audio_quality": {
            "schema_version": "5.1", "audio_sha256": AUDIO_SHA, "provider": "local_fixture",
            "provider_type": "real", "duration_ms": 3000, "peak": 0.5, "peak_dbfs": -6.0,
            "rms": 0.1, "rms_dbfs": -20.0, "voiced_duration_ms": 2800, "voiced_ratio": 0.9,
            "frame_duration_ms": 20,
            "thresholds": {"min_peak": 0.1, "min_rms_dbfs": -35.0,
                            "voiced_frame_rms_dbfs": -40.0, "min_voiced_duration_ms": 100,
                            "min_voiced_ratio": 0.5},
            "passed": True, "gate_reasons": [], "production_eligible": True,
        },
        "voice_review": review, "voice_review_sha256": REVIEW_SHA,
        "script_terminology_sha256": "4" * 64, "human_script_edit_sha256": "5" * 64,
        "alignment": alignment, "alignment_sha256": ALIGNMENT_SHA,
        "subtitle_track": subtitle, "subtitle_sha256": SUBTITLE_SHA,
    }


def _context(**changes):
    inputs = _inputs()
    inputs.update(changes)
    return build_timing_aware_context(**inputs)


def _plan(context, groups=(('retail_001', 'retail_002'), ('retail_003',)), *, claim_override=None):
    roles = ("phenomenon", "judgment", "hook", "mechanism")
    beats = []
    for index, sentence_ids in enumerate(groups, start=1):
        claim_ids = ["claim_retail"] if "retail_002" in sentence_ids else []
        if claim_override is not None and index == 1:
            claim_ids = [claim_override]
        beats.append(VisualBeat(
            beat_id=f"beat_{index:03d}", order=index, cognitive_purpose="show the script",
            narrative_role=roles[min(index - 1, 3)], sentence_ids=list(sentence_ids),
            narration_summary="", core_visual_relationship="script-led scene", claim_ids=claim_ids,
            recommended_renderer="program_animation", estimated_duration_seconds=99.0,
        ))
    return VisualBeatPlan(run_id=RUN_ID, script_id="script_synthetic", beats=beats)


def test_timing_aware_context_binds_approved_media_and_uses_display_copy() -> None:
    context = _context()
    request = VisualPlanningRequest(run_id=RUN_ID, script=_inputs()["script"],
                                    allowed_claim_ids=set(context.allowed_claim_ids),
                                    timing_context=context)

    assert context.audio_sha256 == AUDIO_SHA
    assert context.audio_duration_ms == 3000
    assert context.timing_quality == "estimated"
    assert [segment.sentence_id for segment in context.segments] == [
        "retail_001", "retail_002", "retail_003"]
    assert context.segments[1].display_text == "合成零售指数：120 → 135。"
    assert context.segments[1].display_text != _inputs()["narration"]["sentences"][1]["tts_spoken_text"]
    assert "raw_audio" not in request.model_dump(mode="json")
    assert context.allowed_claim_ids == ["claim_retail"]
    assert [claim.claim_id for claim in context.eligible_claims] == ["claim_retail"]


def test_audio_without_human_approval_fails_closed() -> None:
    with pytest.raises(ValueError, match="VOICE_APPROVAL_REQUIRED"):
        _context(voice_review=None)


def test_stale_audio_approval_fails_closed() -> None:
    inputs = _inputs()
    inputs["voice_review"]["audio_sha256"] = "9" * 64
    with pytest.raises(ValueError, match="VOICE_APPROVAL_STALE"):
        build_timing_aware_context(**inputs)


def test_alignment_bound_to_different_audio_fails_closed() -> None:
    inputs = _inputs()
    inputs["alignment"]["audio_sha256"] = "9" * 64
    with pytest.raises(ValueError, match="ALIGNMENT_AUDIO_SHA_MISMATCH"):
        build_timing_aware_context(**inputs)


def test_subtitle_bound_to_different_script_or_alignment_fails_closed() -> None:
    inputs = _inputs()
    inputs["subtitle_track"]["source"]["script_sha256"] = "9" * 64
    with pytest.raises(ValueError, match="SUBTITLE_BINDING_MISMATCH"):
        build_timing_aware_context(**inputs)


@pytest.mark.parametrize("changed", ["audio/review.json", "alignment.json", "subtitle_track.json",
                                      "angle_selection.json"])
def test_timing_input_changes_invalidate_storyboard_descendants(tmp_path, changed) -> None:
    manifest = RunManifest(run_id=RUN_ID, created_at="2026-09-29T00:00:00+00:00",
                           updated_at="2026-09-29T00:00:00+00:00")
    registry = ArtifactRegistry(tmp_path, manifest, human_angle_selection_mode=True,
                                timing_aware_storyboard_mode=True)
    assert set(("audio/review.json", "alignment.json", "subtitle_track.json", "angle_selection.json")) <= set(
        registry.graph["storyboard.json"][1])
    for name in ("visual_beats.json", "storyboard.json", "visual_plan.md"):
        manifest.artifacts[name].status = "valid"
    registry.invalidate_descendants(changed)
    assert manifest.artifacts["storyboard.json"].status == "stale"
    assert manifest.artifacts["visual_plan.md"].status == "stale"


def test_adjacent_segments_derive_scene_ranges_from_alignment_not_planner_durations() -> None:
    inputs = _inputs()
    context = build_timing_aware_context(**inputs)
    plan = _plan(context)
    validate_timed_scene_coverage(plan, context, inputs["script"])
    board = apply_alignment_derived_timing(
        build_storyboard(plan, inputs["script"], inputs["facts"]), plan, context,
    )

    assert [(scene.start_ms, scene.end_ms) for scene in board.scenes] == [(0, 2000), (2000, 3000)]
    assert board.scenes[0].estimated_duration_seconds == 2.0
    assert board.scenes[0].relative_start == 0.0
    assert board.scenes[0].relative_end == pytest.approx(2 / 3)
    assert board.schema_version == "5.0"
    assert board.timing_basis == "alignment_derived"


def test_provider_timestamp_fields_are_rejected_as_non_authoritative() -> None:
    payload = {"schema_version": "4.0", "run_id": RUN_ID, "script_id": "script_synthetic",
               "beats": [{"beat_id": "beat_001", "order": 1, "cognitive_purpose": "x",
                          "narrative_role": "phenomenon", "sentence_ids": ["retail_001"],
                          "narration_summary": "x", "core_visual_relationship": "x",
                          "recommended_renderer": "program_animation", "estimated_duration_seconds": 1,
                          "start_ms": 100, "end_ms": 200}]}
    with pytest.raises(ValidationError):
        VisualBeatPlan.model_validate(payload)


def test_omitted_narration_segment_is_rejected() -> None:
    context = _context()
    plan = _plan(context, groups=(("retail_001",), ("retail_003",)))
    with pytest.raises(ValueError, match="VISUAL_SEGMENT_COVERAGE_INVALID"):
        validate_timed_scene_coverage(plan, context, _inputs()["script"])


def test_duplicate_primary_segment_is_rejected() -> None:
    context = _context()
    with pytest.raises(ValidationError, match="sentence IDs must be unique"):
        _plan(context, groups=(("retail_001", "retail_002"), ("retail_002", "retail_003")))


def test_noncontiguous_primary_group_is_rejected() -> None:
    context = _context()
    plan = _plan(context, groups=(("retail_001", "retail_003"), ("retail_002",)))
    with pytest.raises(ValueError, match="VISUAL_SEGMENT_COVERAGE_INVALID"):
        validate_timed_scene_coverage(plan, context, _inputs()["script"])


def test_noneligible_claim_reference_is_rejected() -> None:
    context = _context()
    plan = _plan(context, claim_override="claim_restricted")
    with pytest.raises(ValueError, match="VISUAL_CLAIM_NOT_ALLOWED"):
        validate_timed_scene_coverage(plan, context, _inputs()["script"])


def test_proportional_alignment_provenance_is_estimated_not_acoustic() -> None:
    inputs = _inputs()
    context = build_timing_aware_context(**inputs)
    plan = _plan(context)
    board = apply_alignment_derived_timing(build_storyboard(plan, inputs["script"], inputs["facts"]),
                                           plan, context)

    assert board.timing_provenance.alignment_method == "proportional_by_normalized_char_count"
    assert board.timing_provenance.timing_quality == "estimated"
    assert board.timing_provenance.scene_range_source == "alignment-derived"
    assert board.timing_provenance.final_render_approval_inferred is False


def test_legacy_visual_request_keeps_estimated_speech_storyboard_contract() -> None:
    script = _inputs()["script"]
    request = VisualPlanningRequest(run_id=RUN_ID, script=script, allowed_claim_ids={"claim_retail"})
    plan = DeterministicVisualPlanningProvider().plan(request)
    board = build_storyboard(plan, script, _inputs()["facts"])

    assert request.timing_context is None
    assert board.schema_version == "4.0"
    assert board.timing_basis == "estimated_speech"
    assert board.timing_provenance is None
