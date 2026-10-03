from __future__ import annotations

from fanglei.visual_models import Storyboard
from fanglei.visual_render import render_visual_plan


def _storyboard(*, timing_basis: str = "estimated_speech", alignment_method: str = "") -> Storyboard:
    provenance = None
    schema_version = "4.0"
    first_start = first_end = second_start = second_end = None
    if timing_basis == "alignment_derived":
        schema_version = "5.0"
        first_start, first_end, second_start, second_end = 125, 2_375, 2_375, 4_125
        provenance = {
            "audio_sha256": "a" * 64,
            "audio_duration_ms": 5_000,
            "voice_review_sha256": "b" * 64,
            "alignment_sha256": "c" * 64,
            "alignment_method": alignment_method or "proportional_by_normalized_char_count",
            "subtitle_sha256": "d" * 64,
            "scene_range_source": "alignment-derived",
            "timing_quality": "estimated",
            "final_render_approval_inferred": False,
        }
    return Storyboard.model_validate({
        "schema_version": schema_version,
        "run_id": "synthetic-run",
        "script_id": "synthetic-script",
        "timing_basis": timing_basis,
        "total_estimated_duration_seconds": 5.0 if provenance else 12.0,
        "renderer_selection": {"primary_route": "program_animation", "reason": "synthetic fixture"},
        "timing_provenance": provenance,
        "scenes": [
            {
                "scene_id": "scene-synthetic-1",
                "order": 1,
                "beat_ids": ["beat-1"],
                "sentence_ids": ["sentence-1", "sentence-2"],
                "narrative_role": "phenomenon",
                "estimated_duration_seconds": 2.25,
                "relative_start": 0.0,
                "relative_end": 0.45,
                "start_ms": first_start,
                "end_ms": first_end,
                "layout": "comparison",
                "renderer_directives": {"primary_route": "program_animation", "structure": "comparison"},
            },
            {
                "scene_id": "scene-synthetic-2",
                "order": 2,
                "beat_ids": ["beat-2"],
                "sentence_ids": ["sentence-3"],
                "narrative_role": "judgment",
                "estimated_duration_seconds": 1.75,
                "relative_start": 0.45,
                "relative_end": 0.825,
                "start_ms": second_start,
                "end_ms": second_end,
                "layout": "single_scene",
                "renderer_directives": {"primary_route": "program_animation", "structure": "single_scene"},
            },
        ],
    })


def test_legacy_estimated_speech_retains_no_audio_timestamp_wording() -> None:
    rendered = render_visual_plan(_storyboard())

    assert "All durations are estimated from the script; no audio timestamps exist in V0.4." in rendered
    assert "Scene range:" not in rendered


def test_alignment_derived_rendering_reports_provenance_and_estimated_precision() -> None:
    rendered = render_visual_plan(_storyboard(timing_basis="alignment_derived"))

    assert "alignment-derived" in rendered
    assert "proportional_by_normalized_char_count" in rendered
    assert "estimated" in rendered.lower()
    assert "Audio-backed: yes" in rendered
    assert "Scene timestamps: present" in rendered
    assert "no audio timestamps exist" not in rendered
    assert "not proven word-accurate acoustic alignment" in rendered
    assert "not approved as frame-accurate final subtitle timing" in rendered


def test_alignment_derived_scene_ranges_come_from_storyboard_fields() -> None:
    board = _storyboard(timing_basis="alignment_derived")
    rendered = render_visual_plan(board)

    assert "125–2375 ms" in rendered
    assert "2375–4125 ms" in rendered
    assert "2.250s" in rendered
    assert "1.750s" in rendered


def test_alignment_method_is_data_driven_for_future_generic_methods() -> None:
    rendered = render_visual_plan(_storyboard(
        timing_basis="alignment_derived",
        alignment_method="synthetic_token_boundary_method_v9",
    ))

    assert "synthetic_token_boundary_method_v9" in rendered
    assert "proportional_by_normalized_char_count" not in rendered
