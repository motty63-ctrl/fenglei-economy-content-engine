"""Deterministic downstream pause refinement and safe mobile subtitle layout."""
from __future__ import annotations

from dataclasses import dataclass
import io
import math
import re
import struct
import wave
import xml.etree.ElementTree as ET
from typing import Literal

from pydantic import Field, model_validator

from fanglei.v05_models import AlignmentDocument, StrictModel, TimelineDocument
from fanglei.v1b_models import SubtitleLayout, SubtitleRect
from fanglei.v1b_models import SubtitleTrack
from fanglei.subtitle_generation import _layout_lines


TIMING_METHOD = "pause_refined_from_proportional"
DEFAULT_FRAME_MS = 20
DEFAULT_SEARCH_WINDOW_MS = 750
DEFAULT_MINIMUM_PAUSE_MS = 160


class PauseEvidence(StrictModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    duration_ms: int = Field(gt=0)
    center_ms: int = Field(ge=0)
    minimum_rms_dbfs: float
    threshold_dbfs: float

    @model_validator(mode="after")
    def evidence_range_is_consistent(self) -> "PauseEvidence":
        if self.end_ms <= self.start_ms or self.end_ms - self.start_ms != self.duration_ms:
            raise ValueError("PLAYBACK_PAUSE_EVIDENCE_RANGE_INVALID")
        if self.center_ms != (self.start_ms + self.end_ms) // 2:
            raise ValueError("PLAYBACK_PAUSE_EVIDENCE_CENTER_INVALID")
        return self


class BoundaryRefinement(StrictModel):
    ordinal: int = Field(gt=0)
    original_ms: int = Field(gt=0)
    refined_ms: int = Field(gt=0)
    delta_ms: int
    status: Literal["pause_refined", "fallback_estimate"]
    pause_evidence: PauseEvidence | None = None

    @model_validator(mode="after")
    def refinement_is_consistent(self) -> "BoundaryRefinement":
        if self.delta_ms != self.refined_ms - self.original_ms:
            raise ValueError("PLAYBACK_BOUNDARY_DELTA_INVALID")
        if (self.status == "pause_refined") != (self.pause_evidence is not None):
            raise ValueError("PLAYBACK_BOUNDARY_EVIDENCE_STATUS_INVALID")
        if self.pause_evidence and self.pause_evidence.center_ms != self.refined_ms:
            raise ValueError("PLAYBACK_BOUNDARY_EVIDENCE_BINDING_INVALID")
        return self


class PauseTimingResult(StrictModel):
    method: Literal["pause_refined_from_proportional"] = TIMING_METHOD
    frame_ms: int = Field(gt=0)
    search_window_ms: int = Field(gt=0)
    minimum_pause_ms: int = Field(gt=0)
    duration_ms: int = Field(gt=0)
    boundaries: list[BoundaryRefinement]

    @model_validator(mode="after")
    def boundaries_are_monotonic_and_bounded(self) -> "PauseTimingResult":
        values = [row.refined_ms for row in self.boundaries]
        if values != sorted(values) or len(values) != len(set(values)):
            raise ValueError("PLAYBACK_BOUNDARIES_NOT_MONOTONIC")
        if any(not 0 < value < self.duration_ms for value in values):
            raise ValueError("PLAYBACK_BOUNDARY_OUT_OF_BOUNDS")
        return self


class PlaybackSegmentTiming(StrictModel):
    sentence_id: str = Field(min_length=1)
    original_start_ms: int = Field(ge=0)
    original_end_ms: int = Field(gt=0)
    refined_start_ms: int = Field(ge=0)
    refined_end_ms: int = Field(gt=0)
    start_delta_ms: int
    end_delta_ms: int
    start_status: Literal["audio_edge", "pause_refined", "fallback_estimate"]
    end_status: Literal["audio_edge", "pause_refined", "fallback_estimate"]

    @model_validator(mode="after")
    def segment_is_consistent(self) -> "PlaybackSegmentTiming":
        if (
            self.original_end_ms <= self.original_start_ms
            or self.refined_end_ms <= self.refined_start_ms
            or self.start_delta_ms != self.refined_start_ms - self.original_start_ms
            or self.end_delta_ms != self.refined_end_ms - self.original_end_ms
        ):
            raise ValueError("PLAYBACK_SEGMENT_TIMING_INVALID")
        return self


class PlaybackTimingRefinementV1(StrictModel):
    schema_version: Literal["playback-timing-refinement/1.0"] = "playback-timing-refinement/1.0"
    run_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    method: Literal["pause_refined_from_proportional"] = TIMING_METHOD
    audio_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    audio_duration_ms: int = Field(gt=0)
    narration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    planning_alignment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    script_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    frame_ms: int = Field(gt=0)
    search_window_ms: int = Field(gt=0)
    minimum_pause_ms: int = Field(gt=0)
    boundaries: list[BoundaryRefinement]
    segments: list[PlaybackSegmentTiming] = Field(min_length=1)

    @model_validator(mode="after")
    def segment_coverage_is_contiguous(self) -> "PlaybackTimingRefinementV1":
        if len(self.boundaries) != len(self.segments) - 1:
            raise ValueError("PLAYBACK_BOUNDARY_COVERAGE_INVALID")
        if len({row.sentence_id for row in self.segments}) != len(self.segments):
            raise ValueError("PLAYBACK_SEGMENT_IDS_NOT_UNIQUE")
        if self.segments[0].refined_start_ms != 0 or self.segments[-1].refined_end_ms != self.audio_duration_ms:
            raise ValueError("PLAYBACK_AUDIO_EDGE_COVERAGE_INVALID")
        for previous, current in zip(self.segments, self.segments[1:]):
            if previous.refined_end_ms != current.refined_start_ms:
                raise ValueError("PLAYBACK_SEGMENT_GAP_OR_OVERLAP")
        if any(row.refined_end_ms > self.audio_duration_ms for row in self.segments):
            raise ValueError("PLAYBACK_SEGMENT_OUT_OF_BOUNDS")
        return self


class PreviewSubtitleCueV1(StrictModel):
    cue_id: str = Field(min_length=1)
    sentence_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    lines: list[str] = Field(min_length=1, max_length=2)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    font_size_px: int = Field(ge=40)

    @model_validator(mode="after")
    def cue_is_valid(self) -> "PreviewSubtitleCueV1":
        if self.end_ms <= self.start_ms or "".join(self.lines) != self.text:
            raise ValueError("PREVIEW_SUBTITLE_TEXT_OR_TIMING_INVALID")
        return self


class PreviewSubtitleTrackV1(StrictModel):
    schema_version: Literal["preview-subtitle-track/1.0"] = "preview-subtitle-track/1.0"
    run_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    candidate_id: Literal[2] = 2
    canonical_subtitle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    timing_refinement_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    audio_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    script_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    layout: SubtitleLayout
    cues: list[PreviewSubtitleCueV1] = Field(min_length=1)

    @model_validator(mode="after")
    def cue_ids_and_ranges_are_valid(self) -> "PreviewSubtitleTrackV1":
        if len({row.cue_id for row in self.cues}) != len(self.cues):
            raise ValueError("PREVIEW_SUBTITLE_CUE_IDS_NOT_UNIQUE")
        for previous, current in zip(self.cues, self.cues[1:]):
            if current.start_ms < previous.end_ms:
                raise ValueError("PREVIEW_SUBTITLE_CUES_OVERLAP")
        return self


@dataclass(frozen=True)
class _EnergyFrame:
    start_ms: int
    end_ms: int
    rms_dbfs: float


@dataclass(frozen=True)
class _PauseCandidate:
    start_ms: int
    end_ms: int
    minimum_rms_dbfs: float
    threshold_dbfs: float

    @property
    def center_ms(self) -> int:
        return (self.start_ms + self.end_ms) // 2


def _decode_pcm_frames(audio_bytes: bytes, frame_ms: int) -> tuple[list[_EnergyFrame], int]:
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as stream:
            if stream.getcomptype() != "NONE" or stream.getsampwidth() != 2:
                raise ValueError("PLAYBACK_AUDIO_MUST_BE_PCM_S16LE")
            channels = stream.getnchannels()
            sample_rate = stream.getframerate()
            if channels < 1 or sample_rate < 1:
                raise ValueError("PLAYBACK_AUDIO_FORMAT_INVALID")
            frame_count = stream.getnframes()
            pcm = stream.readframes(frame_count)
    except (wave.Error, EOFError) as error:
        raise ValueError("PLAYBACK_WAV_INVALID") from error
    if len(pcm) != frame_count * channels * 2:
        raise ValueError("PLAYBACK_WAV_TRUNCATED")

    samples = [sample[0] for sample in struct.iter_unpack("<h", pcm)]
    samples_per_window = max(1, round(sample_rate * frame_ms / 1000)) * channels
    frames: list[_EnergyFrame] = []
    for offset in range(0, len(samples), samples_per_window):
        block = samples[offset:offset + samples_per_window]
        if not block:
            continue
        rms = math.sqrt(sum(value * value for value in block) / len(block)) / 32768
        dbfs = 20 * math.log10(rms) if rms > 0 else float("-inf")
        start_sample = offset // channels
        end_sample = min(frame_count, start_sample + len(block) // channels)
        frames.append(_EnergyFrame(
            start_ms=round(start_sample * 1000 / sample_rate),
            end_ms=round(end_sample * 1000 / sample_rate),
            rms_dbfs=dbfs,
        ))
    return frames, round(frame_count * 1000 / sample_rate)


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return float("-inf")
    index = min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1)
    return ordered[max(0, index)]


def _candidates_for_boundary(
    frames: list[_EnergyFrame], *, expected_ms: int, lower_ms: int, upper_ms: int,
    frame_ms: int, minimum_pause_ms: int,
) -> list[_PauseCandidate]:
    local = [frame for frame in frames if frame.end_ms > lower_ms and frame.start_ms < upper_ms]
    finite = [frame.rms_dbfs for frame in local if math.isfinite(frame.rms_dbfs)]
    baseline = _percentile(finite, .75)
    if not math.isfinite(baseline) or baseline < -55:
        return []
    threshold = max(-48.0, min(-32.0, baseline - 14.0))
    qualifying = [
        frame for frame in local
        if frame.rms_dbfs <= threshold
        and frame.end_ms > lower_ms
        and frame.start_ms < upper_ms
    ]
    runs: list[list[_EnergyFrame]] = []
    for frame in qualifying:
        if not runs or frame.start_ms - runs[-1][-1].end_ms > frame_ms + 1:
            runs.append([frame])
        else:
            runs[-1].append(frame)
    result: list[_PauseCandidate] = []
    for run in runs:
        start = max(lower_ms, run[0].start_ms)
        end = min(upper_ms, run[-1].end_ms)
        duration = end - start
        center = (start + end) // 2
        if duration < minimum_pause_ms or abs(center - expected_ms) > upper_ms - lower_ms:
            continue
        result.append(_PauseCandidate(
            start_ms=start, end_ms=end,
            minimum_rms_dbfs=min(frame.rms_dbfs for frame in run),
            threshold_dbfs=threshold,
        ))
    return result


def refine_pause_boundaries(
    audio_bytes: bytes,
    expected_boundaries_ms: list[int],
    *,
    duration_ms: int,
    frame_ms: int = DEFAULT_FRAME_MS,
    search_window_ms: int = DEFAULT_SEARCH_WINDOW_MS,
    minimum_pause_ms: int = DEFAULT_MINIMUM_PAUSE_MS,
) -> PauseTimingResult:
    """Refine internal segment boundaries from bounded low-energy pause evidence only."""
    if frame_ms <= 0 or search_window_ms <= 0 or minimum_pause_ms <= 0 or duration_ms <= 0:
        raise ValueError("PLAYBACK_TIMING_CONFIG_INVALID")
    frames, decoded_duration = _decode_pcm_frames(audio_bytes, frame_ms)
    if decoded_duration != duration_ms:
        raise ValueError("PLAYBACK_AUDIO_DURATION_MISMATCH")
    if any(not 0 < item < duration_ms for item in expected_boundaries_ms):
        raise ValueError("PLAYBACK_BOUNDARY_OUT_OF_BOUNDS")
    if expected_boundaries_ms != sorted(expected_boundaries_ms) or len(set(expected_boundaries_ms)) != len(expected_boundaries_ms):
        raise ValueError("PLAYBACK_BOUNDARIES_NOT_MONOTONIC")

    output: list[BoundaryRefinement] = []
    for index, expected in enumerate(expected_boundaries_ms):
        logical_lower = 0 if index == 0 else (expected_boundaries_ms[index - 1] + expected) // 2
        logical_upper = duration_ms if index + 1 == len(expected_boundaries_ms) else (
            expected + expected_boundaries_ms[index + 1] + 1
        ) // 2
        lower = max(0, expected - search_window_ms, logical_lower)
        upper = min(duration_ms, expected + search_window_ms, logical_upper)
        candidates = _candidates_for_boundary(
            frames, expected_ms=expected, lower_ms=lower, upper_ms=upper,
            frame_ms=frame_ms, minimum_pause_ms=minimum_pause_ms,
        )
        if candidates:
            selected = max(candidates, key=lambda row: (
                (row.end_ms - row.start_ms) - .25 * abs(row.center_ms - expected),
                -abs(row.center_ms - expected), row.end_ms - row.start_ms,
            ))
            refined = selected.center_ms
            evidence = PauseEvidence(
                start_ms=selected.start_ms,
                end_ms=selected.end_ms,
                duration_ms=selected.end_ms - selected.start_ms,
                center_ms=refined,
                minimum_rms_dbfs=selected.minimum_rms_dbfs,
                threshold_dbfs=selected.threshold_dbfs,
            )
            status: Literal["pause_refined", "fallback_estimate"] = "pause_refined"
        else:
            refined = expected
            evidence = None
            status = "fallback_estimate"
        output.append(BoundaryRefinement(
            ordinal=index + 1,
            original_ms=expected,
            refined_ms=refined,
            delta_ms=refined - expected,
            status=status,
            pause_evidence=evidence,
        ))
    return PauseTimingResult(
        frame_ms=frame_ms,
        search_window_ms=search_window_ms,
        minimum_pause_ms=minimum_pause_ms,
        duration_ms=duration_ms,
        boundaries=output,
    )


def build_playback_timing_refinement(
    audio_bytes: bytes,
    alignment: AlignmentDocument,
    *,
    run_id: str,
    case_id: str,
    audio_sha256: str,
    narration_sha256: str,
    planning_alignment_sha256: str,
    script_sha256: str,
) -> PlaybackTimingRefinementV1:
    """Create a downstream timing artifact without changing the planning alignment."""
    if alignment.run_id != run_id:
        raise ValueError("PLAYBACK_RUN_ID_MISMATCH")
    if alignment.method != "proportional_by_normalized_char_count" or alignment.provider != "proportional_sentence_timing":
        raise ValueError("PLAYBACK_ALIGNMENT_NOT_PROPORTIONAL")
    if alignment.audio_sha256 != audio_sha256:
        raise ValueError("PLAYBACK_AUDIO_HASH_MISMATCH")
    expected_ids = [row.sentence_id for row in alignment.sentences]
    if len(expected_ids) != len(set(expected_ids)):
        raise ValueError("PLAYBACK_SEGMENT_IDS_NOT_UNIQUE")
    if alignment.sentences[0].start_ms != 0 or alignment.sentences[-1].end_ms != alignment.audio_duration_ms:
        raise ValueError("PLAYBACK_AUDIO_EDGE_COVERAGE_INVALID")
    if any(row.start_ms != previous.end_ms for previous, row in zip(alignment.sentences, alignment.sentences[1:])):
        raise ValueError("PLAYBACK_ALIGNMENT_NOT_CONTIGUOUS")

    result = refine_pause_boundaries(
        audio_bytes,
        [row.end_ms for row in alignment.sentences[:-1]],
        duration_ms=alignment.audio_duration_ms,
    )
    starts = [0, *(row.refined_ms for row in result.boundaries)]
    ends = [*(row.refined_ms for row in result.boundaries), alignment.audio_duration_ms]
    segments: list[PlaybackSegmentTiming] = []
    for index, sentence in enumerate(alignment.sentences):
        start_status = "audio_edge" if index == 0 else result.boundaries[index - 1].status
        end_status = "audio_edge" if index + 1 == len(alignment.sentences) else result.boundaries[index].status
        segments.append(PlaybackSegmentTiming(
            sentence_id=sentence.sentence_id,
            original_start_ms=sentence.start_ms,
            original_end_ms=sentence.end_ms,
            refined_start_ms=starts[index],
            refined_end_ms=ends[index],
            start_delta_ms=starts[index] - sentence.start_ms,
            end_delta_ms=ends[index] - sentence.end_ms,
            start_status=start_status,
            end_status=end_status,
        ))
    return PlaybackTimingRefinementV1(
        run_id=run_id,
        case_id=case_id,
        audio_sha256=audio_sha256,
        audio_duration_ms=alignment.audio_duration_ms,
        narration_sha256=narration_sha256,
        planning_alignment_sha256=planning_alignment_sha256,
        script_sha256=script_sha256,
        frame_ms=result.frame_ms,
        search_window_ms=result.search_window_ms,
        minimum_pause_ms=result.minimum_pause_ms,
        boundaries=result.boundaries,
        segments=segments,
    )


def required_subtitle_panel_height(
    line_count: int, font_size_px: int, line_height: float, vertical_padding_px: int,
) -> int:
    if line_count < 1 or line_count > 2 or font_size_px < 40 or line_height <= 1 or vertical_padding_px < 0:
        raise ValueError("SUBTITLE_LAYOUT_CONFIG_INVALID")
    return math.ceil(line_count * font_size_px * line_height + 2 * vertical_padding_px)


def _svg_source_footer_bottom(asset: bytes) -> float | None:
    try:
        root = ET.fromstring(asset)
    except ET.ParseError as error:
        raise ValueError("SUBTITLE_VISUAL_ASSET_INVALID") from error
    bottoms: list[float] = []
    for element in root.iter():
        if "data-source-ids" not in element.attrib:
            continue
        if element.attrib.get("transform"):
            raise ValueError("SUBTITLE_SOURCE_FOOTER_GEOMETRY_UNSUPPORTED")
        try:
            baseline = float(element.attrib["y"].removesuffix("px"))
            font_size = float(element.attrib.get("font-size", "16").removesuffix("px"))
        except (KeyError, ValueError) as error:
            raise ValueError("SUBTITLE_SOURCE_FOOTER_GEOMETRY_UNSUPPORTED") from error
        bottoms.append(baseline + font_size * .35)
    return max(bottoms) if bottoms else None


def derive_compact_subtitle_layout(
    visual_manifest: dict,
    visual_assets: dict[str, bytes],
    *,
    canvas_width: int = 1080,
    canvas_height: int = 1920,
    horizontal_margin_px: int = 48,
    bottom_margin_px: int = 64,
    safe_gap_px: int = 16,
) -> SubtitleLayout:
    """Derive one compact shared subtitle zone below every declared visual/footer bound."""
    scene_rows = visual_manifest.get("scenes")
    if not isinstance(scene_rows, list) or not scene_rows:
        raise ValueError("SUBTITLE_VISUAL_SCENES_MISSING")
    visual_bottoms: list[float] = []
    for scene in scene_rows:
        asset_path = scene.get("asset_path")
        if not isinstance(asset_path, str) or asset_path not in visual_assets:
            raise ValueError("SUBTITLE_VISUAL_ASSET_MISSING")
        for obj in scene.get("objects", []):
            placement = obj.get("placement")
            if not isinstance(placement, dict):
                raise ValueError("SUBTITLE_VISUAL_BOUNDS_MISSING")
            try:
                y, height = float(placement["y"]), float(placement["height"])
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError("SUBTITLE_VISUAL_BOUNDS_INVALID") from error
            if y < 0 or height <= 0 or y + height > 1.000001:
                raise ValueError("SUBTITLE_VISUAL_BOUNDS_INVALID")
            visual_bottoms.append((y + height) * canvas_height)
        source_footer = scene.get("source_footer")
        footer_bottom = _svg_source_footer_bottom(visual_assets[asset_path])
        if source_footer and footer_bottom is None:
            raise ValueError("SUBTITLE_SOURCE_FOOTER_BOUNDS_MISSING")
        if footer_bottom is not None:
            visual_bottoms.append(footer_bottom)
    if not visual_bottoms:
        raise ValueError("SUBTITLE_VISUAL_BOUNDS_MISSING")

    default_font = 48
    minimum_font = 40
    line_height = 1.08
    vertical_padding = 8
    maximum_panel_height = required_subtitle_panel_height(2, default_font, line_height, vertical_padding)
    top = math.ceil(max(visual_bottoms)) + safe_gap_px
    top = ((top + 3) // 4) * 4
    right = canvas_width - horizontal_margin_px
    bottom = canvas_height - bottom_margin_px
    width = right - horizontal_margin_px
    if width <= 0 or top + maximum_panel_height > bottom:
        raise ValueError("SUBTITLE_SAFE_ZONE_UNAVAILABLE")
    return SubtitleLayout(
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        reserved_zone=SubtitleRect(
            x=horizontal_margin_px,
            y=top,
            width=width,
            height=maximum_panel_height,
        ),
        maximum_lines=2,
        default_font_size_px=default_font,
        minimum_font_size_px=minimum_font,
        line_height=line_height,
        horizontal_padding_px=14,
        vertical_padding_px=vertical_padding,
    )


def layout_preview_subtitle(text: str, layout: SubtitleLayout) -> tuple[int, list[str]]:
    if not text:
        raise ValueError("SUBTITLE_TEXT_EMPTY")
    font_size, lines = _layout_lines(text, layout)
    panel_height = required_subtitle_panel_height(
        len(lines), font_size, layout.line_height, layout.vertical_padding_px,
    )
    if panel_height > layout.reserved_zone.height:
        raise ValueError("SUBTITLE_TEXT_OVERFLOW")
    return font_size, [line.text for line in lines]


def build_preview_subtitle_track(
    canonical_track: SubtitleTrack,
    refinement: PlaybackTimingRefinementV1,
    layout: SubtitleLayout,
    *,
    canonical_subtitle_sha256: str,
    timing_refinement_sha256: str,
    audio_sha256: str,
) -> PreviewSubtitleTrackV1:
    """Retiming and reflow exact canonical display copy for preview candidate 2."""
    if canonical_track.run_id != refinement.run_id:
        raise ValueError("PREVIEW_SUBTITLE_RUN_MISMATCH")
    if canonical_track.source.alignment_audio_sha256 != audio_sha256 or refinement.audio_sha256 != audio_sha256:
        raise ValueError("PREVIEW_SUBTITLE_AUDIO_BINDING_INVALID")
    if canonical_track.source.script_sha256 != refinement.script_sha256:
        raise ValueError("PREVIEW_SUBTITLE_SCRIPT_BINDING_INVALID")
    segment_by_id = {row.sentence_id: row for row in refinement.segments}
    if [cue.sentence_id for cue in canonical_track.cues] != [row.sentence_id for row in refinement.segments]:
        raise ValueError("PREVIEW_SUBTITLE_COVERAGE_MISMATCH")
    cues: list[PreviewSubtitleCueV1] = []
    for cue in canonical_track.cues:
        segment = segment_by_id[cue.sentence_id]
        font_size, lines = layout_preview_subtitle(cue.text, layout)
        cues.append(PreviewSubtitleCueV1(
            cue_id=cue.cue_id,
            sentence_id=cue.sentence_id,
            text=cue.text,
            lines=lines,
            start_ms=segment.refined_start_ms,
            end_ms=segment.refined_end_ms,
            font_size_px=font_size,
        ))
    return PreviewSubtitleTrackV1(
        run_id=refinement.run_id,
        case_id=refinement.case_id,
        canonical_subtitle_sha256=canonical_subtitle_sha256,
        timing_refinement_sha256=timing_refinement_sha256,
        audio_sha256=audio_sha256,
        script_sha256=refinement.script_sha256,
        layout=layout,
        cues=cues,
    )


def compile_playback_timeline_candidate_2(
    base_timeline: TimelineDocument,
    refinement: PlaybackTimingRefinementV1,
    preview_subtitles: PreviewSubtitleTrackV1,
    *,
    current_dependency_hashes: dict[str, str],
    base_timeline_sha256: str,
) -> TimelineDocument:
    """Derive a preview-only timeline while preserving approved scene and asset identity."""
    composition = base_timeline.composition
    if base_timeline.schema_version != "5.1" or composition is None:
        raise ValueError("PLAYBACK_TIMELINE_REQUIRES_APPROVED_COMPOSITION")
    if (
        not re.fullmatch(r"[0-9a-f]{64}", base_timeline_sha256)
        or current_dependency_hashes.get("timeline.json") != base_timeline_sha256
    ):
        raise ValueError("PLAYBACK_BASE_TIMELINE_HASH_MISMATCH")
    if (
        refinement.run_id != base_timeline.run_id
        or refinement.audio_sha256 != base_timeline.audio.get("sha256")
        or refinement.audio_duration_ms != base_timeline.validation.actual_audio_duration_ms
        or refinement.planning_alignment_sha256 != composition.dependency_hashes.get("alignment.json")
        or refinement.script_sha256 != composition.script_sha256
    ):
        raise ValueError("PLAYBACK_REFINEMENT_BASE_BINDING_INVALID")
    if (
        preview_subtitles.run_id != refinement.run_id
        or preview_subtitles.case_id != refinement.case_id
        or preview_subtitles.audio_sha256 != refinement.audio_sha256
        or preview_subtitles.script_sha256 != refinement.script_sha256
        or preview_subtitles.canonical_subtitle_sha256 != composition.subtitle_sha256
        or current_dependency_hashes.get("playback_timing_refinement.json")
        != preview_subtitles.timing_refinement_sha256
    ):
        raise ValueError("PLAYBACK_SUBTITLE_BINDING_INVALID")
    for name, digest in composition.dependency_hashes.items():
        if name in current_dependency_hashes and current_dependency_hashes[name] != digest:
            raise ValueError(f"PLAYBACK_UPSTREAM_DEPENDENCY_CHANGED:{name}")
    if any(
        not name or not re.fullmatch(r"[0-9a-f]{64}", digest)
        for name, digest in current_dependency_hashes.items()
    ):
        raise ValueError("PLAYBACK_DEPENDENCY_HASH_INVALID")

    expected_sentence_ids = [row.sentence_id for row in base_timeline.sentences if row.sentence_id]
    refined_sentence_ids = [row.sentence_id for row in refinement.segments]
    if not expected_sentence_ids or refined_sentence_ids != expected_sentence_ids:
        raise ValueError("PLAYBACK_TIMELINE_SENTENCE_COVERAGE_INVALID")
    if [row.sentence_id for row in preview_subtitles.cues] != expected_sentence_ids:
        raise ValueError("PLAYBACK_TIMELINE_SUBTITLE_COVERAGE_INVALID")
    if [row.sentence_id for row in composition.subtitle_cues] != expected_sentence_ids:
        raise ValueError("PLAYBACK_CANONICAL_SUBTITLE_COVERAGE_INVALID")
    for old_cue, cue, segment in zip(
        composition.subtitle_cues, preview_subtitles.cues, refinement.segments, strict=True,
    ):
        if (
            cue.cue_id != old_cue.cue_id
            or cue.text != old_cue.text
            or cue.start_ms != segment.refined_start_ms
            or cue.end_ms != segment.refined_end_ms
        ):
            raise ValueError("PLAYBACK_SUBTITLE_TEXT_OR_TIMING_CHANGED")

    segment_by_id = {row.sentence_id: row for row in refinement.segments}

    def refine_span(row: dict) -> dict:
        sentence_ids = row.get("sentence_ids", [])
        if not sentence_ids or any(sentence_id not in segment_by_id for sentence_id in sentence_ids):
            raise ValueError("PLAYBACK_TIMELINE_SPAN_SENTENCE_MAPPING_INVALID")
        first, last = segment_by_id[sentence_ids[0]], segment_by_id[sentence_ids[-1]]
        return {**row, "start_ms": first.refined_start_ms, "end_ms": last.refined_end_ms}

    payload = base_timeline.model_dump(mode="json")
    payload["sentences"] = [
        refine_span(row.model_dump(mode="json")) for row in base_timeline.sentences
    ]
    payload["beats"] = [refine_span(row.model_dump(mode="json")) for row in base_timeline.beats]
    payload["scenes"] = [refine_span(row.model_dump(mode="json")) for row in base_timeline.scenes]
    payload["gaps"] = []

    visual_by_scene = {row.scene_id: row for row in composition.scene_visuals}
    scene_by_id = {row.scene_id: row for row in base_timeline.scenes}
    if set(visual_by_scene) != set(scene_by_id):
        raise ValueError("PLAYBACK_TIMELINE_VISUAL_COVERAGE_INVALID")
    refined_visuals: list[dict] = []
    for scene in payload["scenes"]:
        visual = visual_by_scene[scene["scene_id"]]
        duration = scene["end_ms"] - scene["start_ms"]
        motion = []
        for cue in visual.motion:
            delay = min(cue.delay_ms, max(0, duration - 1))
            cue_duration = min(cue.duration_ms, max(1, duration - delay))
            motion.append({
                **cue.model_dump(mode="json"),
                "delay_ms": delay,
                "duration_ms": cue_duration,
            })
        refined_visuals.append({
            **visual.model_dump(mode="json"),
            "start_ms": scene["start_ms"],
            "end_ms": scene["end_ms"],
            "motion": motion,
        })

    updated_composition = composition.model_dump(mode="json")
    updated_composition.update({
        "alignment_method": refinement.method,
        "scene_visuals": refined_visuals,
        "subtitle_layout": preview_subtitles.layout.model_dump(mode="json"),
        "subtitle_cues": [
            {
                "cue_id": cue.cue_id,
                "sentence_id": cue.sentence_id,
                "text": cue.text,
                "lines": cue.lines,
                "start_ms": cue.start_ms,
                "end_ms": cue.end_ms,
                "font_size_px": cue.font_size_px,
            }
            for cue in preview_subtitles.cues
        ],
        "dependency_hashes": current_dependency_hashes,
        "preview_review_status": "pending_human_preview_review",
        "preview_only": True,
    })
    payload["composition"] = updated_composition
    payload["schema_version"] = "5.1"
    result = TimelineDocument.model_validate(payload)
    if (
        [(row.scene_id, row.sentence_ids) for row in result.scenes]
        != [(row.scene_id, row.sentence_ids) for row in base_timeline.scenes]
        or [(row.scene_id, row.asset_path, row.asset_sha256) for row in result.composition.scene_visuals]
        != [(row.scene_id, row.asset_path, row.asset_sha256) for row in composition.scene_visuals]
    ):
        raise ValueError("PLAYBACK_UPSTREAM_SCENE_IDENTITY_CHANGED")
    return result
