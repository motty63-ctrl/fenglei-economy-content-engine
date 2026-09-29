"""Artifact-first V0.3 content planning pipeline."""
from __future__ import annotations
import json
import re
from datetime import datetime
from pathlib import Path
from fanglei.angle_policy import (
    build_angle_quality_report,
    score_angles,
    select_angle,
    validate_angle_diversity,
)
from fanglei.angle_selection import HumanAngleSelectionV1
from fanglei.content_models import AngleCandidate, ScriptDraft
from fanglei.content_policy import build_fact_palette
from fanglei.content_render import render_angle_markdown, render_script_json, render_script_markdown
from fanglei.artifact_registry import ArtifactRegistry
from fanglei.artifacts import read_json
from fanglei.models import RunManifest
from fanglei.paths import resolve_run_dir
from fanglei.pipeline import _execute, _load
from fanglei.research_focus import ResearchFocusV1
from fanglei.errors import ArtifactConflictError
from fanglei.providers.content import (
    AngleGenerationInput,
    ContentPlanningProvider,
    RepairIssue,
    ScriptGenerationInput,
    ScriptRepairInput,
)
from fanglei.script_lint import lint_script
from fanglei.script_patch import apply_script_patches, build_repair_scope


def submit_human_script_recovery(
    run_id: str,
    runs_dir: Path,
    draft: ScriptDraft | dict,
    *,
    reviewer: str,
    rationale: str,
    failed_draft_sha256: str | None = None,
    speaking_rate: float = 4.0,
) -> Path:
    """Validate and register a human-edited script without invoking a provider."""
    from datetime import datetime

    from fanglei.angle_selection import HumanAngleSelectionV1
    from fanglei.human_script_recovery import (
        HumanScriptEditV1,
        canonical_json_sha256,
        failed_draft_sha256_from_manifest,
    )
    from fanglei.research_focus import ResearchFocusV1
    from fanglei.script_terminology import validate_script_terminology_map

    run_dir = resolve_run_dir(Path(runs_dir), run_id)
    manifest = RunManifest.model_validate(read_json(run_dir / "run.json"))
    if manifest.run_id != run_id:
        raise ArtifactConflictError("SCRIPT_RECOVERY_RUN_ID_MISMATCH")
    registry = ArtifactRegistry(
        run_dir,
        manifest,
        research_focus_mode=True,
        human_angle_selection_mode=True,
        script_terminology_mode=True,
        human_script_recovery_mode=True,
    )
    if registry.imported_checkpoint_mode:
        raise ArtifactConflictError("SCRIPT_RECOVERY_NOT_SUPPORTED_FOR_IMPORTED_CHECKPOINT")

    required_artifacts = (
        "source.md", "facts.json", "research_focus.json", "research.md", "angles.json",
        "angle_selection.json", "angle.md", "script_terminology.json",
    )
    try:
        for name in required_artifacts:
            registry.validate(name)
    except Exception as error:
        # Validation only changes the in-memory manifest here. Do not save a
        # stale state when a human candidate is rejected before publication.
        raise ArtifactConflictError(f"SCRIPT_RECOVERY_UPSTREAM_NOT_CURRENT: {error}") from error

    facts = registry.read_json("facts.json")
    if facts.get("run_id") != run_id or not isinstance(facts.get("claims"), list):
        raise ArtifactConflictError("SCRIPT_RECOVERY_FACTS_IDENTITY_INVALID")
    focus = ResearchFocusV1.model_validate(registry.read_json("research_focus.json"))
    if focus.run_id != run_id or not focus.case_id.strip():
        raise ArtifactConflictError("SCRIPT_RECOVERY_CASE_IDENTITY_INVALID")

    angles = registry.read_json("angles.json")
    if angles.get("run_id") != run_id or not isinstance(angles.get("candidates"), list):
        raise ArtifactConflictError("SCRIPT_RECOVERY_ANGLES_IDENTITY_INVALID")
    selection = HumanAngleSelectionV1.model_validate(registry.read_json("angle_selection.json"))
    if selection.run_id != run_id:
        raise ArtifactConflictError("SCRIPT_RECOVERY_SELECTION_IDENTITY_INVALID")
    if (selection.angles_sha256 != manifest.artifacts["angles.json"].content_hash
            or selection.facts_sha256 != manifest.artifacts["facts.json"].content_hash):
        raise ArtifactConflictError("SCRIPT_RECOVERY_SELECTION_STALE")
    candidates = [row for row in angles["candidates"]
                  if isinstance(row, dict) and row.get("angle_id") == selection.selected_angle_id]
    if len(candidates) != 1:
        raise ArtifactConflictError("SCRIPT_RECOVERY_SELECTED_ANGLE_INVALID")
    try:
        selected = AngleCandidate.model_validate(candidates[0])
    except Exception as error:
        raise ArtifactConflictError("SCRIPT_RECOVERY_SELECTED_ANGLE_INVALID") from error
    if selected.eligibility != "eligible":
        raise ArtifactConflictError("SCRIPT_RECOVERY_SELECTED_ANGLE_INELIGIBLE")
    eligible_claim_ids = {claim.claim_id for claim in build_fact_palette(facts)}
    if not set(selected.supporting_claim_ids) <= eligible_claim_ids:
        raise ArtifactConflictError("SCRIPT_RECOVERY_SELECTED_ANGLE_HAS_INELIGIBLE_CLAIMS")
    angle_markers = re.findall(
        r"(?m)^selected_angle_id: `([^`]+)`\s*$",
        (run_dir / "angle.md").read_text(encoding="utf-8"),
    )
    if angle_markers != [selection.selected_angle_id]:
        raise ArtifactConflictError("SCRIPT_RECOVERY_RENDERED_ANGLE_MISMATCH")

    facts_hash = manifest.artifacts["facts.json"].content_hash
    if not facts_hash:
        raise ArtifactConflictError("SCRIPT_RECOVERY_FACTS_HASH_MISSING")
    try:
        terminology = validate_script_terminology_map(
            registry.read_json("script_terminology.json"), facts,
            expected_run_id=run_id, expected_case_id=focus.case_id,
            facts_sha256=facts_hash,
            allowed_claim_ids=set(selected.supporting_claim_ids), require_approved=True,
        )
    except Exception as error:
        raise ArtifactConflictError("SCRIPT_RECOVERY_TERMINOLOGY_INVALID") from error

    try:
        parsed_draft = draft if isinstance(draft, ScriptDraft) else ScriptDraft.model_validate(draft)
    except Exception as error:
        raise ArtifactConflictError(f"SCRIPT_HUMAN_DRAFT_INVALID: {error}") from error
    if parsed_draft.angle_id != selection.selected_angle_id:
        raise ArtifactConflictError("SCRIPT_ANGLE_ID_MISMATCH")
    if (not parsed_draft.target_language
            or parsed_draft.target_language.casefold() != terminology.target_language.casefold()):
        raise ArtifactConflictError("SCRIPT_TARGET_LANGUAGE_MISMATCH")

    source_text = (run_dir / "source.md").read_text(encoding="utf-8")
    lint = lint_script(
        parsed_draft, selected, facts, source_text,
        speaking_rate=speaking_rate,
        target_duration_seconds=parsed_draft.target_duration_seconds,
        target_language=terminology.target_language,
        terminology_map=terminology,
        current_facts_sha256=facts_hash,
        run_id=run_id,
        case_id=focus.case_id,
    )
    if not lint.passed:
        issue_codes = list(dict.fromkeys(issue.code for issue in lint.issues if issue.severity == "error"))
        raise ArtifactConflictError("SCRIPT_HUMAN_DRAFT_REJECTED:" + ",".join(issue_codes))

    # A submitted human edit is write-once. Existing artifacts must be reviewed
    # explicitly through a later owner flow rather than silently overwritten.
    for name in ("human_script_edit.json", "script.json", "script.md"):
        path = run_dir / name
        state = manifest.artifacts[name]
        if path.exists() or state.status != "missing":
            raise ArtifactConflictError(f"SCRIPT_RECOVERY_OUTPUT_ALREADY_EXISTS: {name}")

    submitted_at = datetime.now().astimezone().isoformat(timespec="seconds")
    draft_payload = parsed_draft.model_dump(mode="json")
    failed_hash = failed_draft_sha256_from_manifest(manifest.model_dump(mode="json"))
    if failed_draft_sha256 is not None:
        if failed_hash is not None and failed_draft_sha256 != failed_hash:
            raise ArtifactConflictError("SCRIPT_RECOVERY_FAILED_DRAFT_HASH_MISMATCH")
        failed_hash = failed_draft_sha256
    edit = HumanScriptEditV1(
        schema_version="human-script-edit/1.0",
        status="pending_human_review",
        run_id=run_id,
        case_id=focus.case_id,
        angle_id=selection.selected_angle_id,
        reviewer=reviewer,
        submitted_at=submitted_at,
        rationale=rationale,
        target_language=terminology.target_language,
        facts_sha256=facts_hash,
        research_sha256=manifest.artifacts["research.md"].content_hash or "",
        source_sha256=manifest.artifacts["source.md"].content_hash or "",
        angles_sha256=manifest.artifacts["angles.json"].content_hash or "",
        angle_selection_sha256=manifest.artifacts["angle_selection.json"].content_hash or "",
        terminology_sha256=manifest.artifacts["script_terminology.json"].content_hash or "",
        failed_draft_sha256=failed_hash,
        draft_sha256=canonical_json_sha256(draft_payload),
        draft=parsed_draft,
    )
    edit_payload = edit.model_dump(mode="json")
    script_payload = render_script_json(parsed_draft, lint)
    rendered_script = render_script_markdown(parsed_draft, lint)

    def write_human_edit() -> None:
        registry.write_json("human_script_edit.json", edit_payload, "human_script_recovery")

    _execute(manifest, registry, "human_script_recovery", write_human_edit)
    script_payload.update({
        "authoring_method": "human_edit",
        "human_review_status": "pending",
        "human_script_edit_sha256": manifest.artifacts["human_script_edit.json"].content_hash,
        "script_lint": {
            "status": "passed",
            "issue_codes": [issue.code for issue in lint.issues],
            "estimated_duration_seconds": lint.estimated_duration_seconds,
            "submitted_at": submitted_at,
        },
    })

    def write_script() -> None:
        registry.write_json("script.json", script_payload, "script_generation")

    _execute(manifest, registry, "script_generation", write_script, force=True)

    def render_script() -> None:
        registry.write_text("script.md", rendered_script, "script_render")

    _execute(manifest, registry, "script_render", render_script, force=True)
    manifest.status = "scripted"
    registry.save_manifest()
    return run_dir / "human_script_edit.json"


