"""Hash-bound human approval for a specific Script to enter TTS."""
from __future__ import annotations

from datetime import datetime
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


class HumanScriptApprovalV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["human-script-approval/1.0"]
    status: Literal["approved_for_tts"]
    run_id: str
    case_id: str
    angle_id: str
    facts_sha256: str
    angles_sha256: str
    angle_selection_sha256: str
    terminology_sha256: str
    human_script_edit_sha256: str
    script_sha256: str
    target_language: str
    reviewer: str
    approved_at: str
    rationale: str

    @field_validator(
        "run_id", "case_id", "angle_id", "target_language", "reviewer", "rationale",
    )
    @classmethod
    def required_nonempty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("approval identity and review fields must be non-empty")
        return value

    @field_validator(
        "facts_sha256", "angles_sha256", "angle_selection_sha256", "terminology_sha256",
        "human_script_edit_sha256", "script_sha256",
    )
    @classmethod
    def lowercase_sha256(cls, value: str) -> str:
        if re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("approval hashes must be lowercase SHA-256 values")
        return value

    @field_validator("approved_at")
    @classmethod
    def timezone_aware_timestamp(cls, value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("approved_at must be timezone-aware ISO-8601") from error
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("approved_at must be timezone-aware ISO-8601")
        return value
