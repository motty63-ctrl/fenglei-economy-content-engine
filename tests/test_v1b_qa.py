from __future__ import annotations

from fanglei.v1b_qa import run_v1b_qa
from tests.test_visual_project_v1b import _inputs
from fanglei.visual_project_v1b import build_v1b_renderer_project


def _bounds(*, y=1510, bottom=1700, font=52):
    return {"zone": {"x": 96, "y": 1480, "width": 888, "height": 260,
                     "right": 984, "bottom": 1740},
            "cues": [{"cue_id": "cue-1", "sentence_id": "sentence_001", "start_ms": 500,
                      "end_ms": 3521, "font_size_px": font, "midpoint_opacity": 1.0,
                      "cue_bounds": {"x": 132, "y": 1504, "width": 816, "height": 212,
                                     "right": 948, "bottom": 1716},
                      "line_bounds": [{"x": 250, "y": y, "width": 580,
                                       "height": 60, "right": 830, "bottom": y+60},
                                      {"x": 300, "y": bottom-60, "width": 480,
                                       "height": 60, "right": 780, "bottom": bottom}]}],
            "primary_bounds": [{"x": 100, "y": 400, "width": 800, "height": 400,
                                "right": 900, "bottom": 800}]}


def test_combined_qa_accepts_measured_dom_geometry():
    base, manifest, track, report, audio = _inputs()
    files, adapted = build_v1b_renderer_project(base, manifest, track, report, audio)
    qa = run_v1b_qa(files, adapted, track, report, dom_measurements=_bounds())
    assert qa["passed"]


def test_combined_qa_rejects_actual_safe_area_violation():
    base, manifest, track, report, audio = _inputs()
    files, adapted = build_v1b_renderer_project(base, manifest, track, report, audio)
    measurements = _bounds(y=1690, bottom=1770)
    qa = run_v1b_qa(files, adapted, track, report, dom_measurements=measurements)
    assert not qa["passed"]
    assert "SUBTITLE_SAFE_AREA_VIOLATION" in qa["issues"]


def test_combined_qa_rejects_hidden_cue_despite_valid_bounds():
    base, manifest, track, report, audio = _inputs()
    files, adapted = build_v1b_renderer_project(base, manifest, track, report, audio)
    measurements = _bounds()
    measurements["cues"][0]["midpoint_opacity"] = 0
    qa = run_v1b_qa(files, adapted, track, report, dom_measurements=measurements)
    assert "SUBTITLE_NOT_VISIBLE_AT_CUE_MIDPOINT" in qa["issues"]


def test_combined_qa_rejects_primary_collision_and_small_font():
    base, manifest, track, report, audio = _inputs()
    files, adapted = build_v1b_renderer_project(base, manifest, track, report, audio)
    measurements = _bounds(font=38)
    measurements["primary_bounds"][0]["y"] = 1600
    measurements["primary_bounds"][0]["bottom"] = 1800
    qa = run_v1b_qa(files, adapted, track, report, dom_measurements=measurements)
    assert "SUBTITLE_PRIMARY_COLLISION" in qa["issues"]
    assert "SUBTITLE_FONT_TOO_SMALL" in qa["issues"]
