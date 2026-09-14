from typer.testing import CliRunner

from fanglei.cli import app
from tests.test_v05_pipeline import _ready


def test_prepare_renderer_cli_runs_fake_pipeline_without_mp4(tmp_path) -> None:
    run = _ready(tmp_path)
    result = CliRunner().invoke(app, [
        "--runs-dir", str(tmp_path), "prepare-renderer", run.name,
        "--narration-provider", "fake", "--alignment-provider", "fake", "--probe", "fake",
    ])
    assert result.exit_code == 0, result.output
    assert "renderer_ready" in result.output
    assert (run / "render_qa.json").is_file()
    assert not (run / "final.mp4").exists()
