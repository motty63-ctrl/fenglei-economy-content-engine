import json
from pathlib import Path
import pytest

from fanglei.artifact_registry import ArtifactRegistry
from fanglei.models import RunManifest
from fanglei.content_pipeline import _repair_issues, run_content_pipeline
from fanglei.providers.content import MockContentPlanningProvider
from fanglei.script_patch import ScriptPatch, ScriptPatchResult
from fanglei.script_lint import lint_script
from tests.test_script_quality import _angle, _draft, _facts


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
        "claim_id": "claim_007", "claim_text": "United States real GDP grew 2.8% in 2024.", "claim_type": "fact",
        "verification_status": "verified", "allowed_downstream": True,
        "source_ids": ["bea", "worldbank", "oecd"],
        "evidence": [{"source_id": "worldbank", "original_url": "https://api.worldbank.test/data",
                      "evidence_eligible": True, "observation": 2.7938}],
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
    assert script["sentences"][1]["text"] == "美国2024年实际GDP增长2.8%。"
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


class _RepairingProvider(MockContentPlanningProvider):
    def __init__(self, pass_on_attempt: int | None):
        self.pass_on_attempt = pass_on_attempt
        self.repair_calls = 0
        self.angle_calls = 0

    def generate_angles(self, request):
        self.angle_calls += 1
        raise AssertionError("valid angles must not be regenerated")

    def _bad(self, request):
        draft = super().generate_script(request)
        draft.sentences[0].text = "同一个增长率为什么会出现两种写法这是不是说明两个权威机构对美国经济给出了互相矛盾的判断"
        return draft

    def generate_script(self, request):
        return self._bad(request)

    def repair_script(self, request):
        self.repair_calls += 1
        if self.pass_on_attempt == request.repair_attempt:
            text = "同一个增长率，为什么会出现两种写法？"
        else:
            text = "同一个增长率为什么会出现两种写法这是不是说明两个权威机构对美国经济给出了互相矛盾的判断"
        return ScriptPatchResult(patches=[ScriptPatch(
            sentence_id="sentence_001", operation="replace", new_text=text,
        )])


def test_script_repair_loop_passes_on_second_repair_and_preserves_angles(tmp_path: Path) -> None:
    run = _prepared_run(tmp_path)
    run_content_pipeline(run.name, tmp_path, MockContentPlanningProvider(), stop_after="angle_selection")
    before = json.loads((run / "run.json").read_text(encoding="utf-8"))
    angle_hash = before["artifacts"]["angles.json"]["content_hash"]
    angle_attempts = before["stages"]["angle_generation"]["attempts"]
    provider = _RepairingProvider(pass_on_attempt=2)

    run_content_pipeline(run.name, tmp_path, provider, force_stage="script_generation")

    after = json.loads((run / "run.json").read_text(encoding="utf-8"))
    script = json.loads((run / "script.json").read_text(encoding="utf-8"))
    audit = script["repair_audit"]
    assert provider.angle_calls == 0
    assert provider.repair_calls == 2
    assert after["artifacts"]["angles.json"]["content_hash"] == angle_hash
    assert after["stages"]["angle_generation"]["attempts"] == angle_attempts
    assert audit["initial_issue_codes"] == ["HOOK_INVALID"]
    assert [row["attempt_number"] for row in audit["repairs"]] == [1, 2]
    assert audit["repairs"][0]["issue_codes_after"] == ["HOOK_INVALID"]
    assert audit["repairs"][1]["issue_codes_after"] == []
    assert audit["final_status"] == "passed"
    assert audit["repairs"][0]["issues_before"][0]["code"] == "HOOK_INVALID"
    first = audit["repairs"][0]
    assert first["editable_sentence_ids"] == ["sentence_001"]
    assert "sentence_002" in first["protected_sentence_ids"]
    assert first["patches_requested"] == first["patches_applied"]
    assert first["patches_rejected"] == []
    assert first["protected_hashes_unchanged"] is True
    assert script["generation_config"]["max_repair_attempts"] == 2
    assert manifest_status(run, "script.json") == "valid"
    assert manifest_status(run, "script.md") == "valid"


def test_script_repair_loop_stops_after_two_and_does_not_publish_failed_draft(tmp_path: Path) -> None:
    run = _prepared_run(tmp_path)
    run_content_pipeline(run.name, tmp_path, MockContentPlanningProvider(), stop_after="angle_selection")
    provider = _RepairingProvider(pass_on_attempt=None)

    with pytest.raises(ValueError, match="SCRIPT_REPAIR_EXHAUSTED"):
        run_content_pipeline(run.name, tmp_path, provider, force_stage="script_generation")

    manifest = json.loads((run / "run.json").read_text(encoding="utf-8"))
    assert provider.angle_calls == 0
    assert provider.repair_calls == 2
    assert manifest["stages"]["script_generation"]["status"] == "failed"
    assert manifest["artifacts"]["script.json"]["status"] != "valid"
    assert manifest["artifacts"]["script.md"]["status"] != "valid"
    error = manifest["stages"]["script_generation"]["error"]["message"]
    assert "HOOK_INVALID" in error
    assert "互相矛盾" not in error


def test_structured_repair_issues_include_safe_machine_readable_fields() -> None:
    draft = _draft()
    draft.sentences[2].text = "世界银行显示增长3.6%。"
    draft.sentences[-2].sentence_type = "interpretation"
    lint = lint_script(draft, _angle(), _facts(), "不同原文", speaking_rate=6.0)
    issues = _repair_issues(lint, draft)
    by_code = {}
    for issue in issues:
        by_code.setdefault(issue.code, issue)
    duration = by_code["DURATION_TOO_SHORT"]
    assert duration.current_seconds < duration.min_seconds == 60
    assert duration.target_seconds == 75
    binding = by_code["CLAIM_BINDING_MISSING"]
    assert binding.sentence_id == "sentence_003"
    mismatch = by_code["SENTENCE_TYPE_MISMATCH"]
    assert mismatch.current_type == "interpretation"
    assert mismatch.expected_constraint == "obvious analogy markers require sentence_type=analogy"
