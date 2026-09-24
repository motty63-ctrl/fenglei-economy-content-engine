"""Versioned contracts for native source-selection artifacts."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import re
from typing import Annotated, Any, Literal, Mapping, Union
from urllib.parse import urlsplit

from fanglei.artifacts import sha256_bytes, sha256_text

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator


class UnsupportedSourcesVersionError(ValueError):
    """A source artifact version has no explicit contract."""


class SourcePackageValidationError(ValueError):
    """A source package does not match its run, approval, or captured documents."""


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
        source_ids = [row.source_id for row in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source rows must have unique source_id values")
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


def _raw_capture_hash(document: Any) -> str | None:
    raw_bytes = getattr(document, "raw_bytes", None)
    raw_content = getattr(document, "raw_content", None)
    if raw_bytes is not None:
        if not isinstance(raw_bytes, bytes):
            raise SourcePackageValidationError("raw_bytes must contain captured bytes")
        return sha256_bytes(raw_bytes)
    if raw_content is not None:
        if not isinstance(raw_content, str):
            raise SourcePackageValidationError("raw_content must contain captured text")
        return sha256_text(raw_content)
    return None


def _validate_document_index(documents: list[Any], document_index: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    if not isinstance(document_index, Mapping) or document_index.get("schema_version") != "2.1":
        raise SourcePackageValidationError("source_documents/index.json must use schema_version 2.1")
    indexed_rows = document_index.get("documents")
    if not isinstance(indexed_rows, list):
        raise SourcePackageValidationError("source document index must contain a documents list")
    indexed: dict[str, dict[str, Any]] = {}
    for row in indexed_rows:
        if not isinstance(row, Mapping):
            raise SourcePackageValidationError("source document index row must be an object")
        source_id = row.get("source_id")
        if not isinstance(source_id, str) or not source_id or source_id in indexed:
            raise SourcePackageValidationError("source document index source_id values must be unique and nonblank")
        indexed[source_id] = dict(row)
    document_ids = [getattr(document, "source_id", None) for document in documents]
    if any(not isinstance(source_id, str) or not source_id for source_id in document_ids):
        raise SourcePackageValidationError("captured documents require explicit source_id values")
    if len(document_ids) != len(set(document_ids)) or set(document_ids) != set(indexed):
        raise SourcePackageValidationError("captured documents must exactly match source document index identities")
    for document in documents:
        source_id = document.source_id
        row = indexed[source_id]
        url = getattr(document, "url", None)
        text = getattr(document, "text", None)
        if not isinstance(url, str) or row.get("url") != url:
            raise SourcePackageValidationError(f"source URL mismatch for {source_id}")
        if row.get("original_url") != getattr(document, "original_url", None):
            raise SourcePackageValidationError(f"source original URL mismatch for {source_id}")
        if not isinstance(text, str):
            raise SourcePackageValidationError(f"normalized source text is missing for {source_id}")
        normalized_hash = sha256_text(text)
        if row.get("content_hash") != normalized_hash:
            raise SourcePackageValidationError(f"normalized source content hash mismatch for {source_id}")
        document_hash = getattr(document, "document_hash", None)
        if document_hash is not None and row.get("document_hash") != document_hash:
            raise SourcePackageValidationError(f"captured document hash mismatch for {source_id}")
        document_format = getattr(document, "document_format", "html")
        if document_format == "pdf":
            raw_bytes = getattr(document, "raw_bytes", None)
            expected_document_hash = sha256_bytes(raw_bytes) if isinstance(raw_bytes, bytes) else None
        elif document_format == "api":
            raw_content = getattr(document, "raw_content", None)
            expected_document_hash = sha256_text(raw_content) if isinstance(raw_content, str) else None
        else:
            expected_document_hash = normalized_hash
        if not isinstance(document_hash, str) or document_hash != expected_document_hash:
            raise SourcePackageValidationError(f"document hash does not match its capture format for {source_id}")
        files = row.get("files")
        if not isinstance(files, list):
            raise SourcePackageValidationError(f"indexed files are missing for {source_id}")
        normalized_files = [asset for asset in files if isinstance(asset, Mapping) and asset.get("role") == "normalized_text"]
        if (
            len(normalized_files) != 1
            or normalized_files[0].get("content_hash") != normalized_hash
            or normalized_files[0].get("path") != row.get("path")
            or not isinstance(row.get("path"), str)
            or not row["path"]
        ):
            raise SourcePackageValidationError(f"normalized text asset hash mismatch for {source_id}")
        raw_assets = [asset for asset in files if isinstance(asset, Mapping) and asset.get("role") == "raw_response"]
        expected_raw_hash = _raw_capture_hash(document)
        if expected_raw_hash is None and raw_assets:
            raise SourcePackageValidationError(f"unreadable raw capture is indexed for {source_id}")
        if expected_raw_hash is not None and (
            len(raw_assets) != 1 or raw_assets[0].get("content_hash") != expected_raw_hash
        ):
            raise SourcePackageValidationError(f"raw capture hash mismatch for {source_id}")
    return indexed


def validate_sources_artifact_v21(
    artifact: Mapping[str, Any],
    *,
    documents: list[Any],
    document_index: Mapping[str, Any],
    run_id: str,
    case_id: str | None = None,
) -> SourcesV21:
    """Validate a V2.1 source artifact against this run's exact captured documents."""
    try:
        parsed = SourcesV21.model_validate(artifact)
    except Exception as error:
        raise SourcePackageValidationError(f"invalid sources.json 2.1 contract: {error}") from error
    if not isinstance(run_id, str) or not run_id.strip():
        raise SourcePackageValidationError("run_id must be explicitly supplied")
    indexed = _validate_document_index(documents, document_index)
    source_by_id = {row.source_id: row for row in parsed.sources}
    documents_by_id = {document.source_id: document for document in documents}
    if set(source_by_id) != set(documents_by_id):
        raise SourcePackageValidationError("source rows must exactly match captured document identities")
    for source_id, source_row in source_by_id.items():
        document = documents_by_id[source_id]
        if source_row.url != document.url or indexed[source_id].get("url") != source_row.url:
            raise SourcePackageValidationError(f"source row URL does not match captured document {source_id}")
    policy = parsed.source_policy
    if isinstance(policy, IndependentSourcesPolicyV1):
        expected_admissibility = "admissible" if parsed.independent_source_count >= 3 else "inadmissible"
        if parsed.package_admissibility != expected_admissibility:
            raise SourcePackageValidationError("independent_sources package_admissibility does not match the three-source requirement")
        return parsed
    if policy.run_id != run_id:
        raise SourcePackageValidationError("approved source policy run_id does not match the active run")
    if case_id is None or not isinstance(case_id, str) or not case_id.strip():
        raise SourcePackageValidationError("authoritative_primary_set requires an explicit case_id")
    if policy.case_id != case_id:
        raise SourcePackageValidationError("approved source policy case_id does not match the active case")
    approved_by_id = {row.source_id: row for row in policy.approved_documents}
    if set(approved_by_id) != set(documents_by_id):
        raise SourcePackageValidationError("approved document IDs must exactly match captured documents")
    for source_id, approved in approved_by_id.items():
        document = documents_by_id[source_id]
        index_row = indexed[source_id]
        if approved.url != document.url or approved.url != index_row.get("url"):
            raise SourcePackageValidationError(f"approved URL does not match capture for {source_id}")
        if approved.source_text_sha256 != sha256_text(document.text):
            raise SourcePackageValidationError(f"approved normalized source text hash mismatch for {source_id}")
        if approved.raw_capture_bytes_sha256 != _raw_capture_hash(document):
            raise SourcePackageValidationError(f"approved raw capture hash mismatch for {source_id}")
        published_at = getattr(document, "published_at", None)
        if not isinstance(published_at, str) or published_at[:10] != approved.release_date:
            raise SourcePackageValidationError(f"approved release date does not match capture metadata for {source_id}")
    if parsed.package_admissibility != "admissible":
        raise SourcePackageValidationError("a valid approved authoritative primary package must be admissible")
    return parsed


