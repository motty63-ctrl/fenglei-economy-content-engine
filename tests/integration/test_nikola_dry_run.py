import io
import os
from pathlib import Path
import wave

import pytest

from fanglei.artifacts import sha256_bytes
from fanglei.nikola_adapter import build_nikola_project
from fanglei.render_preflight import (
    LocalRendererProbe,
    resolve_renderer_environment,
    run_render_preflight,
)
from fanglei.timeline import compile_timeline
from tests.test_timeline import _inputs


pytestmark = pytest.mark.integration


@pytest.mark.skipif(os.environ.get("RUN_NIKOLA_DRY_RUN") != "1",
                    reason="set RUN_NIKOLA_DRY_RUN=1 to run Nikola compatibility dry-run")
def test_real_nikola_program_animation_dependencies(tmp_path) -> None:
    environment = resolve_renderer_environment()
    if environment.failure_codes:
        pytest.fail("renderer dependencies unavailable: " + ",".join(environment.failure_codes))
    alignment, board, beats, audio = _inputs()
    timeline = compile_timeline(alignment, board, beats, audio)
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(24000)
        stream.writeframes(b"\x00\x00" * round(24000 * audio.duration_ms / 1000))
    narration_audio = output.getvalue()
    timeline.audio["sha256"] = sha256_bytes(narration_audio)
    files, manifest = build_nikola_project(board, timeline, narration_audio)
    project = tmp_path / "renderer_project"
    for relative, value in files.items():
        target = project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value) if isinstance(value, bytes) else target.write_text(value, encoding="utf-8")
    probe = LocalRendererProbe(environment)
    preflight, qa = run_render_preflight(project, manifest, probe, probe_root=tmp_path / "probe")
    assert preflight["passed"], preflight["issues"]
    assert qa["passed"], qa["issues"]
    assert not any(project.rglob("*.mp4"))
