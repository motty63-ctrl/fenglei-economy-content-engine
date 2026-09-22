"""Opt-in real-media calibration; no full composition render."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from fanglei.artifact_registry import ArtifactRegistry
from fanglei.audio_mastering import master_audio
from fanglei.content_models import ScriptDraft
from fanglei.models import RunManifest
from fanglei.providers.mastering import FFmpegLoudnormMasteringEngine
from fanglei.subtitle_generation import compile_subtitle_track
from fanglei.v05_models import AlignmentDocument, AudioMetadata, VoiceReviewDocument
from fanglei.v1b_models import AudioMasteringDocument, SubtitleTrack
from fanglei.visual_project_v1b import build_v1b_renderer_project
from fanglei.v1b_qa import measure_subtitle_dom, run_v1b_qa
from fanglei.subtitle_renderer import render_subtitle_layer
from fanglei.visual_system_v1 import VisualTheme
from fanglei.v1b_pipeline import run_v1b_render_adaptation
from fanglei.render_preflight import LocalRendererProbe, resolve_renderer_environment, run_render_preflight


GDP_RUN = Path("D:/Projects/fanglei-economy-content-engine/runs/2026-09-08-004-2024-us-real-gdp-growth")


@pytest.mark.skipif(os.getenv("RUN_V1B_GDP_CALIBRATION") != "1", reason="opt-in real GDP media")
def test_gdp_subtitle_and_mastering_calibration():
    run = GDP_RUN
    manifest = RunManifest.model_validate(json.loads((run / "run.json").read_text(encoding="utf-8")))
    registry = ArtifactRegistry(run, manifest)
    frozen = ["script.json", "alignment.json", "timeline.json", "storyboard.json",
              "audio/narration.wav", "audio/metadata.json", "audio/review.json"]
    before = {name: hashlib.sha256((run / name).read_bytes()).hexdigest() for name in frozen}
    for name in frozen: registry.validate(name)
    script = ScriptDraft.model_validate(registry.read_json("script.json"))
    alignment = AlignmentDocument.model_validate(registry.read_json("alignment.json"))
    track = compile_subtitle_track(script, alignment, run_id=run.name,
                                   script_sha256=manifest.artifacts["script.json"].content_hash,
                                   alignment_sha256=manifest.artifacts["alignment.json"].content_hash)
    assert len(track.cues) == 14
    assert track.validation.sentence_coverage == 1.0
    assert all(1 <= len(cue.lines) <= 2 and cue.font_size_px >= 40 for cue in track.cues)
    metadata = AudioMetadata.model_validate(registry.read_json("audio/metadata.json"))
    review = VoiceReviewDocument.model_validate(registry.read_json("audio/review.json"))
    ffmpeg = os.getenv("NIKOLA_FFMPEG_PATH", "ffmpeg")
    ffprobe = os.getenv("NIKOLA_FFPROBE_PATH", "ffprobe")
    mastered = master_audio(run / "audio" / "narration.wav", metadata, review,
                            FFmpegLoudnormMasteringEngine(ffmpeg=ffmpeg, ffprobe=ffprobe),
                            run_id=run.name)
    assert mastered.document.gate.passed
    assert mastered.document.output.sample_rate_hz == 24000
    assert mastered.document.output.channels == 1
    assert abs(mastered.document.output.integrated_lufs + 16) <= .5
    assert mastered.document.output.true_peak_dbtp <= -1
    assert abs(mastered.document.duration_delta_ms) <= 20
    assert {name: hashlib.sha256((run / name).read_bytes()).hexdigest()
            for name in frozen} == before


@pytest.mark.skipif(os.getenv("RUN_V1B_GDP_CALIBRATION") != "1", reason="opt-in real GDP media")
def test_gdp_renderer_subtitles_fit_actual_browser_boxes(tmp_path):
    run = GDP_RUN
    track = SubtitleTrack.model_validate(json.loads((run / "subtitle_track.json").read_text(encoding="utf-8")))
    report = AudioMasteringDocument.model_validate(json.loads((run / "audio_mastering.json").read_text(encoding="utf-8")))
    base_dir = run / "renderer_project_v1a"
    base_files = {}
    for path in base_dir.rglob("*"):
        if path.is_file():
            relative = path.relative_to(base_dir).as_posix()
            base_files[relative] = path.read_bytes() if path.suffix == ".wav" else path.read_text(encoding="utf-8")
    base_manifest = json.loads((run / "render_manifest_v1a.json").read_text(encoding="utf-8"))
    files, manifest = build_v1b_renderer_project(
        base_files, base_manifest, track, report,
        (run / "audio" / "mastered_narration.wav").read_bytes())
    for relative, content in files.items():
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes): destination.write_bytes(content)
        else: destination.write_text(content, encoding="utf-8")
    measured = measure_subtitle_dom(tmp_path)
    qa = run_v1b_qa(files, manifest, track, report, dom_measurements=measured)
    assert qa["passed"], qa["issues"]
    assert all(row.get("midpoint_opacity", 0) >= .95 for row in measured["cues"])


@pytest.mark.skipif(os.getenv("RUN_V1B_GDP_CALIBRATION") != "1", reason="opt-in real GDP media")
def test_gdp_v1b_renderer_stage_materializes_valid_pair():
    run_v1b_render_adaptation(GDP_RUN.name, GDP_RUN.parent)
    manifest = json.loads((GDP_RUN / "run.json").read_text(encoding="utf-8"))
    for name in ("renderer_project_v1b", "render_manifest_v1b.json"):
        assert manifest["artifacts"][name]["status"] == "valid"
    assert (GDP_RUN / "renderer_project_v1b" / "assets" / "mastered_narration.wav").is_file()


@pytest.mark.skipif(os.getenv("RUN_V1B_GDP_CALIBRATION") != "1", reason="opt-in real GDP media")
def test_gdp_v1b_preflight_and_dom_qa(tmp_path):
    run = GDP_RUN
    project = run / "renderer_project_v1b"
    manifest = json.loads((run / "render_manifest_v1b.json").read_text(encoding="utf-8"))
    track = SubtitleTrack.model_validate(json.loads((run / "subtitle_track.json").read_text(encoding="utf-8")))
    mastering = AudioMasteringDocument.model_validate(json.loads((run / "audio_mastering.json").read_text(encoding="utf-8")))
    environment = resolve_renderer_environment()
    preflight, render_qa = run_render_preflight(project, manifest, LocalRendererProbe(environment),
                                                 probe_root=tmp_path / "preflight")
    assert preflight["passed"], preflight["issues"]
    assert render_qa["passed"], render_qa["issues"]
    files = {path.relative_to(project).as_posix(): (path.read_bytes() if path.suffix == ".wav"
             else path.read_text(encoding="utf-8")) for path in project.rglob("*") if path.is_file()}
    measured = measure_subtitle_dom(project, browser_path=environment.browser)
    qa = run_v1b_qa(files, manifest, track, mastering, dom_measurements=measured)
    assert qa["passed"], qa["issues"]


@pytest.mark.skipif(os.getenv("RUN_V1B_GDP_CALIBRATION") != "1", reason="opt-in real GDP media")
def test_old_gdp_mp4_delivery_gate_catches_missing_subtitles_and_loudness():
    from fanglei.v1b_qa import audit_v1b_delivery

    run = GDP_RUN
    track = SubtitleTrack.model_validate(json.loads((run / "subtitle_track.json").read_text(encoding="utf-8")))
    mastering = AudioMasteringDocument.model_validate(json.loads((run / "audio_mastering.json").read_text(encoding="utf-8")))
    report = audit_v1b_delivery(
        run / "final-v1.0b-gdp.mp4", track, mastering,
        ffmpeg=os.getenv("NIKOLA_FFMPEG_PATH", "ffmpeg"),
        ffprobe=os.getenv("NIKOLA_FFPROBE_PATH", "ffprobe"),
        sample_times_ms=(1000, 8000, 22000, 59500),
    )
    assert "SUBTITLE_RASTER_MISSING" in report["issues"]
    assert "DELIVERY_LOUDNESS_OUT_OF_RANGE" in report["issues"]
    assert report["audio"]["channels"] == 2
    assert abs(report["audio"]["integrated_lufs"] + 13.38) < .15


@pytest.mark.skipif(os.getenv("RUN_V1B_GDP_CALIBRATION") != "1", reason="opt-in real GDP media")
def test_short_hyperframes_preview_rasterizes_subtitle_and_preserves_audio_gain(tmp_path):
    run = GDP_RUN
    track = SubtitleTrack.model_validate(json.loads((run / "subtitle_track.json").read_text(encoding="utf-8")))
    first = track.model_copy(update={"cues": [track.cues[0]]})
    bundle = render_subtitle_layer(first, VisualTheme())
    (tmp_path / "assets").mkdir()
    shutil.copyfile(run / "audio" / "mastered_narration.wav",
                    tmp_path / "assets" / "mastered_narration.wav")
    (tmp_path / "hyperframes.json").write_text(
        (run / "renderer_project_v1a" / "hyperframes.json").read_text(encoding="utf-8"),
        encoding="utf-8")
    html = (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><style>'
        "@font-face{font-family:'FangleiSans';src:local('Microsoft YaHei')}"
        'html,body{margin:0;width:1080px;height:1920px;background:#F7F2E8}'
        '#root{position:relative;width:1080px;height:1920px}'
        + bundle.css + '</style></head><body>'
        '<main id="root" data-composition-id="subtitle-preview" data-no-timeline '
        'data-duration="4" data-fps="30" data-width="1080" data-height="1920">'
        + bundle.html
        + '<audio id="full_narration" class="clip" data-start="0" data-duration="4" '
        'data-track-index="5" data-volume="0.707107" '
        'src="assets/mastered_narration.wav"></audio></main>'
        '<script>' + bundle.javascript + '\nwindow.installFangleiSubtitles(4000);'
        '</script></body></html>'
    )
    (tmp_path / "index.html").write_text(html, encoding="utf-8")
    preview = tmp_path / "subtitle-preview.mp4"
    command = shutil.which("npx.cmd") or shutil.which("npx")
    assert command is not None
    render = subprocess.run([command, "--yes", "hyperframes@0.8.20", "render", ".",
                             "--output", str(preview), "--fps", "30", "--workers", "1"],
                            cwd=tmp_path, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", check=False)
    assert render.returncode == 0, render.stderr[-1200:]
    ffmpeg = os.getenv("NIKOLA_FFMPEG_PATH", "ffmpeg")
    dark_counts = []
    for seconds in (0.1, 1.0):
        frame = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", str(seconds),
                                "-i", str(preview), "-vf", "crop=888:260:96:1480,format=gray",
                                "-frames:v", "1", "-f", "rawvideo", "pipe:1"],
                               capture_output=True, check=False)
        assert frame.returncode == 0
        dark_counts.append(sum(value < 120 for value in frame.stdout))
    assert dark_counts[0] < 200
    assert dark_counts[1] > 200
    measured = subprocess.run([
        ffmpeg, "-hide_banner", "-nostats", "-t", "4", "-i", str(preview),
        "-af", "loudnorm=I=-16:TP=-1.2:LRA=11:print_format=json", "-f", "null", "NUL",
    ], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    assert measured.returncode == 0
    from fanglei.providers.mastering import _loudnorm_json
    audio = _loudnorm_json(measured.stderr)
    assert abs(float(audio["input_i"]) + 16) <= .5
    assert float(audio["input_tp"]) <= -1
    print(f"SHORT_PREVIEW={preview}; dark_counts={dark_counts}; "
          f"lufs={audio['input_i']}; true_peak={audio['input_tp']}")


@pytest.mark.skipif(os.getenv("RUN_V1B_GDP_CALIBRATION") != "1", reason="opt-in real GDP media")
def test_r1_gdp_mp4_delivery_audio_and_four_rasterized_subtitles():
    from fanglei.v1b_qa import audit_v1b_delivery

    run = GDP_RUN
    track = SubtitleTrack.model_validate(json.loads((run / "subtitle_track.json").read_text(encoding="utf-8")))
    mastering = AudioMasteringDocument.model_validate(json.loads((run / "audio_mastering.json").read_text(encoding="utf-8")))
    report = audit_v1b_delivery(
        run / "final-v1.0b-r1-gdp.mp4", track, mastering,
        ffmpeg=os.getenv("NIKOLA_FFMPEG_PATH", "ffmpeg"),
        ffprobe=os.getenv("NIKOLA_FFPROBE_PATH", "ffprobe"),
        sample_times_ms=(1000, 8000, 22000, 59500),
    )
    assert report["passed"], report
    assert len(report["raster_samples"]) == 4
    assert all(row["dark_pixels"] >= 200 for row in report["raster_samples"])
    print("R1_DELIVERY_QA=" + json.dumps(report, ensure_ascii=False))