def build_sources_artifact_v21(
    source_rows: list[Mapping[str, Any]],
    *,
    documents: list[Any],
    document_index: Mapping[str, Any],
    run_id: str,
    case_id: str | None = None,
    source_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic source-selection 2.1 artifact after capture validation."""
    policy_body: Mapping[str, Any]
    if source_policy is None:
        policy_body = {"name": "independent_sources", "version": "1.0"}
    else:
        policy_body = source_policy
    try:
        if policy_body.get("name") == "independent_sources":
            policy_model = IndependentSourcesPolicyV1.model_validate(policy_body)
        elif policy_body.get("name") == "authoritative_primary_set":
            policy_model = AuthoritativePrimarySetPolicyV1.model_validate(policy_body)
        else:
            raise SourcePackageValidationError(f"unsupported source policy: {policy_body.get('name')!r}")
    except SourcePackageValidationError:
        raise
    except Exception as error:
        raise SourcePackageValidationError(f"invalid source policy: {error}") from error
    rows = [SourceRowV21.model_validate(row).model_dump(mode="json") for row in source_rows]
    independent_keys = [row["independence_key"] for row in rows if row["counts_as_independent"]]
    if len(independent_keys) != len(set(independent_keys)):
        raise SourcePackageValidationError("independent source rows must use distinct independence_key values")
    independent_count = len(set(independent_keys))
    selection_status = "selected" if independent_count >= 3 else "insufficient_sources"
    package_admissibility = "inadmissible" if independent_count < 3 else "admissible"
    if isinstance(policy_model, AuthoritativePrimarySetPolicyV1):
        package_admissibility = "admissible"
    artifact = {
        "schema_version": "2.1",
        "source_policy": policy_model.model_dump(mode="json"),
        "package_admissibility": package_admissibility,
        "independent_source_count": independent_count,
        "selection_status": selection_status,
        "sources": rows,
    }
    validate_sources_artifact_v21(
        artifact,
        documents=documents,
        document_index=document_index,
        run_id=run_id,
        case_id=case_id,
    )
    return artifact
