"""Renderer compatibility dry-run boundary; no final media is retained."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import subprocess
import tempfile
from typing import Protocol


CAPABILITIES = (
    "project_schema", "node", "hyperframes", "browser", "ffmpeg", "ffprobe", "fonts",
    "svg_assets", "timeline", "animation_directives",
)


class RendererProbe(Protocol):
    def check(self, project_dir: Path, temporary_dir: Path) -> dict[str, bool]: ...


@dataclass
class FakeRendererProbe:
    missing: str | None = None

    def check(self, project_dir: Path, temporary_dir: Path) -> dict[str, bool]:
        temporary_dir.mkdir(parents=True, exist_ok=True)
        (temporary_dir / "frame.png").write_bytes(b"temporary-frame")
        (temporary_dir / "probe.mp4").write_bytes(b"temporary-video")
        return {name: name != self.missing for name in CAPABILITIES}


@dataclass(frozen=True)
class LocalRendererProbe:
    node: Path
    hyperframes_cli: Path
    browser: Path
    ffmpeg: Path
    ffprobe: Path

    @staticmethod
    def _run(arguments: list[str], cwd: Path | None = None) -> bool:
        try:
            result = subprocess.run(
                arguments, cwd=cwd, capture_output=True, text=True, timeout=30, check=False,
            )
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def check(self, project_dir: Path, temporary_dir: Path) -> dict[str, bool]:
        temporary_dir.mkdir(parents=True, exist_ok=True)
        capabilities = {name: False for name in CAPABILITIES}
        try:
            project = json.loads((project_dir / "project-manifest.json").read_text(encoding="utf-8"))
            timeline = json.loads((project_dir / "data" / "timeline.json").read_text(encoding="utf-8"))
            capabilities["project_schema"] = project.get("schema_version") == "5.0"
            capabilities["timeline"] = (
                timeline.get("timing_authority") == "real_narration_audio"
                and bool(timeline.get("scenes"))
            )
            capabilities["animation_directives"] = all(
                isinstance(scene.get("renderer_directives"), dict) for scene in project.get("scenes", [])
            )
            capabilities["svg_assets"] = True
        except (OSError, ValueError, TypeError):
            pass
        capabilities["node"] = self.node.is_file() and self._run([str(self.node), "--version"])
        capabilities["hyperframes"] = self.hyperframes_cli.is_file() and self._run(
            [str(self.node), str(self.hyperframes_cli), "check"], cwd=project_dir,
        )
        screenshot = temporary_dir / "frame.png"
        capabilities["browser"] = self.browser.is_file() and self._run([
            str(self.browser), "--headless=new", "--disable-gpu", "--no-sandbox",
            f"--screenshot={screenshot}", "--window-size=360,640",
            (project_dir / "index.html").resolve().as_uri(),
        ]) and screenshot.is_file() and screenshot.stat().st_size > 0
        capabilities["fonts"] = capabilities["browser"]
        probe_video = temporary_dir / "probe.mp4"
        capabilities["ffmpeg"] = self.ffmpeg.is_file() and self._run([
            str(self.ffmpeg), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
            "color=c=white:s=64x64:d=0.12", "-frames:v", "3", "-c:v", "libx264",
            "-pix_fmt", "yuv420p", "-y", str(probe_video),
        ]) and probe_video.is_file()
        capabilities["ffprobe"] = self.ffprobe.is_file() and capabilities["ffmpeg"] and self._run([
            str(self.ffprobe), "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1", str(probe_video),
        ])
        return capabilities


def run_render_preflight(project_dir: Path, manifest: dict, probe: RendererProbe, *,
                         probe_root: Path) -> tuple[dict, dict]:
    required = (
        "project-manifest.json", "hyperframes.json", "data/storyboard.json", "data/timeline.json",
        "assets/narration.wav", "index.html", "scripts/compatibility-check.mjs",
    )
    static_issues = [f"PROJECT_FILE_MISSING:{relative}" for relative in required
                     if not (project_dir / relative).is_file()]
    probe_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=probe_root, prefix="nikola-dry-run-") as temporary:
        capabilities = probe.check(project_dir, Path(temporary))
    issues = list(static_issues)
    issues.extend(f"PREFLIGHT_{name.upper()}_UNAVAILABLE"
                  for name, available in capabilities.items() if not available)
    preflight = {
        "schema_version": "5.0",
        "passed": not issues,
        "capabilities": capabilities,
        "issues": issues,
        "full_render_performed": False,
    }
    qa_issues = list(issues)
    if manifest.get("renderer", {}).get("full_render_requested") is not False:
        qa_issues.append("FULL_RENDER_NOT_ALLOWED")
    if manifest.get("provenance", {}).get("all_factual_objects_traceable") is not True:
        qa_issues.append("RENDER_FACT_PROVENANCE_INVALID")
    qa = {
        "schema_version": "5.0",
        "passed": not qa_issues,
        "issues": qa_issues,
        "temporary_outputs_registered": False,
        "full_mp4_generated": False,
    }
    return preflight, qa
