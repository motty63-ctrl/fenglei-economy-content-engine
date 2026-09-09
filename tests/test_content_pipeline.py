import json
from pathlib import Path

from fanglei.artifact_registry import ArtifactRegistry
from fanglei.models import RunManifest
from fanglei.content_pipeline import run_content_pipeline
from fanglei.providers.content import MockContentPlanningProvider


def _write_json(registry, name, value, owner):
    registry.write_json(name, value, owner)


def _prepared_run(tmp_path: Path) -> Path:
    run = tmp_path / "2026-09-09-001-gdp-run"
    run.mkdir()
    manifest = RunManifest(run_id=run.name, created_at="2026-09-09T00:00:00+08:00", updated_at="2026-09-09T00:00:00+08:00")
    registry = ArtifactRegistry(run, manifest)
    registry.write_text("source.md", "# 原始选题\n为什么两个数字看起来不一样？", "ingest")
    _write_json(registry, "questions.json", {"core_topic": "美国GDP精度差异", "research_questions": [{"question": "为何显示不同？"}]}, "analyze")
    _write_json(registry, "search_results.json", {"results": []}, "search")
    _write_json(registry, "source_documents/index.json", {"documents": []}, "source_fetch")
    _write_json(registry, "sources.json", {"sources": []}, "source_selection")
    _write_json(registry, "facts.json", {"claims": [{
        "claim_id": "claim_007", "claim_text": "美国2024年实际GDP增长2.8%", "claim_type": "fact",
        "verification_status": "verified", "allowed_downstream": True,
        "source_ids": ["bea", "worldbank", "oecd"],
        "evidence": [{"source_id": "worldbank", "evidence_eligible": True, "observation": 2.7938}],
    }]}, "factcheck")
    registry.write_text("research.md", "# 研究\n两个值来自相同年度指标，显示精度不同。", "research_synthesis")
    registry.save_manifest()
    return run


def test_pipeline_separates_recommendation_selection_and_clean_script(tmp_path: Path) -> None:
    run = _prepared_run(tmp_path)
    provider = MockContentPlanningProvider()
    run_content_pipeline(run.name, tmp_path, provider, angle_id="angle_003", speaking_rate=4.0)
    angles = json.loads((run / "angles.json").read_text(encoding="utf-8"))
    assert len(angles["candidates"]) == 3
    assert angles["recommended_angle_id"] == "angle_001"
    assert "selected_angle_id: `angle_003`" in (run / "angle.md").read_text(encoding="utf-8")
    script = json.loads((run / "script.json").read_text(encoding="utf-8"))
    assert script["speaking_rate_chars_per_second"] == 4.0
    assert 60 <= script["estimated_duration_seconds"] <= 90
    assert script["sentences"][1]["claim_ids"] == ["claim_007"]
    spoken = (run / "script.md").read_text(encoding="utf-8")
    assert "claim_" not in spoken and "sentence_" not in spoken
    assert manifest_status(run, "script.md") == "valid"


def manifest_status(run: Path, artifact: str) -> str:
    return json.loads((run / "run.json").read_text(encoding="utf-8"))["artifacts"][artifact]["status"]


def test_rate_change_rebuilds_script_and_stales_are_resolved(tmp_path: Path) -> None:
    run = _prepared_run(tmp_path)
    provider = MockContentPlanningProvider()
    run_content_pipeline(run.name, tmp_path, provider, speaking_rate=4.0)
    run_content_pipeline(run.name, tmp_path, provider, speaking_rate=3.8)
    script = json.loads((run / "script.json").read_text(encoding="utf-8"))
    assert script["speaking_rate_chars_per_second"] == 3.8
    assert manifest_status(run, "script.json") == "valid"
    assert manifest_status(run, "script.md") == "valid"
