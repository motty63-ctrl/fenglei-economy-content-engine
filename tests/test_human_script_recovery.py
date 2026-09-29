from __future__ import annotations

import json
from pathlib import Path

import pytest

from fanglei.artifact_registry import ArtifactRegistry
from fanglei.content_models import ScriptDraft
from fanglei.errors import ArtifactConflictError
from fanglei.models import RunManifest


def _draft_payload() -> dict:
    return {
        "schema_version": "3.0",
        "script_id": "script_001",
        "angle_id": "angle_synthetic",
        "title": "Synthetic comparison",
        "target_duration_seconds": 75,
        "target_language": "zh-Hans",
        "sentences": [
            {"sentence_id": "hook", "section": "hook", "sentence_type": "interpretation",
             "text": "先看这份记录。", "claim_ids": []},
            {"sentence_id": "fact", "section": "phenomenon", "sentence_type": "verified_fact",
             "text": "数据署报告，8月零售调查的甲指标增加10单位。", "claim_ids": ["claim_alpha"]},
            {"sentence_id": "mechanism", "section": "mechanism", "sentence_type": "explanation",
             "text": "对象和月份要分别核对。", "claim_ids": []},
            {"sentence_id": "close", "section": "core_judgment", "sentence_type": "interpretation",
             "text": "这项记录仍应放在原有统计范围内理解。", "claim_ids": []},
        ],
    }


def test_human_script_edit_contract_is_strict_and_not_an_approval() -> None:
    from fanglei.human_script_recovery import HumanScriptEditV1, canonical_json_sha256
    from fanglei.content_models import ScriptDraft

    draft = ScriptDraft.model_validate(_draft_payload()).model_dump(mode="json")

    payload = {
        "schema_version": "human-script-edit/1.0",
        "status": "pending_human_review",
        "run_id": "synthetic-run-001",
        "case_id": "synthetic-retail-case",
        "angle_id": "angle_synthetic",
        "reviewer": "motty63-ctrl",
        "submitted_at": "2026-09-29T12:00:00+08:00",
        "rationale": "Human-edited candidate submitted for lint; not approved for narration.",
        "target_language": "zh-Hans",
        "facts_sha256": "a" * 64,
        "research_sha256": "b" * 64,
        "source_sha256": "c" * 64,
        "angles_sha256": "d" * 64,
        "angle_selection_sha256": "e" * 64,
        "terminology_sha256": "f" * 64,
        "failed_draft_sha256": None,
        "draft_sha256": canonical_json_sha256(draft),
        "draft": draft,
    }

    parsed = HumanScriptEditV1.model_validate(payload)
    assert parsed.status == "pending_human_review"
    assert parsed.draft.sentences[1].claim_ids == ["claim_alpha"]
    with pytest.raises(ValueError):
        HumanScriptEditV1.model_validate({**payload, "unexpected": True})
    with pytest.raises(ValueError):
        HumanScriptEditV1.model_validate({**payload, "submitted_at": "2026-09-29T12:00:00"})
    with pytest.raises(ValueError):
        HumanScriptEditV1.model_validate({**payload, "status": "approved"})


def test_human_script_recovery_graph_is_opt_in_and_hash_binds_inputs(tmp_path: Path) -> None:
    run = tmp_path / "synthetic-run-001"
    run.mkdir()
    manifest = RunManifest(run_id=run.name, created_at="2026-09-29T00:00:00+00:00",
                           updated_at="2026-09-29T00:00:00+00:00")
    legacy = ArtifactRegistry(run, manifest)
    assert "human_script_edit.json" not in legacy.graph

    recovery = ArtifactRegistry(run, manifest, research_focus_mode=True,
                                 human_angle_selection_mode=True, script_terminology_mode=True,
                                 human_script_recovery_mode=True)
    assert recovery.graph["human_script_edit.json"][0] == "human_script_recovery"
    assert set(recovery.graph["human_script_edit.json"][1]) >= {
        "facts.json", "research.md", "source.md", "angles.json", "angle_selection.json",
        "script_terminology.json",
    }
    assert "human_script_edit.json" in recovery.graph["script.json"][1]


def test_failed_generation_audit_hash_extracts_initial_draft_deterministically() -> None:
    from fanglei.human_script_recovery import failed_draft_sha256_from_manifest

    initial = _draft_payload()
    message = "SCRIPT_REPAIR_EXHAUSTED:" + json.dumps(
        {"initial_script": initial}, ensure_ascii=False, separators=(",", ":")
    )
    manifest = {"stages": {"script_generation": {"error": {"message": message}}}}
    first = failed_draft_sha256_from_manifest(manifest)
    assert first is not None and len(first) == 64
    assert failed_draft_sha256_from_manifest(manifest) == first
    assert failed_draft_sha256_from_manifest({"stages": {}}) is None


