"""Compile renderer timing exclusively from real sentence alignment."""
from __future__ import annotations

import json

from fanglei.artifacts import sha256_text
from fanglei.v05_models import (
    AlignmentDocument,
    AudioMetadata,
    TimelineDocument,
    TimelineGap,
    TimelineSpan,
    TimelineValidation,
)


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
