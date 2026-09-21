"""V1.0b structural and browser-measured subtitle QA."""

from __future__ import annotations

import html
import json
from pathlib import Path
import re
import subprocess

from .render_preflight import resolve_renderer_environment
from .v1b_models import AudioMasteringDocument, SubtitleTrack


def _intersects(left: dict, right: dict) -> bool:
    return (left["x"] < right["right"] and left["right"] > right["x"]
            and left["y"] < right["bottom"] and left["bottom"] > right["y"])


def measure_subtitle_dom(project_dir: Path, *, browser_path: str | None = None) -> dict:
    """Measure actual browser boxes; absence/failure is a blocking QA result."""
    browser = browser_path or resolve_renderer_environment().browser
    if not browser:
        raise ValueError("SUBTITLE_BROWSER_UNAVAILABLE")
    result = subprocess.run([
        browser, "--headless=new", "--disable-gpu", "--no-sandbox",
        "--allow-file-access-from-files", "--virtual-time-budget=3000", "--dump-dom",
        (project_dir / "index.html").resolve().as_uri(),
    ], capture_output=True, text=True, check=False)
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
