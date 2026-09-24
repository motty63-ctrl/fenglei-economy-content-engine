"""Versioned contracts for native source-selection artifacts."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import re
from typing import Annotated, Any, Literal, Mapping, Union
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator


class UnsupportedSourcesVersionError(ValueError):
    """A source artifact version has no explicit contract."""


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


NonBlank = Annotated[str, StringConstraints(strict=True, min_length=1), AfterValidator(_nonblank)]
Sha256 = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$")]


def _aware_timestamp(value: str) -> str:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError("must be a valid ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("must include a timezone")
    return value


AwareTimestamp = Annotated[NonBlank, AfterValidator(_aware_timestamp)]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _LegacyModel(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)


class SourceRowV21(_StrictModel):
    source_id: NonBlank
    url: NonBlank
    title: NonBlank
    published_at: str | None
    retrieved_at: AwareTimestamp
    source_type: NonBlank
    credibility_tier: NonBlank
    independence_key: NonBlank
    counts_as_independent: bool
    independence_reason: NonBlank
    origin_chain: list[NonBlank] = Field(min_length=1)

    @field_validator("url")
    @classmethod
    def require_exact_https_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if value != value.strip() or parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("must be an exact HTTPS URL")
        return value


class IndependentSourcesPolicyV1(_StrictModel):
    name: Literal["independent_sources"]
    version: Literal["1.0"]


class InstitutionIdentity(_StrictModel):
    institution_id: NonBlank
    display_name: NonBlank


class ApprovedPrimaryDocument(_StrictModel):
    source_id: NonBlank
    url: NonBlank
    document_identity: NonBlank
    evidence_role: NonBlank
    release_date: NonBlank
    classification: Literal["official_primary"]
    source_text_sha256: Sha256
    raw_capture_bytes_sha256: Sha256 | None

    @field_validator("url")
    @classmethod
    def require_exact_https_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if value != value.strip() or parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("must be an exact HTTPS URL")
        return value

    @field_validator("release_date")
    @classmethod
    def require_iso_date(cls, value: str) -> str:
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d")
        except ValueError as error:
            raise ValueError("must be an ISO-8601 calendar date") from error
        if parsed.strftime("%Y-%m-%d") != value:
            raise ValueError("must be an ISO-8601 calendar date")
        return value


class SourcePolicyApproval(_StrictModel):
    status: Literal["approved"]
    reviewer: NonBlank
    approved_at: AwareTimestamp
    rationale: NonBlank
    package_sha256: Sha256


class AuthoritativePrimarySetPolicyV1(_StrictModel):
    name: Literal["authoritative_primary_set"]
    version: Literal["1.0"]
    run_id: NonBlank
    case_id: NonBlank
    institution: InstitutionIdentity
    approved_documents: list[ApprovedPrimaryDocument] = Field(min_length=2)
    approval: SourcePolicyApproval

    @model_validator(mode="after")
    def package_is_distinct_and_approval_is_bound(self) -> "AuthoritativePrimarySetPolicyV1":
        documents = self.approved_documents
        for field_name in ("source_id", "url", "document_identity"):
            values = [getattr(row, field_name) for row in documents]
            if len(values) != len(set(values)):
                raise ValueError(f"approved_documents must have distinct {field_name} values")
        text_hashes = [row.source_text_sha256 for row in documents]
        if len(text_hashes) != len(set(text_hashes)):
            raise ValueError("approved_documents must have distinct source_text_sha256 values")
        if len({row.evidence_role for row in documents}) < 2:
            raise ValueError("approved_documents must contain distinct evidence roles")
        if len({row.release_date for row in documents}) < 2:
            raise ValueError("approved_documents must span distinct release dates")
        body = self.model_dump(mode="json", exclude={"approval"})
        if authoritative_source_package_sha256(body) != self.approval.package_sha256:
            raise ValueError("approval package_sha256 does not match the approved source package")
        return self


SourcePolicyV21 = Annotated[
    Union[IndependentSourcesPolicyV1, AuthoritativePrimarySetPolicyV1],
    Field(discriminator="name"),
]


class SourcesV20(_LegacyModel):
    """Legacy source-selection artifact; unknown legacy fields are preserved."""

    schema_version: Literal["2.0"]
    selection_status: Literal["selected", "insufficient_sources"]
    sources: list[dict[str, Any]]


class SourcesV21(_StrictModel):
    schema_version: Literal["2.1"]
    source_policy: SourcePolicyV21
    package_admissibility: Literal["admissible", "inadmissible"]
    independent_source_count: int = Field(ge=0)
    selection_status: Literal["selected", "insufficient_sources"]
    sources: list[SourceRowV21]

    @model_validator(mode="after")
    def counts_and_approved_set_match(self) -> "SourcesV21":
        independent_keys = [
            row.independence_key for row in self.sources if row.counts_as_independent
        ]
        if len(independent_keys) != len(set(independent_keys)):
            raise ValueError("independent source rows must have distinct independence_key values")
        actual_count = len(set(independent_keys))
        if actual_count != self.independent_source_count:
            raise ValueError("independent_source_count must equal distinct counted independence_key values")
        expected_status = "selected" if actual_count >= 3 else "insufficient_sources"
        if self.selection_status != expected_status:
            raise ValueError("selection_status must represent the three-independent-source gate")
        if (
            isinstance(self.source_policy, IndependentSourcesPolicyV1)
            and self.package_admissibility == "admissible"
            and self.selection_status != "selected"
        ):
            raise ValueError("independent_sources policy cannot admit a package below the three-source gate")
        if isinstance(self.source_policy, AuthoritativePrimarySetPolicyV1):
            expected = {(row.source_id, row.url) for row in self.source_policy.approved_documents}
            actual = {(row.source_id, row.url) for row in self.sources}
            if actual != expected or len(actual) != len(self.sources):
                raise ValueError("approved document set must exactly match source rows")
        return self


def authoritative_source_package_sha256(policy_body: Mapping[str, Any]) -> str:
    """Hash policy identity and approved document bindings, excluding approval itself."""
    if not isinstance(policy_body, Mapping):
        raise TypeError("Source policy body must be an object")
    body = {key: value for key, value in policy_body.items() if key != "approval"}
    canonical = json.dumps(
        body,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def parse_sources_artifact(value: Mapping[str, Any]) -> SourcesV20 | SourcesV21:
    if not isinstance(value, Mapping):
        raise TypeError("sources.json must be an object")
    version = value.get("schema_version")
    if version == "2.0":
        return SourcesV20.model_validate(value)
    if version == "2.1":
        return SourcesV21.model_validate(value)
    raise UnsupportedSourcesVersionError(f"Unsupported sources schema version: {version!r}")