def _prepare_recovery_run(tmp_path: Path):
    from fanglei.angle_selection import HumanAngleSelectionV1
    from fanglei.content_render import render_angle_markdown
    from fanglei.research_focus import ResearchFocusV1
    from fanglei.script_terminology import ScriptTerminologyMapV1
    from tests.test_script_terminology import _angle, _approved_map, _draft, _facts

    run_id = "2026-09-29-001-synthetic-retail-run"
    case_id = "synthetic-retail-case"
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    manifest = RunManifest(run_id=run_id, created_at="2026-09-29T00:00:00+00:00",
                           updated_at="2026-09-29T00:00:00+00:00")
    registry = ArtifactRegistry(
        run_dir, manifest, research_focus_mode=True, human_angle_selection_mode=True,
        script_terminology_mode=True, human_script_recovery_mode=True,
    )
    registry.write_text("source.md", "Synthetic source prompt", "ingest")
    registry.write_json("questions.json", {"core_topic": "retail sales", "research_questions": []}, "analyze")
    registry.write_json("search_results.json", {"results": []}, "search")
    registry.write_json("source_documents/index.json", {"documents": []}, "source_fetch")
    registry.write_json("sources.json", {"schema_version": "2.0", "selection_status": "selected",
                                         "sources": []}, "source_selection")
    facts = _facts()
    facts["run_id"] = run_id
    registry.write_json("facts.json", facts, "factcheck")
    focus = ResearchFocusV1(
        schema_version="research-focus/1.0", run_id=run_id, case_id=case_id,
        primary_question="What changed in the synthetic retail measure?",
        subquestions=["What was reported?"], constraints=["Use only the verified claim."],
        created_at="2026-09-29T00:00:00+00:00", created_by="test",
    )
    registry.write_json("research_focus.json", focus.model_dump(mode="json"), "research_focus")
    registry.write_text("research.md", "Data Office reports the verified retail measure.", "research_synthesis")
    angle = _angle(["claim_alpha"])
    angles = {"schema_version": "3.0", "run_id": run_id, "candidates": [angle.model_dump(mode="json")]}
    registry.write_json("angles.json", angles, "angle_generation")
    selection = HumanAngleSelectionV1(
        schema_version="human-angle-selection/1.0", run_id=run_id,
        selected_angle_id=angle.angle_id, source="human", selected_at="2026-09-29T00:00:00+00:00",
        angles_sha256=manifest.artifacts["angles.json"].content_hash,
        facts_sha256=manifest.artifacts["facts.json"].content_hash,
        reviewer="test-reviewer", rationale="test selection",
    )
    registry.write_json("angle_selection.json", selection.model_dump(mode="json"), "human_angle_selection")
    registry.write_text("angle.md", render_angle_markdown(angle), "angle_selection")
    terms = _approved_map()
    terms.update(run_id=run_id, case_id=case_id, facts_sha256=manifest.artifacts["facts.json"].content_hash)
    registry.write_json("script_terminology.json", terms, "script_terminology_review")
    registry.save_manifest()
    draft = _draft("数据署报告，8月零售调查的甲指标增加10单位。")
    draft = draft.model_copy(update={"target_language": "zh-Hans"})
    return run_dir, run_id, draft


def test_human_script_recovery_rejects_before_writes_and_success_uses_registered_owners(tmp_path: Path) -> None:
    from fanglei.content_pipeline import submit_human_script_recovery

    run_dir, run_id, draft = _prepare_recovery_run(tmp_path)
    paths_before = {path.relative_to(run_dir).as_posix(): path.read_bytes()
                    for path in run_dir.rglob("*") if path.is_file()}
    invalid = draft.model_copy(update={"angle_id": "angle_other"})
    with pytest.raises(ArtifactConflictError, match="SCRIPT_ANGLE_ID_MISMATCH"):
        submit_human_script_recovery(
            run_id, tmp_path, invalid, reviewer="motty63-ctrl",
            rationale="Manual candidate submitted for lint only.",
        )
    paths_after = {path.relative_to(run_dir).as_posix(): path.read_bytes()
                   for path in run_dir.rglob("*") if path.is_file()}
    assert paths_after == paths_before

    bad_sentences = list(draft.sentences)
    bad_sentences[1] = bad_sentences[1].model_copy(
        update={"text": "数据署报告，8月零售调查的甲指标增加99单位。"}
    )
    rejected_lint = draft.model_copy(update={"sentences": bad_sentences})
    with pytest.raises(ArtifactConflictError, match="SCRIPT_HUMAN_DRAFT_REJECTED"):
        submit_human_script_recovery(
            run_id, tmp_path, rejected_lint, reviewer="motty63-ctrl",
            rationale="Manual candidate submitted for lint only.",
        )
    paths_after_lint_rejection = {path.relative_to(run_dir).as_posix(): path.read_bytes()
                                  for path in run_dir.rglob("*") if path.is_file()}
    assert paths_after_lint_rejection == paths_before

    edit_path = submit_human_script_recovery(
        run_id, tmp_path, draft, reviewer="motty63-ctrl",
        rationale="Manual candidate submitted for lint only; this is not approval for narration.",
    )
    assert edit_path.name == "human_script_edit.json"
    manifest = RunManifest.model_validate(json.loads((run_dir / "run.json").read_text(encoding="utf-8")))
    assert manifest.artifacts["human_script_edit.json"].status == "valid"
    assert manifest.artifacts["script.json"].status == "valid"
    assert manifest.artifacts["script.md"].status == "valid"
    script = json.loads((run_dir / "script.json").read_text(encoding="utf-8"))
    edit = json.loads(edit_path.read_text(encoding="utf-8"))
    assert script["authoring_method"] == "human_edit"
    assert script["human_script_edit_sha256"] == manifest.artifacts["human_script_edit.json"].content_hash
    assert edit["status"] == "pending_human_review"
    assert "approved" not in edit["status"]
    assert [(row["sentence_id"], row["text"], row["claim_ids"]) for row in script["sentences"]] == [
        (row.sentence_id, row.text, row.claim_ids) for row in draft.sentences
    ]
    registry = ArtifactRegistry(
        run_dir, manifest, research_focus_mode=True, human_angle_selection_mode=True,
        script_terminology_mode=True, human_script_recovery_mode=True,
    )
    for artifact in ("human_script_edit.json", "script.json", "script.md"):
        registry.validate(artifact)