def _selection_failure(code: str, detail: str) -> ArtifactConflictError:
    return ArtifactConflictError(f"{code}: {detail}")


def _load_human_selected_angle(
    run_id: str,
    run_dir: Path,
    manifest,
    registry,
    angles: dict,
    eligible_claim_ids: set[str],
) -> AngleCandidate:
    selection_path = run_dir / "angle_selection.json"
    state = manifest.artifacts["angle_selection.json"]
    if state.status == "missing":
        code = "ANGLE_SELECTION_INVALID" if selection_path.exists() else "ANGLE_SELECTION_REQUIRED"
        raise _selection_failure(code, "record an explicit human selection with select-angle")
    if state.status != "valid":
        raise _selection_failure("ANGLE_SELECTION_STALE", "selection artifact is not current")
    try:
        registry.validate("angle_selection.json")
        raw = registry.read_json("angle_selection.json")
    except Exception as error:
        registry.save_manifest()
        raise _selection_failure("ANGLE_SELECTION_STALE", str(error)) from error
    try:
        selection = HumanAngleSelectionV1.model_validate(raw)
    except Exception as error:
        raise _selection_failure("ANGLE_SELECTION_INVALID", str(error)) from error

    if selection.run_id != run_id:
        raise _selection_failure("ANGLE_SELECTION_INVALID", "run identity does not match")
    if (selection.angles_sha256 != manifest.artifacts["angles.json"].content_hash
            or selection.facts_sha256 != manifest.artifacts["facts.json"].content_hash):
        raise _selection_failure("ANGLE_SELECTION_STALE", "bound angles or facts hash changed")

    candidates = angles.get("candidates")
    if not isinstance(candidates, list):
        raise _selection_failure("ANGLE_SELECTION_INVALID", "angles.json has no candidate list")
    matches = [row for row in candidates if isinstance(row, dict)
               and row.get("angle_id") == selection.selected_angle_id]
    if len(matches) != 1:
        raise _selection_failure("ANGLE_SELECTION_INVALID", "selected candidate is missing or ambiguous")
    try:
        selected = AngleCandidate.model_validate(matches[0])
    except Exception as error:
        raise _selection_failure("ANGLE_SELECTION_INVALID", f"selected candidate is malformed: {error}") from error
    if selected.eligibility != "eligible":
        raise _selection_failure("ANGLE_SELECTION_INVALID", "selected candidate is not eligible")
    if not set(selected.supporting_claim_ids) <= eligible_claim_ids:
        raise _selection_failure("ANGLE_SELECTION_INVALID", "selected candidate has ineligible supporting claims")

    try:
        registry.validate("angle.md")
        angle_markdown = (run_dir / "angle.md").read_text(encoding="utf-8")
    except Exception as error:
        registry.save_manifest()
        raise _selection_failure("ANGLE_SELECTION_STALE", f"rendered angle is not current: {error}") from error
    markers = re.findall(r"(?m)^selected_angle_id: `([^`]+)`\s*$", angle_markdown)
    if markers != [selection.selected_angle_id]:
        raise _selection_failure("ANGLE_SELECTION_INVALID", "angle.md does not match the human selection")
    return selected


