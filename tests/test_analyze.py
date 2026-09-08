import json
from pathlib import Path

import pytest

from fanglei.errors import ArtifactConflictError, ProviderError, RunPathError
from fanglei.models import AnalysisResult
from fanglei.providers.mock import MockAnalysisProvider
from fanglei.stages.analyze import analyze_run
from fanglei.stages.ingest import ingest_text


def _create_run(tmp_path: Path) -> tuple[Path, Path]:
    runs_dir = tmp_path / "runs"
    run_dir = ingest_text(
        "Interest Rates and Households\n"
        "The policy rate fell by 0.25 percentage points.\n"
        "The author argues that lower rates improve household cash flow.",
        runs_dir,
    )
    return runs_dir, run_dir


def test_analyze_writes_structured_questions_and_research(tmp_path: Path) -> None:
    runs_dir, run_dir = _create_run(tmp_path)

    analyze_run(run_dir.name, runs_dir, MockAnalysisProvider())

    questions = json.loads((run_dir / "questions.json").read_text(encoding="utf-8"))
    research = (run_dir / "research.md").read_text(encoding="utf-8")
    manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert questions["core_topic"] == "Interest Rates and Households"
    assert questions["key_facts"]
    assert questions["author_arguments"]
    assert questions["claims_requiring_external_verification"]
    assert questions["research_questions"]
    assert questions["single_source_dependency_risks"]
    assert "## 研究问题 1：" in research
    assert "未进行外部事实核查" in research
    repeated_clue = "- The author argues that lower rates improve household cash flow."
    assert research.count(repeated_clue) == len(questions["research_questions"])
    assert manifest["status"] == "analyzed"
    assert manifest["stages"]["analyze"]["status"] == "succeeded"


def test_analyze_reuses_valid_outputs_without_rewriting(tmp_path: Path) -> None:
    runs_dir, run_dir = _create_run(tmp_path)
    provider = MockAnalysisProvider()
    analyze_run(run_dir.name, runs_dir, provider)
    first_questions = (run_dir / "questions.json").read_bytes()
    first_research = (run_dir / "research.md").read_bytes()
    first_manifest = (run_dir / "run.json").read_bytes()

    analyze_run(run_dir.name, runs_dir, provider)

    assert (run_dir / "questions.json").read_bytes() == first_questions
    assert (run_dir / "research.md").read_bytes() == first_research
    assert (run_dir / "run.json").read_bytes() == first_manifest


def test_force_analyze_snapshots_previous_outputs(tmp_path: Path) -> None:
    runs_dir, run_dir = _create_run(tmp_path)
    provider = MockAnalysisProvider()
    analyze_run(run_dir.name, runs_dir, provider)

    analyze_run(run_dir.name, runs_dir, provider, force=True)

    snapshots = list((run_dir / ".history" / "analyze").glob("*"))
    assert len(snapshots) == 1
    assert (snapshots[0] / "questions.json").is_file()
    assert (snapshots[0] / "research.md").is_file()


def test_analyze_rejects_unsafe_or_missing_run_ids(tmp_path: Path) -> None:
    with pytest.raises(RunPathError):
        analyze_run("../outside", tmp_path / "runs", MockAnalysisProvider())
    with pytest.raises(RunPathError):
        analyze_run("2026-09-07-999-missing", tmp_path / "runs", MockAnalysisProvider())


def test_modified_output_requires_force(tmp_path: Path) -> None:
    runs_dir, run_dir = _create_run(tmp_path)
    provider = MockAnalysisProvider()
    analyze_run(run_dir.name, runs_dir, provider)
    (run_dir / "research.md").write_text("manual edit", encoding="utf-8")

    with pytest.raises(ArtifactConflictError):
        analyze_run(run_dir.name, runs_dir, provider)


class FailingProvider:
    name = "failing"
    prompt_version = "questions-v1"

    def analyze(self, source: str, title: str) -> AnalysisResult:
        raise RuntimeError("provider unavailable")


def test_provider_failure_is_persisted_and_retry_only_runs_analyze(tmp_path: Path) -> None:
    runs_dir, run_dir = _create_run(tmp_path)
    source_before = (run_dir / "source.md").read_bytes()

    with pytest.raises(ProviderError):
        analyze_run(run_dir.name, runs_dir, FailingProvider())

    failed = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert failed["stages"]["ingest"]["attempts"] == 1
    assert failed["stages"]["analyze"]["status"] == "failed"
    assert failed["stages"]["analyze"]["attempts"] == 1

    analyze_run(run_dir.name, runs_dir, MockAnalysisProvider())

    recovered = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert recovered["stages"]["ingest"]["attempts"] == 1
    assert recovered["stages"]["analyze"]["attempts"] == 2
    assert (run_dir / "source.md").read_bytes() == source_before


def test_corrupt_manifest_is_reported_as_artifact_conflict(tmp_path: Path) -> None:
    runs_dir, run_dir = _create_run(tmp_path)
    (run_dir / "run.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ArtifactConflictError, match="run.json"):
        analyze_run(run_dir.name, runs_dir, MockAnalysisProvider())


def test_source_artifact_conflict_is_not_recorded_as_provider_failure(tmp_path: Path) -> None:
    runs_dir, run_dir = _create_run(tmp_path)
    (run_dir / "source.md").write_text("invalid source", encoding="utf-8")

    with pytest.raises(ArtifactConflictError):
        analyze_run(run_dir.name, runs_dir, MockAnalysisProvider())

    manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert manifest["stages"]["analyze"]["error"]["code"] == "ARTIFACT_CONFLICT"


def test_modified_source_is_rejected_before_first_analyze(tmp_path: Path) -> None:
    runs_dir, run_dir = _create_run(tmp_path)
    source_path = run_dir / "source.md"
    source_path.write_text(source_path.read_text(encoding="utf-8").replace("0.25", "99"), encoding="utf-8")

    with pytest.raises(ArtifactConflictError, match="ingest hash"):
        analyze_run(run_dir.name, runs_dir, MockAnalysisProvider(), force=True)
