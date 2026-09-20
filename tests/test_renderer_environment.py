from pathlib import Path
import subprocess
import sys

import pytest

import fanglei.render_preflight as preflight_module
from fanglei.render_preflight import LocalRendererProbe, resolve_renderer_environment, run_render_preflight
from tests.test_render_preflight import _project


def _runtime(tmp_path: Path) -> tuple[dict[str, str], dict[str, str]]:
    binaries = tmp_path / "bin"
    binaries.mkdir()
    paths: dict[str, str] = {}
    for name in ("node", "npx", "chrome", "ffmpeg", "ffprobe"):
        path = binaries / f"{name}.exe"
        path.write_bytes(b"executable")
        paths[name] = str(path)
    skill_root = tmp_path / ".codex" / "skills" / "hand-drawn-explainer-video-nikola"
    skill_root.mkdir(parents=True)
    (skill_root / "SKILL.md").write_text("# Nikola", encoding="utf-8")
    return paths, {"USERPROFILE": str(tmp_path)}


def _which(paths: dict[str, str]):
    return lambda command: paths.get(command)


def _successful_subprocess(command, **kwargs):
    arguments = [str(item) for item in command]
    stdout = ""
    if "--version" in arguments and Path(arguments[0]).stem == "node":
        stdout = "v22.4.0\n"
    elif "--version" in arguments and "hyperframes@0.8.20" in arguments:
        stdout = "0.8.20\n"
    elif "--dump-dom" in arguments:
        stdout = '<main data-composition-id="full" data-animation-status="ready"><svg></svg></main>'
    for argument in arguments:
        if argument.startswith("--screenshot="):
            Path(argument.split("=", 1)[1]).write_bytes(b"png")
    if "libx264" in arguments:
        Path(arguments[-1]).write_bytes(b"mp4")
    return subprocess.CompletedProcess(arguments, 0, stdout=stdout, stderr="")


def test_system_dependencies_pass_without_nikola_environment_variables(tmp_path, monkeypatch) -> None:
    paths, environ = _runtime(tmp_path)
    environment = resolve_renderer_environment(environ=environ, which=_which(paths))
    project, manifest = _project(tmp_path / "run")
    monkeypatch.setattr(preflight_module.subprocess, "run", _successful_subprocess)

    report, qa = run_render_preflight(
        project, manifest, LocalRendererProbe(environment), probe_root=tmp_path / "probe",
    )

    assert report["passed"] is True
    assert qa["passed"] is True
    assert environment.hyperframes_command == (
        paths["npx"], "--yes", "hyperframes@0.8.20",
    )


def test_subprocess_output_is_decoded_as_utf8_on_windows() -> None:
    result = LocalRendererProbe._run([
        sys.executable,
        "-c",
        "import sys;sys.stdout.buffer.write(bytes.fromhex('f09f8eac'))",
    ])

    assert result is not None
    assert result.stdout == "\U0001f3ac"


def test_hyperframes_is_detected_via_npx_without_global_install(tmp_path, monkeypatch) -> None:
    paths, environ = _runtime(tmp_path)
    commands: list[list[str]] = []

    def record(command, **kwargs):
        commands.append([str(item) for item in command])
        return _successful_subprocess(command, **kwargs)

    monkeypatch.setattr(preflight_module.subprocess, "run", record)
    project, manifest = _project(tmp_path / "run")
    report, _ = run_render_preflight(
        project, manifest,
        LocalRendererProbe(resolve_renderer_environment(environ=environ, which=_which(paths))),
        probe_root=tmp_path / "probe",
    )

    assert report["capabilities"]["hyperframes"] is True
    assert [paths["npx"], "--yes", "hyperframes@0.8.20", "--version"] in commands
    assert [paths["npx"], "--yes", "hyperframes@0.8.20", "check"] in commands


def test_ffmpeg_and_ffprobe_are_resolved_from_path(tmp_path) -> None:
    paths, environ = _runtime(tmp_path)
    environment = resolve_renderer_environment(environ=environ, which=_which(paths))
    assert environment.ffmpeg == paths["ffmpeg"]
    assert environment.ffprobe == paths["ffprobe"]


def test_ffprobe_is_checked_independently_when_ffmpeg_is_missing(tmp_path, monkeypatch) -> None:
    paths, environ = _runtime(tmp_path)
    paths.pop("ffmpeg")
    project, manifest = _project(tmp_path / "run")
    monkeypatch.setattr(preflight_module.subprocess, "run", _successful_subprocess)

    report, _ = run_render_preflight(
        project,
        manifest,
        LocalRendererProbe(resolve_renderer_environment(environ=environ, which=_which(paths))),
        probe_root=tmp_path / "probe",
    )

    assert report["capabilities"]["ffmpeg"] is False
    assert report["capabilities"]["ffprobe"] is True
    assert "PREFLIGHT_FFMPEG_NOT_FOUND" in report["issues"]
    assert "PREFLIGHT_FFPROBE_EXECUTION_FAILED" not in report["issues"]


