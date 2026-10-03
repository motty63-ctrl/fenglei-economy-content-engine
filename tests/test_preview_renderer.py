"""Actual Chromium/HyperFrames regressions for the exported review composition."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import wave

import pytest

from fanglei.nikola_adapter import _review_preview_html
from fanglei.v1b_models import SubtitleRect
from test_timeline_composition import _compose


@pytest.fixture
def renderer_tools():
    names = ("FENGLEI_RENDER_NODE", "FENGLEI_PUPPETEER_MODULE", "FENGLEI_RENDER_BROWSER", "FENGLEI_HYPERFRAMES_RUNTIME")
    values = [os.environ.get(name) for name in names]
    if not all(values):
        pytest.skip("Local renderer-level test requires explicit installed browser/Node/HyperFrames paths")
    assert all(Path(value).exists() for value in values)
    return values


def _synthetic_preview(tmp_path: Path, *, impossible_text=False):
    timeline = _compose()
    assets = {}
    scenes, cues = [], []
    for index, letter in enumerate("ABC"):
        scene_id, object_id = f"scene_{letter}", f"marker_{letter}"
        payload = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1920">'
                   f'<rect width="1080" height="1920" fill="#ffffff"/>'
                   f'<g data-object-id="{object_id}"><rect x="200" y="500" width="680" height="400" fill="#186050"/>'
                   f'<text x="540" y="760" font-size="160" text-anchor="middle">{letter}</text></g>'
                   '<text x="80" y="1800" font-size="24" data-source-ids="synthetic">Source: Synthetic</text></svg>').encode()
        path = f"{letter}.svg"
        import hashlib
        assets[path] = payload
        original = timeline.composition.scene_visuals[0]
        motion = original.motion[0].model_copy(update={"object_id": object_id, "delay_ms": 0, "duration_ms": 350})
        scenes.append(original.model_copy(update={
            "scene_id": scene_id, "order": index + 1, "start_ms": index * 2000,
            "end_ms": (index + 1) * 2000, "asset_path": path,
            "asset_sha256": hashlib.sha256(payload).hexdigest(), "object_ids": [object_id], "motion": [motion],
        }))
        text = "这是合成测试文本" * (2, 4, 7)[index]
        if impossible_text:
            text *= 100
        cues.append(timeline.composition.subtitle_cues[0].model_copy(update={
            "cue_id": f"cue_{letter}", "sentence_id": f"sentence_{letter}",
            "text": text, "lines": [text], "font_size_px": 48,
            "start_ms": index * 2000, "end_ms": (index + 1) * 2000,
        }))
    layout = timeline.composition.subtitle_layout.model_copy(update={
        "default_font_size_px": 48, "reserved_zone": SubtitleRect(x=48,y=1520,width=984,height=200),
        "horizontal_padding_px": 14, "vertical_padding_px": 8, "line_height": 1.08,
    })
    composition = timeline.composition.model_copy(update={"scene_visuals": scenes, "subtitle_cues": cues, "subtitle_layout": layout})
    timeline = timeline.model_copy(update={"audio": {**timeline.audio, "duration_ms": 6000}, "composition": composition})
    (tmp_path / "review-preview.html").write_text(_review_preview_html(timeline, assets), encoding="utf-8")
    (tmp_path / "assets").mkdir()
    with wave.open(str(tmp_path / "assets/narration.wav"), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b"\x00\x00" * 48000)
    return tmp_path / "review-preview.html"


def _probe(tmp_path, renderer_tools, *, impossible_text=False):
    node, puppeteer, browser, runtime = renderer_tools
    entry = _synthetic_preview(tmp_path, impossible_text=impossible_text)
    result = subprocess.run([
        node, str(Path(__file__).with_name("preview_renderer_probe.mjs")),
        puppeteer, browser, runtime, str(entry), str(tmp_path),
    ], check=True, capture_output=True, text=True, encoding="utf-8", timeout=60)
    return json.loads(result.stdout)


def test_native_hyperframes_time_selects_three_scenes_without_audio_clock(tmp_path, renderer_tools):
    result = _probe(tmp_path, renderer_tools)
    assert result["native_time_ready"], result
    assert [row["scene_id"] for row in result["samples"]] == ["scene_A", "scene_B", "scene_C"]
    assert all(row["visible_object_count"] == 1 for row in result["samples"])
    assert result["same_frame_after_audio_seek"], result
    assert all((tmp_path / f"sample-{letter}.png").stat().st_size > 1000 for letter in "ABC")


def test_actual_font_wraps_one_two_three_lines_without_clipping(tmp_path, renderer_tools):
    result = _probe(tmp_path, renderer_tools)
    assert result["layout_ready"], result
    assert [row["line_count"] for row in result["layout"]] == [1, 2, 3]
    assert all(not row["overflow"] and row["safe_area_ok"] and not row["footer_collision"]
               and not row["critical_collision"] for row in result["layout"])
    assert max(row["panel"]["height"] for row in result["layout"]) < 220
    assert all(row["text"] == row["rendered_text"] for row in result["layout"])


def test_actual_font_layout_fails_closed_when_text_cannot_fit(tmp_path, renderer_tools):
    result = _probe(tmp_path, renderer_tools, impossible_text=True)
    assert not result["layout_ready"]
    assert result["layout_error"] == "RENDER_SUBTITLE_NO_SAFE_SPACE"
