from pathlib import Path

import pytest
from pydantic import ValidationError

from fanglei.artifacts import atomic_write_json, atomic_write_text, read_json, sha256_text
from fanglei.models import AnalysisResult, RunManifest, StageState
import fanglei.artifacts as artifact_io


def test_atomic_writes_round_trip_utf8(tmp_path: Path) -> None:
    text_path = tmp_path / "source.md"
    json_path = tmp_path / "questions.json"

    atomic_write_text(text_path, "利率与通胀\n")
    atomic_write_json(json_path, {"topic": "利率"})

    assert text_path.read_text(encoding="utf-8") == "利率与通胀\n"
    assert read_json(json_path) == {"topic": "利率"}
    assert not list(tmp_path.glob("*.tmp"))


def test_atomic_write_retries_transient_windows_replace_lock(tmp_path: Path, monkeypatch) -> None:
    original_replace = artifact_io.os.replace
    attempts = 0

    def flaky_replace(source, target):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError("transient sync lock")
        return original_replace(source, target)

    monkeypatch.setattr(artifact_io.os, "replace", flaky_replace)
    target = tmp_path / "run.json"
    atomic_write_text(target, "ready")
    assert target.read_text(encoding="utf-8") == "ready"
    assert attempts == 3


def test_sha256_text_is_deterministic() -> None:
    assert sha256_text("同一内容") == sha256_text("同一内容")
    assert sha256_text("内容一") != sha256_text("内容二")


def test_stage_state_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        StageState(status="unknown")


def test_analysis_result_requires_all_collections() -> None:
    with pytest.raises(ValidationError):
        AnalysisResult(core_topic="利率")


def test_manifest_has_pending_stage_defaults() -> None:
    manifest = RunManifest(run_id="2026-09-07-001-topic", created_at="2026-09-07T00:00:00+08:00", updated_at="2026-09-07T00:00:00+08:00")

    assert manifest.stages["ingest"].status == "pending"
    assert manifest.stages["analyze"].status == "pending"
