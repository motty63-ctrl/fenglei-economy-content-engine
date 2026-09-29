"""Artifact-first V0.4 semantic and render visual planning pipeline."""
from __future__ import annotations

from pathlib import Path
from datetime import datetime
import re
import wave

from fanglei.artifact_registry import ArtifactRegistry
from fanglei.artifacts import read_json, sha256_bytes
from fanglei.angle_selection import HumanAngleSelectionV1
from fanglei.errors import ArtifactConflictError
from fanglei.evidence_policy import is_claim_eligible_for_content
from fanglei.human_script_approval import HumanScriptApprovalV1
from fanglei.human_storyboard_approval import HumanStoryboardApprovalV1
from fanglei.human_storyboard_recovery import (
    HumanStoryboardEditV1,
    HumanStoryboardReviewV1,
    canonical_json_sha256,
    validate_human_storyboard_candidate,
)
from fanglei.human_visual_asset_recovery import (
    HumanVisualAssetReviewV1,
    VisualAssetRecoveryPlanV1,
    validate_visual_asset_recovery_plan,
)
from fanglei.models import RunManifest
from fanglei.paths import resolve_run_dir
from fanglei.pipeline import _execute, _load
from fanglei.providers.visual import VisualPlanningProvider, VisualPlanningRequest
from fanglei.research_focus import ResearchFocusV1
from fanglei.storyboard import build_storyboard
from fanglei.storyboard_quality import lint_storyboard
from fanglei.v05_models import VoiceReviewDocument
from fanglei.visual_models import Storyboard, VisualBeatPlan
from fanglei.visual_render import render_visual_plan
from fanglei.visual_assets import build_visual_asset_bundle
from fanglei.visual_timing import apply_alignment_derived_timing, build_timing_aware_context, validate_timed_scene_coverage


VISUAL_STAGES = {
    "visual_planning", "storyboard_generation", "visual_plan_render",
    "human_storyboard_review", "human_storyboard_recovery", "human_storyboard_approval",
    "visual_asset_generation", "human_visual_asset_review", "visual_asset_recovery",
}


