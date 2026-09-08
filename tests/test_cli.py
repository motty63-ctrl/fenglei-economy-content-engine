import json
from pathlib import Path

from typer.testing import CliRunner

from fanglei.cli import app


runner = CliRunner()


def _run_id(output: str) -> str:
    line = next(line for line in output.splitlines() if line.startswith("Created run:"))
    return line.split(":", 1)[1].strip()


def test_cli_ingest_file_then_analyze(tmp_path: Path) -> None:
    article = tmp_path / "article.md"
    article.write_text("# Employment Trends\n\nEmployment rose by 2%.\nThe author argues that hiring remains uneven.\n", encoding="utf-8")
    runs_dir = tmp_path / "runs"

    ingest = runner.invoke(app, ["--runs-dir", str(runs_dir), "ingest", str(article)])
    assert ingest.exit_code == 0, ingest.output
    run_id = _run_id(ingest.output)

    analyze = runner.invoke(app, ["--runs-dir", str(runs_dir), "analyze", run_id])
    assert analyze.exit_code == 0, analyze.output
    run_dir = runs_dir / run_id
    assert (run_dir / "source.md").is_file()
    assert (run_dir / "questions.json").is_file()
    assert not (run_dir / "research.md").exists()
    assert (run_dir / "run.json").is_file()
    assert json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["status"] == "analyzed"


def test_cli_ingest_text_and_stdin(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"

    pasted = runner.invoke(app, ["--runs-dir", str(runs_dir), "ingest", "--text", "Pasted Topic\nInflation is 3%."])
    stdin = runner.invoke(app, ["--runs-dir", str(runs_dir), "ingest", "--stdin"], input="Stdin Topic\nRates are 4%.\n")

    assert pasted.exit_code == 0, pasted.output
    assert stdin.exit_code == 0, stdin.output
    assert _run_id(pasted.output) != _run_id(stdin.output)


def test_cli_rejects_empty_and_invalid_input(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"

    empty = runner.invoke(app, ["--runs-dir", str(runs_dir), "ingest", "--text", "   "])
    missing = runner.invoke(app, ["--runs-dir", str(runs_dir), "ingest", str(tmp_path / "missing.txt")])

    assert empty.exit_code == 2
    assert missing.exit_code == 3
    assert not runs_dir.exists()


def test_cli_repeated_analyze_reuses_artifacts(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    ingest = runner.invoke(app, ["--runs-dir", str(runs_dir), "ingest", "--text", "Stable Topic\nGDP rose 1%."])
    run_id = _run_id(ingest.output)

    first = runner.invoke(app, ["--runs-dir", str(runs_dir), "analyze", run_id])
    manifest_before = (runs_dir / run_id / "run.json").read_bytes()
    second = runner.invoke(app, ["--runs-dir", str(runs_dir), "analyze", run_id])

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    assert "already current" in second.output
    assert (runs_dir / run_id / "run.json").read_bytes() == manifest_before


def test_cli_requires_exactly_one_input_mode(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"

    none = runner.invoke(app, ["--runs-dir", str(runs_dir), "ingest"])
    both = runner.invoke(app, ["--runs-dir", str(runs_dir), "ingest", "article.md", "--text", "content"])

    assert none.exit_code == 2
    assert both.exit_code == 2


def test_cli_reports_corrupt_manifest_with_stable_exit_code(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    ingest = runner.invoke(app, ["--runs-dir", str(runs_dir), "ingest", "--text", "Topic\nGDP rose 1%."])
    run_id = _run_id(ingest.output)
    (runs_dir / run_id / "run.json").write_text("{}", encoding="utf-8")

    analyze = runner.invoke(app, ["--runs-dir", str(runs_dir), "analyze", run_id])

    assert analyze.exit_code == 6
    assert "run.json" in analyze.output


def test_cli_research_with_mock_provider(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    ingest = runner.invoke(app, ["--runs-dir", str(runs_dir), "ingest", "--text", "GDP增长5.0%。"])
    run_id = _run_id(ingest.output)
    assert runner.invoke(app, ["--runs-dir", str(runs_dir), "analyze", run_id]).exit_code == 0
    result = runner.invoke(app, ["--runs-dir", str(runs_dir), "research", run_id, "--provider", "mock"])
    assert result.exit_code == 0, result.output
    assert (runs_dir / run_id / "facts.json").is_file()
