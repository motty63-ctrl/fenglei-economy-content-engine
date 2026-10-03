"""Auditable human selection contract for content angles."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class HumanAngleSelectionV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["human-angle-selection/1.0"]
    run_id: str = Field(min_length=1)
    selected_angle_id: str = Field(min_length=1)
    source: Literal["human"]
    selected_at: str = Field(min_length=1)
    angles_sha256: str
    facts_sha256: str
    reviewer: str | None = None
    rationale: str | None = None

    @field_validator("run_id", "selected_angle_id", "selected_at", "reviewer", "rationale")
    @classmethod
    def require_nonblank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("angles_sha256", "facts_sha256")
    @classmethod
    def require_sha256(cls, value: str) -> str:
        if not _SHA256.fullmatch(value):
            raise ValueError("must be lowercase SHA-256 hex")
        return value

    @field_validator("selected_at")
    @classmethod
    def require_aware_timestamp(cls, value: str) -> str:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            timestamp = datetime.fromisoformat(normalized)
        except ValueError as error:
            raise ValueError("must be an ISO-8601 timestamp") from error
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("must include a timezone")
        return value
