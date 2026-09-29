from __future__ import annotations

import pytest

from fanglei.playback_timing import (
    BoundaryRefinement,
    PauseEvidence,
    PlaybackSegmentTiming,
    PlaybackTimingRefinementV1,
    PreviewSubtitleCueV1,
    PreviewSubtitleTrackV1,
    compile_playback_timeline_candidate_2,
)
from fanglei.v05_models import (
    TimelineComposition,
    TimelineDocument,
    TimelineMotionCue,
    TimelineSceneVisual,
    TimelineSpan,
    TimelineSubtitleCue,
    TimelineValidation,
)
from fanglei.v1b_models import SubtitleLayout, SubtitleRect


def _h(char: str) -> str:
    return char * 64


def _base_timeline() -> TimelineDocument:
    deps = {
        "visual_assets_candidate_3": _h("1"),
        "human_visual_asset_review_candidate_3.json": _h("2"),
        "human_storyboard_candidate.json": _h("3"),
        "human_storyboard_approval.json": _h("4"),
        "script.json": _h("5"),
        "human_script_approval.json": _h("6"),
        "audio/narration.wav": _h("7"),
        "audio/review.json": _h("8"),
        "alignment.json": _h("9"),
        "subtitle_track.json": _h("a"),
    }
    scenes = [
        TimelineSpan(scene_id="scene_001", sentence_ids=["sentence_001"], start_ms=0, end_ms=500,
                     timing_source="proportional_sentence_timing"),
        TimelineSpan(scene_id="scene_002", sentence_ids=["sentence_002"], start_ms=500, end_ms=1000,
                     timing_source="proportional_sentence_timing"),
    ]
    sentence_spans = [
        TimelineSpan(sentence_id="sentence_001", sentence_ids=["sentence_001"], start_ms=0, end_ms=500,
                     timing_source="proportional_sentence_timing"),
        TimelineSpan(sentence_id="sentence_002", sentence_ids=["sentence_002"], start_ms=500, end_ms=1000,
                     timing_source="proportional_sentence_timing"),
    ]
    visuals = [TimelineSceneVisual(
        scene_id=f"scene_{index:03d}", order=index, start_ms=(index - 1) * 500,
        end_ms=index * 500, asset_path=f"scene_{index:03d}.svg", asset_sha256=_h(str(index)),
        sentence_ids=[f"sentence_{index:03d}"], object_ids=[f"obj_{index}"],
        motion=[TimelineMotionCue(object_id=f"obj_{index}", delay_ms=0, duration_ms=120)],
    ) for index in (1, 2)]
    composition = TimelineComposition(
        visual_candidate_id=3,
        visual_bundle_artifact="visual_assets_candidate_3",
        visual_review_artifact="human_visual_asset_review_candidate_3.json",
        visual_bundle_sha256=deps["visual_assets_candidate_3"],
        visual_review_sha256=deps["human_visual_asset_review_candidate_3.json"],
        storyboard_sha256=_h("b"),
        storyboard_artifact_sha256=deps["human_storyboard_candidate.json"],
        storyboard_approval_sha256=deps["human_storyboard_approval.json"],
        script_sha256=deps["script.json"],
        script_approval_sha256=deps["human_script_approval.json"],
        audio_sha256=deps["audio/narration.wav"],
        audio_review_sha256=deps["audio/review.json"],
        alignment_sha256=deps["alignment.json"],
        subtitle_sha256=deps["subtitle_track.json"],
        dependency_hashes=deps,
        alignment_method="proportional_by_normalized_char_count",
        timing_quality="estimated",
        scene_visuals=visuals,
        subtitle_layout=SubtitleLayout(reserved_zone=SubtitleRect(x=60, y=1500, width=960, height=250)),
        subtitle_cues=[
            TimelineSubtitleCue(cue_id="cue_001", sentence_id="sentence_001", text="第一句", lines=["第一句"],
                                start_ms=0, end_ms=500, font_size_px=52),
            TimelineSubtitleCue(cue_id="cue_002", sentence_id="sentence_002", text="第二句", lines=["第二句"],
                                start_ms=500, end_ms=1000, font_size_px=52),
        ],
    )
    return TimelineDocument(
        schema_version="5.1", run_id="run-1",
        audio={"path": "audio/narration.wav", "sha256": deps["audio/narration.wav"], "duration_ms": 1000},
        alignment={"artifact": "alignment.json", "sha256": deps["alignment.json"],
                   "method": "proportional_by_normalized_char_count", "provider": "proportional_sentence_timing"},
        sentences=sentence_spans, beats=[], scenes=scenes,
        validation=TimelineValidation(passed=True, actual_audio_duration_ms=1000),
        composition=composition,
    )


def _refinement() -> PlaybackTimingRefinementV1:
    return PlaybackTimingRefinementV1(
        run_id="run-1", case_id="case-1", audio_sha256=_h("7"), audio_duration_ms=1000,
        narration_sha256=_h("c"), planning_alignment_sha256=_h("9"), script_sha256=_h("5"),
        frame_ms=20, search_window_ms=750, minimum_pause_ms=160,
        boundaries=[BoundaryRefinement(
            ordinal=1, original_ms=500, refined_ms=450, delta_ms=-50,
            status="pause_refined",
            pause_evidence=PauseEvidence(
                start_ms=400, end_ms=500, duration_ms=100, center_ms=450,
                minimum_rms_dbfs=-50, threshold_dbfs=-40,
            ),
        )],
        segments=[
            PlaybackSegmentTiming(sentence_id="sentence_001", original_start_ms=0, original_end_ms=500,
                                  refined_start_ms=0, refined_end_ms=450, start_delta_ms=0, end_delta_ms=-50,
                                  start_status="audio_edge", end_status="pause_refined"),
            PlaybackSegmentTiming(sentence_id="sentence_002", original_start_ms=500, original_end_ms=1000,
                                  refined_start_ms=450, refined_end_ms=1000, start_delta_ms=-50, end_delta_ms=0,
                                  start_status="pause_refined", end_status="audio_edge"),
        ],
    )


