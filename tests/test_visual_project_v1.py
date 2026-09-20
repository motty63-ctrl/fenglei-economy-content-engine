from __future__ import annotations

import json
from pathlib import Path

from fanglei.artifacts import sha256_bytes
from fanglei.gdp_calibration_v1 import build_gdp_calibration_storyboard
from fanglei.visual_project_v1 import (
    _scene_markup,
    build_v1_renderer_project,
    materialize_gdp_v1a,
)
from fanglei.visual_system_v1 import VisualProgramCompiler, build_default_registry

from test_gdp_calibration_v1 import _legacy_storyboard, _timeline


def test_v1_project_has_independent_full_composition_and_debug_entry() -> None:
    storyboard = build_gdp_calibration_storyboard(
        _legacy_storyboard(), run_id="gdp-run", script_id="script_001"
    )
    program = VisualProgramCompiler(build_default_registry()).compile(storyboard, _timeline())

    files, manifest = build_v1_renderer_project(
        storyboard, program, _timeline(), b"approved-wave-bytes", audio_sha256="audio-sha"
    )

    assert manifest["renderer"]["full_composition_entry"] == "index.html"
    assert manifest["renderer"]["compatibility_composition_entry"] == "compositions/beat-001.html"
    assert manifest["renderer"]["frame_count"] == 1819
    assert manifest["renderer"]["duration_ms"] == 60611
    assert manifest["renderer"]["full_render_requested"] is False
    assert files["assets/narration.wav"] == b"approved-wave-bytes"
    assert "data-composition-id=\"full\"" in files["index.html"]
    assert files["index.html"].count("data-scene-id=") == 5
    assert "visual-program.v1.0a" in files["data/visual_program.json"]
    assert "storyboard.v1" in files["data/storyboard-v1.json"]


def test_v1_project_preserves_scene_order_and_audio_binding() -> None:
    storyboard = build_gdp_calibration_storyboard(
        _legacy_storyboard(), run_id="gdp-run", script_id="script_001"
    )
    program = VisualProgramCompiler(build_default_registry()).compile(storyboard, _timeline())

    files, manifest = build_v1_renderer_project(
        storyboard, program, _timeline(), b"audio", audio_sha256="audio-sha"
    )
    html = files["index.html"]

    assert html.index('data-scene-id="scene_001"') < html.index('data-scene-id="scene_002"')
    assert html.index('data-scene-id="scene_002"') < html.index('data-scene-id="scene_003"')
    assert html.index('data-scene-id="scene_003"') < html.index('data-scene-id="scene_004"')
    assert html.index('data-scene-id="scene_004"') < html.index('data-scene-id="scene_005"')
    assert 'src="assets/narration.wav"' in html
    assert manifest["audio"]["sha256"] == "audio-sha"
    assert [row["scene_id"] for row in manifest["renderer"]["scene_frame_ranges"]] == [
        "scene_001", "scene_002", "scene_003", "scene_004", "scene_005",
    ]


def test_v1_project_uses_all_five_distinct_renderer_components() -> None:
    storyboard = build_gdp_calibration_storyboard(
        _legacy_storyboard(), run_id="gdp-run", script_id="script_001"
    )
    program = VisualProgramCompiler(build_default_registry()).compile(storyboard, _timeline())

    files, _ = build_v1_renderer_project(
        storyboard, program, _timeline(), b"audio", audio_sha256="audio-sha"
    )
    html = files["index.html"]

    for marker in (
        "hook-stage", "comparison-grid", "number-transform", "process-flow", "conclusion-lockup",
    ):
        assert marker in html
    assert "data-animation-status=\"ready\"" in html
    assert "data-layout-status=\"ready\"" in html
    assert 'data-semantic-object="true"' in html
    assert "<svg" in html
    assert "querySelector(`" not in html
    assert "@font-face{font-family:'Microsoft YaHei';src:local('Microsoft YaHei')}" in html


def test_number_transform_uses_persistent_semantic_highlight_for_transform_state() -> None:
    storyboard = build_gdp_calibration_storyboard(
        _legacy_storyboard(), run_id="gdp-run", script_id="script_001"
    )
    program = VisualProgramCompiler(build_default_registry()).compile(storyboard, _timeline())

    _, schedule = _scene_markup(storyboard, program)
    files, _ = build_v1_renderer_project(
        storyboard, program, _timeline(), b"audio", audio_sha256="audio-sha"
    )
    number_transform = next(item for item in schedule if item["scene_id"] == "scene_003")
    states = {state["state_id"]: state for state in number_transform["states"]}

    assert states["state_002"].get("object_actions") == [
        {"object_id": "world_bank_value", "operation": "reveal"}
    ]
    assert states["state_004"].get("object_actions") == [
        {"object_id": "world_bank_value", "operation": "transform"}
    ]
    assert 'action.operation==="transform"' in files["index.html"]
    assert 'backgroundColor:"#FFF3DF"' in files["index.html"]
    assert states["state_005"].get("object_actions") == [
        {"object_id": "bea_value", "operation": "reveal"}
    ]
    assert states["state_007"].get("object_actions") == [
        {"object_id": "bea_value", "operation": "emphasize"},
        {"object_id": "world_bank_value", "operation": "emphasize"},
    ]


def test_last_scene_holds_final_state_through_last_frame() -> None:
    storyboard = build_gdp_calibration_storyboard(
        _legacy_storyboard(), run_id="gdp-run", script_id="script_001"
    )
    program = VisualProgramCompiler(build_default_registry()).compile(storyboard, _timeline())

    _, schedule = _scene_markup(storyboard, program)
    last_scene = schedule[-1]

    assert program.scenes[-1].end_frame_exclusive == program.frame_count
    assert last_scene.get("hold_end_frame_exclusive") == program.frame_count
    assert last_scene.get("terminal_visibility") == "hold"
    assert last_scene["states"][-1]["target_object_ids"]


def test_materialize_calibration_keeps_old_final_and_does_not_render(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    audio = b"approved-real-audio"
    timeline = _timeline()
    timeline["audio"]["sha256"] = sha256_bytes(audio)
    timeline["timing_authority"] = "real_narration_audio"
    (run_dir / "storyboard.json").write_text(
        json.dumps(_legacy_storyboard()), encoding="utf-8"
    )
    (run_dir / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")
    (run_dir / "script.json").write_text(
        json.dumps({"script_id": "script_001"}), encoding="utf-8"
    )
    (run_dir / "audio").mkdir()
    (run_dir / "audio" / "narration.wav").write_bytes(audio)
    (run_dir / "final.mp4").write_bytes(b"frozen-old-final")

    result = materialize_gdp_v1a(run_dir)

    assert result["program"].frame_count == 1819
    assert (run_dir / "final.mp4").read_bytes() == b"frozen-old-final"
    assert not (run_dir / "final-v1.0a-calibration.mp4").exists()
    assert (run_dir / "storyboard-v1a.json").is_file()
    assert (run_dir / "visual_program.json").is_file()
    assert (run_dir / "visual_qa_v1a.json").is_file()
    assert (run_dir / "renderer_project_v1a" / "index.html").is_file()
