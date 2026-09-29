"""Compile renderer timing exclusively from real sentence alignment."""
from __future__ import annotations

import json
import hashlib
from pathlib import PurePosixPath
import xml.etree.ElementTree as ET
from typing import Any, Mapping

from fanglei.artifacts import sha256_text
from fanglei.human_storyboard_recovery import canonical_json_sha256
from fanglei.human_visual_asset_recovery import HumanVisualAssetReviewV1
from fanglei.v05_models import (
    AlignmentDocument,
    AudioMetadata,
    TimelineComposition,
    TimelineDocument,
    TimelineGap,
    TimelineMotionCue,
    TimelineSceneVisual,
    TimelineSpan,
    TimelineSubtitleCue,
    TimelineValidation,
)
from fanglei.v1b_models import SubtitleTrack


def _range(sentence_ids: list[str], aligned: dict[str, TimelineSpan]) -> tuple[int, int]:
    if not sentence_ids or any(sentence_id not in aligned for sentence_id in sentence_ids):
        raise ValueError("TIMELINE_SENTENCE_MAPPING_INVALID")
    return aligned[sentence_ids[0]].start_ms, aligned[sentence_ids[-1]].end_ms


def compile_timeline(alignment: AlignmentDocument, storyboard: dict,
                     visual_beats: dict, audio: AudioMetadata) -> TimelineDocument:
    if alignment.audio_sha256 != audio.sha256 or alignment.audio_duration_ms != audio.duration_ms:
        raise ValueError("TIMELINE_AUDIO_MISMATCH")
    proportional_mode = (
        alignment.provider == "proportional_sentence_timing"
        and alignment.method == "proportional_by_normalized_char_count"
    )
    proportional_rows = [row for row in alignment.sentences
                         if row.timing_source == "proportional_sentence"]
    if proportional_mode:
        if (alignment.confidence != 0
                or "SENTENCE_BOUNDARIES_PROPORTIONAL_ESTIMATE_NOT_MEASURED" not in alignment.warnings
                or len(proportional_rows) != len(alignment.sentences)
                or any(row.provider != alignment.provider or row.method != alignment.method
                       or row.audio_sha256 != alignment.audio_sha256
                       or row.measured is not False or row.interpolated is not True
                       for row in alignment.sentences)):
            raise ValueError("TIMELINE_PROPORTIONAL_PROVENANCE_INVALID")
    elif proportional_rows:
        raise ValueError("TIMELINE_PROPORTIONAL_PROVENANCE_INVALID")
    timing_source = (
        "proportional_sentence_timing" if proportional_mode else "real_sentence_alignment"
    )
    sentences = [TimelineSpan(
        sentence_id=row.sentence_id,
        sentence_ids=[row.sentence_id],
        start_ms=row.start_ms,
        end_ms=row.end_ms,
        timing_source=timing_source,
    ) for row in alignment.sentences]
    by_sentence = {row.sentence_id: row for row in sentences if row.sentence_id}
    beats: list[TimelineSpan] = []
    for beat in visual_beats.get("beats", []):
        start, end = _range(beat["sentence_ids"], by_sentence)
        beats.append(TimelineSpan(
            beat_id=beat["beat_id"], sentence_ids=beat["sentence_ids"],
            start_ms=start, end_ms=end, timing_source=timing_source,
        ))
    scenes: list[TimelineSpan] = []
    for scene in storyboard.get("scenes", []):
        start, end = _range(scene["sentence_ids"], by_sentence)
        scenes.append(TimelineSpan(
            scene_id=scene["scene_id"], beat_ids=scene["beat_ids"],
            sentence_ids=scene["sentence_ids"], start_ms=start, end_ms=end,
            timing_source=timing_source,
        ))
    gaps = [TimelineGap(
        after_sentence_id=previous.sentence_id or "",
        start_ms=previous.end_ms,
        end_ms=current.start_ms,
        duration_ms=current.start_ms - previous.end_ms,
    ) for previous, current in zip(sentences, sentences[1:]) if current.start_ms > previous.end_ms]
    estimated = storyboard.get("total_estimated_duration_seconds")
    alignment_payload = json.dumps(alignment.model_dump(mode="json"), ensure_ascii=False,
                                   sort_keys=True, separators=(",", ":"))
    return TimelineDocument(
        run_id=alignment.run_id,
        audio={
            "path": audio.path,
            "sha256": audio.sha256,
            "duration_ms": audio.duration_ms,
        },
        alignment={
            "artifact": "alignment.json",
            "sha256": sha256_text(alignment_payload),
            "method": alignment.method,
            "provider": alignment.provider,
        },
        sentences=sentences,
        beats=beats,
        scenes=scenes,
        gaps=gaps,
        validation=TimelineValidation(
            passed=True,
            actual_audio_duration_ms=audio.duration_ms,
            estimated_duration_reference_ms=round(float(estimated) * 1000) if estimated is not None else None,
            issues=[],
        ),
    )


