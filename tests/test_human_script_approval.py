from __future__ import annotations

import json
from datetime import datetime

import pytest

from fanglei.artifact_registry import ArtifactRegistry
from fanglei.errors import ArtifactConflictError
from fanglei.models import RunManifest
from tests.test_human_script_recovery import _prepare_recovery_run


def test_script_approval_gate_is_opt_in_for_existing_runs(tmp_path) -> None:
    run_dir, _ = _approved_run(tmp_path)
    manifest = RunManifest.model_validate(json.loads((run_dir / "run.json").read_text(encoding="utf-8")))
    registry = ArtifactRegistry(
        run_dir, manifest, research_focus_mode=True, human_angle_selection_mode=True,
        evidence_targets_mode=True, script_terminology_mode=True,
        human_script_recovery_mode=True,
    )
    assert "human_script_approval.json" not in registry.graph
    assert registry.graph["narration.json"][1] == ("script.json",)


def _approved_run(tmp_path):
    from fanglei.content_pipeline import submit_human_script_recovery

    run_dir, run_id, draft = _prepare_recovery_run(tmp_path)
    submit_human_script_recovery(
        run_id, tmp_path, draft, reviewer="motty63-ctrl",
        rationale="Submitted for the approval-gate test; no provider call.",
    )
    return run_dir, run_id


def test_script_approval_contract_is_strict_hash_bound_and_timezone_aware() -> None:
    from fanglei.human_script_approval import HumanScriptApprovalV1

    payload = {
        "schema_version": "human-script-approval/1.0",
        "status": "approved_for_tts",
        "run_id": "synthetic-run-001",
        "case_id": "synthetic-retail-case",
        "angle_id": "angle_synthetic",
        "facts_sha256": "a" * 64,
        "angles_sha256": "b" * 64,
        "angle_selection_sha256": "c" * 64,
        "terminology_sha256": "d" * 64,
        "human_script_edit_sha256": "e" * 64,
        "script_sha256": "f" * 64,
        "target_language": "zh-Hans",
        "reviewer": "motty63-ctrl",
        "approved_at": "2026-09-29T12:00:00+08:00",
        "rationale": "Approved for the bound TTS run only.",
    }
    approval = HumanScriptApprovalV1.model_validate(payload)
    assert approval.status == "approved_for_tts"
    for invalid in (
        {**payload, "unexpected": True},
        {**payload, "status": "approved"},
        {**payload, "script_sha256": "E" * 64},
        {**payload, "approved_at": "2026-09-29T12:00:00"},
        {**payload, "reviewer": "  "},
    ):
        with pytest.raises(ValueError):
            HumanScriptApprovalV1.model_validate(invalid)


def test_script_approval_owner_binds_current_script_and_all_required_dependencies(tmp_path) -> None:
    from fanglei.content_pipeline import approve_human_script_for_tts

    run_dir, run_id = _approved_run(tmp_path)
    path = approve_human_script_for_tts(
        run_id, tmp_path, reviewer="motty63-ctrl",
        rationale="人工审阅当前脚本后批准进入 TTS；事实、术语和 Script lint 已通过，65 秒处于 60–90 秒硬有效范围。后续仍需人工审核实际音频，不代表批准 Storyboard 或视频制作。",
    )

    manifest = RunManifest.model_validate(json.loads((run_dir / "run.json").read_text(encoding="utf-8")))
    approval = json.loads(path.read_text(encoding="utf-8"))
    assert path.name == "human_script_approval.json"
    assert approval["status"] == "approved_for_tts"
    assert approval["reviewer"] == "motty63-ctrl"
    assert approval["run_id"] == run_id
    assert approval["case_id"] == "synthetic-retail-case"
    assert approval["angle_id"] == "angle_synthetic"
    assert approval["script_sha256"] == manifest.artifacts["script.json"].content_hash
    assert approval["angles_sha256"] == manifest.artifacts["angles.json"].content_hash
    assert approval["human_script_edit_sha256"] == manifest.artifacts["human_script_edit.json"].content_hash
    assert approval["facts_sha256"] == manifest.artifacts["facts.json"].content_hash
    assert approval["angle_selection_sha256"] == manifest.artifacts["angle_selection.json"].content_hash
    assert approval["terminology_sha256"] == manifest.artifacts["script_terminology.json"].content_hash
    assert datetime.fromisoformat(approval["approved_at"]).utcoffset() is not None
    assert manifest.artifacts["human_script_approval.json"].status == "valid"
    assert "human_script_approval.json" in manifest.artifacts["narration.json"].dependencies


def test_selected_angle_change_stales_script_approval(tmp_path) -> None:
    from fanglei.content_pipeline import approve_human_script_for_tts

    run_dir, run_id = _approved_run(tmp_path)
    approve_human_script_for_tts(
        run_id, tmp_path, reviewer="motty63-ctrl", rationale="Approved for stale-angle test.",
    )
    manifest = RunManifest.model_validate(json.loads((run_dir / "run.json").read_text(encoding="utf-8")))
    registry = ArtifactRegistry(
        run_dir, manifest, research_focus_mode=True, human_angle_selection_mode=True,
        evidence_targets_mode=True, script_terminology_mode=True,
        human_script_recovery_mode=True, human_script_approval_mode=True,
    )
    angles = registry.read_json("angles.json")
    angles["candidates"][0]["title"] = "Changed selected angle"
    registry.write_json("angles.json", angles, "angle_generation", force=True)
    assert manifest.artifacts["human_script_approval.json"].status == "stale"


def test_script_change_stales_approval_and_blocks_narration_owner(tmp_path) -> None:
    from fanglei.content_pipeline import approve_human_script_for_tts

    run_dir, run_id = _approved_run(tmp_path)
    approve_human_script_for_tts(
        run_id, tmp_path, reviewer="motty63-ctrl", rationale="Approved for stale-binding test.",
    )
    manifest = RunManifest.model_validate(json.loads((run_dir / "run.json").read_text(encoding="utf-8")))
    registry = ArtifactRegistry(
        run_dir, manifest, research_focus_mode=True, human_angle_selection_mode=True,
        evidence_targets_mode=True, script_terminology_mode=True,
        human_script_recovery_mode=True, human_script_approval_mode=True,
    )
    script = registry.read_json("script.json")
    script["title"] = "Changed after approval"
    registry.write_json("script.json", script, "script_generation", force=True)
    assert manifest.artifacts["human_script_approval.json"].status == "stale"
    with pytest.raises(ArtifactConflictError, match="human_script_approval.json is stale"):
        registry.write_json("narration.json", {"run_id": run_id}, "narration_generation")
    assert not (run_dir / "narration.json").exists()


def test_narration_owner_requires_script_approval_for_opted_in_run(tmp_path) -> None:
    run_dir, run_id = _approved_run(tmp_path)
    manifest = RunManifest.model_validate(json.loads((run_dir / "run.json").read_text(encoding="utf-8")))
    registry = ArtifactRegistry(
        run_dir, manifest, research_focus_mode=True, human_angle_selection_mode=True,
        evidence_targets_mode=True, script_terminology_mode=True,
        human_script_recovery_mode=True, human_script_approval_mode=True,
    )
    with pytest.raises(ArtifactConflictError, match="Dependency human_script_approval.json is missing"):
        registry.write_json("narration.json", {"run_id": run_id}, "narration_generation")
    assert not (run_dir / "narration.json").exists()
