from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from fanglei.artifact_registry import ArtifactRegistry
from fanglei.cli import app
from fanglei.content_pipeline import run_content_pipeline, run_legacy_content_pipeline
from fanglei.errors import ArtifactConflictError
from fanglei.models import RunManifest
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


def _prepared_retail_run(tmp_path):
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
    registry.write_json("facts.json", {
        "run_id": run.name,
        "claims": [{
            "claim_id": "claim_retail_001",
            "claim_text": "March retail index: 103.",
            "claim_type": "fact",
            "verification_status": "verified",
            "allowed_downstream": True,
            "verification_basis": "independent_corroboration",
            "source_ids": ["src_retail_001"],
            "evidence": [{
                "source_id": "src_retail_001",
                "original_url": "https://retail.example.test/march",
                "evidence_eligible": True,
                "evidence_text": "March index: 103.",
                "published_at": "2026-04-15",
            }],
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