def compile_approved_visual_timeline(
    alignment: AlignmentDocument,
    *,
    storyboard: dict[str, Any],
    visual_beats: dict[str, Any],
    audio: AudioMetadata,
    visual_bundle_manifest: dict[str, Any],
    visual_bundle_sha256: str,
    visual_review: HumanVisualAssetReviewV1 | dict[str, Any],
    visual_review_sha256: str,
    subtitle_track: SubtitleTrack | dict[str, Any],
    subtitle_sha256: str,
    dependency_hashes: dict[str, str],
    asset_bytes: Mapping[str, bytes],
    storyboard_artifact_sha256: str,
    storyboard_approval_sha256: str,
    script_sha256: str,
    script_approval_sha256: str,
    audio_review_sha256: str,
) -> TimelineDocument:
    """Compile a V0.2 timeline only from a current human-approved visual bundle."""
    review = (
        visual_review if isinstance(visual_review, HumanVisualAssetReviewV1)
        else HumanVisualAssetReviewV1.model_validate(visual_review)
    )
    subtitles = subtitle_track if isinstance(subtitle_track, SubtitleTrack) else SubtitleTrack.model_validate(
        subtitle_track
    )
    base = compile_timeline(alignment, storyboard, visual_beats, audio)
    storyboard_sha256 = canonical_json_sha256(storyboard)
    if (
        review.decision != "approved_for_timeline"
        or review.candidate_id != visual_bundle_manifest.get("candidate_id")
        or review.run_id != alignment.run_id
        or review.case_id != visual_bundle_manifest.get("case_id")
        or visual_bundle_manifest.get("run_id") != alignment.run_id
        or visual_bundle_manifest.get("review_status") != "pending_human_visual_review"
        or review.storyboard_sha256 != storyboard_sha256
        or visual_bundle_manifest.get("candidate_storyboard_sha256") != storyboard_sha256
        or review.storyboard_artifact_sha256 != storyboard_artifact_sha256
        or review.storyboard_approval_sha256 != storyboard_approval_sha256
        or review.visual_bundle_sha256 != visual_bundle_sha256
    ):
        raise ValueError("TIMELINE_VISUAL_APPROVAL_BINDING_INVALID")
    if review.candidate_id == 3 and not {
        "angle_selection.json", "facts.json", "script.json", "human_script_approval.json",
        "audio/narration.wav", "audio/review.json", "alignment.json", "subtitle_track.json",
    }.issubset(review.dependency_hashes):
        raise ValueError("TIMELINE_VISUAL_APPROVAL_CHAIN_INCOMPLETE")
    for name, digest in review.dependency_hashes.items():
        if dependency_hashes.get(name) != digest:
            raise ValueError("TIMELINE_VISUAL_APPROVAL_DEPENDENCIES_STALE")

    if subtitles.run_id != alignment.run_id:
        raise ValueError("TIMELINE_SUBTITLE_RUN_MISMATCH")
    if (
        subtitles.source.script_sha256 != script_sha256
        or subtitles.source.alignment_sha256 != dependency_hashes.get("alignment.json")
        or subtitles.source.alignment_audio_sha256 != audio.sha256
    ):
        raise ValueError("TIMELINE_SUBTITLE_SOURCE_BINDING_INVALID")
    if not subtitles.validation.passed:
        raise ValueError("TIMELINE_SUBTITLE_VALIDATION_FAILED")

    scene_rows = visual_bundle_manifest.get("scenes")
    if (
        not isinstance(scene_rows, list)
        or len(scene_rows) != len(base.scenes)
        or visual_bundle_manifest.get("scene_count") != len(base.scenes)
    ):
        raise ValueError("TIMELINE_VISUAL_SCENE_COVERAGE_INVALID")
    visuals: list[TimelineSceneVisual] = []
    storyboard_scenes = storyboard.get("scenes")
    if not isinstance(storyboard_scenes, list) or len(storyboard_scenes) != len(base.scenes):
        raise ValueError("TIMELINE_STORYBOARD_SCENE_COVERAGE_INVALID")
    for index, (timing, asset_row, storyboard_scene) in enumerate(
        zip(base.scenes, scene_rows, storyboard_scenes, strict=True), start=1,
    ):
        if (
            asset_row.get("scene_id") != timing.scene_id
            or asset_row.get("order") != index
            or asset_row.get("start_ms") != timing.start_ms
            or asset_row.get("end_ms") != timing.end_ms
            or storyboard_scene.get("scene_id") != timing.scene_id
        ):
            raise ValueError("TIMELINE_SCENE_RANGE_MISMATCH")
        expected_claim_ids = list(dict.fromkeys(
            claim_id for item in storyboard_scene.get("objects", [])
            for claim_id in item.get("claim_ids", [])
        ))
        if (
            asset_row.get("sentence_ids") != storyboard_scene.get("sentence_ids")
            or asset_row.get("claim_ids") != expected_claim_ids
        ):
            raise ValueError("TIMELINE_SCENE_EVIDENCE_MAPPING_MISMATCH")
        asset_name = asset_row.get("asset_path")
        asset_path = PurePosixPath(asset_name) if isinstance(asset_name, str) else None
        if (
            asset_path is None or asset_path.is_absolute()
            or any(part in {"", ".", ".."} for part in asset_path.parts)
            or "\\" in asset_name
        ):
            raise ValueError("TIMELINE_VISUAL_ASSET_PATH_INVALID")
        payload = asset_bytes.get(asset_name)
        expected_asset_hash = asset_row.get("asset_sha256")
        if (
            payload is None or not isinstance(payload, bytes)
            or hashlib.sha256(payload).hexdigest() != expected_asset_hash
        ):
            raise ValueError("TIMELINE_VISUAL_ASSET_HASH_MISMATCH")
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as error:
            raise ValueError("TIMELINE_VISUAL_ASSET_SVG_INVALID") from error
        object_ids = [
            node.attrib["data-object-id"] for node in root.iter()
            if "data-object-id" in node.attrib
        ]
        manifest_objects = asset_row.get("objects")
        expected_object_ids = [
            row.get("object_id") for row in manifest_objects if isinstance(row, dict)
        ] if isinstance(manifest_objects, list) else []
        if not object_ids or len(object_ids) != len(set(object_ids)) or set(object_ids) != set(expected_object_ids):
            raise ValueError("TIMELINE_VISUAL_OBJECT_MAPPING_INVALID")
        duration = timing.end_ms - timing.start_ms
        motion_window = min(900, max(0, duration // 4))
        motion_duration = min(360, max(120, duration // 12))
        step_ms = motion_window // max(1, len(object_ids) - 1)
        motion = [TimelineMotionCue(
            object_id=object_id,
            effect="fade_in",
            delay_ms=min(index * step_ms, max(0, duration - 120)),
            duration_ms=min(motion_duration, max(1, duration - min(index * step_ms, max(0, duration - 120)))),
        ) for index, object_id in enumerate(object_ids)]
        visuals.append(TimelineSceneVisual(
            scene_id=timing.scene_id or "",
            order=index,
            start_ms=timing.start_ms,
            end_ms=timing.end_ms,
            asset_path=asset_path.as_posix(),
            asset_sha256=expected_asset_hash,
            claim_ids=list(asset_row.get("claim_ids", [])),
            sentence_ids=list(asset_row.get("sentence_ids", [])),
            object_ids=object_ids,
            motion=motion,
        ))

    sentence_spans = {row.sentence_id: row for row in base.sentences if row.sentence_id}
    if [cue.sentence_id for cue in subtitles.cues] != [
        row.sentence_id for row in base.sentences if row.sentence_id
    ]:
        raise ValueError("TIMELINE_SUBTITLE_SENTENCE_COVERAGE_INVALID")
    subtitle_cues: list[TimelineSubtitleCue] = []
    for cue in subtitles.cues:
        aligned = sentence_spans[cue.sentence_id]
        if cue.start_ms != aligned.start_ms or cue.end_ms != aligned.end_ms:
            raise ValueError("TIMELINE_SUBTITLE_ALIGNMENT_MISMATCH")
        if cue.end_ms > audio.duration_ms:
            raise ValueError("TIMELINE_SUBTITLE_EXCEEDS_AUDIO")
        subtitle_cues.append(TimelineSubtitleCue(
            cue_id=cue.cue_id,
            sentence_id=cue.sentence_id,
            text=cue.text,
            lines=[line.text for line in cue.lines],
            start_ms=cue.start_ms,
            end_ms=cue.end_ms,
            font_size_px=cue.font_size_px,
        ))

    bundle_artifact = (
        "visual_assets" if review.candidate_id == 1
        else f"visual_assets_candidate_{review.candidate_id}"
    )
    review_artifact = f"human_visual_asset_review_candidate_{review.candidate_id}.json"
    expected_bindings = {
        bundle_artifact: visual_bundle_sha256,
        review_artifact: visual_review_sha256,
        "human_storyboard_candidate.json": storyboard_artifact_sha256,
        "human_storyboard_approval.json": storyboard_approval_sha256,
        "script.json": script_sha256,
        "human_script_approval.json": script_approval_sha256,
        "audio/narration.wav": audio.sha256,
        "audio/review.json": audio_review_sha256,
        "alignment.json": dependency_hashes.get("alignment.json", ""),
        "subtitle_track.json": subtitle_sha256,
    }
    if review.candidate_id == 3:
        expected_bindings.update({
            "angle_selection.json": dependency_hashes.get("angle_selection.json", ""),
            "facts.json": dependency_hashes.get("facts.json", ""),
        })
    if any(dependency_hashes.get(name) != digest for name, digest in expected_bindings.items()):
        raise ValueError("TIMELINE_COMPOSITION_DEPENDENCIES_STALE")

    timing_quality = (
        "measured"
        if alignment.sentences and all(
            row.timing_source in {"native_timestamp", "forced_alignment"}
            and row.measured is True and row.interpolated is False
            for row in alignment.sentences
        )
        else "estimated"
    )
    composition = TimelineComposition(
        visual_candidate_id=review.candidate_id,
        visual_bundle_artifact=bundle_artifact,
        visual_review_artifact=review_artifact,
        visual_bundle_sha256=visual_bundle_sha256,
        visual_review_sha256=visual_review_sha256,
        storyboard_sha256=storyboard_sha256,
        storyboard_artifact_sha256=storyboard_artifact_sha256,
        storyboard_approval_sha256=storyboard_approval_sha256,
        script_sha256=script_sha256,
        script_approval_sha256=script_approval_sha256,
        audio_sha256=audio.sha256,
        audio_review_sha256=audio_review_sha256,
        alignment_sha256=dependency_hashes["alignment.json"],
        subtitle_sha256=subtitle_sha256,
        dependency_hashes=dependency_hashes,
        alignment_method=alignment.method,
        timing_quality=timing_quality,
        scene_visuals=visuals,
        subtitle_layout=subtitles.layout.model_dump(mode="json"),
        subtitle_cues=subtitle_cues,
    )
    payload = base.model_dump(mode="json")
    payload["schema_version"] = "5.1"
    payload["composition"] = composition.model_dump(mode="json")
    return TimelineDocument.model_validate(payload)
