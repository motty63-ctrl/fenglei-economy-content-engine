import json
from pathlib import Path
import pytest

from fanglei.artifact_registry import ArtifactRegistry
from fanglei.models import RunManifest
from fanglei.content_pipeline import _repair_issues, run_content_pipeline
from fanglei.content_models import AngleCandidate, ScriptReadyClaim
from fanglei.providers.content import MockContentPlanningProvider, ScriptGenerationInput
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
    _write_json(registry, "sources.json", {
        "schema_version": "2.0", "selection_status": "insufficient_sources", "sources": []
    }, "source_selection")
    _write_json(registry, "facts.json", {"claims": [{
        "claim_id": "claim_007", "claim_text": "United States real GDP grew 2.8% in 2024.", "claim_type": "fact",
        "verification_status": "verified", "allowed_downstream": True,
        "source_ids": ["bea", "worldbank", "oecd"],
        "evidence": [{"source_id": "worldbank", "original_url": "https://api.worldbank.test/data",
                      "evidence_eligible": True, "observation": 2.7938}],
    }, {
        "claim_id": "claim_999", "claim_text": "Unverified fixture claim.", "claim_type": "fact",
        "verification_status": "unverified", "allowed_downstream": False,
        "source_ids": [], "evidence": [],
    }]}, "factcheck")
    registry.write_text("research.md", "# 研究\n两个值来自相同年度指标，显示精度不同。", "research_synthesis")
    registry.save_manifest()
    return run


def test_pipeline_separates_recommendation_selection_and_clean_script(tmp_path: Path) -> None:
    run = _prepared_run(tmp_path)
    provider = MockContentPlanningProvider()
    run_content_pipeline(run.name, tmp_path, provider, angle_id="angle_003", speaking_rate=4.0)
    angles = json.loads((run / "angles.json").read_text(encoding="utf-8"))
    assert 3 <= len(angles["candidates"]) <= 5
    assert angles["recommended_angle_id"] in {item["angle_id"] for item in angles["candidates"]}
    assert "selected_angle_id: `angle_003`" in (run / "angle.md").read_text(encoding="utf-8")
    script = json.loads((run / "script.json").read_text(encoding="utf-8"))
    assert script["speaking_rate_chars_per_second"] == 4.0
    assert 60 <= script["estimated_duration_seconds"] <= 90
    assert script["sentences"][1]["claim_ids"] == ["claim_007"]
    assert script["sentences"][1]["text"] == "美国2024年实际GDP增长2.8%。"
    spoken = (run / "script.md").read_text(encoding="utf-8")
    assert "claim_" not in spoken and "sentence_" not in spoken
    assert manifest_status(run, "script.md") == "valid"


