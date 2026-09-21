from __future__ import annotations

import hashlib
import json

import pytest

from fanglei.visual_project_v1b import build_v1b_renderer_project
from tests.test_subtitle_renderer import _track
from fanglei.v1b_models import AudioMasteringDocument


def _inputs():
    original = b"original"; mastered = b"mastered"
    original_sha = hashlib.sha256(original).hexdigest()
    mastered_sha = hashlib.sha256(mastered).hexdigest()
    base_project = {
        "index.html": ('<html><head><style>.visual-scene{}</style></head><body><main id="root" '
                       'data-duration="60.611" data-frame-count="1819">'
                       '<section id="scene_001" class="visual-scene"><section class="hook-stage">A</section></section>'
                       '<audio id="full_narration" src="assets/narration.wav"></audio></main>'
                       '<script>const visualSchedule=[];</script></body></html>'),
        "assets/narration.wav": original,
        "project-manifest.json": json.dumps({"audio": {"path": "assets/narration.wav", "sha256": original_sha,
                                              "duration_ms": 60611},
                                        "composition": {"duration_ms": 60611, "frame_count": 1819,
                                                        "scene_frame_ranges": [{"scene_id": "scene_001",
                                                                                "start_frame": 15,
                                                                                "end_frame_exclusive": 1819}]}}),
    }
    base_manifest = {"audio": {"path": "assets/narration.wav", "sha256": original_sha,
                                "duration_ms": 60611},
                     "renderer": {"duration_ms": 60611, "frame_count": 1819,
                                  "scene_frame_ranges": [{"scene_id": "scene_001",
                                                           "start_frame": 15,
                                                           "end_frame_exclusive": 1819}],
                                  "full_render_requested": False},
                     "provenance": {"all_factual_objects_traceable": True}}
    report = AudioMasteringDocument.model_validate({
        "run_id": "run-1", "engine": "ffmpeg_loudnorm",
        "input": {"path": "audio/narration.wav", "sha256": original_sha, "duration_ms": 60611,
                  "leading_silence_ms": 500, "trailing_silence_ms": 40, "integrated_lufs": -22,
                  "true_peak_dbtp": -7, "sample_rate_hz": 24000, "channels": 1},
        "output": {"path": "audio/mastered_narration.wav", "sha256": mastered_sha,
                   "duration_ms": 60611, "leading_silence_ms": 500, "trailing_silence_ms": 40,
                   "integrated_lufs": -16, "true_peak_dbtp": -1.2, "sample_rate_hz": 24000,
                   "channels": 1},
        "duration_delta_ms": 0, "leading_silence_delta_ms": 0,
        "trailing_silence_delta_ms": 0, "gate": {"passed": True},
    })
    track = _track()
    track.source.alignment_audio_sha256 = original_sha
    return base_project, base_manifest, track, report, mastered


def test_v1b_manifest_separates_timing_and_playback_audio():
    base, manifest, track, report, mastered = _inputs()
    files, result = build_v1b_renderer_project(base, manifest, track, report, mastered)
    assert result["timing_authority"]["sha256"] == manifest["audio"]["sha256"]
    assert result["playback_audio"]["sha256"] == report.output.sha256
    assert result["playback_audio"]["source_sha256"] == report.input.sha256
    assert files["assets/mastered_narration.wav"] == mastered


def test_v1b_keeps_scene_ranges_and_primitive_markup():
    base, manifest, track, report, mastered = _inputs()
    files, result = build_v1b_renderer_project(base, manifest, track, report, mastered)
    assert result["renderer"]["scene_frame_ranges"] == manifest["renderer"]["scene_frame_ranges"]
    assert '<section class="hook-stage">A</section>' in files["index.html"]
    assert 'src="assets/mastered_narration.wav"' in files["index.html"]
    assert 'id="subtitle-layer"' in files["index.html"]


def test_adapter_fails_on_unknown_base_anchor():
    base, manifest, track, report, mastered = _inputs()
    base["index.html"] = base["index.html"].replace('id="full_narration"', 'id="elsewhere"')
    with pytest.raises(ValueError, match="V1B_BASE_PROJECT_ANCHOR_MISMATCH"):
        build_v1b_renderer_project(base, manifest, track, report, mastered)
