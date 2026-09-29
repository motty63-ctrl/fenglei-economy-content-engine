from __future__ import annotations

import io
import math
import wave
import xml.etree.ElementTree as ET

import pytest

from fanglei.playback_timing import (
    build_playback_timing_refinement,
    build_preview_subtitle_track,
    derive_compact_subtitle_layout,
    layout_preview_subtitle,
    refine_pause_boundaries,
    required_subtitle_panel_height,
)
from fanglei.v05_models import AlignedSentence, AlignmentDocument
from fanglei.v1b_models import SubtitleTrack


def _wav_with_silences(duration_ms: int, silences: list[tuple[int, int]]) -> bytes:
    sample_rate = 24_000
    frame_samples = sample_rate // 50  # 20 ms frames
    sample_count = duration_ms * sample_rate // 1000
    silent = [False] * sample_count
    for start_ms, end_ms in silences:
        for index in range(start_ms * sample_rate // 1000, end_ms * sample_rate // 1000):
            silent[index] = True
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        pcm = bytearray()
        for index in range(sample_count):
            sample = 0 if silent[index] else round(5000 * math.sin(2 * math.pi * 440 * index / sample_rate))
            pcm.extend(int(sample).to_bytes(2, "little", signed=True))
        stream.writeframes(bytes(pcm))
    return output.getvalue()


def test_pause_near_expected_boundary_moves_boundary_to_silence_center() -> None:
    audio = _wav_with_silences(4000, [(2040, 2240)])

    result = refine_pause_boundaries(audio, [2000], duration_ms=4000)

    assert result.boundaries[0].refined_ms == 2140
    assert result.boundaries[0].status == "pause_refined"
    assert result.boundaries[0].pause_evidence.start_ms == 2040
    assert result.boundaries[0].pause_evidence.end_ms == 2240


def test_pause_before_expected_boundary_is_selected_with_signed_delta() -> None:
    audio = _wav_with_silences(4000, [(1760, 1940)])

    result = refine_pause_boundaries(audio, [2070], duration_ms=4000)

    assert result.boundaries[0].refined_ms == 1850
    assert result.boundaries[0].delta_ms == -220
    assert result.boundaries[0].status == "pause_refined"


def test_no_reliable_nearby_pause_falls_back_to_original_boundary() -> None:
    audio = _wav_with_silences(4000, [])

    result = refine_pause_boundaries(audio, [2000], duration_ms=4000)

    assert result.boundaries[0].refined_ms == 2000
    assert result.boundaries[0].delta_ms == 0
    assert result.boundaries[0].status == "fallback_estimate"
    assert result.boundaries[0].pause_evidence is None


def test_close_boundaries_do_not_reuse_one_pause_candidate() -> None:
    audio = _wav_with_silences(4000, [(2100, 2300)])

    result = refine_pause_boundaries(audio, [2050, 2200], duration_ms=4000)

    assert [item.refined_ms for item in result.boundaries] == [2050, 2212]
    assert [item.status for item in result.boundaries] == ["fallback_estimate", "pause_refined"]
    assert result.boundaries[0].pause_evidence is None


def test_pause_outside_bounded_search_window_is_rejected() -> None:
    audio = _wav_with_silences(4000, [(900, 1100)])

    result = refine_pause_boundaries(audio, [2000], duration_ms=4000, search_window_ms=500)

    assert result.boundaries[0].refined_ms == 2000
    assert result.boundaries[0].status == "fallback_estimate"


def test_edge_adjacent_pauses_keep_internal_boundaries_inside_audio() -> None:
    audio = _wav_with_silences(4000, [(0, 180), (3820, 4000)])

    result = refine_pause_boundaries(audio, [100, 3900], duration_ms=4000)

    assert [item.refined_ms for item in result.boundaries] == [90, 3910]
    assert all(0 < item.refined_ms < 4000 for item in result.boundaries)


def test_subtitle_panel_height_adapts_to_one_or_two_lines() -> None:
    one_line = required_subtitle_panel_height(1, 48, 1.08, 8)
    two_lines = required_subtitle_panel_height(2, 48, 1.08, 8)

    assert one_line == 68
    assert two_lines == 120
    assert two_lines < 160


def test_long_subtitle_wraps_within_compact_width_without_changing_text() -> None:
    manifest = {
        "scenes": [{"asset_path": "scene.svg", "objects": [{"placement": {
            "x": 0.1, "y": 0.2, "width": 0.8, "height": 0.2,
        }}]}]
    }
    layout = derive_compact_subtitle_layout(manifest, {"scene.svg": b"<svg/>"})
    display_text = "A concise comparison stays within its documented scope."

    font_size, lines = layout_preview_subtitle(display_text, layout)

    assert "".join(lines) == display_text
    assert len(lines) <= 2
    assert font_size >= 40
    assert all(len(line) for line in lines)


def test_subtitle_safe_zone_clears_visual_bounds_and_source_footer() -> None:
    svg = b'''<svg xmlns="http://www.w3.org/2000/svg">
      <text x="40" y="1700" font-size="24" data-source-ids="source_1">Source footer</text>
    </svg>'''
    manifest = {"scenes": [{"asset_path": "scene.svg", "objects": [
        {"placement": {"x": 0.1, "y": 0.75, "width": 0.8, "height": 0.1}}
    ]}]}

    layout = derive_compact_subtitle_layout(manifest, {"scene.svg": svg})

    footer = ET.fromstring(svg).find(".//{http://www.w3.org/2000/svg}text")
    assert footer is not None
    footer_bottom = 1700 + 24 * 0.3
    assert layout.reserved_zone.y >= math.ceil(footer_bottom) + 12
    assert layout.reserved_zone.y >= 0.85 * layout.canvas_height
    assert layout.reserved_zone.y + layout.reserved_zone.height <= 1856
    assert layout.reserved_zone.x > 0
    assert layout.reserved_zone.x + layout.reserved_zone.width < layout.canvas_width


def test_layout_fails_closed_when_visuals_leave_no_safe_subtitle_zone() -> None:
    manifest = {"scenes": [{"asset_path": "scene.svg", "objects": [
        {"placement": {"x": 0, "y": 0.91, "width": 1, "height": 0.08}}
    ]}]}

    with pytest.raises(ValueError, match="SUBTITLE_SAFE_ZONE_UNAVAILABLE"):
        derive_compact_subtitle_layout(manifest, {"scene.svg": b"<svg/>"})


def test_planning_boundary_inputs_are_not_mutated() -> None:
    audio = _wav_with_silences(4000, [(2040, 2240)])
    original = [2000]

    result = refine_pause_boundaries(audio, original, duration_ms=4000)

    assert original == [2000]
    assert result.boundaries[0].original_ms == 2000
    assert result.boundaries[0].refined_ms == 2140


def test_refinement_document_binds_audio_narration_script_and_alignment() -> None:
    audio = _wav_with_silences(4000, [(2040, 2240)])
    alignment = AlignmentDocument(
        run_id="synthetic-run", audio_sha256="a" * 64, audio_duration_ms=4000,
        provider="proportional_sentence_timing", method="proportional_by_normalized_char_count",
        sentences=[
            AlignedSentence(sentence_id="sentence_001", start_ms=0, end_ms=2000,
                            confidence=0, timing_source="proportional_sentence"),
            AlignedSentence(sentence_id="sentence_002", start_ms=2000, end_ms=4000,
                            confidence=0, timing_source="proportional_sentence"),
        ], coverage_ratio=1, confidence=0,
    )
    original = alignment.model_dump(mode="json")

    result = build_playback_timing_refinement(
        audio, alignment, run_id="synthetic-run", case_id="synthetic-case",
        audio_sha256="a" * 64, narration_sha256="b" * 64,
        planning_alignment_sha256="c" * 64, script_sha256="d" * 64,
    )

    assert result.audio_sha256 == "a" * 64
    assert result.narration_sha256 == "b" * 64
    assert result.planning_alignment_sha256 == "c" * 64
    assert result.script_sha256 == "d" * 64
    assert [(row.sentence_id, row.refined_start_ms, row.refined_end_ms) for row in result.segments] == [
        ("sentence_001", 0, 2140), ("sentence_002", 2140, 4000),
    ]
    assert alignment.model_dump(mode="json") == original


def test_preview_subtitle_track_preserves_canonical_display_text_and_bounds() -> None:
    audio = _wav_with_silences(4000, [(2040, 2240)])
    alignment = AlignmentDocument(
        run_id="synthetic-run", audio_sha256="a" * 64, audio_duration_ms=4000,
        provider="proportional_sentence_timing", method="proportional_by_normalized_char_count",
        sentences=[
            AlignedSentence(sentence_id="sentence_001", start_ms=0, end_ms=2000,
                            confidence=0, timing_source="proportional_sentence"),
            AlignedSentence(sentence_id="sentence_002", start_ms=2000, end_ms=4000,
                            confidence=0, timing_source="proportional_sentence"),
        ], coverage_ratio=1, confidence=0,
    )
    refinement = build_playback_timing_refinement(
        audio, alignment, run_id="synthetic-run", case_id="synthetic-case",
        audio_sha256="a" * 64, narration_sha256="b" * 64,
        planning_alignment_sha256="c" * 64, script_sha256="d" * 64,
    )
    source = SubtitleTrack.model_validate({
        "schema_version": "subtitle_track.v1", "run_id": "synthetic-run",
        "script_id": "synthetic-script", "source": {
            "script_sha256": "d" * 64, "alignment_sha256": "c" * 64,
            "alignment_audio_sha256": "a" * 64,
        },
        "cues": [
            {"cue_id": "cue_001", "sentence_id": "sentence_001", "text": "Display value: 1,234.",
             "start_ms": 0, "end_ms": 2000, "font_size_px": 52,
             "lines": [{"line_id": "line_01", "text": "Display value: 1,234.",
                        "start_char": 0, "end_char": 21}], "emphasis_spans": []},
            {"cue_id": "cue_002", "sentence_id": "sentence_002", "text": "Second display line.",
             "start_ms": 2000, "end_ms": 4000, "font_size_px": 52,
             "lines": [{"line_id": "line_01", "text": "Second display line.",
                        "start_char": 0, "end_char": 20}], "emphasis_spans": []},
        ],
        "validation": {"passed": True, "sentence_coverage": 1, "text_exact_match": True,
                        "timing_exact_match": True, "issues": []},
    })
    layout = derive_compact_subtitle_layout(
        {"scenes": [{"asset_path": "scene.svg", "objects": [{
            "placement": {"x": 0.1, "y": 0.2, "width": 0.8, "height": 0.2}
        }]}]}, {"scene.svg": b"<svg/>"},
    )

    candidate = build_preview_subtitle_track(
        source, refinement, layout,
        canonical_subtitle_sha256="e" * 64,
        timing_refinement_sha256="f" * 64,
        audio_sha256="a" * 64,
    )

    assert [cue.text for cue in candidate.cues] == [cue.text for cue in source.cues]
    assert [(cue.start_ms, cue.end_ms) for cue in candidate.cues] == [(0, 2140), (2140, 4000)]
    assert candidate.canonical_subtitle_sha256 == "e" * 64
    assert candidate.timing_refinement_sha256 == "f" * 64
    assert all(cue.end_ms <= 4000 for cue in candidate.cues)
