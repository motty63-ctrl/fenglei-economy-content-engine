from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from fanglei.artifact_registry import ArtifactRegistry
from fanglei.cli import app
from fanglei.content_pipeline import run_content_pipeline, run_legacy_content_pipeline
from fanglei.errors import ArtifactConflictError
from fanglei.models import RunManifest, StageState
from fanglei.providers.content import MockContentPlanningProvider


class _ScriptCallTrackingProvider(MockContentPlanningProvider):
    def __init__(self) -> None:
        self.script_calls = 0
        self.repair_calls = 0

    def generate_script(self, request):
        self.script_calls += 1
        return super().generate_script(request)

    def repair_script(self, request):
        self.repair_calls += 1
        return super().repair_script(request)


def test_v02_script_entry_requires_human_selection_before_provider_calls(tmp_path) -> None:
    run = _prepared_retail_run(tmp_path)
    run_content_pipeline(
        run.name, tmp_path, MockContentPlanningProvider(), stop_after="angle_generation"
    )
    angles = json.loads((run / "angles.json").read_text(encoding="utf-8"))
    assert angles["recommended_angle_id"]
    assert manifest_status(run, "angle_selection.json") == "missing"
    provider = _ScriptCallTrackingProvider()

    with pytest.raises(ArtifactConflictError, match="ANGLE_SELECTION_REQUIRED"):
        run_content_pipeline(run.name, tmp_path, provider)

    assert provider.script_calls == 0
    assert provider.repair_calls == 0
    assert not (run / "script.json").exists()


def test_cross_language_authority_script_requires_approved_terminology_before_provider(tmp_path) -> None:
    from fanglei.content_models import AngleCandidate
    from fanglei.content_pipeline import record_human_angle_selection

    run = _prepared_retail_run(tmp_path, authority_claim=True)
    provider = _ScriptCallTrackingProvider()
    manifest = RunManifest.model_validate(json.loads((run / "run.json").read_text(encoding="utf-8")))
    registry = ArtifactRegistry(run, manifest, human_angle_selection_mode=True)
    angle = AngleCandidate(
        angle_id="angle_retail", title="A recorded monthly change",
        hook="What did the record report?", core_question="What changed in March?",
        core_insight="The record reports one monthly index value.",
        supporting_claim_ids=["claim_retail_001"], audience_relevance=3, novelty=3,
        hook_strength=3, visual_potential=3, explainability=4,
        evidence_strength=2, controversy_risk=0, total_score=50,
        eligibility="eligible",
    )
    registry.write_json("angles.json", {
        "schema_version": "3.0", "run_id": run.name,
        "recommended_angle_id": angle.angle_id,
        "recommendation_status": "system_recommendation_human_selection_pending",
        "candidates": [angle.model_dump(mode="json")],
    }, "angle_generation")
    manifest.stages["angle_generation"] = StageState(status="succeeded", attempts=1)
    registry.save_manifest()
    record_human_angle_selection(run.name, tmp_path, angle.angle_id)
    assert json.loads((run / "run.json").read_text(encoding="utf-8"))["stages"][
        "angle_generation"
    ]["status"] == "succeeded"

    with pytest.raises(ArtifactConflictError, match="SCRIPT_TERMINOLOGY_REVIEW_REQUIRED"):
        run_content_pipeline(run.name, tmp_path, provider)

    assert provider.script_calls == provider.repair_calls == 0
    assert not (run / "script.json").exists()
    assert manifest_status(run, "script.json") == "missing"


def _record_approved_retail_terminology(run, target_language="zh-CN"):
    from fanglei.script_terminology import record_reviewed_script_terminology_map

    manifest = RunManifest.model_validate(json.loads((run / "run.json").read_text(encoding="utf-8")))
    facts_hash = manifest.artifacts["facts.json"].content_hash
    entries = [
        ("subject", "authority_attestation.scope.subject", "Retail index", "零售指数"),
        ("metric", "authority_attestation.scope.measure", "index value", "指数值"),
        ("period", "authority_attestation.scope.period", "March", "3月"),
        ("unit", "authority_attestation.scope.unit", "index points", "指数点"),
        ("direction", "authority_attestation.scope.certainty", "reports", "报告"),
        ("source_attribution", "authority_attestation.attribution", "Data Office reports", "数据署报告"),
    ]
    payload = {
        "schema_version": "script-terminology-map/1.0",
        "case_id": "synthetic-retail-sales",
        "run_id": run.name,
        "facts_sha256": facts_hash,
        "source_language": "en",
        "target_language": target_language,
        "review_status": "approved",
        "reviewer": "test-reviewer",
        "reviewed_at": "2026-09-28T10:00:00+08:00",
        "entries": [{
            "entry_id": f"term_{index:02d}",
            "claim_ids": ["claim_retail_001"],
            "source_term": source,
            "source_field": source_field,
            "semantic_role": role,
            "proposed_target_terms": [target],
            "approved_target_terms": [target],
            "review_status": "approved",
        } for index, (role, source_field, source, target) in enumerate(entries, start=1)],
    }
    return record_reviewed_script_terminology_map(run, payload)


