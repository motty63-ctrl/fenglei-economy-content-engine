import json
import math
import copy

import pytest

from fanglei.artifacts import sha256_bytes
from fanglei.nikola_adapter import build_nikola_project
from tests.test_timeline import _inputs


def test_adapter_translates_storyboard_without_changing_objects_or_directives() -> None:
    alignment, board, beats, audio = _inputs()
    from fanglei.timeline import compile_timeline
    timeline = compile_timeline(alignment, board, beats, audio)
    narration_audio = b"RIFF-canonical"
    timeline.audio["sha256"] = sha256_bytes(narration_audio)
    files, manifest = build_nikola_project(board, timeline, narration_audio)
    project = json.loads(files["project-manifest.json"])
    source_objects = [obj["object_id"] for scene in board["scenes"] for obj in scene["objects"]]
    compiled_objects = [obj_id for scene in project["scenes"] for obj_id in scene["object_ids"]]
    assert compiled_objects == source_objects
    assert project["scenes"][2]["animation_steps"] == [
        "source_badges_hold", "rounding_merge", "source_badges_fade",
    ]
    assert project["scenes"][3]["animation_steps"][-1] == "connect_complete_flow"
    assert manifest["renderer"]["route"] == "program_animation"
    assert manifest["provenance"]["all_factual_objects_traceable"] is True
    assert files["assets/narration.wav"] == b"RIFF-canonical"


def test_adapter_rejects_invalid_storyboard_or_timeline() -> None:
    alignment, board, beats, audio = _inputs()
    from fanglei.timeline import compile_timeline
    timeline = compile_timeline(alignment, board, beats, audio)
    timeline.audio["sha256"] = sha256_bytes(b"audio")
    board["quality_gate"]["passed"] = False
    with pytest.raises(ValueError, match="NIKOLA_STORYBOARD_INVALID"):
        build_nikola_project(board, timeline, b"audio")


def test_renderer_project_contains_no_absolute_machine_path() -> None:
    alignment, board, beats, audio = _inputs()
    from fanglei.timeline import compile_timeline
    timeline = compile_timeline(alignment, board, beats, audio)
    timeline.audio["sha256"] = sha256_bytes(b"audio")
    files, _ = build_nikola_project(board, timeline, b"audio")
    text = "\n".join(value for value in files.values() if isinstance(value, str))
    assert "C:\\Users\\" not in text
    assert "/Users/" not in text


def test_adapter_rejects_audio_that_does_not_match_timeline_hash() -> None:
    alignment, board, beats, audio = _inputs()
    from fanglei.timeline import compile_timeline
    timeline = compile_timeline(alignment, board, beats, audio)
    with pytest.raises(ValueError, match="NIKOLA_AUDIO_HASH_MISMATCH"):
        build_nikola_project(board, timeline, b"wrong-audio")


def test_adapter_rejects_unsupported_animation_directive_instead_of_guessing() -> None:
    alignment, board, beats, audio = _inputs()
    from fanglei.timeline import compile_timeline
    timeline = compile_timeline(alignment, board, beats, audio)
    narration_audio = b"audio"
    timeline.audio["sha256"] = sha256_bytes(narration_audio)
    board["scenes"][0]["renderer_directives"]["animation_primitives"].append("explode")
    with pytest.raises(ValueError, match="ADAPTER_UNSUPPORTED_DIRECTIVE"):
        build_nikola_project(board, timeline, narration_audio)


def test_adapter_escapes_storyboard_text_in_preview_html() -> None:
    alignment, board, beats, audio = _inputs()
    from fanglei.timeline import compile_timeline
    timeline = compile_timeline(alignment, board, beats, audio)
    narration_audio = b"audio"
    timeline.audio["sha256"] = sha256_bytes(narration_audio)
    board["scenes"][0]["objects"][0]["content"] = "问题<script>alert(1)</script>"
    files, _ = build_nikola_project(board, timeline, narration_audio)
    assert "<script>alert(1)</script>" not in files["index.html"]
    assert "&lt;script&gt;" in files["index.html"]


def test_adapter_emits_hyperframes_project_contract() -> None:
    alignment, board, beats, audio = _inputs()
    from fanglei.timeline import compile_timeline
    timeline = compile_timeline(alignment, board, beats, audio)
    narration_audio = b"audio"
    timeline.audio["sha256"] = sha256_bytes(narration_audio)
    files, _ = build_nikola_project(board, timeline, narration_audio)
    config = json.loads(files["hyperframes.json"])
    package = json.loads(files["package.json"])
    assert config["$schema"].endswith("/schema/hyperframes.json")
    assert "hyperframes@0.8.20 check" in package["scripts"]["check"]
    assert 'data-composition-id="full"' in files["index.html"]
    assert 'data-composition-id="main"' in files["compositions/beat-001.html"]


def test_adapter_emits_hyperframes_compatible_beat_one_dry_run() -> None:
    alignment, board, beats, audio = _inputs()
    from fanglei.timeline import compile_timeline
    timeline = compile_timeline(alignment, board, beats, audio)
    narration_audio = b"audio"
    timeline.audio["sha256"] = sha256_bytes(narration_audio)

    files, _ = build_nikola_project(board, timeline, narration_audio)
    html = files["compositions/beat-001.html"]

    assert 'data-beat-id="beat_001"' in html
    assert 'data-duration="7.351"' in html
    assert "data-no-timeline" in html
    assert "@font-face" in html
    assert "src:local('Microsoft YaHei')" in html
    assert 'id="gdp_topic"' in html
    assert 'id="question_mark"' in html
    assert 'id="beat_001_narration"' in html
    assert "@keyframes beatReveal" in html
    assert "<svg" in html


