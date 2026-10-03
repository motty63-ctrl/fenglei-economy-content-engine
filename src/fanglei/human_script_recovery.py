"""Strict provenance contract for provider-free human script recovery."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator, model_validator

from fanglei.content_models import ScriptDraft


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def failed_draft_sha256_from_manifest(manifest: dict[str, Any]) -> str | None:
    """Hash the initial draft embedded in a prior SCRIPT_REPAIR_EXHAUSTED audit, if present."""
    try:
        message = manifest["stages"]["script_generation"]["error"]["message"]
        prefix = "SCRIPT_REPAIR_EXHAUSTED:"
        if not isinstance(message, str) or not message.startswith(prefix):
            return None
        audit = json.loads(message[len(prefix):])
        initial = audit.get("initial_script")
        if not isinstance(initial, dict):
            return None
        return canonical_json_sha256(initial)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


class HumanScriptEditV1(BaseModel):
    """A human-authored, lint-passed script awaiting separate human review."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["human-script-edit/1.0"]
    status: Literal["pending_human_review"]
    run_id: StrictStr = Field(min_length=1)
    case_id: StrictStr = Field(min_length=1)
    angle_id: StrictStr = Field(min_length=1)
    reviewer: StrictStr = Field(min_length=1)
    submitted_at: StrictStr = Field(min_length=1)
    rationale: StrictStr = Field(min_length=1)
    target_language: StrictStr = Field(min_length=2)
    facts_sha256: StrictStr
    research_sha256: StrictStr
    source_sha256: StrictStr
    angles_sha256: StrictStr
    angle_selection_sha256: StrictStr
    terminology_sha256: StrictStr
    failed_draft_sha256: StrictStr | None
    draft_sha256: StrictStr
    draft: ScriptDraft

    @field_validator(
        "run_id", "case_id", "angle_id", "reviewer", "rationale", "target_language", "submitted_at",
    )
    @classmethod
    def require_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator(
        "facts_sha256", "research_sha256", "source_sha256", "angles_sha256",
        "angle_selection_sha256", "terminology_sha256", "failed_draft_sha256", "draft_sha256",
    )
    @classmethod
    def require_sha256(cls, value: str | None) -> str | None:
        if value is not None and not _SHA256.fullmatch(value):
            raise ValueError("must be lowercase SHA-256 hex")
        return value

    @field_validator("submitted_at")
    @classmethod
    def require_aware_timestamp(cls, value: str) -> str:
        from datetime import datetime

        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as error:
            raise ValueError("must be an ISO-8601 timestamp") from error
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_draft_binding(self) -> "HumanScriptEditV1":
        if self.draft.angle_id != self.angle_id:
            raise ValueError("draft angle_id does not match edit angle_id")
        if self.draft.target_language != self.target_language:
            raise ValueError("draft target_language does not match edit target_language")
        if canonical_json_sha256(self.draft.model_dump(mode="json")) != self.draft_sha256:
            raise ValueError("draft_sha256 does not match draft")
        return self
