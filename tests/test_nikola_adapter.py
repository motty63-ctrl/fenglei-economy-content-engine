import json

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
    assert 'data-composition-id="main"' in files["index.html"]
