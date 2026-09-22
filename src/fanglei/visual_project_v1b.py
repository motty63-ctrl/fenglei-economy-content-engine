"""Strict downstream overlay of V1.0b subtitles and mastered playback audio."""

from __future__ import annotations

import hashlib
import json
import re

from .subtitle_renderer import render_subtitle_layer
from .v1b_models import AudioMasteringDocument, SubtitleTrack
from .visual_system_v1 import VisualTheme


def _replace_one(source: str, anchor: str, replacement: str) -> str:
    if source.count(anchor) != 1:
        raise ValueError("V1B_BASE_PROJECT_ANCHOR_MISMATCH")
    return source.replace(anchor, replacement, 1)


def build_v1b_renderer_project(
    base_files: dict[str, str | bytes], base_manifest: dict,
    track: SubtitleTrack, mastering: AudioMasteringDocument, mastered_audio: bytes,
) -> tuple[dict[str, str | bytes], dict]:
    """Layer V1.0b onto an already materialized V1.0a project; never rebuild primitives."""
    if not track.validation.passed or not mastering.gate.passed:
        raise ValueError("V1B_UPSTREAM_GATE_FAILED")
    source = base_manifest.get("audio", {})
    duration = int(base_manifest.get("renderer", {}).get("duration_ms", 0))
    if (source.get("sha256") != mastering.input.sha256
            or source.get("duration_ms") != duration
            or mastering.output.sha256 != hashlib.sha256(mastered_audio).hexdigest()
            or abs(mastering.output.duration_ms - duration) > mastering.config.maximum_duration_delta_ms
            or track.source.alignment_audio_sha256 != source.get("sha256")):
        raise ValueError("V1B_AUDIO_OR_TIMING_PROVENANCE_MISMATCH")
    if not isinstance(base_files.get("index.html"), str):
        raise ValueError("V1B_BASE_PROJECT_ANCHOR_MISMATCH")
    bundle = render_subtitle_layer(track, VisualTheme())
    html = base_files["index.html"]
    html = _replace_one(html, "</style>", bundle.css + "</style>")
    html = _replace_one(html, '<audio id="full_narration"', bundle.html + '<audio id="full_narration"')
    html = _replace_one(html, 'src="assets/narration.wav"', 'src="assets/mastered_narration.wav"')
    # HyperFrames 0.8.20 maps mono to identical stereo channels, adding ~3 LU.
    # A per-track gain preserves the approved mastered asset and final LUFS.
    render_gain = 0.707107
    audio_tag = re.search(r'<audio id="full_narration"[^>]*>', html)
    if audio_tag is None:
        raise ValueError("V1B_BASE_PROJECT_ANCHOR_MISMATCH")
    current_tag = audio_tag.group(0)
    if 'data-volume="' in current_tag:
        adapted_tag = re.sub(r'data-volume="[^"]*"', f'data-volume="{render_gain}"',
                             current_tag, count=1)
    else:
        adapted_tag = current_tag.replace(' src=', f' data-volume="{render_gain}" src=', 1)
    html = _replace_one(html, current_tag, adapted_tag)
    html = _replace_one(html, "</script></body>",
                        bundle.javascript + f"\nwindow.installFangleiSubtitles({duration});"
                        "</script></body>")
    files = dict(base_files)
    files["index.html"] = html
    files["assets/mastered_narration.wav"] = mastered_audio
    files["data/subtitle_track.json"] = track.model_dump_json(indent=2) + "\n"
    files["data/audio_mastering.json"] = mastering.model_dump_json(indent=2) + "\n"
    project = json.loads(str(files["project-manifest.json"]))
    project["visual_system_version"] = "1.0b"
    project["timing_authority"] = {
        "path": "assets/narration.wav", "sha256": mastering.input.sha256,
        "duration_ms": duration,
    }
    project["playback_audio"] = {
        "path": "assets/mastered_narration.wav", "sha256": mastering.output.sha256,
        "source_sha256": mastering.input.sha256, "duration_ms": mastering.output.duration_ms,
        "render_gain": render_gain,
    }
    files["project-manifest.json"] = json.dumps(project, ensure_ascii=False, indent=2) + "\n"
    manifest = json.loads(json.dumps(base_manifest))
    manifest["visual_system_version"] = "1.0b"
    manifest["timing_authority"] = project["timing_authority"]
    manifest["playback_audio"] = project["playback_audio"]
    manifest["subtitle"] = {"path": "data/subtitle_track.json", "cue_count": len(track.cues),
                            "script_sha256": track.source.script_sha256,
                            "alignment_sha256": track.source.alignment_sha256}
    return files, manifest
