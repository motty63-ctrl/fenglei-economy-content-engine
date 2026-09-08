import json
import re
from pathlib import Path

import pytest

from fanglei.errors import EmptyInputError, InputPathError
from fanglei.stages.ingest import ingest_file, ingest_text


FIXTURES = Path(__file__).parent / "fixtures"


def test_ingest_txt_creates_source_and_manifest(tmp_path: Path) -> None:
    run_dir = ingest_file(FIXTURES / "article.txt", tmp_path / "runs")

    source = (run_dir / "source.md").read_text(encoding="utf-8")
    manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}-001-interest-rates-and-households", run_dir.name)
    assert "input_type: text" in source
    assert "Interest Rates and Households" in source
    assert manifest["stages"]["ingest"]["status"] == "succeeded"
    assert manifest["input"]["type"] == "text"


def test_ingest_markdown_uses_heading_for_slug(tmp_path: Path) -> None:
    run_dir = ingest_file(FIXTURES / "article.md", tmp_path / "runs")

    source = (run_dir / "source.md").read_text(encoding="utf-8")
    assert run_dir.name.endswith("-inflation-is-not-one-number")
    assert "input_type: markdown" in source
    assert "# Inflation Is Not One Number" in source


def test_ingest_text_normalizes_newlines_and_whitespace(tmp_path: Path) -> None:
    run_dir = ingest_text("  Direct Input\r\n\r\nA claim.  \r\n", tmp_path / "runs")

    source = (run_dir / "source.md").read_text(encoding="utf-8")
    assert "Direct Input\n\nA claim.\n" in source
    assert "input_type: text" in source
    assert "display_name: pasted-text" in source


@pytest.mark.parametrize("value", ["", "   \n\t"])
def test_ingest_rejects_empty_text_without_creating_run(tmp_path: Path, value: str) -> None:
    runs_dir = tmp_path / "runs"

    with pytest.raises(EmptyInputError):
        ingest_text(value, runs_dir)

    assert not runs_dir.exists()


def test_ingest_rejects_missing_or_unsupported_paths(tmp_path: Path) -> None:
    with pytest.raises(InputPathError):
        ingest_file(tmp_path / "missing.md", tmp_path / "runs")

    unsupported = tmp_path / "article.pdf"
    unsupported.write_text("content", encoding="utf-8")
    with pytest.raises(InputPathError):
        ingest_file(unsupported, tmp_path / "runs")


def test_ingest_allocates_sequential_run_ids(tmp_path: Path) -> None:
    first = ingest_text("A Stable Topic\nFirst claim.", tmp_path / "runs")
    second = ingest_text("A Different Topic\nSecond claim.", tmp_path / "runs")

    assert "-001-" in first.name
    assert "-002-" in second.name


def test_ingest_uses_next_nonempty_title_candidate(tmp_path: Path) -> None:
    run_dir = ingest_text("#\nGDP is 1%.", tmp_path / "runs")

    source = (run_dir / "source.md").read_text(encoding="utf-8")
    assert "title: GDP is 1%." in source
    assert "-gdp-is-1" in run_dir.name