def _preview_subtitles() -> PreviewSubtitleTrackV1:
    return PreviewSubtitleTrackV1(
        run_id="run-1", case_id="case-1", canonical_subtitle_sha256=_h("a"),
        timing_refinement_sha256=_h("d"), audio_sha256=_h("7"), script_sha256=_h("5"),
        layout=SubtitleLayout(reserved_zone=SubtitleRect(x=48, y=1724, width=984, height=120)),
        cues=[
            PreviewSubtitleCueV1(cue_id="cue_001", sentence_id="sentence_001", text="第一句", lines=["第一句"],
                                 start_ms=0, end_ms=450, font_size_px=48),
            PreviewSubtitleCueV1(cue_id="cue_002", sentence_id="sentence_002", text="第二句", lines=["第二句"],
                                 start_ms=450, end_ms=1000, font_size_px=48),
        ],
    )


def _current_dependencies() -> dict[str, str]:
    return {
        "timeline.json": _h("e"),
        "human_preview_review_candidate_1.json": _h("f"),
        "visual_assets_candidate_3": _h("1"),
        "human_visual_asset_review_candidate_3.json": _h("2"),
        "human_storyboard_candidate.json": _h("3"),
        "human_storyboard_approval.json": _h("4"),
        "script.json": _h("5"),
        "human_script_approval.json": _h("6"),
        "audio/narration.wav": _h("7"),
        "audio/review.json": _h("8"),
        "alignment.json": _h("9"),
        "subtitle_track.json": _h("a"),
        "playback_timing_refinement.json": _h("d"),
        "preview_subtitle_track_candidate_2.json": _h("e"),
    }


def test_timeline_candidate_two_refines_playback_only_and_keeps_upstream_visual_identity() -> None:
    original = _base_timeline()
    source_bytes = original.model_dump_json()
    result = compile_playback_timeline_candidate_2(
        original, _refinement(), _preview_subtitles(),
        current_dependency_hashes=_current_dependencies(),
        base_timeline_sha256=_h("e"),
    )

    assert original.model_dump_json() == source_bytes
    assert result.schema_version == "5.1"
    assert [(row.scene_id, row.start_ms, row.end_ms) for row in result.scenes] == [
        ("scene_001", 0, 450), ("scene_002", 450, 1000),
    ]
    assert [(row.scene_id, row.asset_path, row.asset_sha256) for row in result.composition.scene_visuals] == [
        ("scene_001", "scene_001.svg", _h("1")), ("scene_002", "scene_002.svg", _h("2")),
    ]
    assert [row.text for row in result.composition.subtitle_cues] == ["第一句", "第二句"]
    assert [(row.start_ms, row.end_ms) for row in result.composition.subtitle_cues] == [(0, 450), (450, 1000)]
    assert result.composition.alignment_sha256 == _h("9")
    assert result.composition.alignment_method == "pause_refined_from_proportional"
    assert result.composition.preview_only is True
    assert result.composition.dependency_hashes["playback_timing_refinement.json"] == _h("d")
    assert result.composition.dependency_hashes["preview_subtitle_track_candidate_2.json"] == _h("e")


def test_timeline_candidate_two_binds_planning_alignment_to_registered_dependency_hash() -> None:
    original = _base_timeline()
    original.alignment["sha256"] = _h("b")

    result = compile_playback_timeline_candidate_2(
        original, _refinement(), _preview_subtitles(),
        current_dependency_hashes=_current_dependencies(), base_timeline_sha256=_h("e"),
    )

    assert result.composition.dependency_hashes["alignment.json"] == _h("9")


def test_timeline_candidate_two_relies_on_current_base_timeline_for_transitive_dependencies() -> None:
    original = _base_timeline()
    composition = original.composition.model_copy(update={
        "dependency_hashes": {**original.composition.dependency_hashes, "visual_beats.json": _h("c")},
    })
    original = original.model_copy(update={"composition": composition})

    result = compile_playback_timeline_candidate_2(
        original, _refinement(), _preview_subtitles(),
        current_dependency_hashes=_current_dependencies(), base_timeline_sha256=_h("e"),
    )

    assert result.composition.dependency_hashes["timeline.json"] == _h("e")
    assert "visual_beats.json" not in result.composition.dependency_hashes


def test_timeline_candidate_two_rejects_unbound_sentence_coverage() -> None:
    original = _base_timeline()
    refinement = _refinement().model_copy(update={"segments": _refinement().segments[:1]})
    with pytest.raises(ValueError, match="PLAYBACK_TIMELINE_SENTENCE_COVERAGE_INVALID"):
        compile_playback_timeline_candidate_2(
            original, refinement, _preview_subtitles(),
            current_dependency_hashes=_current_dependencies(), base_timeline_sha256=_h("e"),
        )