def _now() -> str:
    """Return an ISO-8601 timestamp with the machine's current timezone."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _validate_storyboard_run_identity(
    artifact_name: str, payload: dict, run_id: str, *, allow_missing: bool = False,
) -> None:
    artifact_run_id = payload.get("run_id")
    if artifact_run_id is None and allow_missing:
        return
    if artifact_run_id != run_id:
        raise ArtifactConflictError(f"STORYBOARD_RECOVERY_RUN_ID_MISMATCH:{artifact_name}")


def _load_storyboard_approval_registry(
    run_id: str,
    runs_dir: Path,
    *,
    visual_asset_recovery_mode: bool = False,
):
    run_dir = resolve_run_dir(Path(runs_dir), run_id)
    manifest = RunManifest.model_validate(read_json(run_dir / "run.json"))
    if manifest.run_id != run_id:
        raise ArtifactConflictError("STORYBOARD_APPROVAL_RUN_ID_MISMATCH")
    registry = ArtifactRegistry(
        run_dir, manifest, research_focus_mode=True, human_angle_selection_mode=True,
        script_terminology_mode=True, human_script_recovery_mode=True,
        human_script_approval_mode=True, timing_aware_storyboard_mode=True,
        human_storyboard_recovery_mode=True, human_storyboard_approval_mode=True,
        human_visual_asset_recovery_mode=visual_asset_recovery_mode,
    )
    if registry.imported_checkpoint_mode:
        raise ArtifactConflictError("STORYBOARD_APPROVAL_NOT_SUPPORTED_FOR_IMPORTED_CHECKPOINT")
    return run_dir, manifest, registry


def approve_human_storyboard_candidate(
    run_id: str,
    runs_dir: Path,
    *,
    expected_candidate_sha256: str,
    reviewer: str,
    rationale: str,
) -> Path:
    """Record explicit, write-once human approval for the current recovered Storyboard."""
    from datetime import datetime

    from fanglei.human_storyboard_recovery import canonical_json_sha256

    run_dir, manifest, registry = _load_storyboard_approval_registry(run_id, runs_dir)
    output_path = run_dir / "human_storyboard_approval.json"
    output_state = manifest.artifacts["human_storyboard_approval.json"]
    if output_path.exists() or output_state.status != "missing":
        raise ArtifactConflictError("STORYBOARD_APPROVAL_ALREADY_EXISTS")
    if re.fullmatch(r"[0-9a-f]{64}", expected_candidate_sha256) is None:
        raise ArtifactConflictError("STORYBOARD_APPROVAL_EXPECTED_HASH_INVALID")
    if not reviewer.strip() or not rationale.strip():
        raise ArtifactConflictError("STORYBOARD_APPROVAL_HUMAN_REVIEW_FIELDS_REQUIRED")

    dependency_names = registry.graph["human_storyboard_approval.json"][1]
    try:
        for name in dependency_names:
            registry.validate(name)
    except Exception as error:
        raise ArtifactConflictError(f"STORYBOARD_APPROVAL_UPSTREAM_NOT_CURRENT:{error}") from error

    script = registry.read_json("script.json")
    facts = registry.read_json("facts.json")
    focus = ResearchFocusV1.model_validate(registry.read_json("research_focus.json"))
    selection = HumanAngleSelectionV1.model_validate(registry.read_json("angle_selection.json"))
    script_approval = HumanScriptApprovalV1.model_validate(
        registry.read_json("human_script_approval.json")
    )
    voice_review = VoiceReviewDocument.model_validate(registry.read_json("audio/review.json"))
    original = Storyboard.model_validate(registry.read_json("storyboard.json"))
    review = HumanStoryboardReviewV1.model_validate(registry.read_json("storyboard_review.json"))
    edit = HumanStoryboardEditV1.model_validate(registry.read_json("human_storyboard_edit.json"))
    candidate = Storyboard.model_validate(registry.read_json("human_storyboard_candidate.json"))

    candidate_path = run_dir / "human_storyboard_candidate.json"
    candidate_artifact_hash = sha256_bytes(candidate_path.read_bytes())
    if candidate_artifact_hash != manifest.artifacts["human_storyboard_candidate.json"].content_hash:
        raise ArtifactConflictError("STORYBOARD_APPROVAL_CANDIDATE_ARTIFACT_HASH_MISMATCH")
    candidate_digest = canonical_json_sha256(candidate)
    if candidate_digest != expected_candidate_sha256:
        raise ArtifactConflictError("STORYBOARD_APPROVAL_CANDIDATE_DIGEST_MISMATCH")
    if candidate_digest != edit.candidate_storyboard_sha256 or candidate != edit.candidate_storyboard:
        raise ArtifactConflictError("STORYBOARD_APPROVAL_EDIT_BINDING_MISMATCH")

    if focus.run_id != run_id or not focus.case_id.strip():
        raise ArtifactConflictError("STORYBOARD_APPROVAL_CASE_IDENTITY_INVALID")
    if facts.get("run_id") != run_id:
        raise ArtifactConflictError("STORYBOARD_APPROVAL_FACTS_RUN_ID_MISMATCH")
    if selection.run_id != run_id or selection.source != "human":
        raise ArtifactConflictError("STORYBOARD_APPROVAL_ANGLE_SELECTION_INVALID")
    if script.get("angle_id") != selection.selected_angle_id:
        raise ArtifactConflictError("STORYBOARD_APPROVAL_SELECTED_ANGLE_MISMATCH")

    current_hashes = {
        name: manifest.artifacts[name].content_hash or ""
        for name in dependency_names
    }
    required_hashes = {
        "storyboard.json": manifest.artifacts["storyboard.json"].content_hash,
        "script.json": manifest.artifacts["script.json"].content_hash,
        "facts.json": manifest.artifacts["facts.json"].content_hash,
        "angle_selection.json": manifest.artifacts["angle_selection.json"].content_hash,
        "audio/narration.wav": manifest.artifacts["audio/narration.wav"].content_hash,
        "audio/review.json": manifest.artifacts["audio/review.json"].content_hash,
        "alignment.json": manifest.artifacts["alignment.json"].content_hash,
        "subtitle_track.json": manifest.artifacts["subtitle_track.json"].content_hash,
    }
    if any(not digest for digest in current_hashes.values()) or any(
        current_hashes.get(name) != digest for name, digest in required_hashes.items()
    ):
        raise ArtifactConflictError("STORYBOARD_APPROVAL_DEPENDENCY_HASH_MISSING")
    candidate_hash = current_hashes["human_storyboard_candidate.json"]
    storyboard_hash = current_hashes["storyboard.json"]
    script_hash = current_hashes["script.json"]
    facts_hash = current_hashes["facts.json"]
    selection_hash = current_hashes["angle_selection.json"]
    voice_review_hash = current_hashes["audio/review.json"]
    audio_hash = current_hashes["audio/narration.wav"]
    alignment_hash = current_hashes["alignment.json"]
    subtitle_hash = current_hashes["subtitle_track.json"]

    if (
        original.run_id != run_id or candidate.run_id != run_id
        or original.script_id != script.get("script_id")
        or candidate.script_id != original.script_id
        or review.decision != "changes_required" or review.run_id != run_id
        or review.case_id != focus.case_id or review.original_storyboard_sha256 != storyboard_hash
        or edit.status != "pending_human_review" or edit.run_id != run_id
        or edit.case_id != focus.case_id or edit.review_sha256 != manifest.artifacts["storyboard_review.json"].content_hash
        or edit.original_storyboard_sha256 != storyboard_hash
        or edit.dependency_hashes != review.dependency_hashes
    ):
        raise ArtifactConflictError("STORYBOARD_APPROVAL_RECOVERY_CHAIN_INVALID")
    if (
        script_approval.status != "approved_for_tts" or script_approval.run_id != run_id
        or script_approval.case_id != focus.case_id
        or script_approval.angle_id != selection.selected_angle_id
        or script_approval.script_sha256 != script_hash
        or script_approval.angle_selection_sha256 != selection_hash
        or script_approval.target_language.casefold() != str(script.get("target_language", "")).casefold()
    ):
        raise ArtifactConflictError("STORYBOARD_APPROVAL_SCRIPT_APPROVAL_BINDING_INVALID")
    if (
        voice_review.status != "approved" or voice_review.run_id != run_id
        or voice_review.audio_sha256 != audio_hash
        or (voice_review.script_sha256 and voice_review.script_sha256 != script_hash)
    ):
        raise ArtifactConflictError("STORYBOARD_APPROVAL_AUDIO_REVIEW_BINDING_INVALID")
    if (
        selection.facts_sha256 != facts_hash
        or selection.angles_sha256 != manifest.artifacts["angles.json"].content_hash
    ):
        raise ArtifactConflictError("STORYBOARD_APPROVAL_SELECTION_STALE")
    timing = candidate.timing_provenance
    if (
        timing is None or timing.audio_sha256 != audio_hash
        or timing.voice_review_sha256 != voice_review_hash
        or timing.alignment_sha256 != alignment_hash or timing.subtitle_sha256 != subtitle_hash
    ):
        raise ArtifactConflictError("STORYBOARD_APPROVAL_TIMING_BINDING_INVALID")
    checked = validate_human_storyboard_candidate(original, candidate, script, facts)
    if checked != candidate or not candidate.quality_gate or not candidate.quality_gate.passed:
        raise ArtifactConflictError("STORYBOARD_APPROVAL_CANDIDATE_QUALITY_INVALID")

    eligible_claim_ids = sorted(
        str(claim["claim_id"])
        for claim in facts.get("claims", [])
        if isinstance(claim, dict) and isinstance(claim.get("claim_id"), str)
        and is_claim_eligible_for_content(claim)
    )
    candidate_claim_ids = {
        claim_id for scene in candidate.scenes for obj in scene.objects for claim_id in obj.claim_ids
    }
    if not candidate_claim_ids.issubset(set(eligible_claim_ids)):
        raise ArtifactConflictError("STORYBOARD_APPROVAL_INELIGIBLE_CLAIM_REFERENCE")

    approval = HumanStoryboardApprovalV1(
        schema_version="human-storyboard-approval/1.0",
        decision="approved_for_visual_generation",
        run_id=run_id,
        case_id=focus.case_id,
        reviewer=reviewer,
        approved_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        rationale=rationale,
        original_storyboard_sha256=storyboard_hash or "",
        candidate_storyboard_sha256=candidate_digest,
        candidate_artifact_sha256=candidate_artifact_hash,
        script_sha256=script_hash or "",
        facts_sha256=facts_hash or "",
        angle_selection_sha256=selection_hash or "",
        selected_angle_id=selection.selected_angle_id,
        eligible_claim_ids=eligible_claim_ids,
        audio_sha256=audio_hash or "",
        voice_review_sha256=voice_review_hash or "",
        alignment_sha256=alignment_hash or "",
        subtitle_sha256=subtitle_hash or "",
        dependency_hashes=current_hashes,
    )
    payload = approval.model_dump(mode="json")

    def write_approval() -> None:
        registry.write_json("human_storyboard_approval.json", payload, "human_storyboard_approval")

    _execute(manifest, registry, "human_storyboard_approval", write_approval)
    registry.validate("human_storyboard_approval.json")
    return output_path


def generate_storyboard_visual_assets(run_id: str, runs_dir: Path) -> Path:
    """Generate deterministic scene SVGs only after the bound human approval exists."""
    run_dir, manifest, registry = _load_storyboard_approval_registry(run_id, runs_dir)
    try:
        registry.validate("human_storyboard_approval.json")
        approval = HumanStoryboardApprovalV1.model_validate(
            registry.read_json("human_storyboard_approval.json")
        )
        candidate = Storyboard.model_validate(registry.read_json("human_storyboard_candidate.json"))
        facts = registry.read_json("facts.json")
    except Exception as error:
        raise ArtifactConflictError(f"VISUAL_ASSET_APPROVAL_OR_INPUT_INVALID:{error}") from error

    current_dependencies = {
        name: manifest.artifacts[name].content_hash or ""
        for name in registry.graph["human_storyboard_approval.json"][1]
    }
    if approval.dependency_hashes != current_dependencies:
        raise ArtifactConflictError("VISUAL_ASSET_APPROVAL_DEPENDENCY_MISMATCH")
    if (
        approval.run_id != run_id or candidate.run_id != run_id
        or canonical_json_sha256(candidate) != approval.candidate_storyboard_sha256
        or sha256_bytes((run_dir / "human_storyboard_candidate.json").read_bytes())
        != approval.candidate_artifact_sha256
    ):
        raise ArtifactConflictError("VISUAL_ASSET_CANDIDATE_BINDING_INVALID")
    current_eligible = sorted(
        str(claim["claim_id"])
        for claim in facts.get("claims", [])
        if isinstance(claim, dict) and isinstance(claim.get("claim_id"), str)
        and is_claim_eligible_for_content(claim)
    )
    if current_eligible != approval.eligible_claim_ids:
        raise ArtifactConflictError("VISUAL_ASSET_ELIGIBLE_CLAIMS_CHANGED")

    approval_hash = manifest.artifacts["human_storyboard_approval.json"].content_hash or ""
    files = build_visual_asset_bundle(
        candidate, approval, approval_artifact_sha256=approval_hash,
    )
    target = run_dir / "visual_assets"
    asset_state = manifest.artifacts["visual_assets"]
    if target.exists() or asset_state.status != "missing":
        if asset_state.status == "valid":
            try:
                registry.validate("visual_assets")
                return target
            except Exception as error:
                raise ArtifactConflictError(f"VISUAL_ASSET_EXISTING_BUNDLE_INVALID:{error}") from error
        raise ArtifactConflictError("VISUAL_ASSET_EXISTING_BUNDLE_NOT_REUSABLE")

    def write_assets() -> None:
        registry.write_directory("visual_assets", files, "visual_asset_generation")

    _execute(manifest, registry, "visual_asset_generation", write_assets)
    registry.validate("visual_assets")
    return target


def record_human_visual_asset_review(
    run_id: str,
    runs_dir: Path,
    *,
    expected_storyboard_sha256: str,
    expected_visual_bundle_sha256: str,
    reviewer: str,
    decision: str,
    reason_code: str,
    rationale: str,
    findings: list[str],
) -> Path:
    """Record the first human visual decision without replacing its reviewed bundle."""
    if decision != "changes_required":
        raise ArtifactConflictError("VISUAL_ASSET_REVIEW_DECISION_NOT_SUPPORTED_IN_RECOVERY")
    run_dir, manifest, registry = _load_storyboard_approval_registry(
        run_id, runs_dir, visual_asset_recovery_mode=True,
    )
    if registry.imported_checkpoint_mode:
        raise ArtifactConflictError("VISUAL_ASSET_REVIEW_NOT_SUPPORTED_FOR_IMPORTED_CHECKPOINT")
    output_name = "human_visual_asset_review_candidate_1.json"
    output_path = run_dir / output_name
    output_state = manifest.artifacts[output_name]
    if output_path.exists() or output_state.status != "missing":
        raise ArtifactConflictError("VISUAL_ASSET_CANDIDATE_1_REVIEW_ALREADY_EXISTS")

    dependency_names = registry.graph[output_name][1]
    try:
        for name in dependency_names:
            registry.validate(name)
    except Exception as error:
        raise ArtifactConflictError(f"VISUAL_ASSET_REVIEW_UPSTREAM_NOT_CURRENT:{error}") from error
    candidate = Storyboard.model_validate(registry.read_json("human_storyboard_candidate.json"))
    approval = HumanStoryboardApprovalV1.model_validate(
        registry.read_json("human_storyboard_approval.json")
    )
    candidate_path = run_dir / "human_storyboard_candidate.json"
    candidate_artifact_hash = sha256_bytes(candidate_path.read_bytes())
    visual_bundle_hash = manifest.artifacts["visual_assets"].content_hash or ""
    if (
        candidate.run_id != run_id
        or not approval.case_id.strip()
        or candidate_artifact_hash != approval.candidate_artifact_sha256
        or canonical_json_sha256(candidate) != approval.candidate_storyboard_sha256
        or expected_storyboard_sha256 != canonical_json_sha256(candidate)
        or expected_visual_bundle_sha256 != visual_bundle_hash
        or approval.run_id != run_id
    ):
        raise ArtifactConflictError("VISUAL_ASSET_REVIEW_EXPECTED_HASH_MISMATCH")
    dependency_hashes = {
        name: manifest.artifacts[name].content_hash or ""
        for name in dependency_names
    }
    review = HumanVisualAssetReviewV1.model_validate({
        "schema_version": "human-visual-asset-review/1.0",
        "candidate_id": 1,
        "decision": "changes_required",
        "run_id": run_id,
        "case_id": approval.case_id,
        "reviewer": reviewer,
        "reviewed_at": _now(),
        "reason_code": reason_code,
        "rationale": rationale,
        "findings": findings,
        "storyboard_sha256": canonical_json_sha256(candidate),
        "storyboard_artifact_sha256": candidate_artifact_hash,
        "storyboard_approval_sha256": manifest.artifacts["human_storyboard_approval.json"].content_hash,
        "visual_bundle_sha256": visual_bundle_hash,
        "dependency_hashes": dependency_hashes,
    })

    def write_review() -> None:
        registry.write_json(output_name, review.model_dump(mode="json"), "human_visual_asset_review")

    _execute(manifest, registry, "human_visual_asset_review", write_review)
    registry.validate(output_name)
    return output_path


def recover_visual_asset_candidate(
    run_id: str,
    runs_dir: Path,
    plan: VisualAssetRecoveryPlanV1,
) -> Path:
    """Write a new, pending-review visual candidate using presentation-only edits."""
    run_dir, manifest, registry = _load_storyboard_approval_registry(
        run_id, runs_dir, visual_asset_recovery_mode=True,
    )
    if registry.imported_checkpoint_mode:
        raise ArtifactConflictError("VISUAL_ASSET_RECOVERY_NOT_SUPPORTED_FOR_IMPORTED_CHECKPOINT")
    plan_path = run_dir / "visual_asset_recovery.json"
    target = run_dir / "visual_assets_candidate_2"
    if (
        plan_path.exists() or target.exists()
        or manifest.artifacts["visual_asset_recovery.json"].status != "missing"
        or manifest.artifacts["visual_assets_candidate_2"].status != "missing"
    ):
        raise ArtifactConflictError("VISUAL_ASSET_CANDIDATE_2_ALREADY_EXISTS")

    dependency_names = registry.graph["visual_asset_recovery.json"][1]
    try:
        for name in dependency_names:
            registry.validate(name)
        registry.validate("sources.json")
    except Exception as error:
        raise ArtifactConflictError(f"VISUAL_ASSET_RECOVERY_UPSTREAM_NOT_CURRENT:{error}") from error
    candidate = Storyboard.model_validate(registry.read_json("human_storyboard_candidate.json"))
    approval = HumanStoryboardApprovalV1.model_validate(
        registry.read_json("human_storyboard_approval.json")
    )
    review = HumanVisualAssetReviewV1.model_validate(
        registry.read_json("human_visual_asset_review_candidate_1.json")
    )
    candidate_file_hash = sha256_bytes((run_dir / "human_storyboard_candidate.json").read_bytes())
    if candidate_file_hash != approval.candidate_artifact_sha256:
        raise ArtifactConflictError("VISUAL_ASSET_RECOVERY_CANDIDATE_FILE_HASH_MISMATCH")
    if (
        canonical_json_sha256(candidate) != approval.candidate_storyboard_sha256
        or candidate.run_id != run_id
        or review.storyboard_approval_sha256 != manifest.artifacts["human_storyboard_approval.json"].content_hash
    ):
        raise ArtifactConflictError("VISUAL_ASSET_RECOVERY_APPROVAL_BINDING_INVALID")
    current_dependencies = {
        name: manifest.artifacts[name].content_hash or ""
        for name in dependency_names
    }
    sources = registry.read_json("sources.json")
    approved_source_ids = {
        row["source_id"] for row in sources.get("sources", [])
        if isinstance(row, dict) and isinstance(row.get("source_id"), str)
    }
    validate_visual_asset_recovery_plan(
        candidate,
        review,
        plan,
        current_visual_bundle_sha256=manifest.artifacts["visual_assets"].content_hash or "",
        current_dependency_hashes=current_dependencies,
        approved_source_ids=approved_source_ids,
    )
    if plan.storyboard_artifact_sha256 != candidate_file_hash:
        raise ArtifactConflictError("VISUAL_ASSET_RECOVERY_CANDIDATE_ARTIFACT_HASH_MISMATCH")
    files = build_visual_asset_bundle(
        candidate,
        approval,
        approval_artifact_sha256=manifest.artifacts["human_storyboard_approval.json"].content_hash or "",
        recovery_plan=plan,
    )

    def write_recovery() -> None:
        registry.write_json(
            "visual_asset_recovery.json", plan.model_dump(mode="json"), "visual_asset_recovery",
        )
        registry.write_directory(
            "visual_assets_candidate_2", files, "visual_asset_recovery",
        )

    _execute(manifest, registry, "visual_asset_recovery", write_recovery)
    registry.validate("visual_assets")
    registry.validate("visual_asset_recovery.json")
    registry.validate("visual_assets_candidate_2")
    return target


def submit_human_storyboard_recovery(
    run_id: str,
    runs_dir: Path,
    candidate: Storyboard,
    *,
    reviewer: str,
    rationale: str,
    reason_code: str,
    decision: str = "changes_required",
) -> Path:
    """Register a visual-only Storyboard recovery without invoking a planner."""
    from fanglei.human_script_approval import HumanScriptApprovalV1
    from fanglei.human_storyboard_recovery import (
        HumanStoryboardEditV1,
        HumanStoryboardReviewV1,
        canonical_json_sha256,
        validate_human_storyboard_candidate,
    )
    from fanglei.research_focus import ResearchFocusV1
    from fanglei.v05_models import VoiceReviewDocument

    if decision != "changes_required":
        raise ArtifactConflictError("STORYBOARD_RECOVERY_REQUIRES_CHANGES_REQUIRED_REVIEW")
    run_dir = resolve_run_dir(Path(runs_dir), run_id)
    manifest = RunManifest.model_validate(read_json(run_dir / "run.json"))
    if manifest.run_id != run_id:
        raise ArtifactConflictError("STORYBOARD_RECOVERY_RUN_ID_MISMATCH")
    registry = ArtifactRegistry(
        run_dir, manifest, research_focus_mode=True, human_angle_selection_mode=True,
        script_terminology_mode=True, human_script_recovery_mode=True,
        human_script_approval_mode=True, timing_aware_storyboard_mode=True,
        human_storyboard_recovery_mode=True,
    )
    if registry.imported_checkpoint_mode:
        raise ArtifactConflictError("STORYBOARD_RECOVERY_NOT_SUPPORTED_FOR_IMPORTED_CHECKPOINT")

    required_outputs = ("storyboard_review.json", "human_storyboard_edit.json", "human_storyboard_candidate.json")
    for name in required_outputs:
        state = manifest.artifacts[name]
        if (run_dir / name).exists() or state.status != "missing":
            raise ArtifactConflictError(f"STORYBOARD_RECOVERY_OUTPUT_ALREADY_EXISTS:{name}")

    original_dependencies = tuple(registry.graph["storyboard.json"][1])
    required_current = tuple(dict.fromkeys(("storyboard.json", *original_dependencies)))
    try:
        for name in required_current:
            registry.validate(name)
    except Exception as error:
        raise ArtifactConflictError(f"STORYBOARD_RECOVERY_UPSTREAM_NOT_CURRENT:{error}") from error

    script = registry.read_json("script.json")
    facts = registry.read_json("facts.json")
    focus = ResearchFocusV1.model_validate(registry.read_json("research_focus.json"))
    selection = HumanAngleSelectionV1.model_validate(registry.read_json("angle_selection.json"))
    approval = HumanScriptApprovalV1.model_validate(registry.read_json("human_script_approval.json"))
    voice_review = VoiceReviewDocument.model_validate(registry.read_json("audio/review.json"))
    original = Storyboard.model_validate(registry.read_json("storyboard.json"))
    candidate = candidate if isinstance(candidate, Storyboard) else Storyboard.model_validate(candidate)

    if focus.run_id != run_id or not focus.case_id.strip():
        raise ArtifactConflictError("STORYBOARD_RECOVERY_CASE_IDENTITY_INVALID")
    # Script 3.0 has no inline run_id field; its registry dependency chain and
    # hash-bound human approval provide run provenance. Facts 2.2 is run-bound.
    _validate_storyboard_run_identity("script.json", script, run_id, allow_missing=True)
    _validate_storyboard_run_identity("facts.json", facts, run_id)
    if script.get("angle_id") != selection.selected_angle_id:
        raise ArtifactConflictError("STORYBOARD_RECOVERY_CONTENT_IDENTITY_INVALID")
    if selection.run_id != run_id:
        raise ArtifactConflictError("STORYBOARD_RECOVERY_SELECTION_IDENTITY_INVALID")
    if (
        selection.angles_sha256 != manifest.artifacts["angles.json"].content_hash
        or selection.facts_sha256 != manifest.artifacts["facts.json"].content_hash
    ):
        raise ArtifactConflictError("STORYBOARD_RECOVERY_SELECTION_STALE")

    dependency_hashes = {
        name: manifest.artifacts[name].content_hash or ""
        for name in required_current
    }
    script_hash = dependency_hashes["script.json"]
    storyboard_hash = dependency_hashes["storyboard.json"]
    audio_hash = dependency_hashes["audio/narration.wav"]
    voice_review_hash = dependency_hashes["audio/review.json"]
    alignment_hash = dependency_hashes["alignment.json"]
    subtitle_hash = dependency_hashes["subtitle_track.json"]
    selection_hash = dependency_hashes["angle_selection.json"]
    target_language = script.get("target_language")
    if not isinstance(target_language, str) or not target_language.strip():
        raise ArtifactConflictError("STORYBOARD_RECOVERY_TARGET_LANGUAGE_MISSING")
    if (
        approval.run_id != run_id or approval.case_id != focus.case_id
        or approval.angle_id != selection.selected_angle_id
        or approval.script_sha256 != script_hash
        or approval.angle_selection_sha256 != selection_hash
        or approval.target_language.casefold() != target_language.casefold()
    ):
        raise ArtifactConflictError("STORYBOARD_RECOVERY_SCRIPT_APPROVAL_BINDING_INVALID")
    if (
        voice_review.status != "approved" or voice_review.run_id != run_id
        or voice_review.audio_sha256 != audio_hash
        or (voice_review.script_sha256 and voice_review.script_sha256 != script_hash)
    ):
        raise ArtifactConflictError("STORYBOARD_RECOVERY_AUDIO_REVIEW_BINDING_INVALID")
    if (
        original.run_id != run_id or original.script_id != script.get("script_id")
        or original.timing_provenance is None
        or original.timing_provenance.audio_sha256 != audio_hash
        or original.timing_provenance.voice_review_sha256 != voice_review_hash
        or original.timing_provenance.alignment_sha256 != alignment_hash
        or original.timing_provenance.subtitle_sha256 != subtitle_hash
    ):
        raise ArtifactConflictError("STORYBOARD_RECOVERY_ORIGINAL_BINDING_INVALID")
    if not original.quality_gate or not original.quality_gate.passed:
        raise ArtifactConflictError("STORYBOARD_RECOVERY_ORIGINAL_QUALITY_GATE_FAILED")

    checked_candidate = validate_human_storyboard_candidate(original, candidate, script, facts)
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    review = HumanStoryboardReviewV1(
        schema_version="human-storyboard-review/1.0",
        decision="changes_required",
        run_id=run_id,
        case_id=focus.case_id,
        reviewer=reviewer,
        reviewed_at=timestamp,
        reason_code=reason_code,
        rationale=rationale,
        original_storyboard_sha256=storyboard_hash,
        script_sha256=script_hash,
        audio_sha256=audio_hash,
        voice_review_sha256=voice_review_hash,
        alignment_sha256=alignment_hash,
        subtitle_sha256=subtitle_hash,
        angle_selection_sha256=selection_hash,
        selected_angle_id=selection.selected_angle_id,
        target_language=target_language,
        dependency_hashes=dependency_hashes,
    )
    review_payload = review.model_dump(mode="json")

    def write_review() -> None:
        registry.write_json("storyboard_review.json", review_payload, "human_storyboard_review")

    _execute(manifest, registry, "human_storyboard_review", write_review)
    review_hash = manifest.artifacts["storyboard_review.json"].content_hash or ""
    edit = HumanStoryboardEditV1(
        schema_version="human-storyboard-edit/1.0",
        status="pending_human_review",
        run_id=run_id,
        case_id=focus.case_id,
        reviewer=reviewer,
        submitted_at=timestamp,
        rationale=rationale,
        review_sha256=review_hash,
        original_storyboard_sha256=storyboard_hash,
        candidate_storyboard_sha256=canonical_json_sha256(checked_candidate),
        dependency_hashes=dependency_hashes,
        candidate_storyboard=checked_candidate,
    )
    edit_payload = edit.model_dump(mode="json")
    candidate_payload = checked_candidate.model_dump(mode="json")

    def write_recovery() -> None:
        registry.write_json("human_storyboard_edit.json", edit_payload, "human_storyboard_recovery")
        registry.write_json("human_storyboard_candidate.json", candidate_payload, "human_storyboard_recovery")

    _execute(manifest, registry, "human_storyboard_recovery", write_recovery)

    def render_candidate() -> None:
        registry.write_text(
            "visual_plan.md", render_visual_plan(checked_candidate), "visual_plan_render", force=True,
        )

    _execute(manifest, registry, "visual_plan_render", render_candidate, force=True)
    return run_dir / "human_storyboard_candidate.json"


def build_timing_aware_visual_request(run_id: str, runs_dir: Path) -> VisualPlanningRequest:
    """Validate current V0.2 media dependencies and build a request without writes."""
    run_dir = resolve_run_dir(Path(runs_dir), run_id)
    manifest = RunManifest.model_validate(read_json(run_dir / "run.json"))
    if manifest.run_id != run_id:
        raise ValueError("VISUAL_TIMING_RUN_ID_MISMATCH")
    registry = ArtifactRegistry(
        run_dir, manifest, timing_aware_storyboard_mode=True,
    )
    if "angle_selection.json" not in registry.graph:
        raise ValueError("TIMING_AWARE_STORYBOARD_REQUIRES_HUMAN_ANGLE_SELECTION")
    # These two owner roots cover the full identity/audio/timing dependency set:
    # script approval covers the selected angle and script chain; subtitle covers
    # alignment, voice review, audio metadata, quality, and narration.
    for name in ("human_script_approval.json", "subtitle_track.json"):
        registry.validate(name)

    script = read_json(run_dir / "script.json")
    facts = read_json(run_dir / "facts.json")
    angles = read_json(run_dir / "angles.json")
    selection_raw = read_json(run_dir / "angle_selection.json")
    selection = HumanAngleSelectionV1.model_validate(selection_raw)
    candidates = angles.get("candidates", angles.get("angles", []))
    selected_angle = next((row for row in candidates
                           if row.get("angle_id") == selection.selected_angle_id), None)
    if selected_angle is None:
        raise ValueError("VISUAL_TIMING_SELECTED_ANGLE_MISSING")

    audio_path = run_dir / "audio/narration.wav"
    audio_bytes = audio_path.read_bytes()
    actual_audio_sha256 = sha256_bytes(audio_bytes)
    with wave.open(str(audio_path), "rb") as audio_stream:
        duration_ms = round(audio_stream.getnframes() * 1000 / audio_stream.getframerate())
    audio_metadata = read_json(run_dir / "audio/metadata.json")
    audio_quality = read_json(run_dir / "audio/quality.json")
    voice_review = read_json(run_dir / "audio/review.json")
    alignment = read_json(run_dir / "alignment.json")
    subtitle = read_json(run_dir / "subtitle_track.json")
    narration = read_json(run_dir / "narration.json")
    script_approval = read_json(run_dir / "human_script_approval.json")

    hashes = {name: manifest.artifacts[name].content_hash for name in (
        "script.json", "facts.json", "angles.json", "angle_selection.json",
        "script_terminology.json", "human_script_edit.json", "audio/review.json",
        "alignment.json", "subtitle_track.json",
    )}
    if any(not value for value in hashes.values()):
        raise ValueError("VISUAL_TIMING_REGISTRY_HASH_MISSING")
    context = build_timing_aware_context(
        run_id=run_id,
        script=script,
        script_sha256=hashes["script.json"],
        facts=facts,
        facts_sha256=hashes["facts.json"],
        selected_angle=selected_angle,
        angle_selection=selection_raw,
        angle_selection_sha256=hashes["angle_selection.json"],
        angles_sha256=hashes["angles.json"],
        script_approval=script_approval,
        script_terminology_sha256=hashes["script_terminology.json"],
        human_script_edit_sha256=hashes["human_script_edit.json"],
        narration=narration,
        audio_metadata=audio_metadata,
        actual_audio_sha256=actual_audio_sha256,
        actual_audio_duration_ms=duration_ms,
        audio_quality=audio_quality,
        voice_review=voice_review,
        voice_review_sha256=hashes["audio/review.json"],
        alignment=alignment,
        alignment_sha256=hashes["alignment.json"],
        subtitle_track=subtitle,
        subtitle_sha256=hashes["subtitle_track.json"],
    )
    return VisualPlanningRequest(
        run_id=run_id,
        script=script,
        allowed_claim_ids=set(context.allowed_claim_ids),
        timing_context=context,
    )


def run_visual_pipeline(run_id: str, runs_dir: Path, provider: VisualPlanningProvider, *,
                        stop_after: str | None = None, force_stage: str | None = None) -> Path:
    if stop_after is not None and stop_after not in VISUAL_STAGES:
        raise ValueError("INVALID_VISUAL_STOP_STAGE")
    if force_stage is not None and force_stage not in VISUAL_STAGES:
        raise ValueError("INVALID_VISUAL_FORCE_STAGE")
    run_dir = resolve_run_dir(Path(runs_dir), run_id)
    manifest, registry = _load(run_dir)
    script = registry.read_json("script.json")
    facts = registry.read_json("facts.json")
    registry.validate("angle.md")
    allowed_claim_ids = {
        row["claim_id"] for row in facts.get("claims", [])
        if row.get("verification_status") == "verified" and row.get("allowed_downstream") is True
    }
    timing_aware = "alignment.json" in registry.graph["storyboard.json"][1]

    def plan_beats() -> None:
        request = (build_timing_aware_visual_request(run_id, runs_dir) if timing_aware else
                   VisualPlanningRequest(run_id=run_id, script=script,
                                        allowed_claim_ids=allowed_claim_ids))
        plan = provider.plan(request)
        plan.provider = {"name": provider.name, "model": provider.model,
                         "prompt_version": provider.prompt_version}
        expected = [row["sentence_id"] for row in script.get("sentences", [])]
        actual = [sid for beat in plan.beats for sid in beat.sentence_ids]
        if actual != expected:
            raise ValueError("VISUAL_BEAT_SENTENCE_COVERAGE_INVALID")
        registry.write_json("visual_beats.json", plan.model_dump(mode="json"), "visual_planning",
                            force=force_stage == "visual_planning")

    _execute(manifest, registry, "visual_planning", plan_beats, force_stage == "visual_planning")
    if stop_after == "visual_planning":
        return run_dir

    def assemble_storyboard() -> None:
        plan = VisualBeatPlan.model_validate(registry.read_json("visual_beats.json"))
        storyboard = build_storyboard(plan, script, facts)
        if timing_aware:
            request = build_timing_aware_visual_request(run_id, runs_dir)
            validate_timed_scene_coverage(plan, request.timing_context, script)
            storyboard = apply_alignment_derived_timing(storyboard, plan, request.timing_context)
        gate = lint_storyboard(storyboard, script, facts)
        storyboard.quality_gate = gate
        if not gate.passed:
            raise ValueError("STORYBOARD_QUALITY_FAILED:" + ",".join(issue.code for issue in gate.issues))
        registry.write_json("storyboard.json", storyboard.model_dump(mode="json"),
                            "storyboard_generation", force=force_stage == "storyboard_generation")

    _execute(manifest, registry, "storyboard_generation", assemble_storyboard,
             force_stage == "storyboard_generation")
    if stop_after == "storyboard_generation":
        return run_dir

    def render_plan() -> None:
        from fanglei.visual_models import Storyboard
        storyboard = Storyboard.model_validate(registry.read_json("storyboard.json"))
        registry.write_text("visual_plan.md", render_visual_plan(storyboard), "visual_plan_render",
                            force=force_stage == "visual_plan_render")

    _execute(manifest, registry, "visual_plan_render", render_plan, force_stage == "visual_plan_render")
    manifest.status = "visual_planned"
    registry.save_manifest()
    return run_dir
