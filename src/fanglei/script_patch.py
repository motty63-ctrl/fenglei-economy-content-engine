"""Local authorization and application for sentence-level script repair patches."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from fanglei.content_models import ScriptDraft, ScriptSentence


class ScriptPatch(BaseModel):
    sentence_id: str
    operation: Literal["replace", "add_after"]
    new_text: str = Field(min_length=1)
    new_sentence_id: str | None = None
    new_sentence_type: Literal["verified_fact", "explanation", "interpretation", "analogy"] | None = None
    new_section: Literal["hook", "phenomenon", "mechanism", "core_judgment"] | None = None


class ScriptPatchResult(BaseModel):
    patches: list[ScriptPatch]


class RepairScope(BaseModel):
    editable_sentence_ids: list[str]
    protected_sentence_ids: list[str]
    type_change_sentence_ids: list[str] = Field(default_factory=list)
    allow_additions: bool = False


class RejectedPatch(BaseModel):
    patch: ScriptPatch
    reason: str


class PatchApplicationResult(BaseModel):
    draft: ScriptDraft
    requested: list[ScriptPatch]
    applied: list[ScriptPatch]
    rejected: list[RejectedPatch]
    protected_hashes_before: dict[str, str]
    protected_hashes_after: dict[str, str]
    protected_hashes_unchanged: bool


def build_repair_scope(draft: ScriptDraft, issues: list[Any]) -> RepairScope:
    """Derive the smallest editable sentence set authorized by current lint issues."""
    by_id = {sentence.sentence_id: sentence for sentence in draft.sentences}
    editable: set[str] = set()
    type_change: set[str] = set()
    codes = {issue.code for issue in issues}

    for issue in issues:
        sentence_id = getattr(issue, "sentence_id", None)
        if sentence_id in by_id:
            editable.add(sentence_id)
            if issue.code == "SENTENCE_TYPE_MISMATCH":
                type_change.add(sentence_id)

    if "HOOK_INVALID" in codes:
        editable.update(sentence.sentence_id for sentence in draft.sentences if sentence.section == "hook")
    if "DURATION_TOO_SHORT" in codes:
        expansion_candidates = [
            sentence for sentence in draft.sentences
            if sentence.section == "mechanism"
            and sentence.sentence_type in {"explanation", "interpretation"}
            and not sentence.claim_ids
        ]
        editable.update(sentence.sentence_id for sentence in expansion_candidates[:3])
    if "DURATION_TOO_LONG" in codes:
        compression_candidates = [
            sentence for sentence in draft.sentences
            if sentence.section == "mechanism"
            and sentence.sentence_type in {"explanation", "analogy"}
            and not sentence.claim_ids
        ]
        compression_candidates.sort(key=lambda sentence: len(sentence.text), reverse=True)
        editable.update(sentence.sentence_id for sentence in compression_candidates[:3])
    if codes & {"JARGON_DENSITY", "FORMULAIC_REPETITION"}:
        editable.update(
            sentence.sentence_id for sentence in draft.sentences
            if sentence.section == "mechanism"
            and sentence.sentence_type in {"explanation", "interpretation", "analogy"}
            and not sentence.claim_ids
        )

    ordered_ids = [sentence.sentence_id for sentence in draft.sentences]
    return RepairScope(
        editable_sentence_ids=[sentence_id for sentence_id in ordered_ids if sentence_id in editable],
        protected_sentence_ids=[sentence_id for sentence_id in ordered_ids if sentence_id not in editable],
        type_change_sentence_ids=[sentence_id for sentence_id in ordered_ids if sentence_id in type_change],
        allow_additions="DURATION_TOO_SHORT" in codes,
    )


def _sentence_hash(sentence: ScriptSentence) -> str:
    payload = json.dumps(sentence.model_dump(mode="json"), ensure_ascii=False,
                         sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _protected_hashes(draft: ScriptDraft, protected_ids: set[str]) -> dict[str, str]:
    return {
        sentence.sentence_id: _sentence_hash(sentence)
        for sentence in draft.sentences if sentence.sentence_id in protected_ids
    }


def apply_script_patches(
    draft: ScriptDraft, scope: RepairScope, patches: list[ScriptPatch]
) -> PatchApplicationResult:
    """Apply only authorized patches; reject unknown or protected targets fail-closed."""
    updated = draft.model_copy(deep=True)
    protected = set(scope.protected_sentence_ids)
    editable = set(scope.editable_sentence_ids)
    type_change = set(scope.type_change_sentence_ids)
    before = _protected_hashes(updated, protected)
    applied: list[ScriptPatch] = []
    rejected: list[RejectedPatch] = []

    for patch in patches:
        index_by_id = {sentence.sentence_id: index for index, sentence in enumerate(updated.sentences)}
        if patch.sentence_id not in index_by_id:
            rejected.append(RejectedPatch(patch=patch, reason="SENTENCE_NOT_FOUND"))
            continue
        if patch.sentence_id not in editable or patch.sentence_id in protected:
            rejected.append(RejectedPatch(patch=patch, reason="SENTENCE_PROTECTED"))
            continue

        index = index_by_id[patch.sentence_id]
        current = updated.sentences[index]
        if patch.operation == "replace":
            if patch.new_section is not None and patch.new_section != current.section:
                rejected.append(RejectedPatch(patch=patch, reason="SECTION_CHANGE_NOT_AUTHORIZED"))
                continue
            next_type = patch.new_sentence_type or current.sentence_type
            if next_type != current.sentence_type and patch.sentence_id not in type_change:
                rejected.append(RejectedPatch(patch=patch, reason="SENTENCE_TYPE_CHANGE_NOT_AUTHORIZED"))
                continue
            updated.sentences[index] = current.model_copy(update={
                "text": patch.new_text,
                "sentence_type": next_type,
            })
            applied.append(patch)
            continue

        if not scope.allow_additions:
            rejected.append(RejectedPatch(patch=patch, reason="ADDITION_NOT_AUTHORIZED"))
            continue
        if current.section != "mechanism" or current.sentence_type not in {"explanation", "interpretation"}:
            rejected.append(RejectedPatch(patch=patch, reason="INVALID_ADDITION_ANCHOR"))
            continue
        if not patch.new_sentence_id or patch.new_sentence_id in index_by_id:
            rejected.append(RejectedPatch(patch=patch, reason="INVALID_NEW_SENTENCE_ID"))
            continue
        if patch.new_section != "mechanism" or patch.new_sentence_type not in {"explanation", "interpretation"}:
            rejected.append(RejectedPatch(patch=patch, reason="INVALID_ADDED_SENTENCE_SHAPE"))
            continue
        updated.sentences.insert(index + 1, ScriptSentence(
            sentence_id=patch.new_sentence_id,
            section="mechanism",
            sentence_type=patch.new_sentence_type,
            text=patch.new_text,
            claim_ids=[],
        ))
        applied.append(patch)

    after = _protected_hashes(updated, protected)
    return PatchApplicationResult(
        draft=updated,
        requested=patches,
        applied=applied,
        rejected=rejected,
        protected_hashes_before=before,
        protected_hashes_after=after,
        protected_hashes_unchanged=before == after,
    )
