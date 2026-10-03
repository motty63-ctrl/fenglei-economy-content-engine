"""Strict, provider-free contract for human storyboard recovery."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator, model_validator

from fanglei.errors import ArtifactConflictError
from fanglei.storyboard_quality import lint_storyboard
from fanglei.visual_models import Storyboard


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?:万|亿|%|美元|美分|小时|点|points)?(?![\w.])")
_NUMERIC_ATOM = re.compile(r"(?<![\w.])[+＋\-−]?\d[\d,]*(?:\.\d+)*(?![\w.])")
_SIGNED_NUMBER = re.compile(r"(?P<sign>[+＋\-−])\s*(?P<value>\d+(?:\.\d+)?)")
_POSITIVE_MARKERS = (
    "增加", "上升", "上涨", "上修", "增长", "涨幅", "rose", "risen", "increased", "increase", "up",
)
_NEGATIVE_MARKERS = (
    "减少", "下降", "下修", "declined", "decline", "decreased", "decrease", "fell", "down",
)


def canonical_json_sha256(value: Any) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _aware_timestamp(value: str) -> str:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError("must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("must include a timezone")
    return value


def _hash_map(values: dict[str, str]) -> dict[str, str]:
    if not values or any(not key.strip() or not _SHA256.fullmatch(value) for key, value in values.items()):
        raise ValueError("dependency hashes must be named lowercase SHA-256 values")
    return values


class HumanStoryboardReviewV1(BaseModel):
    """Hash-bound human changes-required decision for an existing Storyboard."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["human-storyboard-review/1.0"]
    decision: Literal["changes_required"]
    run_id: StrictStr = Field(min_length=1)
    case_id: StrictStr = Field(min_length=1)
    reviewer: StrictStr = Field(min_length=1)
    reviewed_at: StrictStr = Field(min_length=1)
    reason_code: StrictStr = Field(min_length=1)
    rationale: StrictStr = Field(min_length=1)
    original_storyboard_sha256: StrictStr
    script_sha256: StrictStr
    audio_sha256: StrictStr
    voice_review_sha256: StrictStr
    alignment_sha256: StrictStr
    subtitle_sha256: StrictStr
    angle_selection_sha256: StrictStr
    selected_angle_id: StrictStr = Field(min_length=1)
    target_language: StrictStr = Field(min_length=2)
    dependency_hashes: dict[str, StrictStr]

    @field_validator("run_id", "case_id", "reviewer", "reason_code", "rationale", "selected_angle_id", "target_language")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("reviewed_at")
    @classmethod
    def timezone_aware(cls, value: str) -> str:
        return _aware_timestamp(value)

    @field_validator(
        "original_storyboard_sha256", "script_sha256", "audio_sha256", "voice_review_sha256",
        "alignment_sha256", "subtitle_sha256", "angle_selection_sha256",
    )
    @classmethod
    def valid_hash(cls, value: str) -> str:
        if not _SHA256.fullmatch(value):
            raise ValueError("must be lowercase SHA-256 hex")
        return value

    @field_validator("dependency_hashes")
    @classmethod
    def valid_dependency_hashes(cls, value: dict[str, str]) -> dict[str, str]:
        return _hash_map(value)