def test_explicit_overrides_take_priority_over_path(tmp_path) -> None:
    paths, environ = _runtime(tmp_path)
    overrides = {}
    for variable in (
        "NIKOLA_NODE_PATH", "NIKOLA_HYPERFRAMES_CLI", "NIKOLA_BROWSER_PATH",
        "NIKOLA_FFMPEG_PATH", "NIKOLA_FFPROBE_PATH",
    ):
        override = tmp_path / f"{variable}.exe"
        override.write_bytes(b"override")
        overrides[variable] = str(override)
    environment = resolve_renderer_environment(
        environ={**environ, **overrides}, which=_which(paths),
    )
    assert environment.node == overrides["NIKOLA_NODE_PATH"]
    assert environment.hyperframes_command == (
        overrides["NIKOLA_NODE_PATH"], overrides["NIKOLA_HYPERFRAMES_CLI"],
    )
    assert environment.browser == overrides["NIKOLA_BROWSER_PATH"]
    assert environment.ffmpeg == overrides["NIKOLA_FFMPEG_PATH"]
    assert environment.ffprobe == overrides["NIKOLA_FFPROBE_PATH"]


def test_missing_c_tools_directory_is_not_a_dependency(tmp_path) -> None:
    paths, environ = _runtime(tmp_path)
    environment = resolve_renderer_environment(environ=environ, which=_which(paths))
    assert not any("C:\\Tools\\nikola-runtime" in item for item in environment.failure_codes)
    assert environment.failure_codes == ()


def test_nikola_skill_root_resolves_from_actual_skill_install_location(tmp_path) -> None:
    paths, environ = _runtime(tmp_path)
    environment = resolve_renderer_environment(environ=environ, which=_which(paths))
    assert environment.skill_root == (
        tmp_path / ".codex" / "skills" / "hand-drawn-explainer-video-nikola"
    )


def test_node_below_22_fails_with_explicit_requirement(tmp_path, monkeypatch) -> None:
    paths, environ = _runtime(tmp_path)

    def old_node(command, **kwargs):
        result = _successful_subprocess(command, **kwargs)
        if "--version" in [str(item) for item in command] and Path(str(command[0])).stem == "node":
            result.stdout = "v20.18.0\n"
        return result

    monkeypatch.setattr(preflight_module.subprocess, "run", old_node)
    project, manifest = _project(tmp_path / "run")
    report, _ = run_render_preflight(
        project, manifest,
        LocalRendererProbe(resolve_renderer_environment(environ=environ, which=_which(paths))),
        probe_root=tmp_path / "probe",
    )
    assert report["passed"] is False
    assert "PREFLIGHT_NODE_VERSION_UNSUPPORTED" in report["issues"]
    assert report["requirements"]["node"] == ">=22"


def test_missing_browser_reports_specific_failure_code(tmp_path) -> None:
    paths, environ = _runtime(tmp_path)
    paths.pop("chrome")
    environment = resolve_renderer_environment(
        environ=environ, which=_which(paths), browser_candidates=[],
    )
    assert "PREFLIGHT_BROWSER_NOT_FOUND" in environment.failure_codes


def test_browser_probe_rejects_a_full_composition_whose_animation_marker_never_becomes_ready(
    tmp_path, monkeypatch,
) -> None:
    paths, environ = _runtime(tmp_path)

    def animation_not_ready(command, **kwargs):
        result = _successful_subprocess(command, **kwargs)
        if "--dump-dom" in [str(item) for item in command]:
            result.stdout = '<main data-composition-id="full" data-animation-status="invalid"></main>'
        return result

    monkeypatch.setattr(preflight_module.subprocess, "run", animation_not_ready)
    project, manifest = _project(tmp_path / "run")
    report, _ = run_render_preflight(
        project,
        manifest,
        LocalRendererProbe(resolve_renderer_environment(environ=environ, which=_which(paths))),
        probe_root=tmp_path / "probe",
    )

    assert report["capabilities"]["browser"] is True
    assert report["capabilities"]["animation_directives"] is False
    assert "PREFLIGHT_ANIMATION_DIRECTIVES_NOT_EXECUTED" in report["issues"]


def test_browser_probe_uses_full_composition_entry(tmp_path, monkeypatch) -> None:
    paths, environ = _runtime(tmp_path)
    commands: list[list[str]] = []

    def record(command, **kwargs):
        commands.append([str(item) for item in command])
        return _successful_subprocess(command, **kwargs)

    monkeypatch.setattr(preflight_module.subprocess, "run", record)
    project, manifest = _project(tmp_path / "run")
    run_render_preflight(
        project,
        manifest,
        LocalRendererProbe(resolve_renderer_environment(environ=environ, which=_which(paths))),
        probe_root=tmp_path / "probe",
    )

    browser_urls = [argument for command in commands for argument in command if argument.startswith("file:")]
    assert browser_urls
    assert all(url.endswith("/index.html") for url in browser_urls)


@pytest.mark.parametrize(
    ("missing", "code"),
    [
        ("node", "PREFLIGHT_NODE_NOT_FOUND"),
        ("npx", "PREFLIGHT_HYPERFRAMES_NOT_FOUND"),
        ("ffmpeg", "PREFLIGHT_FFMPEG_NOT_FOUND"),
        ("ffprobe", "PREFLIGHT_FFPROBE_NOT_FOUND"),
    ],
)
def test_missing_dependency_has_specific_failure_code(tmp_path, missing, code) -> None:
    paths, environ = _runtime(tmp_path)
    paths.pop(missing)
    environment = resolve_renderer_environment(environ=environ, which=_which(paths))
    assert code in environment.failure_codes
