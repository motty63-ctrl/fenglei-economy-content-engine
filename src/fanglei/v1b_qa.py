"""V1.0b structural and browser-measured subtitle QA."""

from __future__ import annotations

import html
import json
from pathlib import Path
import re
import subprocess
import tempfile

from .render_preflight import resolve_renderer_environment
from .providers.mastering import _loudnorm_json
from .v1b_models import AudioMasteringDocument, SubtitleTrack


def _intersects(left: dict, right: dict) -> bool:
    return (left["x"] < right["right"] and left["right"] > right["x"]
            and left["y"] < right["bottom"] and left["bottom"] > right["y"])


def measure_subtitle_dom(project_dir: Path, *, browser_path: str | None = None) -> dict:
    """Measure actual browser boxes; absence/failure is a blocking QA result."""
    browser = browser_path or resolve_renderer_environment().browser
    if not browser:
        raise ValueError("SUBTITLE_BROWSER_UNAVAILABLE")
    # A separate, disposable probe document seeks each WAAPI cue to its midpoint.
    # Bounding boxes alone exist even when opacity remains zero throughout capture.
    probe_script = """<script>
    const subtitleVisibility = [...document.querySelectorAll('.subtitle-cue')].map(cue => {
      const animation = cue.getAnimations()[0];
      if (animation) {
        animation.pause();
        animation.currentTime = (Number(cue.dataset.startMs) + Number(cue.dataset.endMs)) / 2;
      }
      return {sentence_id:cue.dataset.sentenceId,
              opacity:Number(getComputedStyle(cue).opacity)};
    });
    const visibilityMarker = document.createElement('script');
    visibilityMarker.id = 'v1b-visibility-qa';
    visibilityMarker.type = 'application/json';
    visibilityMarker.textContent = JSON.stringify(subtitleVisibility);
    document.body.appendChild(visibilityMarker);
    </script>"""
    with tempfile.TemporaryDirectory(prefix="fanglei-subtitle-probe-") as temporary:
        probe = Path(temporary) / "index.html"
        source = (project_dir / "index.html").read_text(encoding="utf-8")
        if source.count("</body>") != 1:
            raise ValueError("SUBTITLE_BROWSER_MEASUREMENT_INVALID")
        probe.write_text(source.replace("</body>", probe_script + "</body>"), encoding="utf-8")
        result = subprocess.run([
            browser, "--headless=new", "--disable-gpu", "--no-sandbox",
            "--allow-file-access-from-files", "--virtual-time-budget=3000", "--dump-dom",
            probe.resolve().as_uri(),
        ], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if result.returncode != 0:
        raise ValueError("SUBTITLE_BROWSER_MEASUREMENT_FAILED")
    match = re.search(r'<script id="v1b-layout-qa" type="application/json">(.*?)</script>',
                      result.stdout, re.DOTALL)
    if not match:
        raise ValueError("SUBTITLE_BROWSER_MEASUREMENT_MISSING")
    try:
        measured = json.loads(html.unescape(match.group(1)))
    except json.JSONDecodeError as error:
        raise ValueError("SUBTITLE_BROWSER_MEASUREMENT_INVALID") from error
    if not measured.get("cues"):
        raise ValueError("SUBTITLE_BROWSER_MEASUREMENT_EMPTY")
    visibility_match = re.search(
        r'<script id="v1b-visibility-qa" type="application/json">(.*?)</script>',
        result.stdout, re.DOTALL,
    )
    if not visibility_match:
        raise ValueError("SUBTITLE_BROWSER_VISIBILITY_MISSING")
    visibility = {row["sentence_id"]: row["opacity"]
                  for row in json.loads(html.unescape(visibility_match.group(1)))}
    for row in measured["cues"]:
        row["midpoint_opacity"] = visibility.get(row["sentence_id"], 0)
    return measured


def run_v1b_qa(files: dict[str, str | bytes], manifest: dict, track: SubtitleTrack,
               mastering: AudioMasteringDocument, *, dom_measurements: dict | None) -> dict:
    issues: list[str] = []
    source = manifest.get("timing_authority", {})
    playback = manifest.get("playback_audio", {})
    if (source.get("sha256") != mastering.input.sha256
            or playback.get("sha256") != mastering.output.sha256
            or playback.get("source_sha256") != source.get("sha256")):
        issues.append("V1B_AUDIO_PROVENANCE_MISMATCH")
    if (manifest.get("renderer", {}).get("duration_ms") != source.get("duration_ms")
            or not mastering.gate.passed):
        issues.append("V1B_TIMELINE_MISMATCH")
    markup = str(files.get("index.html", ""))
    if (markup.count('class="subtitle-cue"') != len(track.cues)
            or markup.count('id="subtitle-layer"') != 1
            or 'src="assets/mastered_narration.wav"' not in markup):
        issues.append("SUBTITLE_RENDERER_COVERAGE_MISMATCH")
    if dom_measurements is None:
        issues.append("SUBTITLE_BROWSER_MEASUREMENT_MISSING")
    else:
        by_id = {row.get("sentence_id"): row for row in dom_measurements.get("cues", [])}
        if len(by_id) != len(track.cues):
            issues.append("SUBTITLE_DOM_COVERAGE_MISMATCH")
        zone = track.layout.reserved_zone
        for cue in track.cues:
            row = by_id.get(cue.sentence_id)
            if not row or (row.get("start_ms"), row.get("end_ms")) != (cue.start_ms, cue.end_ms):
                issues.append("SUBTITLE_DOM_TIMING_MISMATCH")
                continue
            if row.get("font_size_px", 0) < track.layout.minimum_font_size_px:
                issues.append("SUBTITLE_FONT_TOO_SMALL")
            if row.get("midpoint_opacity", 0) < .95:
                issues.append("SUBTITLE_NOT_VISIBLE_AT_CUE_MIDPOINT")
            if len(row.get("line_bounds", [])) != len(cue.lines):
                issues.append("SUBTITLE_LINE_COUNT_MISMATCH")
            for bounds in row.get("line_bounds", []):
                if (bounds["x"] < zone.x or bounds["right"] > zone.x + zone.width
                        or bounds["y"] < zone.y or bounds["bottom"] > zone.y + zone.height):
                    issues.append("SUBTITLE_SAFE_AREA_VIOLATION")
                for primary in row.get("primary_bounds", dom_measurements.get("primary_bounds", [])):
                    if _intersects(bounds, primary):
                        issues.append("SUBTITLE_PRIMARY_COLLISION")
    issues = list(dict.fromkeys(issues))
    return {"schema_version": "visual-qa.v1.0b", "passed": not issues,
            "issues": issues, "cue_count": len(track.cues),
            "dom_measured": dom_measurements is not None}


def audit_v1b_delivery(video: Path, track: SubtitleTrack,
                       mastering: AudioMasteringDocument, *, ffmpeg: str, ffprobe: str,
                       sample_times_ms: tuple[int, ...]) -> dict:
    """Check encoded subtitle pixels and AAC audio, not just pre-render artifacts."""
    video = Path(video)
    probe = subprocess.run([
        ffprobe, "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=sample_rate,channels,duration", "-of", "json", str(video),
    ], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if probe.returncode != 0:
        raise ValueError("DELIVERY_AUDIO_PROBE_FAILED")
    try:
        stream = json.loads(probe.stdout)["streams"][0]
        duration_ms = round(float(stream["duration"]) * 1000)
        sample_rate_hz = int(stream["sample_rate"])
        channels = int(stream["channels"])
    except (ValueError, TypeError, KeyError, IndexError, json.JSONDecodeError) as error:
        raise ValueError("DELIVERY_AUDIO_PROBE_INVALID") from error
    loudness = subprocess.run([
        ffmpeg, "-hide_banner", "-nostats", "-i", str(video), "-af",
        "loudnorm=I=-16:TP=-1.2:LRA=11:print_format=json", "-f", "null", "NUL",
    ], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if loudness.returncode != 0:
        raise ValueError("DELIVERY_AUDIO_MEASUREMENT_FAILED")
    measured = _loudnorm_json(loudness.stderr)
    audio = {
        "integrated_lufs": float(measured["input_i"]),
        "true_peak_dbtp": float(measured["input_tp"]),
        "sample_rate_hz": sample_rate_hz, "channels": channels,
        "duration_ms": duration_ms,
    }
    issues: list[str] = []
    config = mastering.config
    if abs(audio["integrated_lufs"] - config.target_integrated_lufs) > config.loudness_tolerance_lu:
        issues.append("DELIVERY_LOUDNESS_OUT_OF_RANGE")
    if audio["true_peak_dbtp"] > config.maximum_true_peak_dbtp:
        issues.append("DELIVERY_TRUE_PEAK_EXCEEDED")
    if abs(duration_ms - mastering.output.duration_ms) > config.maximum_duration_delta_ms:
        issues.append("DELIVERY_AUDIO_DURATION_CHANGED")

    zone = track.layout.reserved_zone
    raster: list[dict] = []
    for time_ms in sample_times_ms:
        active = [cue for cue in track.cues if cue.start_ms <= time_ms < cue.end_ms]
        if len(active) != 1:
            issues.append("SUBTITLE_SAMPLE_NOT_IN_CUE")
            continue
        frame = subprocess.run([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", f"{time_ms / 1000:.3f}",
            "-i", str(video), "-vf",
            f"crop={zone.width}:{zone.height}:{zone.x}:{zone.y},format=gray",
            "-frames:v", "1", "-f", "rawvideo", "pipe:1",
        ], capture_output=True, check=False)
        if frame.returncode != 0 or len(frame.stdout) != zone.width * zone.height:
            raise ValueError("SUBTITLE_RASTER_EXTRACTION_FAILED")
        dark_pixels = sum(value < 120 for value in frame.stdout)
        raster.append({"time_ms": time_ms, "sentence_id": active[0].sentence_id,
                       "dark_pixels": dark_pixels})
        if dark_pixels < 200:
            issues.append("SUBTITLE_RASTER_MISSING")
    return {"schema_version": "delivery-qa.v1.0b", "passed": not issues,
            "issues": list(dict.fromkeys(issues)), "audio": audio, "raster_samples": raster}