def _authority_script_inputs():
    metric_specs = [
        ("claim_022", "Change in real GDP", "2.2", "2.3"),
        ("claim_024", "Unemployment rate", "4.3", "4.1"),
        ("claim_025", "PCE inflation", "3.6", "3.7"),
        ("claim_026", "Core PCE inflation", "3.3", "3.4"),
        ("claim_027", "Federal funds rate", "3.8", "4.1"),
    ]
    palette = []
    raw_claims = []
    for claim_id, subject, june_value, september_value in metric_specs:
        evidence = [
            {"source_id": "src_002", "evidence_text": f"{subject}\n{june_value}",
             "published_at": "2026-06-17", "original_url": "https://example.test/june",
             "evidence_eligible": True},
            {"source_id": "src_001", "evidence_text": f"{subject}\n{september_value}",
             "published_at": "2026-09-16", "original_url": "https://example.test/september",
             "evidence_eligible": True},
        ]
        claim_text = (
            f"Federal Reserve FOMC participants (SEP): published Median projection for "
            f"{subject} (2026) changed from {june_value} Percent in June to "
            f"{september_value} Percent in September."
        )
        attestation = {
            "kind": "deterministic_document_comparison",
            "source_ids": ["src_002", "src_001"],
            "attribution": "Federal Reserve FOMC participants (SEP)",
            "scope": {"subject": subject, "measure": "projection", "period": "2026",
                      "unit": "Percent", "statistic": "Median", "certainty": "projection"},
        }
        palette.append(ScriptReadyClaim(
            claim_id=claim_id, claim_text=claim_text, source_ids=["src_002", "src_001"],
            evidence=evidence, verification_basis="authoritative_primary_attestation",
            authority_attestation=attestation,
        ))
        raw_claims.append({
            "claim_id": claim_id, "claim_text": claim_text, "claim_type": "fact",
            "verification_status": "verified", "verification_basis": "authoritative_primary_attestation",
            "allowed_downstream": True, "source_ids": ["src_002", "src_001"],
            "authority_attestation": attestation, "evidence": evidence,
        })

    excerpt = "Inflation remains elevated."
    statement_evidence = [{"source_id": "src_003", "evidence_text": excerpt,
                           "published_at": "2026-09-16", "original_url": "https://example.test/statement",
                           "evidence_eligible": True}]
    statement_attestation = {
        "kind": "document_report", "source_ids": ["src_003"],
        "attribution": "Federal Reserve September FOMC statement says",
        "scope": {"subject": "Inflation", "measure": "remains elevated", "period": "2026-09-16",
                  "unit": None, "statistic": None, "certainty": "remains elevated"},
    }
    statement_text = f'Federal Reserve September FOMC statement says: "{excerpt}"'
    palette.append(ScriptReadyClaim(
        claim_id="claim_037", claim_text=statement_text, source_ids=["src_003"],
        evidence=statement_evidence, verification_basis="authoritative_primary_attestation",
        authority_attestation=statement_attestation,
    ))
    raw_claims.append({
        "claim_id": "claim_037", "claim_text": statement_text, "claim_type": "fact",
        "verification_status": "verified", "verification_basis": "authoritative_primary_attestation",
        "allowed_downstream": True, "source_ids": ["src_003"],
        "authority_attestation": statement_attestation, "evidence": statement_evidence,
    })

    angle = AngleCandidate(
        angle_id="angle_001", title="把一组已核验记录并排看",
        hook="五组预测变化，怎样和九月判断并读？",
        core_question="June to September 2026 SEP projections changed how?",
        core_insight="Compare the five documented participant projections.",
        supporting_claim_ids=[item[0] for item in metric_specs],
        audience_relevance=4, novelty=3, hook_strength=3, visual_potential=4,
        explainability=4, evidence_strength=4, controversy_risk=1, total_score=82,
        eligibility="eligible",
    )
    request = ScriptGenerationInput(
        run_id="fed-case-test", selected_angle=angle,
        research_md="Research citations: " + " ".join(item.claim_id for item in palette),
        fact_palette=tuple(palette),
        research_focus={"primary_question": "compare projections and September public judgment"},
        authority_metadata={
            "source_policy": {"name": "authoritative_primary_set",
                              "institution": {"display_name": "Federal Reserve"},
                              "approval": {"status": "approved"},
                              "approved_documents": [{"source_id": source_id}
                                                     for source_id in ("src_001", "src_002", "src_003")]},
            "package_admissibility": "admissible",
        },
    )
    return angle, request, {"claims": raw_claims}


def test_mock_script_uses_selected_authority_facts_and_research_statement_context() -> None:
    angle, request, facts = _authority_script_inputs()

    draft = MockContentPlanningProvider().generate_script(request)
    lint = lint_script(draft, angle, facts, "unrelated source prompt", speaking_rate=4.0)

    used_claim_ids = {claim_id for sentence in draft.sentences for claim_id in sentence.claim_ids}
    assert {"claim_022", "claim_024", "claim_025", "claim_026", "claim_027", "claim_037"} <= used_claim_ids
    assert draft.angle_id == angle.angle_id
    assert "World Bank" not in "".join(sentence.text for sentence in draft.sentences)
    assert "round" not in "".join(sentence.text for sentence in draft.sentences).lower()
    assert lint.passed, [issue.model_dump() for issue in lint.issues]


def test_authority_script_uses_generic_evidence_framing_and_claim_attribution() -> None:
    angle, request, _ = _authority_script_inputs()
    for claim in request.fact_palette:
        claim.authority_attestation["attribution"] = "Example"
    request.authority_metadata["source_policy"]["institution"]["display_name"] = "Example"

    draft = MockContentPlanningProvider().generate_script(request)

    comparison = next(sentence.text for sentence in draft.sentences if sentence.claim_ids)
    assert comparison.startswith("Example：")
    spoken = "".join(sentence.text for sentence in draft.sentences)
    assert "Federal Reserve" not in spoken
    assert "FOMC" not in spoken
    assert "SEP" not in spoken
    assert "先按各自文件记录的时间和口径逐项比较。" in spoken


