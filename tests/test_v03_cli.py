from typer.testing import CliRunner
from fanglei.cli import app
from tests.test_content_pipeline import _prepared_run


def test_plan_content_cli_writes_four_artifacts(tmp_path) -> None:
    run = _prepared_run(tmp_path)
    result = CliRunner().invoke(app, ["--runs-dir", str(tmp_path), "plan-content", run.name,
                                      "--provider", "mock", "--speaking-rate", "4.0"])
    assert result.exit_code == 0, result.output
    for name in ("angles.json", "angle.md", "script.json", "script.md"):
        assert (run / name).is_file()
