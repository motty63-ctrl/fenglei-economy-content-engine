"""Approved-media bindings and owner-derived timing for visual planning."""
from __future__ import annotations

import re
from typing import Any, Mapping

from fanglei.angle_selection import HumanAngleSelectionV1
from fanglei.content_models import AngleCandidate, ScriptDraft
from fanglei.human_script_approval import HumanScriptApprovalV1
from fanglei.v05_models import (
    AlignmentDocument,
    AudioMetadata,
    AudioQualityDocument,
    NarrationDocument,
    VoiceReviewDocument,
)
from fanglei.v1b_models import SubtitleTrack
from fanglei.visual_models import (
    EligibleVisualClaim,
    Storyboard,
    StoryboardTimingProvenance,
    TimedNarrationSegment,
    TimedSubtitleCue,
    VisualBeatPlan,
    TimingAwareVisualContext,
)
from fanglei.voice_review import validate_voice_approval


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _require_hash(value: str, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{field.upper()}_HASH_INVALID")
    return value


def build_timing_aware_context(
    *,
    run_id: str,
    script: Mapping[str, Any],
    script_sha256: str,
    facts: Mapping[str, Any],
    facts_sha256: str,
    selected_angle: Mapping[str, Any],
    angle_selection: Mapping[str, Any],
    angle_selection_sha256: str,
    angles_sha256: str,
    script_approval: Mapping[str, Any],
    script_terminology_sha256: str,
    human_script_edit_sha256: str,
    narration: Mapping[str, Any],
    audio_metadata: Mapping[str, Any],
    actual_audio_sha256: str,
    actual_audio_duration_ms: int,
    audio_quality: Mapping[str, Any],
    voice_review: Mapping[str, Any] | None,
    voice_review_sha256: str | None,
    alignment: Mapping[str, Any],
    alignment_sha256: str,
    subtitle_track: Mapping[str, Any],
    subtitle_sha256: str,
) -> TimingAwareVisualContext:
    """Build a bounded visual request context after verifying owner artifact bindings.

    Raw audio bytes, complete source documents, and ineligible facts are deliberately
    not accepted by this function.
    """
    for value, field in (
        (script_sha256, "script"), (facts_sha256, "facts"), (angles_sha256, "angles"),
        (angle_selection_sha256, "angle_selection"), (script_terminology_sha256, "script_terminology"),
        (human_script_edit_sha256, "human_script_edit"), (actual_audio_sha256, "audio"),
        (alignment_sha256, "alignment"), (subtitle_sha256, "subtitle"),
    ):
        _require_hash(value, field)

    script_doc = ScriptDraft.model_validate(dict(script))
    if script_doc.angle_id == "" or not run_id.strip():
        raise ValueError("VISUAL_TIMING_IDENTITY_INVALID")
    selection = HumanAngleSelectionV1.model_validate(dict(angle_selection))
    if (selection.run_id != run_id or selection.angles_sha256 != angles_sha256
            or selection.facts_sha256 != facts_sha256
            or selection.selected_angle_id != selected_angle.get("angle_id")
            or selection.selected_angle_id != script_doc.angle_id
            or angle_selection_sha256 != _require_hash(angle_selection_sha256, "angle_selection")):
        raise ValueError("VISUAL_TIMING_ANGLE_SELECTION_STALE")
    angle = AngleCandidate.model_validate(dict(selected_angle))
    if angle.eligibility != "eligible":
        raise ValueError("VISUAL_TIMING_SELECTED_ANGLE_INELIGIBLE")

    approval = HumanScriptApprovalV1.model_validate(dict(script_approval))
    if any((
        approval.run_id != run_id,
        approval.angle_id != angle.angle_id,
        approval.script_sha256 != script_sha256,
        approval.facts_sha256 != facts_sha256,
        approval.angles_sha256 != angles_sha256,
        approval.angle_selection_sha256 != angle_selection_sha256,
        approval.terminology_sha256 != script_terminology_sha256,
        approval.human_script_edit_sha256 != human_script_edit_sha256,
    )):
        raise ValueError("VISUAL_TIMING_SCRIPT_APPROVAL_STALE")

    narration_doc = NarrationDocument.model_validate(dict(narration))
    if narration_doc.run_id != run_id or narration_doc.script_id != script_doc.script_id:
        raise ValueError("VISUAL_TIMING_NARRATION_IDENTITY_MISMATCH")
    script_rows = list(script_doc.sentences)
    narration_rows = list(narration_doc.sentences)
    expected_ids = [row.sentence_id for row in script_rows]
    if [row.sentence_id for row in narration_rows] != expected_ids:
        raise ValueError("VISUAL_TIMING_NARRATION_COVERAGE_MISMATCH")
    for script_row, narration_row in zip(script_rows, narration_rows, strict=True):
        if narration_row.original_text != script_row.text or narration_row.narration_text != script_row.text:
            raise ValueError("VISUAL_TIMING_NARRATION_DISPLAY_TEXT_MISMATCH")

    metadata = AudioMetadata.model_validate(dict(audio_metadata))
    quality = AudioQualityDocument.model_validate(dict(audio_quality))
    if (metadata.sha256 != actual_audio_sha256 or metadata.duration_ms != actual_audio_duration_ms
            or quality.audio_sha256 != actual_audio_sha256 or quality.duration_ms != actual_audio_duration_ms
            or not quality.production_eligible or not quality.passed):
        raise ValueError("VISUAL_TIMING_AUDIO_IDENTITY_OR_QUALITY_MISMATCH")
    if voice_review is None or voice_review_sha256 is None:
        raise ValueError("VOICE_APPROVAL_REQUIRED")
    _require_hash(voice_review_sha256, "voice_review")
    review = VoiceReviewDocument.model_validate(dict(voice_review))
    if review.run_id != run_id:
        raise ValueError("VOICE_APPROVAL_STALE")
    try:
        validate_voice_approval(review, actual_audio_sha256, script_sha256=script_sha256)
    except ValueError as error:
        raise ValueError("VOICE_APPROVAL_STALE") from error

    alignment_doc = AlignmentDocument.model_validate(dict(alignment))
    if (alignment_doc.run_id != run_id or alignment_doc.audio_sha256 != actual_audio_sha256
            or alignment_doc.audio_duration_ms != actual_audio_duration_ms
            or alignment_doc.voice_review_hash != voice_review_sha256
            or alignment_doc.coverage_ratio != 1 or alignment_doc.fallback_used):
        raise ValueError("ALIGNMENT_AUDIO_SHA_MISMATCH")
    if [row.sentence_id for row in alignment_doc.sentences] != expected_ids:
        raise ValueError("VISUAL_TIMING_ALIGNMENT_COVERAGE_MISMATCH")
    for narration_row, aligned in zip(narration_rows, alignment_doc.sentences, strict=True):
        if aligned.text != narration_row.spoken_text or aligned.audio_sha256 != actual_audio_sha256:
            raise ValueError("VISUAL_TIMING_ALIGNMENT_TEXT_OR_AUDIO_MISMATCH")
    previous_end = 0
    for aligned in alignment_doc.sentences:
        if aligned.start_ms < previous_end or aligned.end_ms > actual_audio_duration_ms:
            raise ValueError("VISUAL_TIMING_ALIGNMENT_INVALID_RANGE")
        previous_end = aligned.end_ms
    if not alignment_doc.sentences or alignment_doc.sentences[-1].end_ms != actual_audio_duration_ms:
        raise ValueError("VISUAL_TIMING_ALIGNMENT_DURATION_MISMATCH")

    subtitle = SubtitleTrack.model_validate(dict(subtitle_track))
    if (subtitle.run_id != run_id or subtitle.script_id != script_doc.script_id
            or subtitle.source.script_sha256 != script_sha256
            or subtitle.source.alignment_sha256 != alignment_sha256
            or subtitle.source.alignment_audio_sha256 != actual_audio_sha256
            or not subtitle.validation.passed or not subtitle.validation.text_exact_match
            or not subtitle.validation.timing_exact_match):
        raise ValueError("SUBTITLE_BINDING_MISMATCH")
    if [cue.sentence_id for cue in subtitle.cues] != expected_ids:
        raise ValueError("SUBTITLE_COVERAGE_MISMATCH")
    for script_row, aligned, cue in zip(script_rows, alignment_doc.sentences, subtitle.cues, strict=True):
        if (cue.text != script_row.text or cue.start_ms != aligned.start_ms
                or cue.end_ms != aligned.end_ms):
            raise ValueError("SUBTITLE_DISPLAY_OR_TIMING_MISMATCH")

    fact_rows = {
        row.get("claim_id"): row for row in facts.get("claims", [])
        if isinstance(row, Mapping) and isinstance(row.get("claim_id"), str)
    }
    selected_claim_ids = list(dict.fromkeys(angle.supporting_claim_ids))
    for sentence in script_rows:
        if not set(sentence.claim_ids) <= set(selected_claim_ids):
            raise ValueError("VISUAL_TIMING_SCRIPT_CLAIM_OUTSIDE_SELECTED_ANGLE")
    eligible_rows: list[EligibleVisualClaim] = []
    for claim_id in selected_claim_ids:
        claim = fact_rows.get(claim_id)
        if (claim is None or claim.get("verification_status") != "verified"
                or claim.get("allowed_downstream") is not True
                or claim.get("verification_basis") not in {
                    "independent_corroboration", "authoritative_primary_attestation",
                }):
            raise ValueError("VISUAL_TIMING_ANGLE_CLAIM_NOT_ELIGIBLE")
        attestation = claim.get("authority_attestation")
        eligible_rows.append(EligibleVisualClaim(
            claim_id=claim_id,
            claim_text=str(claim.get("claim_text") or claim.get("claim") or ""),
            source_ids=list(claim.get("source_ids", [])),
            verification_basis=claim["verification_basis"],
            attribution=(attestation.get("attribution") if isinstance(attestation, Mapping) else None),
            scope=(dict(attestation.get("scope", {}))
                   if isinstance(attestation, Mapping) and isinstance(attestation.get("scope"), Mapping)
                   else None),
        ))

    segments = [TimedNarrationSegment(
        sentence_id=script_row.sentence_id,
        start_ms=aligned.start_ms,
        end_ms=aligned.end_ms,
        display_text=script_row.text,
        subtitle_cue_id=cue.cue_id,
        claim_ids=list(script_row.claim_ids),
    ) for script_row, aligned, cue in zip(script_rows, alignment_doc.sentences, subtitle.cues, strict=True)]
    cues = [TimedSubtitleCue(
        cue_id=cue.cue_id, sentence_id=cue.sentence_id, start_ms=cue.start_ms,
        end_ms=cue.end_ms, display_text=cue.text,
    ) for cue in subtitle.cues]
    all_measured = all(row.measured is True and row.interpolated is False for row in alignment_doc.sentences)
    return TimingAwareVisualContext(
        run_id=run_id,
        selected_angle_id=angle.angle_id,
        selected_angle_title=angle.title,
        selected_angle_hook=angle.hook,
        selected_angle_core_question=angle.core_question,
        selected_angle_core_insight=angle.core_insight,
        angle_selection_sha256=angle_selection_sha256,
        script_id=script_doc.script_id,
        script_sha256=script_sha256,
        target_language=script_doc.target_language or narration_doc.language,
        audio_sha256=actual_audio_sha256,
        audio_duration_ms=actual_audio_duration_ms,
        voice_review_sha256=voice_review_sha256,
        alignment_sha256=alignment_sha256,
        alignment_method=alignment_doc.method,
        timing_quality="measured" if all_measured else "estimated",
        subtitle_sha256=subtitle_sha256,
        allowed_claim_ids=selected_claim_ids,
        eligible_claims=eligible_rows,
        segments=segments,
        subtitle_cues=cues,
    )


def validate_timed_scene_coverage(
    plan: VisualBeatPlan,
    context: TimingAwareVisualContext,
    script: Mapping[str, Any],
) -> None:
    if plan.run_id != context.run_id or plan.script_id != context.script_id:
        raise ValueError("VISUAL_TIMING_PLAN_IDENTITY_MISMATCH")
    expected = [row.sentence_id for row in context.segments]
    actual = [sentence_id for beat in plan.beats for sentence_id in beat.sentence_ids]
    if actual != expected:
        raise ValueError("VISUAL_SEGMENT_COVERAGE_INVALID")
    script_rows = {row.get("sentence_id"): row for row in script.get("sentences", [])}
    for beat in plan.beats:
        if not set(beat.claim_ids) <= set(context.allowed_claim_ids):
            raise ValueError("VISUAL_CLAIM_NOT_ALLOWED")
        expected_claims = list(dict.fromkeys(
            claim_id for sentence_id in beat.sentence_ids
            for claim_id in script_rows[sentence_id].get("claim_ids", [])
        ))
        if beat.claim_ids != expected_claims:
            raise ValueError("VISUAL_BEAT_CLAIM_BINDING_MISMATCH")
        if not set(expected_claims) <= set(context.allowed_claim_ids):
            raise ValueError("VISUAL_CLAIM_NOT_ALLOWED")


def apply_alignment_derived_timing(
    storyboard: Storyboard,
    plan: VisualBeatPlan,
    context: TimingAwareVisualContext,
) -> Storyboard:
    """Derive scene ranges from canonical segment IDs; ignore planner durations."""
    validate_timed_scene_coverage(plan, context, {
        "sentences": [
            {"sentence_id": segment.sentence_id, "claim_ids": segment.claim_ids}
            for segment in context.segments
        ],
    })
    if storyboard.run_id != context.run_id or storyboard.script_id != context.script_id:
        raise ValueError("VISUAL_TIMING_STORYBOARD_IDENTITY_MISMATCH")
    if len(storyboard.scenes) != len(plan.beats):
        raise ValueError("VISUAL_TIMING_SCENE_COVERAGE_INVALID")

    segments = {row.sentence_id: row for row in context.segments}
    payload = storyboard.model_dump(mode="json")
    previous_end = 0
    for scene, beat in zip(payload["scenes"], plan.beats, strict=True):
        if scene["beat_ids"] != [beat.beat_id] or scene["sentence_ids"] != beat.sentence_ids:
            raise ValueError("VISUAL_TIMING_SCENE_SEGMENT_BINDING_MISMATCH")
        linked = [segments[sentence_id] for sentence_id in beat.sentence_ids]
        start_ms, end_ms = linked[0].start_ms, linked[-1].end_ms
        if start_ms < previous_end:
            raise ValueError("VISUAL_TIMING_SCENE_OVERLAP")
        if not (0 <= start_ms < end_ms <= context.audio_duration_ms):
            raise ValueError("VISUAL_TIMING_SCENE_OUT_OF_BOUNDS")
        scene["start_ms"] = start_ms
        scene["end_ms"] = end_ms
        scene["estimated_duration_seconds"] = (end_ms - start_ms) / 1000
        scene["relative_start"] = start_ms / context.audio_duration_ms
        scene["relative_end"] = end_ms / context.audio_duration_ms
        previous_end = end_ms

    payload["schema_version"] = "5.0"
    payload["timing_basis"] = "alignment_derived"
    payload["total_estimated_duration_seconds"] = context.audio_duration_ms / 1000
    payload["timing_provenance"] = StoryboardTimingProvenance(
        audio_sha256=context.audio_sha256,
        audio_duration_ms=context.audio_duration_ms,
        voice_review_sha256=context.voice_review_sha256,
        alignment_sha256=context.alignment_sha256,
        alignment_method=context.alignment_method,
        subtitle_sha256=context.subtitle_sha256,
        timing_quality=context.timing_quality,
        final_render_approval_inferred=False,
    ).model_dump(mode="json")
    return Storyboard.model_validate(payload)
