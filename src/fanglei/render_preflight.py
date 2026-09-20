"""Renderer compatibility dry-run boundary; no final media is retained."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import tempfile
from typing import Callable, Mapping, Protocol


CAPABILITIES = (
    "project_schema", "node", "hyperframes", "browser", "ffmpeg", "ffprobe", "fonts",
    "svg_assets", "timeline", "animation_directives", "nikola_skill_root",
)

HYPERFRAMES_VERSION = "0.8.20"
MINIMUM_NODE_MAJOR = 22


@dataclass(frozen=True)
class RendererEnvironment:
    node: str | None
    hyperframes_command: tuple[str, ...] | None
    browser: str | None
    ffmpeg: str | None
    ffprobe: str | None
    skill_root: Path | None
    failure_codes: tuple[str, ...] = ()


def _configured_executable(environ: Mapping[str, str], variable: str, command: str,
                           which: Callable[[str], str | None], failure_code: str,
                           failures: list[str]) -> str | None:
    override = environ.get(variable)
    if override:
        if Path(override).is_file():
            return str(Path(override))
        failures.append(failure_code)
        return None
    discovered = which(command)
    if not discovered:
        failures.append(failure_code)
    return discovered


def _default_browser_candidates(environ: Mapping[str, str]) -> list[Path]:
    roots = [
        environ.get("PROGRAMFILES"), environ.get("PROGRAMFILES(X86)"),
        environ.get("LOCALAPPDATA"),
    ]
    relatives = (
        Path("Google/Chrome/Application/chrome.exe"),
        Path("Microsoft/Edge/Application/msedge.exe"),
        Path("Chromium/Application/chrome.exe"),
    )
    return [Path(root) / relative for root in roots if root for relative in relatives]


def resolve_renderer_environment(*, environ: Mapping[str, str] | None = None,
                                 which: Callable[[str], str | None] = shutil.which,
                                 skill_root: Path | None = None,
                                 browser_candidates: list[Path] | None = None) -> RendererEnvironment:
    values = dict(os.environ if environ is None else environ)
    failures: list[str] = []
    node = _configured_executable(
        values, "NIKOLA_NODE_PATH", "node", which, "PREFLIGHT_NODE_NOT_FOUND", failures,
    )
    ffmpeg = _configured_executable(
        values, "NIKOLA_FFMPEG_PATH", "ffmpeg", which, "PREFLIGHT_FFMPEG_NOT_FOUND", failures,
    )
    ffprobe = _configured_executable(
        values, "NIKOLA_FFPROBE_PATH", "ffprobe", which, "PREFLIGHT_FFPROBE_NOT_FOUND", failures,
    )

    browser_override = values.get("NIKOLA_BROWSER_PATH")
    browser: str | None = None
    if browser_override:
        if Path(browser_override).is_file():
            browser = str(Path(browser_override))
        else:
            failures.append("PREFLIGHT_BROWSER_NOT_FOUND")
    else:
        for command in ("chrome", "msedge", "chromium", "chromium-browser"):
            browser = which(command)
            if browser:
                break
        if not browser:
            candidates = (_default_browser_candidates(values)
                          if browser_candidates is None else browser_candidates)
            browser = next((str(path) for path in candidates if path.is_file()), None)
        if not browser:
            failures.append("PREFLIGHT_BROWSER_NOT_FOUND")

    cli_override = values.get("NIKOLA_HYPERFRAMES_CLI")
    hyperframes_command: tuple[str, ...] | None = None
    if cli_override:
        if node and Path(cli_override).is_file():
            hyperframes_command = (node, str(Path(cli_override)))
        else:
            failures.append("PREFLIGHT_HYPERFRAMES_NOT_FOUND")
    else:
        npx = which("npx") or which("npx.cmd")
        if npx:
            hyperframes_command = (npx, "--yes", f"hyperframes@{HYPERFRAMES_VERSION}")
        else:
            failures.append("PREFLIGHT_HYPERFRAMES_NOT_FOUND")

    resolved_skill_root = Path(skill_root) if skill_root is not None else None
    if resolved_skill_root is None:
        home = Path(values.get("USERPROFILE") or values.get("HOME") or Path.home())
        candidates = (
            home / ".codex" / "skills" / "hand-drawn-explainer-video-nikola",
            home / ".agents" / "skills" / "hand-drawn-explainer-video-nikola",
        )
        resolved_skill_root = next(
            (candidate for candidate in candidates if (candidate / "SKILL.md").is_file()), None,
        )
    elif not (resolved_skill_root / "SKILL.md").is_file():
        resolved_skill_root = None
    if resolved_skill_root is None:
        failures.append("PREFLIGHT_NIKOLA_SKILL_ROOT_NOT_FOUND")

    return RendererEnvironment(
        node=node,
        hyperframes_command=hyperframes_command,
        browser=browser,
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        skill_root=resolved_skill_root,
        failure_codes=tuple(dict.fromkeys(failures)),
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


@dataclass
class LocalRendererProbe:
    environment: RendererEnvironment
    failure_codes: tuple[str, ...] = ()

    @staticmethod
    def _run(arguments: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess | None:
        try:
            result = subprocess.run(
                arguments, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=30, check=False,
            )
            return result if result.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            return None

    def check(self, project_dir: Path, temporary_dir: Path) -> dict[str, bool]:
        temporary_dir.mkdir(parents=True, exist_ok=True)
        capabilities = {name: False for name in CAPABILITIES}
        failures = list(self.environment.failure_codes)
        animation_manifest_valid = False
        full_composition_entry = "index.html"
        try:
            project = json.loads((project_dir / "project-manifest.json").read_text(encoding="utf-8"))
            timeline = json.loads((project_dir / "data" / "timeline.json").read_text(encoding="utf-8"))
            composition = project.get("composition") or {}
            full_composition_entry = composition.get("entry", full_composition_entry)
            entry_path = Path(full_composition_entry)
            entry_is_safe = not entry_path.is_absolute() and ".." not in entry_path.parts
            capabilities["project_schema"] = bool(
                project.get("schema_version") == "5.0"
                and entry_is_safe
                and (project_dir / entry_path).is_file()
                and composition.get("duration_ms") == timeline.get("audio", {}).get("duration_ms")
                and composition.get("fps") == 30
                and composition.get("frame_count")
                and len(composition.get("scene_frame_ranges", [])) == len(project.get("scenes", []))
            )
            capabilities["timeline"] = (
                timeline.get("timing_authority") == "real_narration_audio"
                and bool(timeline.get("scenes"))
            )
            animation_manifest_valid = all(
                isinstance(scene.get("renderer_directives"), dict) for scene in project.get("scenes", [])
            )
        except (OSError, ValueError, TypeError):
            pass
        capabilities["nikola_skill_root"] = self.environment.skill_root is not None
        node_result = (self._run([self.environment.node, "--version"])
                       if self.environment.node else None)
        if node_result is not None:
            match = re.search(r"v?(\d+)", node_result.stdout or "")
            capabilities["node"] = bool(match and int(match.group(1)) >= MINIMUM_NODE_MAJOR)
            if not capabilities["node"]:
                failures.append("PREFLIGHT_NODE_VERSION_UNSUPPORTED")
        elif self.environment.node:
            failures.append("PREFLIGHT_NODE_EXECUTION_FAILED")
        if self.environment.hyperframes_command:
            version_result = self._run([
                *self.environment.hyperframes_command, "--version",
            ], cwd=project_dir)
            check_result = self._run([
                *self.environment.hyperframes_command, "check",
            ], cwd=project_dir)
            capabilities["hyperframes"] = version_result is not None and check_result is not None
            if version_result is None:
                failures.append("PREFLIGHT_HYPERFRAMES_VERSION_FAILED")
            elif check_result is None:
                failures.append("PREFLIGHT_HYPERFRAMES_CHECK_FAILED")
        screenshot = temporary_dir / "frame.png"
        document_url = (project_dir / full_composition_entry).resolve().as_uri()
        browser_result = self._run([
            self.environment.browser, "--headless=new", "--disable-gpu", "--no-sandbox",
            "--allow-file-access-from-files", "--virtual-time-budget=3000",
            f"--screenshot={screenshot}", "--window-size=360,640", document_url,
        ]) if self.environment.browser else None
        capabilities["browser"] = (
            browser_result is not None and screenshot.is_file() and screenshot.stat().st_size > 0
        )
        if self.environment.browser and not capabilities["browser"]:
            failures.append("PREFLIGHT_BROWSER_EXECUTION_FAILED")
        dom_result = self._run([
            self.environment.browser, "--headless=new", "--disable-gpu", "--no-sandbox",
            "--allow-file-access-from-files", "--virtual-time-budget=3000", "--dump-dom",
            document_url,
        ]) if self.environment.browser else None
        rendered_dom = (dom_result.stdout or "") if dom_result is not None else ""
        capabilities["animation_directives"] = bool(
            animation_manifest_valid
            and 'data-composition-id="full"' in rendered_dom
            and 'data-animation-status="ready"' in rendered_dom
        )
        if animation_manifest_valid and self.environment.browser and not capabilities["animation_directives"]:
            failures.append("PREFLIGHT_ANIMATION_DIRECTIVES_NOT_EXECUTED")
        capabilities["svg_assets"] = capabilities["browser"] and "<svg" in rendered_dom
        try:
            source_html = (project_dir / full_composition_entry).read_text(encoding="utf-8")
        except OSError:
            source_html = ""
        capabilities["fonts"] = capabilities["browser"] and "@font-face" in source_html
        probe_video = temporary_dir / "probe.mp4"
        ffmpeg_version = (self._run([self.environment.ffmpeg, "-version"])
                          if self.environment.ffmpeg else None)
        capabilities["ffmpeg"] = ffmpeg_version is not None and self._run([
            self.environment.ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
            "color=c=white:s=64x64:d=0.12", "-frames:v", "3", "-c:v", "libx264",
            "-pix_fmt", "yuv420p", "-y", str(probe_video),
        ]) is not None and probe_video.is_file() and probe_video.stat().st_size > 0
        if self.environment.ffmpeg and not capabilities["ffmpeg"]:
            failures.append("PREFLIGHT_FFMPEG_EXECUTION_FAILED")
        ffprobe_version = (self._run([self.environment.ffprobe, "-version"])
                           if self.environment.ffprobe else None)
        probe_target = probe_video if probe_video.is_file() else project_dir / "assets" / "narration.wav"
        capabilities["ffprobe"] = bool(
            ffprobe_version is not None and probe_target.is_file() and self._run([
            self.environment.ffprobe, "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1", str(probe_target),
        ]) is not None)
        if self.environment.ffprobe and not capabilities["ffprobe"]:
            failures.append("PREFLIGHT_FFPROBE_EXECUTION_FAILED")
        self.failure_codes = tuple(dict.fromkeys(failures))
        return capabilities


def run_render_preflight(project_dir: Path, manifest: dict, probe: RendererProbe, *,
                         probe_root: Path) -> tuple[dict, dict]:
    required = (
        "project-manifest.json", "hyperframes.json", "data/storyboard.json", "data/timeline.json",
        "assets/narration.wav", "index.html", "compositions/beat-001.html",
        "scripts/compatibility-check.mjs",
    )
    static_issues = [f"PROJECT_FILE_MISSING:{relative}" for relative in required
                     if not (project_dir / relative).is_file()]
    probe_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=probe_root, prefix="nikola-dry-run-") as temporary:
        capabilities = probe.check(project_dir, Path(temporary))
    issues = list(static_issues)
    issues.extend(getattr(probe, "failure_codes", ()))
    issues.extend(f"PREFLIGHT_{name.upper()}_UNAVAILABLE"
                  for name, available in capabilities.items() if not available)
    preflight = {
        "schema_version": "5.0",
        "passed": not issues,
        "capabilities": capabilities,
        "issues": issues,
        "requirements": {
            "node": f">={MINIMUM_NODE_MAJOR}",
            "hyperframes": HYPERFRAMES_VERSION,
            "ffmpeg": "PATH or explicit override; H.264/libx264 required",
            "ffprobe": "PATH or explicit override",
        },
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
