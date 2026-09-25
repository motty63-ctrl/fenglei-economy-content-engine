"""Artifact-first V0.3 content planning pipeline."""
from __future__ import annotations
import json
import re
from pathlib import Path
from fanglei.angle_policy import score_angles, select_angle, validate_angle_diversity
from fanglei.content_models import AngleCandidate, ScriptDraft
from fanglei.content_policy import build_fact_palette
from fanglei.content_render import render_angle_markdown, render_script_json, render_script_markdown
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


def _repair_issues(lint, draft: ScriptDraft) -> list[RepairIssue]:
    sentence_by_id = {sentence.sentence_id: sentence for sentence in draft.sentences}
    result: list[RepairIssue] = []
    seen: set[tuple[str, str | None, str | None]] = set()
    for item in lint.issues:
        if item.severity != "error":
            continue
        code, _, locator = item.code.partition("__")
        sentence_id = item.sentence_id or (locator.lower() if locator else None)
        issue: RepairIssue | None
        if code in {"DURATION_OUT_OF_RANGE", "UNDECLARED_FACT"}:
            continue
        if code == "DURATION_TOO_SHORT":
            issue = RepairIssue(code=code, current_seconds=lint.estimated_duration_seconds,
                                min_seconds=60, target_seconds=75)
        elif code == "DURATION_TOO_LONG":
            issue = RepairIssue(code=code, current_seconds=lint.estimated_duration_seconds,
                                max_seconds=90, target_seconds=75)
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
            issue = RepairIssue(code=code, sentence_id=sentence_id)
        key = (issue.code, issue.sentence_id, issue.trigger_category)
        if key not in seen:
            seen.add(key)
            result.append(issue)
    return result


def _issue_codes(issues: list[RepairIssue]) -> list[str]:
    return list(dict.fromkeys(issue.code for issue in issues))


def run_content_pipeline(run_id: str, runs_dir: Path, provider: ContentPlanningProvider, *,
                         stop_after: str | None = None, force_stage: str | None = None,
                         angle_id: str | None = None, speaking_rate: float = 4.0) -> Path:
    run_dir = resolve_run_dir(Path(runs_dir), run_id)
    manifest, registry = _load(run_dir)
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

    def generate_angles() -> None:
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
        )
        if len([c for c in candidates if c.eligibility == "eligible"]) < 3:
            raise ValueError("AT_LEAST_THREE_DISTINCT_ANGLES_REQUIRED")
        eligible_ids = {candidate.angle_id for candidate in candidates if candidate.eligibility == "eligible"}
        eligible_proposals = [proposal for proposal in proposed.candidates if proposal.angle_id in eligible_ids]
        diversity = validate_angle_diversity(eligible_proposals)
        if not diversity.passed:
            raise ValueError("ANGLE_DIVERSITY_FAILED:" + ",".join(diversity.issue_codes))
        recommended = select_angle(candidates)
        registry.write_json("angles.json", {"schema_version": "3.0", "run_id": run_id,
            "provider": {"name": provider.name, "model": provider.model, "prompt_version": provider.angle_prompt_version},
            "planning_context": {
                "framing_source": "research_focus" if focus else "questions",
                "research_focus_sha256": manifest.artifacts["research_focus.json"].content_hash if focus else None,
                "authority_metadata": authority_metadata,
            },
            "recommended_angle_id": recommended.angle_id,
            "recommendation_status": "system_recommendation_human_selection_pending",
            "diversity_gate": diversity.model_dump(mode="json"),
            "candidates": [c.model_dump(mode="json") for c in candidates]},
            "angle_generation", force=force_stage == "angle_generation")
    _execute(manifest, registry, "angle_generation", generate_angles, force_stage == "angle_generation")
    if stop_after == "angle_generation": return run_dir

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
    if stop_after == "angle_selection": return run_dir

    force_script = force_stage == "script_generation"
    if (run_dir / "script.json").is_file():
        old = registry.read_json("script.json") if manifest.artifacts["script.json"].status == "valid" else {}
        force_script = force_script or old.get("speaking_rate_chars_per_second") != speaking_rate
    selected_id = re.search(r"selected_angle_id: `([^`]+)`", (run_dir / "angle.md").read_text(encoding="utf-8")).group(1)
    angles = registry.read_json("angles.json")
    selected = AngleCandidate.model_validate(next(row for row in angles["candidates"] if row["angle_id"] == selected_id))
    def generate_script() -> None:
        if force_script:
            for artifact_name in ("script.json", "script.md"):
                if manifest.artifacts[artifact_name].status == "valid":
                    manifest.artifacts[artifact_name].status = "stale"
            registry.save_manifest()
        draft = provider.generate_script(ScriptGenerationInput(run_id=run_id, selected_angle=selected,
            research_md=research, fact_palette=palette))
        initial_draft = draft.model_dump(mode="json")
        lint = lint_script(draft, selected, facts, source_text, speaking_rate=speaking_rate)
        initial_issues = _repair_issues(lint, draft)
        initial_codes = _issue_codes(initial_issues)
        initial_duration = lint.estimated_duration_seconds
        repairs: list[dict[str, object]] = []
        repair_method = getattr(provider, "repair_script", None)
        for attempt in range(1, 3):
            if lint.passed or not callable(repair_method):
                break
            before_issues = _repair_issues(lint, draft)
            before_codes = _issue_codes(before_issues)
            before_duration = lint.estimated_duration_seconds
            scope = build_repair_scope(draft, before_issues)
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
            ))
            application = apply_script_patches(draft, scope, patch_result.patches)
            draft = application.draft
            lint = lint_script(draft, selected, facts, source_text, speaking_rate=speaking_rate)
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
        lint = lint_script(draft, selected, facts, source_text,
                           speaking_rate=payload["speaking_rate_chars_per_second"])
        registry.write_text("script.md", render_script_markdown(draft, lint), "script_render",
                            force=force_stage == "script_render" or manifest.artifacts["script.md"].status == "stale")
    _execute(manifest, registry, "script_render", render_script, force_stage == "script_render")
    manifest.status = "scripted"
    registry.save_manifest()
    return run_dir
