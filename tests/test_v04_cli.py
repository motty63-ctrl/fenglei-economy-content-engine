from typer.testing import CliRunner

from fanglei.cli import app
from fanglei.content_pipeline import run_content_pipeline
from fanglei.providers.content import MockContentPlanningProvider
from tests.test_content_pipeline import _prepared_run


def _ready(tmp_path):
    run = _prepared_run(tmp_path)
    run_content_pipeline(run.name, tmp_path, MockContentPlanningProvider())
    return run


def test_visual_plan_cli_stops_after_semantic_artifact(tmp_path) -> None:
    run = _ready(tmp_path)
    result = CliRunner().invoke(app, ["--runs-dir", str(tmp_path), "visual-plan", run.name])
    assert result.exit_code == 0, result.output
    assert (run / "visual_beats.json").is_file()
    assert not (run / "storyboard.json").exists()


def test_storyboard_cli_writes_complete_visual_plan(tmp_path) -> None:
    run = _ready(tmp_path)
    result = CliRunner().invoke(app, ["--runs-dir", str(tmp_path), "storyboard", run.name])
    assert result.exit_code == 0, result.output
    assert "storyboard.json" in result.output
    assert (run / "storyboard.json").is_file()
    assert (run / "visual_plan.md").is_file()
