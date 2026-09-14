"""Deterministic quality gate for V0.4 storyboards."""
from __future__ import annotations

import re
from typing import Any

from fanglei.visual_models import Storyboard, StoryboardGateIssue, StoryboardGateResult


def lint_storyboard(storyboard: Storyboard, script: dict[str, Any], facts: dict[str, Any]) -> StoryboardGateResult:
    issues: list[StoryboardGateIssue] = []
    script_rows = {row["sentence_id"]: row for row in script.get("sentences", [])}
    expected = list(script_rows)
    covered = [sid for scene in storyboard.scenes for sid in scene.sentence_ids]
    covered_set = set(covered)
    for sentence_id in expected:
        if sentence_id not in covered_set:
            issues.append(_issue("SCRIPT_SENTENCE_NOT_COVERED", "script sentence has no scene", sentence_id))
    for sentence_id in covered_set - set(expected):
        issues.append(_issue("UNKNOWN_SCRIPT_SENTENCE", "scene references an unknown sentence", sentence_id))
    duplicates = {sid for sid in covered if covered.count(sid) > 1}
    for sentence_id in sorted(duplicates):
        issues.append(_issue("SCRIPT_SENTENCE_DUPLICATED", "sentence has multiple primary scenes", sentence_id))

    sentence_count = max(len(expected), 1)
    density = len(storyboard.scenes) / sentence_count
    if len(storyboard.scenes) >= 4 and density > .5:
        issues.append(_issue("PPT_SCENE_DENSITY", "too many scenes relative to narration sentences"))

    if storyboard.scenes:
        if abs(storyboard.scenes[0].relative_start) > 1e-6:
            issues.append(_issue("RELATIVE_TIMING_START", "relative timing must start at zero"))
        for previous, current in zip(storyboard.scenes, storyboard.scenes[1:]):
            if abs(previous.relative_end - current.relative_start) > 1e-5:
                issues.append(_issue("RELATIVE_TIMING_GAP_OR_OVERLAP", "relative timing must be contiguous",
                                     scene_id=current.scene_id))
        if abs(storyboard.scenes[-1].relative_end - 1) > 1e-5:
            issues.append(_issue("RELATIVE_TIMING_END", "relative timing must finish at one"))

    allowed = {row["claim_id"] for row in facts.get("claims", [])
               if row.get("verification_status") == "verified" and row.get("allowed_downstream") is True}
    known_objects: dict[str, tuple[str, str]] = {}
    active: set[str] = set()
    for scene in storyboard.scenes:
        current = {obj.object_id for obj in scene.objects}
        ordered_ids = [obj.object_id for obj in scene.objects]
        if scene.appearance_sequence != ordered_ids or scene.renderer_directives.draw_order != ordered_ids:
            issues.append(_issue("APPEARANCE_SEQUENCE_INVALID",
                                 "appearance and renderer order must list every active object once",
                                 scene.scene_id))
        if not set(scene.persistent_objects).issubset(set(scene.inherited_objects)):
            issues.append(_issue("PERSISTENT_OBJECT_NOT_INHERITED",
                                 "persistent objects must be inherited from the prior scene",
                                 scene.scene_id))
        for oid in scene.inherited_objects:
            if oid not in active:
                issues.append(_issue("OBJECT_INHERITED_BEFORE_INTRODUCTION",
                                     "object is inherited before it exists", scene.scene_id, oid))
        for oid in scene.removed_objects:
            if oid not in active:
                issues.append(_issue("OBJECT_REMOVED_BEFORE_INTRODUCTION",
                                     "object is removed before it exists", scene.scene_id, oid))
        if set(scene.inherited_objects) & set(scene.introduced_objects):
            issues.append(_issue("OBJECT_CONTINUITY_CONFLICT", "object cannot be introduced and inherited",
                                 scene.scene_id))
        micro_steps = scene.renderer_directives.micro_animation_sequence
        for step in micro_steps:
            for oid in step.target_object_ids:
                if oid not in current:
                    issues.append(_issue("MICRO_ANIMATION_TARGET_UNKNOWN",
                                         "micro animation targets an object outside the scene",
                                         scene.scene_id, oid))
        if scene.renderer_directives.structure == "numeric_animation" and any(
            obj.object_id == "rounding_arrow" for obj in scene.objects
        ):
            source_badges = {"bea_label", "world_bank_label"}
            if not source_badges.issubset(current) or not source_badges.issubset(
                set(scene.inherited_objects)
            ):
                issues.append(_issue("ROUNDING_SOURCE_CONTEXT_MISSING",
                                     "source badges must persist through the rounding merge",
                                     scene.scene_id))
            merge_index = next((i for i, step in enumerate(micro_steps)
                                if "merge" in step.actions), None)
            fade_index = next((i for i, step in enumerate(micro_steps)
                               if "fade_out" in step.actions and
                               source_badges == set(step.target_object_ids)), None)
            if merge_index is None or fade_index is None or fade_index <= merge_index:
                issues.append(_issue("ROUNDING_SOURCE_CONTEXT_SEQUENCE_INVALID",
                                     "source badges may fade only after the numeric merge",
                                     scene.scene_id))
        if scene.renderer_directives.structure == "process_flow":
            node_ids = ["source_check", "indicator_check", "year_check", "precision_check"]
            valid_sequence = len(micro_steps) == len(node_ids) + 1
            if valid_sequence:
                for index, (step, node_id) in enumerate(zip(micro_steps[:4], node_ids)):
                    expected_actions = ["appear", "focus", "check"] + (
                        ["move_focus_next"] if index < len(node_ids) - 1
                        else []
                    )
                    if step.target_object_ids != [node_id] or step.actions != expected_actions:
                        valid_sequence = False
                        break
            if valid_sequence:
                connect_step = micro_steps[-1]
                valid_sequence = (
                    connect_step.target_object_ids == node_ids + ["check_flow"]
                    and connect_step.actions == ["connect_complete_flow"]
                )
            if not valid_sequence:
                issues.append(_issue("PROCESS_FLOW_SEQUENCE_INVALID",
                                     "process flow must animate source, indicator, year, then precision",
                                     scene.scene_id))
        for obj in scene.objects:
            identity = (obj.object_type, obj.content)
            if obj.object_id in known_objects and known_objects[obj.object_id] != identity:
                issues.append(_issue("OBJECT_IDENTITY_CHANGED", "stable object ID changed meaning",
                                     scene.scene_id, obj.object_id))
            known_objects.setdefault(obj.object_id, identity)
            looks_factual = obj.factual or _looks_like_exact_fact(obj.content, obj.object_type)
            if looks_factual:
                if not obj.factual or not obj.sentence_ids:
                    issues.append(_issue("VISUAL_FACT_PROVENANCE_MISSING",
                                         "factual visible content needs sentence provenance",
                                         scene.scene_id, obj.object_id))
                if not obj.claim_ids or not set(obj.claim_ids).issubset(allowed):
                    issues.append(_issue("VISUAL_FACT_CLAIM_NOT_ALLOWED",
                                         "factual visible content needs an allowed verified claim",
                                         scene.scene_id, obj.object_id))
                if not obj.deterministic_render:
                    issues.append(_issue("FACTUAL_TEXT_NOT_DETERMINISTIC",
                                         "exact factual content must use a deterministic layer",
                                         scene.scene_id, obj.object_id))
                for sentence_id in obj.sentence_ids:
                    row = script_rows.get(sentence_id)
                    if row is None or not set(obj.claim_ids).issubset(set(row.get("claim_ids", []))):
                        issues.append(_issue("VISUAL_FACT_SENTENCE_CLAIM_MISMATCH",
                                             "visual claim is not bound by its source sentence",
                                             scene.scene_id, obj.object_id))
                overlays = scene.renderer_directives.deterministic_overlay_object_ids
                if obj.object_id not in overlays:
                    issues.append(_issue("FACTUAL_OVERLAY_NOT_DECLARED",
                                         "deterministic factual layer missing from renderer directives",
                                         scene.scene_id, obj.object_id))
        active = current

    if not storyboard.scenes or storyboard.scenes[-1].narrative_role != "judgment":
        issues.append(_issue("VISUAL_CONCLUSION_MISSING", "last scene must visually express the judgment"))
    coverage = len(covered_set & set(expected)) / sentence_count
    return StoryboardGateResult(
        passed=not any(issue.severity == "error" for issue in issues), issues=issues,
        sentence_coverage_ratio=round(coverage, 4), scene_sentence_ratio=round(density, 4),
    )


def _looks_like_exact_fact(content: str, object_type: str) -> bool:
    if object_type == "number":
        return True
    if re.search(r"\d+(?:\.\d+)?%|\b20\d{2}年?\b", content):
        return True
    return any(token in content for token in ("BEA", "World Bank", "美国实际GDP增长率", "四舍五入到一位小数"))


def _issue(code: str, message: str, scene_id: str | None = None,
           object_id: str | None = None) -> StoryboardGateIssue:
    return StoryboardGateIssue(code=code, message=message, scene_id=scene_id, object_id=object_id)
