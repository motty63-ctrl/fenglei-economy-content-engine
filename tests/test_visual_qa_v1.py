from __future__ import annotations

from fanglei.gdp_calibration_v1 import build_gdp_calibration_storyboard
from fanglei.visual_qa_v1 import FrameSample, LayoutSample, run_minimal_visual_qa
from fanglei.visual_system_v1 import VisualProgramCompiler, build_default_registry

from test_gdp_calibration_v1 import _legacy_storyboard, _timeline


def _program_and_storyboard():
    storyboard = build_gdp_calibration_storyboard(
        _legacy_storyboard(), run_id="gdp-run", script_id="script_001"
    )
    program = VisualProgramCompiler(build_default_registry()).compile(storyboard, _timeline())
    return program, storyboard


def test_blank_active_scene_is_an_error() -> None:
    program, storyboard = _program_and_storyboard()

    report = run_minimal_visual_qa(
        program, storyboard,
        frame_samples=[FrameSample(timestamp_ms=1000, mean_luma=0.0, foreground_ratio=0.0)],
    )

    assert "VISUAL_BLANK_FRAME" in [issue.code for issue in report.issues]
    assert report.passed is False


def test_primary_object_outside_safe_canvas_is_an_error() -> None:
    program, storyboard = _program_and_storyboard()

    report = run_minimal_visual_qa(
        program, storyboard,
        layout_samples=[LayoutSample(
            timestamp_ms=1000, object_id="bea_value", x=-2, y=100,
            width=500, height=200, primary=True,
        )],
    )

    assert "VISUAL_LAYOUT_OVERFLOW" in [issue.code for issue in report.issues]
    assert report.passed is False


def test_scene_timeline_mismatch_is_an_error() -> None:
    program, storyboard = _program_and_storyboard()
    program.scenes[0].end_ms += 100

    report = run_minimal_visual_qa(program, storyboard, timeline=_timeline())

    assert "VISUAL_SCENE_TIMELINE_MISMATCH" in [issue.code for issue in report.issues]


def test_static_duration_issue_is_reported_without_aesthetic_scoring() -> None:
    program, storyboard = _program_and_storyboard()
    program.density_issues.append({
        "code": "VISUAL_STATIC_DURATION_EXCEEDED",
        "severity": "warning",
        "message": "semantic state is unchanged for 3200 ms (reading_need)",
        "scene_id": "scene_002",
        "state_id": "state_002",
    })

    report = run_minimal_visual_qa(program, storyboard)
    payload = report.model_dump(mode="json")

    assert report.passed is True
    assert payload["static_duration_report"][0]["duration_ms"] == 3200
    assert "aesthetic_score" not in payload
    assert "visual_rank" not in payload


def test_perceptual_static_interval_reports_semantic_pixel_mismatch() -> None:
    program, storyboard = _program_and_storyboard()

    report = run_minimal_visual_qa(
        program,
        storyboard,
        perceptual_static_intervals=[(20967, 25800)],
    )

    issue = next(
        item for item in report.issues
        if item.code == "VISUAL_PERCEPTUAL_STATIC_DURATION_EXCEEDED"
    )
    row = next(
        item for item in report.static_duration_report
        if item.reason == "semantic_state_changed_but_perceptual_change_insufficient"
    )
    assert issue.scene_id == "scene_003"
    assert issue.state_id == "state_004"
    assert row.duration_ms == 4833
    assert report.passed is False


def test_last_frame_without_active_semantic_state_is_an_error() -> None:
    program, storyboard = _program_and_storyboard()
    program.scenes[-1].end_frame_exclusive = program.frame_count - 1

    report = run_minimal_visual_qa(program, storyboard)

    assert "VISUAL_FINAL_FRAME_EMPTY" in [issue.code for issue in report.issues]
    assert report.passed is False


def test_rendered_final_frame_with_only_base_canvas_is_an_error() -> None:
    program, storyboard = _program_and_storyboard()
    final_sample = FrameSample.model_construct(
        timestamp_ms=60610,
        mean_luma=220.0,
        foreground_ratio=0.02,
        active_semantic_objects=0,
    )

    report = run_minimal_visual_qa(
        program, storyboard, frame_samples=[final_sample]
    )

    assert "VISUAL_FINAL_FRAME_EMPTY" in [issue.code for issue in report.issues]
    assert report.checks["final_frame_semantic_coverage"] is False
    assert report.passed is False