def record_human_angle_selection(
    run_id: str,
    runs_dir: Path,
    selected_angle_id: str,
    *,
    reviewer: str | None = None,
    rationale: str | None = None,
) -> Path:
    """Record one explicit human choice for the current angles/facts artifacts."""
    from fanglei.paths import resolve_run_dir

    run_dir = resolve_run_dir(Path(runs_dir), run_id)
    manifest, registry = _load(run_dir, human_angle_selection_mode=True)
    if registry.imported_checkpoint_mode:
        raise _selection_failure("ANGLE_SELECTION_INVALID", "checkpoint imports use their materialized angle")
    selection_path = run_dir / "angle_selection.json"
    selection_state = manifest.artifacts["angle_selection.json"]
    if selection_path.exists() and selection_state.status == "missing":
        raise _selection_failure("ANGLE_SELECTION_INVALID", "selection file is not registered")
    if selection_state.status == "valid":
        try:
            registry.validate("angle_selection.json")
            existing_selection = HumanAngleSelectionV1.model_validate(
                registry.read_json("angle_selection.json")
            )
            if existing_selection.run_id != run_id:
                raise ValueError("existing selection run identity does not match")
        except Exception as error:
            registry.save_manifest()
            raise _selection_failure("ANGLE_SELECTION_INVALID", f"existing selection is invalid: {error}") from error
    try:
        registry.validate("angles.json")
        registry.validate("facts.json")
        angles = registry.read_json("angles.json")
        facts = registry.read_json("facts.json")
    except Exception as error:
        registry.save_manifest()
        raise _selection_failure("ANGLE_SELECTION_STALE", str(error)) from error
    if angles.get("run_id") != run_id or (facts.get("run_id") is not None and facts.get("run_id") != run_id):
        raise _selection_failure("ANGLE_SELECTION_INVALID", "angles/facts run identity does not match")
    rows = angles.get("candidates")
    if not isinstance(rows, list):
        raise _selection_failure("ANGLE_SELECTION_INVALID", "angles.json has no candidate list")
    matches = [row for row in rows if isinstance(row, dict) and row.get("angle_id") == selected_angle_id]
    if len(matches) != 1:
        raise _selection_failure("ANGLE_SELECTION_INVALID", "selected candidate is missing or ambiguous")
    try:
        selected = AngleCandidate.model_validate(matches[0])
    except Exception as error:
        raise _selection_failure("ANGLE_SELECTION_INVALID", f"selected candidate is malformed: {error}") from error
    if selected.eligibility != "eligible":
        raise _selection_failure("ANGLE_SELECTION_INVALID", "selected candidate is not eligible")
    eligible_claim_ids = {claim.claim_id for claim in build_fact_palette(facts)}
    if not set(selected.supporting_claim_ids) <= eligible_claim_ids:
        raise _selection_failure("ANGLE_SELECTION_INVALID", "selected candidate has ineligible supporting claims")

    angles_hash = manifest.artifacts["angles.json"].content_hash
    facts_hash = manifest.artifacts["facts.json"].content_hash
    if not angles_hash or not facts_hash:
        raise _selection_failure("ANGLE_SELECTION_STALE", "current angles/facts hashes are unavailable")
    try:
        selection = HumanAngleSelectionV1(
            schema_version="human-angle-selection/1.0",
            run_id=run_id,
            selected_angle_id=selected_angle_id,
            source="human",
            selected_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            angles_sha256=angles_hash,
            facts_sha256=facts_hash,
            reviewer=reviewer,
            rationale=rationale,
        )
    except Exception as error:
        raise _selection_failure("ANGLE_SELECTION_INVALID", str(error)) from error

    def write_selection() -> None:
        registry.write_json(
            "angle_selection.json", selection.model_dump(mode="json", exclude_none=True),
            "human_angle_selection", force=True,
        )

    _execute(manifest, registry, "human_angle_selection", write_selection, force=True)
    # First-time selection may leave an older legacy Script with identical
    # angle text. It still predates this human decision and must be regenerated.
    registry.invalidate_descendants("angle_selection.json")
    registry.write_text(
        "angle.md", render_angle_markdown(selected), "angle_selection", force=True
    )
    registry.save_manifest()
    return run_dir / "angle_selection.json"


