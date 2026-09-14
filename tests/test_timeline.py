from fanglei.audio_alignment import align_audio
from fanglei.narration_normalization import normalize_script
from fanglei.providers.alignment import FakeAlignmentProvider
from fanglei.storyboard import build_storyboard
from fanglei.storyboard_quality import lint_storyboard
from fanglei.providers.visual import DeterministicVisualPlanningProvider, VisualPlanningRequest
from fanglei.timeline import compile_timeline
from fanglei.v05_models import AudioMetadata
from tests.test_visual_planning import _script


def _inputs(duration_ms=81234):
    script = _script()
    narration = normalize_script(script, "2026-09-14-001-gdp")
    audio = AudioMetadata(
        sample_rate_hz=24000, duration_ms=duration_ms, sha256="b" * 64,
        provider="fake", voice_id="fake-voice",
    )
    alignment = align_audio(narration, audio, FakeAlignmentProvider())
    plan = DeterministicVisualPlanningProvider().plan(VisualPlanningRequest(
        run_id=narration.run_id, script=script, allowed_claim_ids={"claim_007"},
    ))
    facts = {"claims": [{"claim_id": "claim_007", "verification_status": "verified",
                          "allowed_downstream": True}]}
    board = build_storyboard(plan, script, facts)
    board.quality_gate = lint_storyboard(board, script, facts)
    return alignment, board.model_dump(mode="json"), plan.model_dump(mode="json"), audio


def test_timeline_uses_integer_audio_alignment_for_sentences_beats_and_scenes() -> None:
    alignment, board, beats, audio = _inputs()
    timeline = compile_timeline(alignment, board, beats, audio)
    assert timeline.timing_authority == "real_narration_audio"
    assert len(timeline.beats) == len(timeline.scenes) == 5
    assert all(isinstance(row.start_ms, int) and isinstance(row.end_ms, int)
               for row in timeline.sentences + timeline.beats + timeline.scenes)
    assert all(row.timing_source == "real_sentence_alignment"
               for row in timeline.sentences + timeline.beats + timeline.scenes)
    assert timeline.sentences[-1].end_ms == audio.duration_ms
    assert timeline.validation.forced_to_estimate is False


def test_storyboard_estimate_never_changes_real_timeline_allocation() -> None:
    alignment, board, beats, audio = _inputs()
    first = compile_timeline(alignment, board, beats, audio)
    board["total_estimated_duration_seconds"] = 5
    for scene in board["scenes"]:
        scene["estimated_duration_seconds"] = 1
    second = compile_timeline(alignment, board, beats, audio)
    assert [(row.start_ms, row.end_ms) for row in first.scenes] == [
        (row.start_ms, row.end_ms) for row in second.scenes
    ]
    assert second.validation.estimated_duration_reference_ms == 5000


def test_timeline_records_real_alignment_gaps_as_canvas_holds() -> None:
    alignment, board, beats, audio = _inputs()
    alignment.sentences[1].start_ms += 120
    timeline = compile_timeline(alignment, board, beats, audio)
    assert timeline.gaps[0].duration_ms == 120
    assert timeline.gaps[0].visual_policy == "hold_previous_canvas"