class HumanStoryboardEditV1(BaseModel):
    """A visual-only candidate awaiting a separate human Storyboard review."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["human-storyboard-edit/1.0"]
    status: Literal["pending_human_review"]
    run_id: StrictStr = Field(min_length=1)
    case_id: StrictStr = Field(min_length=1)
    reviewer: StrictStr = Field(min_length=1)
    submitted_at: StrictStr = Field(min_length=1)
    rationale: StrictStr = Field(min_length=1)
    review_sha256: StrictStr
    original_storyboard_sha256: StrictStr
    candidate_storyboard_sha256: StrictStr
    dependency_hashes: dict[str, StrictStr]
    candidate_storyboard: Storyboard

    @field_validator("run_id", "case_id", "reviewer", "rationale")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("submitted_at")
    @classmethod
    def timezone_aware(cls, value: str) -> str:
        return _aware_timestamp(value)

    @field_validator("review_sha256", "original_storyboard_sha256", "candidate_storyboard_sha256")
    @classmethod
    def valid_hash(cls, value: str) -> str:
        if not _SHA256.fullmatch(value):
            raise ValueError("must be lowercase SHA-256 hex")
        return value

    @field_validator("dependency_hashes")
    @classmethod
    def valid_dependency_hashes(cls, value: dict[str, str]) -> dict[str, str]:
        return _hash_map(value)

    @model_validator(mode="after")
    def candidate_digest_matches(self) -> "HumanStoryboardEditV1":
        if canonical_json_sha256(self.candidate_storyboard) != self.candidate_storyboard_sha256:
            raise ValueError("candidate_storyboard_sha256 does not match candidate_storyboard")
        if self.candidate_storyboard.run_id != self.run_id:
            raise ValueError("candidate Storyboard run_id does not match edit")
        return self


def validate_human_storyboard_candidate(
    original: Storyboard,
    candidate: Storyboard,
    script: dict[str, Any],
    facts: dict[str, Any],
) -> Storyboard:
    """Validate a visual-only edit while preserving content and timing provenance."""
    if candidate.run_id != original.run_id or candidate.script_id != original.script_id:
        raise ArtifactConflictError("STORYBOARD_RECOVERY_IDENTITY_CHANGED")
    if (
        candidate.schema_version != original.schema_version
        or candidate.timing_basis != original.timing_basis
        or candidate.total_estimated_duration_seconds != original.total_estimated_duration_seconds
        or candidate.renderer_selection != original.renderer_selection
        or candidate.timing_provenance != original.timing_provenance
    ):
        raise ArtifactConflictError("STORYBOARD_RECOVERY_TIMING_CHANGED")
    if len(candidate.scenes) != len(original.scenes):
        raise ArtifactConflictError("STORYBOARD_RECOVERY_SCENE_STRUCTURE_CHANGED")

    script_rows = {
        row.get("sentence_id"): row for row in script.get("sentences", [])
        if isinstance(row, dict) and isinstance(row.get("sentence_id"), str)
    }
    facts_by_id = {
        row.get("claim_id"): row for row in facts.get("claims", [])
        if isinstance(row, dict) and isinstance(row.get("claim_id"), str)
    }
    allowed_claims = {
        claim_id for claim_id, row in facts_by_id.items()
        if row.get("verification_status") == "verified" and row.get("allowed_downstream") is True
    }

    for old_scene, new_scene in zip(original.scenes, candidate.scenes, strict=True):
        if old_scene.scene_id != new_scene.scene_id or old_scene.order != new_scene.order:
            raise ArtifactConflictError("STORYBOARD_RECOVERY_SCENE_STRUCTURE_CHANGED")
        if old_scene.sentence_ids != new_scene.sentence_ids:
            raise ArtifactConflictError("STORYBOARD_RECOVERY_SEGMENT_OWNERSHIP_CHANGED")
        immutable_scene_fields = (
            "beat_ids", "narrative_role", "estimated_duration_seconds", "relative_start", "relative_end",
            "start_ms", "end_ms",
        )
        if any(getattr(old_scene, field) != getattr(new_scene, field) for field in immutable_scene_fields):
            raise ArtifactConflictError("STORYBOARD_RECOVERY_TIMING_CHANGED")

        old_claim_ids = {claim_id for obj in old_scene.objects for claim_id in obj.claim_ids}
        new_claim_ids = {claim_id for obj in new_scene.objects for claim_id in obj.claim_ids}
        if old_claim_ids != new_claim_ids:
            raise ArtifactConflictError("STORYBOARD_RECOVERY_CLAIM_SET_CHANGED")

        for obj in new_scene.objects:
            claim_ids = set(obj.claim_ids)
            sentence_ids = set(obj.sentence_ids)
            if not sentence_ids.issubset(script_rows):
                raise ArtifactConflictError("STORYBOARD_RECOVERY_UNKNOWN_SENTENCE")
            if obj.factual or claim_ids:
                if not obj.factual or not sentence_ids or not claim_ids:
                    raise ArtifactConflictError("STORYBOARD_RECOVERY_FACT_BINDING_INVALID")
                if not claim_ids <= old_claim_ids or not claim_ids <= allowed_claims:
                    raise ArtifactConflictError("STORYBOARD_RECOVERY_CLAIM_SET_CHANGED")
                source_texts: list[str] = []
                for sentence_id in sentence_ids:
                    row = script_rows[sentence_id]
                    if sentence_id not in new_scene.sentence_ids:
                        raise ArtifactConflictError("STORYBOARD_RECOVERY_SEGMENT_OWNERSHIP_CHANGED")
                    if row.get("sentence_type") != "verified_fact" or not claim_ids <= set(row.get("claim_ids", [])):
                        raise ArtifactConflictError("STORYBOARD_RECOVERY_CLAIM_BINDING_INVALID")
                    source_texts.append(str(row.get("text", "")))
                source_text = " ".join(source_texts)
                normalized_copy = obj.content.strip()
                if normalized_copy[:1] in {"+", "＋", "-", "−"}:
                    normalized_copy = normalized_copy[1:].lstrip()
                if not normalized_copy or normalized_copy not in source_text:
                    candidate_numbers = {
                        token.replace(",", "").lstrip("+＋")
                        for token in _NUMERIC_ATOM.findall(obj.content)
                    }
                    source_numbers = {
                        token.replace(",", "").lstrip("+＋")
                        for token in _NUMERIC_ATOM.findall(source_text)
                    }
                    if candidate_numbers - source_numbers:
                        raise ArtifactConflictError("STORYBOARD_RECOVERY_NUMERIC_VALUE_UNSUPPORTED")
                    raise ArtifactConflictError("STORYBOARD_RECOVERY_FACT_TEXT_UNSUPPORTED")
                _validate_explicit_number_signs(obj.content, source_text)
            else:
                if _NUMBER.search(obj.content):
                    raise ArtifactConflictError("STORYBOARD_RECOVERY_UNBOUND_NUMERIC_TEXT")
                if sentence_ids and not any(
                    obj.content.strip() in str(script_rows[sentence_id].get("text", ""))
                    for sentence_id in sentence_ids
                ):
                    raise ArtifactConflictError("STORYBOARD_RECOVERY_UNBOUND_COPY")

    gate = lint_storyboard(candidate, script, facts)
    if not gate.passed:
        codes = ",".join(issue.code for issue in gate.issues if issue.severity == "error")
        raise ArtifactConflictError(f"STORYBOARD_RECOVERY_QUALITY_GATE_FAILED:{codes}")
    return candidate.model_copy(update={"quality_gate": gate}, deep=True)


def _validate_explicit_number_signs(content: str, source_text: str) -> None:
    for match in _SIGNED_NUMBER.finditer(content):
        value = match.group("value")
        expected_signs: set[str] = set()
        for source_match in re.finditer(rf"(?<![\d.]){re.escape(value)}(?![\d.])", source_text):
            nearby: list[tuple[int, str]] = []
            for markers, sign in ((_POSITIVE_MARKERS, "+"), (_NEGATIVE_MARKERS, "-")):
                for marker in markers:
                    for marker_match in re.finditer(re.escape(marker), source_text, re.IGNORECASE):
                        if marker_match.end() <= source_match.start():
                            distance = source_match.start() - marker_match.end()
                        elif marker_match.start() >= source_match.end():
                            distance = marker_match.start() - source_match.end()
                        else:
                            distance = 0
                        if distance <= 16:
                            nearby.append((distance, sign))
            if nearby:
                nearest_distance = min(distance for distance, _ in nearby)
                nearest_signs = {sign for distance, sign in nearby if distance == nearest_distance}
                if len(nearest_signs) == 1:
                    expected_signs.update(nearest_signs)
        actual_sign = "-" if match.group("sign") in {"-", "−"} else "+"
        if actual_sign not in expected_signs:
            raise ArtifactConflictError(f"STORYBOARD_RECOVERY_NUMERIC_SIGN_UNSUPPORTED:{match.group(0)}")