def _repair_issues(lint, draft: ScriptDraft) -> list[RepairIssue]:
    sentence_by_id = {sentence.sentence_id: sentence for sentence in draft.sentences}
    result: list[RepairIssue] = []
    seen: set[tuple[str, str | None, str | None]] = set()
    for item in lint.issues:
        if item.severity != "error" and item.code != "DURATION_TARGET_MISSED":
            continue
        code, _, locator = item.code.partition("__")
        sentence_id = item.sentence_id or (locator.lower() if locator else None)
        diagnostics = item.diagnostics
        issue: RepairIssue | None
        if code in {"DURATION_OUT_OF_RANGE", "UNDECLARED_FACT"}:
            continue
        if code == "DURATION_TOO_SHORT":
            issue = RepairIssue(code=code, current_seconds=lint.estimated_duration_seconds,
                                min_seconds=60, target_seconds=75)
        elif code == "DURATION_TOO_LONG":
            issue = RepairIssue(code=code, current_seconds=lint.estimated_duration_seconds,
                                max_seconds=90, target_seconds=draft.target_duration_seconds)
        elif code == "DURATION_TARGET_MISSED":
            issue = RepairIssue(code=code, current_seconds=lint.estimated_duration_seconds,
                                min_seconds=60, max_seconds=90,
                                target_seconds=draft.target_duration_seconds)
        elif code.startswith("SEMANTIC_FACTUALITY_UNSUPPORTED_"):
            signal = code.removeprefix("SEMANTIC_FACTUALITY_UNSUPPORTED_").lower()
            issue = RepairIssue(code="CLAIM_BINDING_MISSING", sentence_id=sentence_id,
                                trigger_category=signal,
                                expected_constraint="bind an allowed verified claim or rewrite as non-factual")
        elif code == "SENTENCE_TYPE_MISMATCH":
            sentence = sentence_by_id.get(sentence_id or "")
            issue = RepairIssue(code=code, sentence_id=sentence_id,
                                current_type=sentence.sentence_type if sentence else None,
                                expected_constraint="obvious analogy markers require sentence_type=analogy")
        else:
            issue = RepairIssue(code=code, sentence_id=sentence_id, diagnostics=diagnostics)
        key = (issue.code, issue.sentence_id, issue.trigger_category)
        if key not in seen:
            seen.add(key)
            result.append(issue)
        elif diagnostics:
            existing = next(item for item in result
                            if (item.code, item.sentence_id, item.trigger_category) == key)
            if existing.diagnostics is None:
                existing.diagnostics = diagnostics
            elif existing.diagnostics != diagnostics:
                related = existing.diagnostics.setdefault("related_claim_diagnostics", [])
                if not related:
                    related.append({key: value for key, value in existing.diagnostics.items()
                                    if key != "related_claim_diagnostics"})
                if diagnostics not in related:
                    related.append(diagnostics)
    return result