def _prepare_reviewed_retail_run(run, runs_dir, target_language="zh-CN"):
    from fanglei.content_pipeline import record_human_angle_selection
    from fanglei.content_models import AngleCandidate

    manifest = RunManifest.model_validate(json.loads((run / "run.json").read_text(encoding="utf-8")))
    registry = ArtifactRegistry(run, manifest, human_angle_selection_mode=True)
    angle = AngleCandidate(
        angle_id="angle_retail_001", title="A recorded monthly change",
        hook="What changed in the March record?",
        core_question="What did the synthetic report say about March?",
        core_insight="Compare the value recorded in the release.",
        supporting_claim_ids=["claim_retail_001"], audience_relevance=3, novelty=3,
        hook_strength=3, visual_potential=3, explainability=4,
        evidence_strength=2, controversy_risk=0, total_score=50,
        eligibility="eligible",
    )
    registry.write_json("angles.json", {
        "schema_version": "3.0", "run_id": run.name,
        "recommended_angle_id": angle.angle_id,
        "recommendation_status": "system_recommendation_human_selection_pending",
        "candidates": [angle.model_dump(mode="json")],
    }, "angle_generation")
    manifest.stages["angle_generation"] = StageState(status="succeeded", attempts=1)
    registry.save_manifest()
    record_human_angle_selection(run.name, runs_dir, angle.angle_id)
    _record_approved_retail_terminology(run, target_language)


def _make_angle_generation_due(run):
    manifest_path = run / "run.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["stages"]["angle_generation"]["status"] = "failed"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class _TargetCapturingProvider(MockContentPlanningProvider):
    script_target_language = "zh-Hans"

    def __init__(self):
        self.script_requests = []
        self.angle_calls = 0

    def generate_angles(self, request):
        self.angle_calls += 1
        return super().generate_angles(request)

    def generate_script(self, request):
        from fanglei.content_models import ScriptDraft, ScriptSentence

        self.script_requests.append(request)
        return ScriptDraft(
            angle_id=request.selected_angle.angle_id,
            title=request.selected_angle.title,
            target_language=request.target_language,
            sentences=[
                ScriptSentence(sentence_id="sentence_001", section="hook",
                               sentence_type="interpretation", text=request.selected_angle.hook),
                ScriptSentence(sentence_id="sentence_002", section="core_judgment",
                               sentence_type="interpretation", text="只呈现记录支持的范围。"),
            ],
        )


def test_reviewed_terminology_establishes_canonical_language_for_provider_and_lint(tmp_path, monkeypatch) -> None:
    import fanglei.content_pipeline as content_pipeline
    from fanglei.content_models import ScriptLintResult

    run = _prepared_retail_run(tmp_path, authority_claim=True)
    _prepare_reviewed_retail_run(run, tmp_path, "zh-CN")
    provider = _TargetCapturingProvider()
    lint_targets = []

    def passing_lint(_draft, *_args, **kwargs):
        lint_targets.append(kwargs["target_language"])
        return ScriptLintResult(
            passed=True, speaking_rate_chars_per_second=4.0,
            spoken_character_count=120, estimated_duration_seconds=30.0,
        )

    monkeypatch.setattr(content_pipeline, "lint_script", passing_lint)
    run_content_pipeline(run.name, tmp_path, provider)

    assert provider.script_requests[0].target_language == "zh-CN"
    assert provider.script_requests[0].terminology_map["target_language"] == "zh-CN"
    assert lint_targets == ["zh-CN", "zh-CN"]
    assert provider.script_requests[0].target_language != provider.script_target_language