class _CapturingScriptProvider(MockContentPlanningProvider):
    def generate_script(self, request):
        self.script_request = request
        return super().generate_script(request)


def test_content_pipeline_passes_research_focus_and_authority_metadata_to_script_provider(tmp_path: Path) -> None:
    run = _prepared_run(tmp_path)
    manifest = RunManifest.model_validate(json.loads((run / "run.json").read_text(encoding="utf-8")))
    registry = ArtifactRegistry(run, manifest, research_focus_mode=True)
    focus = {
        "schema_version": "research-focus/1.0", "run_id": run.name, "case_id": "gdp-test",
        "primary_question": "Focus question for script planning?",
        "subquestions": ["Focus subquestion"], "constraints": ["Do not infer causality."],
        "created_at": "2026-09-25T00:00:00+00:00", "created_by": "test",
    }
    registry.write_json("research_focus.json", focus, "research_focus")
    registry.write_text("research.md", (run / "research.md").read_text(encoding="utf-8"),
                        "research_synthesis", force=True)
    registry.save_manifest()

    provider = _CapturingScriptProvider()
    run_content_pipeline(run.name, tmp_path, provider, speaking_rate=4.0)

    assert provider.script_request.research_focus["primary_question"] == focus["primary_question"]
    assert provider.script_request.authority_metadata["selection_status"] == "insufficient_sources"
    assert isinstance(provider.script_request.authority_metadata["sources_sha256"], str)


def manifest_status(run: Path, artifact: str) -> str:
    return json.loads((run / "run.json").read_text(encoding="utf-8"))["artifacts"][artifact]["status"]


class _CapturingOfflineProvider(MockContentPlanningProvider):
    def generate_angles(self, request):
        self.angle_request = request
        self.angle_result = super().generate_angles(request)
        return self.angle_result


def test_angle_generation_prefers_current_research_focus_and_stops_before_selection(tmp_path: Path) -> None:
    run = _prepared_run(tmp_path)
    manifest = RunManifest.model_validate(json.loads((run / "run.json").read_text("utf-8")))
    registry = ArtifactRegistry(run, manifest, research_focus_mode=True)
    focus = {
        "schema_version": "research-focus/1.0",
        "run_id": run.name,
        "case_id": "case-from-focus",
        "primary_question": "FOCUS: what did the verified documents record?",
        "subquestions": ["FOCUS subquestion A", "FOCUS subquestion B", "FOCUS subquestion C"],
        "constraints": ["FOCUS constraint: do not infer causality."],
        "created_at": "2026-09-25T00:00:00+00:00",
        "created_by": "test",
    }
    registry.write_json("research_focus.json", focus, "research_focus")
    research = (run / "research.md").read_text(encoding="utf-8")
    registry.write_text("research.md", research, "research_synthesis", force=True)
    registry.save_manifest()

    provider = _CapturingOfflineProvider()
    run_content_pipeline(run.name, tmp_path, provider, stop_after="angle_generation", force_stage="angle_generation")

    request = provider.angle_request
    assert all(
        set(candidate.supporting_claim_ids) <= {claim.claim_id for claim in request.fact_palette}
        for candidate in provider.angle_result.candidates
    )
    assert "claim_999" not in {claim.claim_id for claim in request.fact_palette}
    assert request.research_focus["primary_question"] == focus["primary_question"]
    assert request.research_questions == focus["subquestions"]
    assert request.core_topic == focus["primary_question"]
    assert request.research_focus["constraints"] == focus["constraints"]
    assert request.research_md == research
    assert "angle.md" not in {path.name for path in run.iterdir()}
    assert manifest_status(run, "angle.md") == "missing"


def test_angle_generation_uses_legacy_questions_when_focus_is_absent(tmp_path: Path) -> None:
    run = _prepared_run(tmp_path)
    provider = _CapturingOfflineProvider()
    run_content_pipeline(run.name, tmp_path, provider, stop_after="angle_generation", force_stage="angle_generation")
    assert provider.angle_request.research_focus is None
    assert provider.angle_request.core_topic == "美国GDP精度差异"
    assert provider.angle_request.research_questions == ["为何显示不同？"]


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
    analogy = next(sentence for sentence in draft.sentences if sentence.sentence_type == "analogy")
    analogy.sentence_type = "interpretation"
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
