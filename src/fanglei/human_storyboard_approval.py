"""Hash-bound human approval of a recovered Storyboard for visual generation."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator, model_validator


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_BOUND_HASHES = {
    "human_storyboard_candidate.json": "candidate_artifact_sha256",
    "storyboard.json": "original_storyboard_sha256",
    "script.json": "script_sha256",
    "facts.json": "facts_sha256",
    "angle_selection.json": "angle_selection_sha256",
    "audio/narration.wav": "audio_sha256",
    "audio/review.json": "voice_review_sha256",
    "alignment.json": "alignment_sha256",
    "subtitle_track.json": "subtitle_sha256",
}


class HumanStoryboardApprovalV1(BaseModel):
    """Approval is for one candidate, run, case, selection and reviewed media chain."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schema_version: Literal["human-storyboard-approval/1.0"]
    decision: Literal["approved_for_visual_generation"]
    run_id: StrictStr = Field(min_length=1)
    case_id: StrictStr = Field(min_length=1)
    reviewer: StrictStr = Field(min_length=1)
    approved_at: StrictStr = Field(min_length=1)
    rationale: StrictStr = Field(min_length=1)
    original_storyboard_sha256: StrictStr
    candidate_storyboard_sha256: StrictStr
    candidate_artifact_sha256: StrictStr
    script_sha256: StrictStr
    facts_sha256: StrictStr
    angle_selection_sha256: StrictStr
    selected_angle_id: StrictStr = Field(min_length=1)
    eligible_claim_ids: list[StrictStr]
    audio_sha256: StrictStr
    voice_review_sha256: StrictStr
    alignment_sha256: StrictStr
    subtitle_sha256: StrictStr
    dependency_hashes: dict[StrictStr, StrictStr]

    @field_validator("run_id", "case_id", "reviewer", "rationale", "selected_angle_id")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("approved_at")
    @classmethod
    def timezone_aware(cls, value: str) -> str:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as error:
            raise ValueError("must be an ISO-8601 timestamp") from error
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("must include a timezone")
        return value

    @field_validator(
        "original_storyboard_sha256", "candidate_storyboard_sha256", "candidate_artifact_sha256",
        "script_sha256", "facts_sha256", "angle_selection_sha256", "audio_sha256",
        "voice_review_sha256", "alignment_sha256", "subtitle_sha256",
    )
    @classmethod
    def valid_hash(cls, value: str) -> str:
        if not _SHA256.fullmatch(value):
            raise ValueError("must be lowercase SHA-256 hex")
        return value

    @field_validator("eligible_claim_ids")
    @classmethod
    def unique_claims(cls, value: list[str]) -> list[str]:
        if any(not claim_id.strip() for claim_id in value) or value != sorted(set(value)):
            raise ValueError("eligible_claim_ids must be nonblank, unique, and sorted")
        return value

    @field_validator("dependency_hashes")
    @classmethod
    def valid_dependency_hashes(cls, value: dict[str, str]) -> dict[str, str]:
        if not value or any(not key.strip() or not _SHA256.fullmatch(digest)
                            for key, digest in value.items()):
            raise ValueError("dependency hashes must be named lowercase SHA-256 values")
        return value

    @model_validator(mode="after")
    def hashes_match_explicit_bindings(self) -> "HumanStoryboardApprovalV1":
        for artifact_name, field_name in _BOUND_HASHES.items():
            digest = self.dependency_hashes.get(artifact_name)
            if digest is None or digest != getattr(self, field_name):
                raise ValueError(f"dependency hash does not match {field_name}: {artifact_name}")
        if "human_script_approval.json" not in self.dependency_hashes:
            raise ValueError("human script approval must be included in dependency hashes")
        return self