def test_case_only_language_tag_difference_uses_reviewed_canonical_spelling(tmp_path, monkeypatch) -> None:
    import fanglei.content_pipeline as content_pipeline
    from fanglei.content_models import ScriptLintResult

    run = _prepared_retail_run(tmp_path, authority_claim=True)
    _prepare_reviewed_retail_run(run, tmp_path, "zh-CN")
    provider = _TargetCapturingProvider()
    monkeypatch.setattr(content_pipeline, "lint_script", lambda *_args, **kwargs: ScriptLintResult(
        passed=True, speaking_rate_chars_per_second=4.0,
        spoken_character_count=120, estimated_duration_seconds=30.0,
    ))

    run_content_pipeline(run.name, tmp_path, provider, target_language="zh-cn")

    assert provider.script_requests[0].target_language == "zh-CN"


def test_explicit_language_conflict_fails_before_provider_call(tmp_path) -> None:
    run = _prepared_retail_run(tmp_path, authority_claim=True)
    _prepare_reviewed_retail_run(run, tmp_path, "zh-CN")
    _make_angle_generation_due(run)
    provider = _TargetCapturingProvider()

    with pytest.raises(ArtifactConflictError, match="SCRIPT_TARGET_LANGUAGE_MISMATCH"):
        run_content_pipeline(run.name, tmp_path, provider, target_language="en-US")

    assert provider.script_requests == []
    assert provider.angle_calls == 0