def _issue_codes(issues: list[RepairIssue]) -> list[str]:
    return list(dict.fromkeys(issue.code for issue in issues))


def run_content_pipeline(run_id: str, runs_dir: Path, provider: ContentPlanningProvider, *,
                         stop_after: str | None = None, force_stage: str | None = None,
                         angle_id: str | None = None, speaking_rate: float = 4.0,
                         legacy_auto_recommended: bool = False,
                         target_language: str | None = None) -> Path:
    run_dir = resolve_run_dir(Path(runs_dir), run_id)
    manifest, registry = _load(
        run_dir, human_angle_selection_mode=not legacy_auto_recommended
    )
    if legacy_auto_recommended and "angle_selection.json" in registry.graph:
        raise _selection_failure(
            "ANGLE_SELECTION_INVALID",
            "legacy recommendation fallback cannot downgrade a run using human selection",
        )
    facts = registry.read_json("facts.json")
    palette = build_fact_palette(facts)
    if not palette: raise ValueError("NO_SCRIPT_READY_FACTS")
    source_text = (run_dir / "source.md").read_text(encoding="utf-8")
    research = (run_dir / "research.md").read_text(encoding="utf-8")
    sources = registry.read_json("sources.json")
    focus = None
    if "research_focus.json" in registry.graph:
        focus = ResearchFocusV1.model_validate(registry.read_json("research_focus.json"))
        if focus.run_id != run_id:
            raise ArtifactConflictError("research_focus.json run_id does not match the active run")
        core_topic = focus.primary_question
        research_questions = focus.subquestions
    else:
        questions = registry.read_json("questions.json")
        core_topic = questions.get("core_topic", "")
        research_questions = [q.get("question", "") for q in questions.get("research_questions", [])]

    source_independence_keys = {
        row["source_id"]: row["independence_key"]
        for row in sources.get("sources", [])
        if row.get("counts_as_independent") is True
        and isinstance(row.get("source_id"), str)
        and isinstance(row.get("independence_key"), str)
        and row["independence_key"].strip()
    }
    authority_metadata = {
        "source_policy": sources.get("source_policy"),
        "package_admissibility": sources.get("package_admissibility"),
        "independent_source_count": sources.get("independent_source_count"),
        "selection_status": sources.get("selection_status"),
        "sources_sha256": manifest.artifacts["sources.json"].content_hash,
    }

    v02_script_flow = focus is not None or "angle_selection.json" in registry.graph
    explicit_target_language = target_language
    if explicit_target_language is not None and (
        not isinstance(explicit_target_language, str) or not explicit_target_language.strip()
    ):
        raise ArtifactConflictError("SCRIPT_TARGET_LANGUAGE_INVALID")
    target_language = explicit_target_language or (
        getattr(provider, "script_target_language", None) if v02_script_flow else None
    )
    terminology_payload: dict[str, object] | None = None
    terminology = None
    terminology_path = run_dir / "script_terminology.json"
    if terminology_path.is_file():
        from fanglei.script_terminology import validate_script_terminology_map

        case_id = (focus.case_id if focus else
                   (sources.get("source_policy", {}) or {}).get("case_id"))
        if not isinstance(case_id, str) or not case_id.strip():
            raise ArtifactConflictError("SCRIPT_TERMINOLOGY_REVIEW_REQUIRED: case identity missing")
        try:
            registry.validate("script_terminology.json")
            raw_terminology = registry.read_json("script_terminology.json")
            terminology = validate_script_terminology_map(
                raw_terminology, facts, expected_run_id=run_id,
                expected_case_id=case_id,
                facts_sha256=manifest.artifacts["facts.json"].content_hash,
                require_approved=True,
            )
        except Exception as error:
            raise ArtifactConflictError(
                "SCRIPT_TERMINOLOGY_REVIEW_REQUIRED: current map invalid"
            ) from error
        if (explicit_target_language is not None
                and terminology.target_language.casefold() != explicit_target_language.casefold()):
            raise ArtifactConflictError("SCRIPT_TARGET_LANGUAGE_MISMATCH")
        # The reviewed spelling is canonical. An explicit caller value is a
        # constraint on that identity, not a second language authority.
        target_language = terminology.target_language
        terminology_payload = terminology.model_dump(mode="json")

    def generate_angles() -> None:
        # A deliberate regeneration is a new review event. Invalidate a human
        # choice even when deterministic/provider output happens to hash alike.
        if force_stage == "angle_generation" and "angle_selection.json" in registry.graph:
            registry.invalidate_descendants("angles.json")
        proposed = provider.generate_angles(AngleGenerationInput(run_id=run_id,
            core_topic=core_topic,
            research_questions=research_questions,
            research_focus=focus.model_dump(mode="json") if focus else None,
            research_md=research, fact_palette=palette,
            authority_metadata=authority_metadata))
        if not 3 <= len(proposed.candidates) <= 5:
            raise ValueError("ANGLE_DIVERSITY_FAILED:ANGLE_COUNT_OUT_OF_RANGE")
        candidates = score_angles(
            proposed.candidates, palette, source_text,
            source_independence_keys=source_independence_keys,
            quality_metadata=proposed.quality_metadata or None,
        )
        if len([c for c in candidates if c.eligibility == "eligible"]) < 3:
            raise ValueError("AT_LEAST_THREE_DISTINCT_ANGLES_REQUIRED")
        eligible_ids = {candidate.angle_id for candidate in candidates if candidate.eligibility == "eligible"}
        eligible_proposals = [proposal for proposal in proposed.candidates if proposal.angle_id in eligible_ids]
        diversity = validate_angle_diversity(eligible_proposals, proposed.quality_metadata or None)
        if not diversity.passed:
            raise ValueError("ANGLE_DIVERSITY_FAILED:" + ",".join(diversity.issue_codes))
        recommended = select_angle(candidates)
        artifact = {"schema_version": "3.0", "run_id": run_id,
            "provider": {"name": provider.name, "model": provider.model, "prompt_version": provider.angle_prompt_version},
            "planning_context": {
                "framing_source": "research_focus" if focus else "questions",
                "research_focus_sha256": manifest.artifacts["research_focus.json"].content_hash if focus else None,
                "authority_metadata": authority_metadata,
            },
            "recommended_angle_id": recommended.angle_id,
            "recommendation_status": "system_recommendation_human_selection_pending",
            "diversity_gate": diversity.model_dump(mode="json"),
            "candidates": [c.model_dump(mode="json") for c in candidates]}
        if proposed.quality_metadata:
            artifact["angle_quality"] = build_angle_quality_report(
                proposed.quality_metadata, proposed.candidates, candidates
            )
        registry.write_json("angles.json", artifact,
            "angle_generation", force=force_stage == "angle_generation")
    _execute(manifest, registry, "angle_generation", generate_angles, force_stage == "angle_generation")
    if stop_after == "angle_generation": return run_dir

    if legacy_auto_recommended:
        existing_selected = None
        if (run_dir / "angle.md").is_file():
            match = re.search(r"selected_angle_id: `([^`]+)`", (run_dir / "angle.md").read_text(encoding="utf-8"))
            existing_selected = match.group(1) if match else None
        force_select = force_stage == "angle_selection" or bool(angle_id and angle_id != existing_selected)

        def choose_angle() -> None:
            artifact = registry.read_json("angles.json")
            candidates = [AngleCandidate.model_validate(row) for row in artifact["candidates"]]
            chosen = select_angle(candidates, angle_id or artifact["recommended_angle_id"])
            registry.write_text("angle.md", render_angle_markdown(chosen), "angle_selection", force=force_select)

        _execute(manifest, registry, "angle_selection", choose_angle, force_select)
        if stop_after == "angle_selection":
            return run_dir
        selected_id = re.search(r"selected_angle_id: `([^`]+)`", (run_dir / "angle.md").read_text(encoding="utf-8")).group(1)
        angles = registry.read_json("angles.json")
        selected = AngleCandidate.model_validate(next(row for row in angles["candidates"] if row["angle_id"] == selected_id))
    else:
        if angle_id is not None:
            raise _selection_failure("ANGLE_SELECTION_REQUIRED", "use select-angle to record the human choice")
        angles = registry.read_json("angles.json")
        selected = _load_human_selected_angle(
            run_id, run_dir, manifest, registry, angles,
            {claim.claim_id for claim in palette},
        )
        if stop_after == "angle_selection":
            return run_dir

    if target_language:
        from fanglei.script_lint import _is_cross_language_claim
        from fanglei.script_terminology import validate_script_terminology_map

        claims_by_id = {claim.get("claim_id"): claim for claim in facts.get("claims", [])
                        if isinstance(claim, dict)}
        selected_cross_language = [
            claims_by_id[claim_id] for claim_id in selected.supporting_claim_ids
            if claim_id in claims_by_id
            and claims_by_id[claim_id].get("verification_basis") == "authoritative_primary_attestation"
            and _is_cross_language_claim(claims_by_id[claim_id], target_language)
        ]
        if selected_cross_language:
            if terminology is None:
                raise ArtifactConflictError("SCRIPT_TERMINOLOGY_REVIEW_REQUIRED")
            case_id = (focus.case_id if focus else
                       (sources.get("source_policy", {}) or {}).get("case_id"))
            if not isinstance(case_id, str) or not case_id.strip():
                raise ArtifactConflictError("SCRIPT_TERMINOLOGY_REVIEW_REQUIRED: case identity missing")
            try:
                terminology = validate_script_terminology_map(
                    terminology, facts, expected_run_id=run_id,
                    expected_case_id=case_id,
                    facts_sha256=manifest.artifacts["facts.json"].content_hash,
                    allowed_claim_ids=set(selected.supporting_claim_ids), require_approved=True,
                )
                terminology_payload = terminology.model_dump(mode="json")
            except Exception as error:
                raise ArtifactConflictError("SCRIPT_TERMINOLOGY_REVIEW_REQUIRED: current map invalid") from error

    force_script = force_stage == "script_generation"
    if (run_dir / "script.json").is_file():
        old = registry.read_json("script.json") if manifest.artifacts["script.json"].status == "valid" else {}
        force_script = force_script or old.get("speaking_rate_chars_per_second") != speaking_rate
    def generate_script() -> None:
        if force_script:
            for artifact_name in ("script.json", "script.md"):
                if manifest.artifacts[artifact_name].status == "valid":
                    manifest.artifacts[artifact_name].status = "stale"
            registry.save_manifest()
        draft = provider.generate_script(ScriptGenerationInput(run_id=run_id, selected_angle=selected,
            research_md=research, fact_palette=palette,
            research_focus=focus.model_dump(mode="json") if focus else None,
            authority_metadata=authority_metadata,
            target_language=target_language,
            target_duration_seconds=75,
            speaking_rate_chars_per_second=speaking_rate,
            terminology_map=terminology_payload))
        initial_draft = draft.model_dump(mode="json", exclude_none=True)
        lint_options = {
            "speaking_rate": speaking_rate,
            "target_duration_seconds": 75,
            "target_language": target_language,
            "terminology_map": terminology_payload,
            "current_facts_sha256": manifest.artifacts["facts.json"].content_hash,
            "run_id": run_id,
            "case_id": focus.case_id if focus else (sources.get("source_policy", {}) or {}).get("case_id"),
        }
        lint = lint_script(draft, selected, facts, source_text, **lint_options)
        initial_issues = _repair_issues(lint, draft)
        initial_codes = _issue_codes(initial_issues)
        initial_duration = lint.estimated_duration_seconds
        repairs: list[dict[str, object]] = []
        repair_method = getattr(provider, "repair_script", None)
        for attempt in range(1, 3):
            target_warning = any(issue.code == "DURATION_TARGET_MISSED" for issue in lint.issues)
            if (lint.passed and not target_warning) or not callable(repair_method):
                break
            before_issues = _repair_issues(lint, draft)
            before_codes = _issue_codes(before_issues)
            before_duration = lint.estimated_duration_seconds
            scope = build_repair_scope(draft, before_issues,
                                       allowed_claim_ids=selected.supporting_claim_ids)
            patch_result = repair_method(ScriptRepairInput(
                run_id=run_id,
                repair_attempt=attempt,
                selected_angle=selected,
                current_script=draft,
                editable_sentence_ids=scope.editable_sentence_ids,
                protected_sentence_ids=scope.protected_sentence_ids,
                allow_additions=scope.allow_additions,
                fact_palette=palette,
                issues=before_issues,
                target_language=target_language,
                target_duration_seconds=draft.target_duration_seconds,
                speaking_rate_chars_per_second=speaking_rate,
                terminology_map=terminology_payload,
                clear_attribution_context_sentence_ids=scope.clear_attribution_context_sentence_ids,
                closing_claim_bind_sentence_ids=scope.closing_claim_bind_sentence_ids,
                allowed_closing_claim_ids=scope.allowed_closing_claim_ids,
            ))
            application = apply_script_patches(draft, scope, patch_result.patches)
            draft = application.draft
            lint = lint_script(draft, selected, facts, source_text, **lint_options)
            after_issues = _repair_issues(lint, draft)
            after_codes = _issue_codes(after_issues)
            repairs.append({
                "attempt": attempt,
                "attempt_number": attempt,
                "issue_codes_before": before_codes,
                "issue_codes_after": after_codes,
                "issues_before": [issue.model_dump(mode="json", exclude_none=True) for issue in before_issues],
                "issues_after": [issue.model_dump(mode="json", exclude_none=True) for issue in after_issues],
                "editable_sentence_ids": scope.editable_sentence_ids,
                "protected_sentence_ids": scope.protected_sentence_ids,
                "patches_requested": [patch.model_dump(mode="json", exclude_none=True)
                                      for patch in application.requested],
                "patches_applied": [patch.model_dump(mode="json", exclude_none=True)
                                    for patch in application.applied],
                "patches_rejected": [row.model_dump(mode="json", exclude_none=True)
                                     for row in application.rejected],
                "protected_hashes_before": application.protected_hashes_before,
                "protected_hashes_after": application.protected_hashes_after,
                "protected_hashes_unchanged": application.protected_hashes_unchanged,
                "estimated_duration_before": before_duration,
                "estimated_duration_after": lint.estimated_duration_seconds,
            })
        final_issues = _repair_issues(lint, draft)
        final_codes = _issue_codes(final_issues)
        audit = {
            "initial_script": initial_draft,
            "initial_issue_codes": initial_codes,
            "initial_issues": [issue.model_dump(mode="json", exclude_none=True) for issue in initial_issues],
            "initial_estimated_duration_seconds": initial_duration,
            "repairs": repairs,
            "final_issue_codes": final_codes,
            "final_issues": [issue.model_dump(mode="json", exclude_none=True) for issue in final_issues],
            "final_estimated_duration_seconds": lint.estimated_duration_seconds,
            "final_status": "passed" if lint.passed else "failed",
        }
        if not lint.passed:
            raise ValueError("SCRIPT_REPAIR_EXHAUSTED:" + json.dumps(audit, separators=(",", ":")))
        payload = render_script_json(draft, lint)
        payload["repair_audit"] = audit
        payload["provider"] = {
            "name": provider.name,
            "model": provider.model,
            "prompt_version": provider.script_prompt_version,
        }
        payload["generation_config"] = {
            key: getattr(provider, key)
            for key in ("angle_temperature", "script_temperature", "repair_temperature")
            if hasattr(provider, key)
        }
        payload["generation_config"]["max_repair_attempts"] = 2
        registry.write_json("script.json", payload, "script_generation", force=force_script)
    _execute(manifest, registry, "script_generation", generate_script, force_script)
    if stop_after == "script_generation": return run_dir

    def render_script() -> None:
        payload = registry.read_json("script.json")
        draft = ScriptDraft.model_validate(payload)
        lint = lint_script(
            draft, selected, facts, source_text,
            speaking_rate=payload["speaking_rate_chars_per_second"],
            target_duration_seconds=draft.target_duration_seconds,
            target_language=target_language,
            terminology_map=terminology_payload,
            current_facts_sha256=manifest.artifacts["facts.json"].content_hash,
            run_id=run_id,
            case_id=focus.case_id if focus else (sources.get("source_policy", {}) or {}).get("case_id"),
        )
        registry.write_text("script.md", render_script_markdown(draft, lint), "script_render",
                            force=force_stage == "script_render" or manifest.artifacts["script.md"].status == "stale")
    _execute(manifest, registry, "script_render", render_script, force_stage == "script_render")
    manifest.status = "scripted"
    registry.save_manifest()
    return run_dir


def run_legacy_content_pipeline(
    run_id: str,
    runs_dir: Path,
    provider: ContentPlanningProvider,
    **kwargs,
) -> Path:
    """Explicit compatibility path retaining the historical recommendation fallback."""
    return run_content_pipeline(
        run_id, runs_dir, provider, legacy_auto_recommended=True, **kwargs
    )