def _full_composition_fixture():
    alignment, board, beats, audio = _inputs()
    from fanglei.timeline import compile_timeline
    timeline = compile_timeline(alignment, board, beats, audio)
    narration_audio = b"audio"
    timeline.audio["sha256"] = sha256_bytes(narration_audio)
    files, manifest = build_nikola_project(board, timeline, narration_audio)
    project = json.loads(files["project-manifest.json"])
    return timeline, files, manifest, project


def test_adapter_emits_separate_full_and_beat_one_composition_entries() -> None:
    _, files, manifest, _ = _full_composition_fixture()

    assert manifest["renderer"]["compatibility_composition_entry"] == "compositions/beat-001.html"
    assert manifest["renderer"]["full_composition_entry"] == "index.html"
    assert manifest["renderer"]["full_render_requested"] is False
    assert "compositions/beat-001.html" in files
    assert 'data-composition-id="full"' in files["index.html"]
    assert 'data-composition-id="main"' in files["compositions/beat-001.html"]


def test_full_and_debug_compositions_do_not_conflict_in_hyperframes_project() -> None:
    _, files, _, _ = _full_composition_fixture()
    full_html = files["index.html"]
    debug_html = files["compositions/beat-001.html"]

    assert 'data-composition-id="full" data-no-timeline' in full_html
    assert 'src="assets/narration.wav"' in debug_html
    assert 'src="../assets/narration.wav"' not in debug_html
    assert 'data-track-index="6"' in debug_html


def test_full_composition_duration_and_frame_count_come_from_real_audio() -> None:
    timeline, files, manifest, project = _full_composition_fixture()
    duration_ms = timeline.audio["duration_ms"]
    expected_frames = math.ceil(duration_ms * 30 / 1000)
    html = files["index.html"]

    assert project["composition"]["duration_ms"] == duration_ms
    assert project["composition"]["fps"] == 30
    assert project["composition"]["frame_count"] == expected_frames
    assert manifest["renderer"]["duration_ms"] == duration_ms
    assert manifest["renderer"]["frame_count"] == expected_frames
    assert f'data-duration="{duration_ms / 1000:g}"' in html
    assert 'data-fps="30"' in html


def test_full_composition_declares_local_alias_for_subtitle_font():
    _, files, _, _ = _full_composition_fixture()
    assert "@font-face{font-family:'FangleiSans';src:local('Microsoft YaHei')}" in files["index.html"]


def test_full_composition_accepts_eight_scenes_instead_of_fixed_five() -> None:
    timeline, files, manifest, project = _full_composition_fixture()
    storyboard = json.loads(files["data/storyboard.json"])
    last = storyboard["scenes"][-1]
    last_timing = timeline.scenes[-1]
    for index in range(6, 9):
        scene = copy.deepcopy(last)
        scene["scene_id"] = f"scene_{index:03d}"
        storyboard["scenes"].append(scene)
        timeline.scenes.append(last_timing.model_copy(update={
            "scene_id": scene["scene_id"],
        }))

    audio_bytes = b"eight-scene-audio"
    timeline.audio["sha256"] = sha256_bytes(audio_bytes)
    eight_scene_files, _ = build_nikola_project(storyboard, timeline, audio_bytes)

    assert 'sceneSchedule.length===8?"ready":"invalid"' in eight_scene_files["index.html"]


def test_full_composition_preserves_scene_order_and_exact_timeline_ranges() -> None:
    timeline, files, manifest, project = _full_composition_fixture()
    expected = []
    for scene in timeline.scenes:
        expected.append({
            "scene_id": scene.scene_id,
            "start_ms": scene.start_ms,
            "end_ms": scene.end_ms,
            "start_frame": math.ceil(scene.start_ms * 30 / 1000),
            "end_frame_exclusive": math.ceil(scene.end_ms * 30 / 1000),
        })

    assert project["composition"]["scene_frame_ranges"] == expected
    assert manifest["renderer"]["scene_frame_ranges"] == expected
    assert [row["scene_id"] for row in expected] == [
        "scene_001", "scene_002", "scene_003", "scene_004", "scene_005",
    ]
    html = files["index.html"]
    positions = [html.index(f'data-scene-id="{row["scene_id"]}"') for row in expected]
    assert positions == sorted(positions)
    for row in expected:
        assert f'data-start-ms="{row["start_ms"]}"' in html
        assert f'data-end-ms="{row["end_ms"]}"' in html
        assert f'data-start-frame="{row["start_frame"]}"' in html
        assert f'data-end-frame-exclusive="{row["end_frame_exclusive"]}"' in html


def test_full_composition_binds_one_real_full_length_narration_track() -> None:
    timeline, files, manifest, project = _full_composition_fixture()
    html = files["index.html"]

    assert html.count("<audio ") == 1
    assert 'id="full_narration"' in html
    assert 'src="assets/narration.wav"' in html
    assert f'data-duration="{timeline.audio["duration_ms"] / 1000:g}"' in html
    assert project["audio"]["sha256"] == timeline.audio["sha256"]
    assert manifest["audio"]["sha256"] == timeline.audio["sha256"]


def test_same_placement_objects_receive_non_overlapping_visibility_windows() -> None:
    _, files, _, project = _full_composition_fixture()
    html = files["index.html"]

    for scene in project["scenes"]:
        by_placement = {}
        for window in scene["object_visibility"]:
            by_placement.setdefault(window["placement_key"], []).append(window)
            assert f'data-visible-start-ms="{window["start_ms"]}"' in html
            assert f'data-visible-end-ms="{window["end_ms"]}"' in html
        for windows in by_placement.values():
            ordered = sorted(windows, key=lambda item: item["start_ms"])
            assert all(left["end_ms"] <= right["start_ms"]
                       for left, right in zip(ordered, ordered[1:]))