def test_stale_terminology_artifact_fails_before_provider_call(tmp_path) -> None:
    run = _prepared_retail_run(tmp_path, authority_claim=True)
    _prepare_reviewed_retail_run(run, tmp_path, "zh-CN")
    _make_angle_generation_due(run)
    terminology_path = run / "script_terminology.json"
    terminology_path.write_text(terminology_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    provider = _TargetCapturingProvider()

    with pytest.raises(ArtifactConflictError, match="SCRIPT_TERMINOLOGY_REVIEW_REQUIRED"):
        run_content_pipeline(run.name, tmp_path, provider)

    assert provider.script_requests == []
    assert provider.angle_calls == 0


def test_unapproved_terminology_artifact_fails_before_provider_call(tmp_path) -> None:
    run = _prepared_retail_run(tmp_path, authority_claim=True)
    _prepare_reviewed_retail_run(run, tmp_path, "zh-CN")
    manifest = RunManifest.model_validate(json.loads((run / "run.json").read_text(encoding="utf-8")))
    registry = ArtifactRegistry(run, manifest, human_angle_selection_mode=True, script_terminology_mode=True)
    terminology = registry.read_json("script_terminology.json")
    terminology["review_status"] = "pending"
    terminology["reviewer"] = None
    terminology["reviewed_at"] = None
    for entry in terminology["entries"]:
        entry["review_status"] = "pending"
        entry["approved_target_terms"] = []
    registry.write_json(
        "script_terminology.json", terminology, "script_terminology_review", force=True
    )
    _make_angle_generation_due(run)
    provider = _TargetCapturingProvider()

    with pytest.raises(ArtifactConflictError, match="SCRIPT_TERMINOLOGY_REVIEW_REQUIRED"):
        run_content_pipeline(run.name, tmp_path, provider)

    assert provider.script_requests == []
    assert provider.angle_calls == 0


def test_v02_angle_id_argument_is_not_a_human_selection_record(tmp_path) -> None:
    run = _prepared_retail_run(tmp_path)
    run_content_pipeline(run.name, tmp_path, MockContentPlanningProvider(), stop_after="angle_generation")
    selected_id = _select_first_eligible(run, tmp_path)
    provider = _ScriptCallTrackingProvider()

    with pytest.raises(ArtifactConflictError, match="ANGLE_SELECTION_REQUIRED"):
        run_content_pipeline(run.name, tmp_path, provider, angle_id=selected_id)

    assert provider.script_calls == provider.repair_calls == 0


def test_select_angle_records_hash_bound_human_choice_without_creating_script(tmp_path) -> None:
    run = _prepared_retail_run(tmp_path)
    run_content_pipeline(
        run.name, tmp_path, MockContentPlanningProvider(), stop_after="angle_generation"
    )
    angles = json.loads((run / "angles.json").read_text(encoding="utf-8"))
    selected_id = next(row["angle_id"] for row in angles["candidates"] if row["eligibility"] == "eligible")

    result = CliRunner().invoke(
        app, ["--runs-dir", str(tmp_path), "select-angle", run.name, "--angle-id", selected_id]
    )

    assert result.exit_code == 0, result.output
    record = json.loads((run / "angle_selection.json").read_text(encoding="utf-8"))
    manifest = RunManifest.model_validate(
        json.loads((run / "run.json").read_text(encoding="utf-8"))
    )
    assert record["schema_version"] == "human-angle-selection/1.0"
    assert record["source"] == "human"
    assert record["selected_angle_id"] == selected_id
    assert record["angles_sha256"] == manifest.artifacts["angles.json"].content_hash
    assert record["facts_sha256"] == manifest.artifacts["facts.json"].content_hash
    assert manifest.artifacts["angle_selection.json"].status == "valid"
    assert not (run / "script.json").exists()

    provider = _ScriptCallTrackingProvider()
    run_content_pipeline(run.name, tmp_path, provider)
    script = json.loads((run / "script.json").read_text(encoding="utf-8"))
    assert script["angle_id"] == selected_id
    assert provider.script_calls == 1
    assert manifest_status(run, "script.json") == "valid"


def test_human_selection_invalidates_preexisting_script_even_when_angle_is_unchanged(tmp_path) -> None:
    run = _prepared_retail_run(tmp_path)
    run_legacy_content_pipeline(run.name, tmp_path, MockContentPlanningProvider())
    legacy_script = json.loads((run / "script.json").read_text(encoding="utf-8"))

    result = CliRunner().invoke(
        app, ["--runs-dir", str(tmp_path), "select-angle", run.name, "--angle-id", legacy_script["angle_id"]]
    )

    assert result.exit_code == 0, result.output
    assert manifest_status(run, "script.json") == "stale"
    provider = _ScriptCallTrackingProvider()
    run_content_pipeline(run.name, tmp_path, provider)
    assert provider.script_calls == 1
    assert json.loads((run / "script.json").read_text(encoding="utf-8"))["angle_id"] == legacy_script["angle_id"]


def test_forced_angle_regeneration_stales_selection_even_when_bytes_are_identical(tmp_path) -> None:
    run = _prepared_retail_run(tmp_path)
    run_content_pipeline(run.name, tmp_path, MockContentPlanningProvider(), stop_after="angle_generation")
    angles_hash_before = json.loads((run / "run.json").read_text("utf-8"))["artifacts"]["angles.json"]["content_hash"]
    selected_id = _select_first_eligible(run, tmp_path)

    run_content_pipeline(
        run.name, tmp_path, MockContentPlanningProvider(),
        stop_after="angle_generation", force_stage="angle_generation",
    )

    manifest = json.loads((run / "run.json").read_text(encoding="utf-8"))
    assert manifest["artifacts"]["angles.json"]["content_hash"] == angles_hash_before
    assert manifest["artifacts"]["angle_selection.json"]["status"] == "stale"
    provider = _ScriptCallTrackingProvider()
    with pytest.raises(ArtifactConflictError, match="ANGLE_SELECTION_STALE"):
        run_content_pipeline(run.name, tmp_path, provider, force_stage="script_generation")
    assert provider.script_calls == provider.repair_calls == 0
    assert selected_id


def test_selection_record_with_nonhuman_source_fails_before_script_provider(tmp_path) -> None:
    run = _prepared_retail_run(tmp_path)
    run_content_pipeline(run.name, tmp_path, MockContentPlanningProvider(), stop_after="angle_generation")
    _select_first_eligible(run, tmp_path)
    manifest = RunManifest.model_validate(json.loads((run / "run.json").read_text(encoding="utf-8")))
    registry = ArtifactRegistry(run, manifest)
    selection = registry.read_json("angle_selection.json")
    selection["source"] = "system"
    registry.write_json("angle_selection.json", selection, "human_angle_selection", force=True)
    registry.save_manifest()

    provider = _ScriptCallTrackingProvider()
    with pytest.raises(ArtifactConflictError, match="ANGLE_SELECTION_INVALID"):
        run_content_pipeline(run.name, tmp_path, provider)
    assert provider.script_calls == provider.repair_calls == 0


def test_selection_bound_to_old_angles_hash_fails_before_script_provider(tmp_path) -> None:
    run = _prepared_retail_run(tmp_path)
    run_content_pipeline(run.name, tmp_path, MockContentPlanningProvider(), stop_after="angle_generation")
    _select_first_eligible(run, tmp_path)
    manifest = RunManifest.model_validate(json.loads((run / "run.json").read_text(encoding="utf-8")))
    registry = ArtifactRegistry(run, manifest)
    selection = registry.read_json("angle_selection.json")
    selection["angles_sha256"] = "0" * 64
    registry.write_json("angle_selection.json", selection, "human_angle_selection", force=True)
    registry.save_manifest()

    provider = _ScriptCallTrackingProvider()
    with pytest.raises(ArtifactConflictError, match="ANGLE_SELECTION_STALE"):
        run_content_pipeline(run.name, tmp_path, provider)
    assert provider.script_calls == provider.repair_calls == 0


def test_current_facts_change_invalidates_selection_before_script_provider(tmp_path) -> None:
    run = _prepared_retail_run(tmp_path)
    run_content_pipeline(run.name, tmp_path, MockContentPlanningProvider(), stop_after="angle_generation")
    _select_first_eligible(run, tmp_path)

    manifest = RunManifest.model_validate(json.loads((run / "run.json").read_text(encoding="utf-8")))
    registry = ArtifactRegistry(run, manifest)
    facts = registry.read_json("facts.json")
    facts["claims"][0]["claim_text"] = "March retail index: 104."
    registry.write_json("facts.json", facts, "factcheck", force=True)
    registry.save_manifest()

    provider = _ScriptCallTrackingProvider()
    with pytest.raises(ArtifactConflictError):
        run_content_pipeline(run.name, tmp_path, provider)
    assert provider.script_calls == provider.repair_calls == 0
    assert manifest_status(run, "angle_selection.json") == "stale"


def test_legacy_fallback_cannot_downgrade_v02_human_selection_run(tmp_path) -> None:
    run = _prepared_retail_run(tmp_path)
    run_content_pipeline(run.name, tmp_path, MockContentPlanningProvider(), stop_after="angle_generation")
    _select_first_eligible(run, tmp_path)
    provider = _ScriptCallTrackingProvider()

    with pytest.raises(ArtifactConflictError, match="ANGLE_SELECTION_INVALID"):
        run_content_pipeline(
            run.name, tmp_path, provider, legacy_auto_recommended=True,
        )

    assert provider.script_calls == provider.repair_calls == 0


def test_selection_rejects_candidate_whose_eligibility_changed(tmp_path) -> None:
    run = _prepared_retail_run(tmp_path)
    run_content_pipeline(run.name, tmp_path, MockContentPlanningProvider(), stop_after="angle_generation")
    manifest = RunManifest.model_validate(json.loads((run / "run.json").read_text(encoding="utf-8")))
    registry = ArtifactRegistry(run, manifest)
    angles = registry.read_json("angles.json")
    selected = next(row for row in angles["candidates"] if row["eligibility"] == "eligible")
    selected["eligibility"] = "rejected"
    selected_id = selected["angle_id"]
    registry.write_json("angles.json", angles, "angle_generation", force=True)
    registry.save_manifest()

    result = CliRunner().invoke(
        app, ["--runs-dir", str(tmp_path), "select-angle", run.name, "--angle-id", selected_id]
    )

    assert result.exit_code != 0
    assert "ANGLE_SELECTION_INVALID" in (result.output + str(result.exception))
    assert not (run / "angle_selection.json").exists()


def test_missing_candidate_cannot_be_selected(tmp_path) -> None:
    run = _prepared_retail_run(tmp_path)
    run_content_pipeline(run.name, tmp_path, MockContentPlanningProvider(), stop_after="angle_generation")
    result = CliRunner().invoke(
        app, ["--runs-dir", str(tmp_path), "select-angle", run.name, "--angle-id", "angle_missing"]
    )

    assert result.exit_code != 0
    assert "ANGLE_SELECTION_INVALID" in (result.output + str(result.exception))
    assert not (run / "angle_selection.json").exists()


def test_unregistered_selection_file_is_not_silently_overwritten(tmp_path) -> None:
    run = _prepared_retail_run(tmp_path)
    run_content_pipeline(run.name, tmp_path, MockContentPlanningProvider(), stop_after="angle_generation")
    rogue_bytes = b'{"schema_version":"human-angle-selection/1.0","source":"system"}\n'
    (run / "angle_selection.json").write_bytes(rogue_bytes)
    angles = json.loads((run / "angles.json").read_text(encoding="utf-8"))
    selected_id = next(row["angle_id"] for row in angles["candidates"] if row["eligibility"] == "eligible")
    result = CliRunner().invoke(
        app, ["--runs-dir", str(tmp_path), "select-angle", run.name, "--angle-id", selected_id]
    )

    assert result.exit_code != 0
    assert "ANGLE_SELECTION_INVALID" in (result.output + str(result.exception))
    assert (run / "angle_selection.json").read_bytes() == rogue_bytes


def _prepared_retail_run(tmp_path, *, authority_claim: bool = False):
    from fanglei.research_focus import ResearchFocusV1

    run = tmp_path / "2026-09-27-001-synthetic-retail-sales"
    run.mkdir()
    manifest = RunManifest(
        run_id=run.name, created_at="2026-09-27T00:00:00+08:00", updated_at="2026-09-27T00:00:00+08:00"
    )
    registry = ArtifactRegistry(run, manifest)
    registry.write_text("source.md", "Baseline synthetic source material that differs from claim wording.", "ingest")
    registry.write_json("questions.json", {
        "core_topic": "How did the synthetic monthly retail sales index change?",
        "research_questions": [{"question": "What value did the March release record?"}],
    }, "analyze")
    registry.write_json("search_results.json", {"results": []}, "search")
    registry.write_json("source_documents/index.json", {"documents": []}, "source_fetch")
    registry.write_json("sources.json", {
        "schema_version": "2.0", "selection_status": "selected", "sources": [],
    }, "source_selection")
    retail_claim = {
        "claim_id": "claim_retail_001",
        "claim_text": "Data Office reports: March retail index: 103.",
        "claim_type": "fact",
        "verification_status": "verified",
        "allowed_downstream": True,
        "source_ids": ["src_retail_001"],
        "evidence": [{
            "source_id": "src_retail_001",
            "original_url": "https://retail.example.test/march",
            "evidence_eligible": True,
            "evidence_text": "March index: 103.",
            "published_at": "2026-04-15",
        }],
    }
    if authority_claim:
        from fanglei.evidence_targets import atomic_proposition_spans

        scope = {
            "subject": "Retail index", "measure": "index value", "period": "March",
            "unit": "index points", "statistic": None, "certainty": "reports",
            "reporting_scope": "Retail Survey",
        }
        excerpt = "Data Office reports: March retail index: 103."
        retail_claim.update({
            "verification_basis": "authoritative_primary_attestation",
            "authority_attestation": {
                "kind": "document_report",
                "source_ids": ["src_retail_001"],
                "attribution": "Data Office reports",
                "scope": scope,
            },
            "claim_text": excerpt,
            "evidence": [{
                "source_id": "src_retail_001", "original_url": "https://retail.example.test/march",
                "evidence_eligible": True, "evidence_text": excerpt,
                "published_at": "2026-04-15", "document_hash": "a" * 64,
                "paragraph_locator": "line:1", "proposition_span": atomic_proposition_spans(excerpt)[0],
                "evidence_kind": "narrative_sentence", "authority_scope_candidate": scope,
            }],
        })
    registry.write_json("facts.json", {
        "run_id": run.name,
        "claims": [{**retail_claim, "verification_basis": retail_claim.get(
            "verification_basis", "independent_corroboration")
        }],
    }, "factcheck")
    registry.write_text("research.md", "The research records [claim_retail_001] from the synthetic March release.",
                        "research_synthesis")
    registry.save_manifest()
    focus_registry = ArtifactRegistry(run, manifest, research_focus_mode=True)
    focus_registry.write_json("research_focus.json", ResearchFocusV1(
        schema_version="research-focus/1.0",
        run_id=run.name,
        case_id="synthetic-retail-sales",
        primary_question="How did the synthetic March retail sales index change?",
        subquestions=["What value did the March release record?"],
        constraints=["Use only the synthetic source record."],
        created_at="2026-09-27T00:00:00+08:00",
        created_by="test",
    ).model_dump(mode="json"), "research_focus")
    focus_registry.write_text("research.md", "The research records [claim_retail_001] from the synthetic March release.",
                             "research_synthesis", force=True)
    focus_registry.save_manifest()
    return run


def _select_first_eligible(run, runs_dir):
    angles = json.loads((run / "angles.json").read_text(encoding="utf-8"))
    selected_id = next(row["angle_id"] for row in angles["candidates"] if row["eligibility"] == "eligible")
    result = CliRunner().invoke(
        app, ["--runs-dir", str(runs_dir), "select-angle", run.name, "--angle-id", selected_id]
    )
    assert result.exit_code == 0, result.output
    return selected_id


def manifest_status(run, artifact):
    return json.loads((run / "run.json").read_text(encoding="utf-8"))["artifacts"][artifact]["status"]
