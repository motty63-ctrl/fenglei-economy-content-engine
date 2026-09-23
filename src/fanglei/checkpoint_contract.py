"""Strict contracts and canonical hashing for approved checkpoints V2."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import re
from typing import Annotated, Any, Literal, Mapping
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, field_validator


class CheckpointContractError(ValueError):
    """A checkpoint does not satisfy a versioned authoring contract."""


class UnsupportedCheckpointVersionError(CheckpointContractError):
    """A checkpoint version has no explicit importer dispatch branch."""


class ApprovalBodyHashMismatch(CheckpointContractError):
    """The V2 approval is not bound to the current canonical body."""

    code = "APPROVAL_BODY_HASH_MISMATCH"


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


NonBlankStr = Annotated[
    str,
    StringConstraints(strict=True, min_length=1),
    AfterValidator(_nonblank),
]
Sha256 = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$")]
_ISO8601_DATETIME_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}T")


def _timezone_aware_iso8601(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("must be an ISO-8601 string")
    if _ISO8601_DATETIME_PREFIX.match(value) is None:
        raise ValueError("must use the ISO-8601 date/time separator 'T'")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as error:
        raise ValueError("must be a valid ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("must include a timezone")
    return value


TimezoneAwareTimestamp = Annotated[NonBlankStr, AfterValidator(_timezone_aware_iso8601)]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ProtectedArtifactHashes(_StrictModel):
    checkpoint_authoring_binding: Sha256 = Field(alias="checkpoint_authoring_binding.json")
    source: Sha256 = Field(alias="source.md")
    questions: Sha256 = Field(alias="questions.json")
    source_documents_index: Sha256 = Field(alias="source_documents/index.json")
    sources: Sha256 = Field(alias="sources.json")
    facts: Sha256 = Field(alias="facts.json")
    research: Sha256 = Field(alias="research.md")
    angles: Sha256 = Field(alias="angles.json")
    angle: Sha256 = Field(alias="angle.md")
    script_json: Sha256 = Field(alias="script.json")
    script_markdown: Sha256 = Field(alias="script.md")


class FactsSource(_StrictModel):
    schema_version: Literal["2.1"]
    policy_version: NonBlankStr
    summary: dict[str, Any]


class Research(_StrictModel):
    content: NonBlankStr


class OfficialReview(_StrictModel):
    decision: Literal["approved_official"]
    reviewer: NonBlankStr
    reviewed_at: TimezoneAwareTimestamp
    basis: NonBlankStr


class IndexedFileHash(_StrictModel):
    role: NonBlankStr
    path: NonBlankStr
    hash_kind: Literal["utf8_text_sha256", "file_bytes_sha256"]
    sha256: Sha256


class SourceSnapshot(_StrictModel):
    source_text_sha256: Sha256
    raw_capture_bytes_sha256: Sha256 | None
    indexed_file_hashes: list[IndexedFileHash] = Field(min_length=1)


class CheckpointSource(_StrictModel):
    external_id: NonBlankStr
    url: NonBlankStr
    official: Literal[True]
    official_review: OfficialReview
    title: NonBlankStr
    published_at: NonBlankStr | None
    snapshot: SourceSnapshot

    @field_validator("url")
    @classmethod
    def require_https_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if value != value.strip() or parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("must be an exact HTTPS URL")
        return value


class NativeClaimMetadata(_StrictModel):
    domain: NonBlankStr | None = None
    risk_level: NonBlankStr | None = None
    script_usage: NonBlankStr | None = None


class CheckpointClaim(_StrictModel):
    external_id: NonBlankStr
    proposition: NonBlankStr
    classification: Literal["fact", "opinion", "inference"]
    verification_status: Literal["verified", "conflicted", "unverified"]
    rationale: NonBlankStr
    allowed_downstream: bool
    source_ids: list[NonBlankStr]
    evidence_ids: list[NonBlankStr]
    native_metadata: NativeClaimMetadata | None = None


class CheckpointEvidence(_StrictModel):
    external_id: NonBlankStr
    claim_ids: list[NonBlankStr] = Field(min_length=1)
    source_ids: list[NonBlankStr] = Field(min_length=1)
    relation: Literal["supports", "contradicts", "context"]
    evidence_text: NonBlankStr
    excerpt_anchor: NonBlankStr
    source_section: NonBlankStr | None
    paragraph_locator: NonBlankStr | None
    published_at: NonBlankStr | None
    retrieved_at: NonBlankStr
    original_url: NonBlankStr


class CheckpointAngle(_StrictModel):
    external_id: NonBlankStr
    title: NonBlankStr
    hook: NonBlankStr
    core_question: NonBlankStr
    core_insight: NonBlankStr
    hook_mechanism: NonBlankStr
    audience_takeaway: NonBlankStr
    narrative_framing: NonBlankStr
    supporting_claim_ids: list[NonBlankStr]
    audience_relevance: int = Field(ge=0, le=5)
    novelty: int = Field(ge=0, le=5)
    hook_strength: int = Field(ge=0, le=5)
    visual_potential: int = Field(ge=0, le=5)
    explainability: int = Field(ge=0, le=5)
    risk_notes: list[NonBlankStr]
    evidence_strength: int = Field(ge=0, le=5)
    controversy_risk: int = Field(ge=0, le=5)
    total_score: int = Field(ge=0, le=100)
    eligibility: Literal["eligible", "rejected"]
    rejection_codes: list[NonBlankStr]
    originality: dict[str, Any]


class CheckpointScriptSentence(_StrictModel):
    external_id: NonBlankStr
    section: Literal["hook", "phenomenon", "mechanism", "core_judgment"]
    sentence_type: Literal["verified_fact", "explanation", "interpretation", "analogy"]
    text: NonBlankStr
    claim_ids: list[NonBlankStr]
    byte_start: int = Field(ge=0)
    byte_end: int = Field(ge=0)
    evidence_ids: list[NonBlankStr]


class CheckpointScript(_StrictModel):
    external_id: NonBlankStr
    angle_external_id: NonBlankStr
    title: NonBlankStr
    target_duration_seconds: int = Field(ge=60, le=90)
    speaking_rate_chars_per_second: float = Field(gt=0)
    spoken_character_count: int = Field(ge=0)
    estimated_duration_seconds: float = Field(ge=0)
    text: NonBlankStr
    sentences: list[CheckpointScriptSentence] = Field(min_length=1)


class CheckpointApproval(_StrictModel):
    status: Literal["approved"]
    reviewer: NonBlankStr
    approved_at: TimezoneAwareTimestamp
    body_sha256: Sha256


class CheckpointBodyV2(_StrictModel):
    checkpoint_schema_version: Literal["approved-checkpoint/2.0"]
    checkpoint_id: NonBlankStr
    case_id: NonBlankStr
    source_run_id: NonBlankStr
    protected_artifact_hashes: ProtectedArtifactHashes
    facts_source: FactsSource
    research: Research
    sources: list[CheckpointSource] = Field(min_length=1)
    claims: list[CheckpointClaim] = Field(min_length=1)
    evidence: list[CheckpointEvidence] = Field(min_length=1)
    angle: CheckpointAngle
    script: CheckpointScript


class CheckpointDraft(CheckpointBodyV2):
    """Strict in-memory V2 checkpoint body; drafts have no approval field."""


class ApprovedCheckpointV2(CheckpointBodyV2):
    approval: CheckpointApproval


class CheckpointAuthoringBindingV1(_StrictModel):
    schema_version: Literal["checkpoint-authoring-binding/1.0"]
    run_id: NonBlankStr
    case_id: NonBlankStr


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    """Serialize a JSON mapping using the V2 canonical JSON rules."""
    if not isinstance(value, Mapping):
        raise TypeError("Canonical checkpoint JSON must be an object")
    if any(not isinstance(key, str) for key in value):
        raise TypeError("Canonical JSON object keys must be strings")
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_body_sha256(checkpoint: Mapping[str, Any]) -> str:
    """Hash the complete checkpoint object after removing only top-level approval."""
    if not isinstance(checkpoint, Mapping):
        raise TypeError("Checkpoint must be an object")
    body = {key: value for key, value in checkpoint.items() if key != "approval"}
    return hashlib.sha256(canonical_json_bytes(body)).hexdigest()


def classify_checkpoint_version(checkpoint: Any) -> Literal["legacy_v1", "v2"]:
    if not isinstance(checkpoint, dict):
        raise UnsupportedCheckpointVersionError("Checkpoint must be an object with a supported version")
    version = checkpoint.get("checkpoint_schema_version")
    if version == "1.0" or version == "approved-checkpoint/1.0":
        return "legacy_v1"
    if version == "approved-checkpoint/2.0":
        return "v2"
    raise UnsupportedCheckpointVersionError(f"Unsupported checkpoint schema version: {version!r}")


def verify_approval_body_hash(checkpoint: Mapping[str, Any]) -> str:
    parsed = ApprovedCheckpointV2.model_validate(checkpoint)
    actual = canonical_body_sha256(checkpoint)
    expected = parsed.approval.body_sha256
    if actual != expected:
        raise ApprovalBodyHashMismatch(
            f"APPROVAL_BODY_HASH_MISMATCH: approval has {expected}; canonical body has {actual}"
        )
    return actual


def parse_approved_checkpoint_v2(checkpoint: Mapping[str, Any]) -> ApprovedCheckpointV2:
    parsed = ApprovedCheckpointV2.model_validate(checkpoint)
    verify_approval_body_hash(checkpoint)
    return parsed
