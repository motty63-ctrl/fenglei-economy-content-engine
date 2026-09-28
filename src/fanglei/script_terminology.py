"""Hash-bound, human-reviewed terminology bridge for cross-language scripts."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator, model_validator


SemanticRole = Literal[
    "subject", "metric", "population", "reporting_scope", "industry_category",
    "unit", "period", "statistic", "direction", "revision_previous",
    "revision_revised", "revision_delta", "source_attribution",
]

SourceField = Literal[
    "authority_attestation.scope.subject",
    "authority_attestation.scope.measure",
    "authority_attestation.scope.population",
    "authority_attestation.scope.reporting_scope",
    "authority_attestation.scope.period",
    "authority_attestation.scope.unit",
    "authority_attestation.scope.statistic",
    "authority_attestation.scope.certainty",
    "authority_attestation.attribution",
    "evidence.source_section",
    "evidence.evidence_period_matches",
    "evidence.evidence_target_concept",
    "evidence.explicit_values.unit",
    "evidence.revision_values.previous_value",
    "evidence.revision_values.revised_value",
    "evidence.revision_values.revision_amount",
    "evidence.revision_values.direction",
]

_ROLE_SOURCE_FIELDS: dict[str, set[str]] = {
    "subject": {"authority_attestation.scope.subject"},
    "metric": {"authority_attestation.scope.measure", "evidence.evidence_target_concept"},
    "population": {"authority_attestation.scope.population"},
    "reporting_scope": {
        "authority_attestation.scope.reporting_scope", "evidence.source_section",
    },
    "industry_category": {
        "authority_attestation.scope.subject", "evidence.evidence_target_concept",
    },
    "unit": {"authority_attestation.scope.unit", "evidence.explicit_values.unit"},
    "period": {
        "authority_attestation.scope.period", "evidence.evidence_period_matches",
    },
    "statistic": {"authority_attestation.scope.statistic"},
    "direction": {
        "authority_attestation.scope.certainty", "evidence.revision_values.direction",
    },
    "revision_previous": {"evidence.revision_values.previous_value"},
    "revision_revised": {"evidence.revision_values.revised_value"},
    "revision_delta": {"evidence.revision_values.revision_amount"},
    "source_attribution": {"authority_attestation.attribution"},
}

# A review proposal covers terms the validator actually needs to establish
# claim scope. Broader evidence-target prose and duplicated industry labels
# remain available for explicit human-added entries, but are not bulk-proposed.
_PROPOSAL_SOURCE_FIELDS: dict[str, tuple[str, ...]] = {
    "subject": ("authority_attestation.scope.subject",),
    "metric": ("authority_attestation.scope.measure",),
    "population": ("authority_attestation.scope.population",),
    "reporting_scope": (
        "authority_attestation.scope.reporting_scope", "evidence.source_section",
    ),
    "unit": ("authority_attestation.scope.unit", "evidence.explicit_values.unit"),
    "period": ("authority_attestation.scope.period",),
    "statistic": ("authority_attestation.scope.statistic",),
    "direction": (
        "authority_attestation.scope.certainty", "evidence.revision_values.direction",
    ),
    "revision_previous": ("evidence.revision_values.previous_value",),
    "revision_revised": ("evidence.revision_values.revised_value",),
    "revision_delta": ("evidence.revision_values.revision_amount",),
    "source_attribution": ("authority_attestation.attribution",),
}

_HEX_256 = re.compile(r"^[0-9a-f]{64}$")


class ScriptTerminologyEntryV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    entry_id: StrictStr = Field(min_length=1)
    claim_ids: list[StrictStr] = Field(min_length=1)
    source_term: StrictStr = Field(min_length=1)
    source_field: SourceField
    semantic_role: SemanticRole
    proposed_target_terms: list[StrictStr]
    approved_target_terms: list[StrictStr]
    review_status: Literal["pending", "approved"]

    @model_validator(mode="after")
    def validate_review_state(self) -> "ScriptTerminologyEntryV1":
        if len(set(self.claim_ids)) != len(self.claim_ids):
            raise ValueError("claim_ids must be unique")
        if not self.source_term.strip() or not self.entry_id.strip():
            raise ValueError("entry_id and source_term must be non-empty")
        if len(set(self.proposed_target_terms)) != len(self.proposed_target_terms):
            raise ValueError("proposed_target_terms must be unique")
        if len(set(self.approved_target_terms)) != len(self.approved_target_terms):
            raise ValueError("approved_target_terms must be unique")
        if any(not value.strip() for value in (*self.proposed_target_terms, *self.approved_target_terms)):
            raise ValueError("terminology aliases must be non-empty")
        if self.source_field not in _ROLE_SOURCE_FIELDS[self.semantic_role]:
            raise ValueError("SOURCE_FIELD_ROLE_MISMATCH")
        if self.review_status == "pending" and self.approved_target_terms:
            raise ValueError("PENDING_ENTRY_CANNOT_HAVE_APPROVED_TERMS")
        if self.review_status == "approved" and not self.approved_target_terms:
            raise ValueError("APPROVED_ENTRY_REQUIRES_APPROVED_TERMS")
        return self


class ScriptTerminologyMapV1(BaseModel):
    """A review proposal or a human-approved, facts-hash-bound term map."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["script-terminology-map/1.0"]
    case_id: StrictStr = Field(min_length=1)
    run_id: StrictStr = Field(min_length=1)
    facts_sha256: StrictStr
    source_language: StrictStr = Field(min_length=2)
    target_language: StrictStr = Field(min_length=2)
    review_status: Literal["pending", "approved"]
    reviewer: StrictStr | None
    reviewed_at: StrictStr | None
    entries: list[ScriptTerminologyEntryV1] = Field(min_length=1)

    @field_validator("facts_sha256")
    @classmethod
    def validate_facts_sha256(cls, value: str) -> str:
        if not _HEX_256.fullmatch(value):
            raise ValueError("facts_sha256 must be lowercase SHA-256 hex")
        return value

    @field_validator("reviewed_at")
    @classmethod
    def validate_reviewed_at(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("reviewed_at must be ISO-8601") from error
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("reviewed_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_review_state(self) -> "ScriptTerminologyMapV1":
        if not self.case_id.strip() or not self.run_id.strip():
            raise ValueError("run_id and case_id must be explicit and non-empty")
        if self.source_language.casefold() == self.target_language.casefold():
            raise ValueError("terminology map is only for cross-language review")
        entry_ids = [item.entry_id for item in self.entries]
        if len(set(entry_ids)) != len(entry_ids):
            raise ValueError("entry_id values must be unique")
        if self.review_status == "pending":
            if self.reviewer is not None or self.reviewed_at is not None:
                raise ValueError("pending terminology cannot carry approval metadata")
            if any(item.review_status != "pending" for item in self.entries):
                raise ValueError("pending map entries must remain pending")
        else:
            if not isinstance(self.reviewer, str) or not self.reviewer.strip():
                raise ValueError("approved terminology requires a reviewer")
            if self.reviewed_at is None:
                raise ValueError("approved terminology requires reviewed_at")
            if any(item.review_status != "approved" for item in self.entries):
                raise ValueError("approved map requires every entry to be approved")
        return self


def _canonical_field_values(claim: Mapping[str, Any], source_field: str) -> list[str]:
    attestation = claim.get("authority_attestation")
    scope = attestation.get("scope") if isinstance(attestation, Mapping) else None
    if not isinstance(scope, Mapping):
        scope = {}
    if source_field.startswith("authority_attestation.scope."):
        value = scope.get(source_field.rsplit(".", 1)[1])
        return [value] if isinstance(value, str) and value.strip() else []
    if source_field == "authority_attestation.attribution":
        value = attestation.get("attribution") if isinstance(attestation, Mapping) else None
        return [value] if isinstance(value, str) and value.strip() else []

    values: list[str] = []
    for evidence in claim.get("evidence", []):
        if not isinstance(evidence, Mapping):
            continue
        if source_field == "evidence.source_section":
            value = evidence.get("source_section")
            if isinstance(value, str) and value.strip():
                values.append(value)
        elif source_field == "evidence.evidence_period_matches":
            values.extend(value for value in evidence.get("evidence_period_matches", [])
                          if isinstance(value, str) and value.strip())
        elif source_field == "evidence.evidence_target_concept":
            value = evidence.get("evidence_target_concept")
            if isinstance(value, str) and value.strip():
                values.append(value)
        elif source_field == "evidence.explicit_values.unit":
            values.extend(value["unit"] for value in evidence.get("explicit_values", [])
                          if isinstance(value, Mapping) and isinstance(value.get("unit"), str)
                          and value["unit"].strip())
        elif source_field.startswith("evidence.revision_values."):
            revision = evidence.get("revision_values")
            key = source_field.rsplit(".", 1)[1]
            value = revision.get(key) if isinstance(revision, Mapping) else None
            if isinstance(value, str) and value.strip():
                values.append(value)
    return values


def _same_source_term(left: str, right: str) -> bool:
    return " ".join(left.split()).casefold() == " ".join(right.split()).casefold()


def _claim_is_authority_eligible(claim: Mapping[str, Any]) -> bool:
    if (claim.get("claim_type") != "fact" or claim.get("verification_status") != "verified"
            or claim.get("verification_basis") != "authoritative_primary_attestation"
            or claim.get("allowed_downstream") is not True):
        return False
    from fanglei.authority_safety import _atomic_evidence_rows

    attestation = claim.get("authority_attestation")
    return isinstance(attestation, Mapping) and _atomic_evidence_rows(dict(claim), dict(attestation)) is not None


def validate_script_terminology_map(
    value: ScriptTerminologyMapV1 | Mapping[str, Any],
    facts: Mapping[str, Any],
    *,
    expected_run_id: str,
    expected_case_id: str,
    facts_sha256: str,
    allowed_claim_ids: set[str] | None = None,
    require_approved: bool = True,
) -> ScriptTerminologyMapV1:
    """Validate structure, approval, identities, facts binding and claim scope."""
    try:
        terminology = (value if isinstance(value, ScriptTerminologyMapV1)
                       else ScriptTerminologyMapV1.model_validate(value))
    except Exception as error:
        raise ValueError(f"TERMINOLOGY_MAP_INVALID: {error}") from error
    if require_approved and terminology.review_status != "approved":
        raise ValueError("TERMINOLOGY_APPROVAL_REQUIRED")
    if (terminology.run_id != expected_run_id or terminology.case_id != expected_case_id
            or terminology.facts_sha256 != facts_sha256):
        raise ValueError("IDENTITY_OR_FACTS_HASH_MISMATCH")

    claims = {item.get("claim_id"): item for item in facts.get("claims", [])
              if isinstance(item, Mapping) and isinstance(item.get("claim_id"), str)}
    for entry in terminology.entries:
        for claim_id in entry.claim_ids:
            claim = claims.get(claim_id)
            if claim is None or not _claim_is_authority_eligible(claim):
                raise ValueError("TERMINOLOGY_CLAIM_NOT_AUTHORITY_ELIGIBLE")
            if allowed_claim_ids is not None and claim_id not in allowed_claim_ids:
                raise ValueError("TERMINOLOGY_CLAIM_SCOPE_MISMATCH")
            if not any(_same_source_term(entry.source_term, candidate)
                       for candidate in _canonical_field_values(claim, entry.source_field)):
                raise ValueError("SOURCE_TERM_NOT_IN_BOUND_CLAIM")
    return terminology


def build_script_terminology_proposal(
    *,
    facts: Mapping[str, Any],
    run_id: str,
    case_id: str,
    facts_sha256: str,
    selected_claim_ids: Sequence[str],
    source_language: str,
    target_language: str,
    proposed_terms: Mapping[tuple[str, str, str], Sequence[str]] | None = None,
) -> ScriptTerminologyMapV1:
    """Build a deterministic pending proposal from selected eligible claims.

    Candidate translations are explicit caller-provided proposals. This helper
    extracts verified source terms but never translates or approves them.
    """
    proposed_terms = proposed_terms or {}
    claims = {item.get("claim_id"): item for item in facts.get("claims", [])
              if isinstance(item, Mapping) and isinstance(item.get("claim_id"), str)}
    grouped: dict[tuple[str, str, str], set[str]] = {}
    selected = list(dict.fromkeys(selected_claim_ids))
    if not selected:
        raise ValueError("TERMINOLOGY_PROPOSAL_REQUIRES_SELECTED_CLAIMS")
    for claim_id in selected:
        claim = claims.get(claim_id)
        if claim is None or not _claim_is_authority_eligible(claim):
            raise ValueError("TERMINOLOGY_PROPOSAL_CLAIM_NOT_AUTHORITY_ELIGIBLE")
        for role, fields in _PROPOSAL_SOURCE_FIELDS.items():
            applicable_fields = fields
            if role == "reporting_scope":
                applicable_fields = (fields[0],) if _canonical_field_values(
                    claim, fields[0]
                ) else (fields[1],)
            for source_field in applicable_fields:
                for term in _canonical_field_values(claim, source_field):
                    grouped.setdefault((role, source_field, term), set()).add(claim_id)
    rows: list[dict[str, Any]] = []
    for role, source_field, term in sorted(grouped):
        claim_ids = sorted(grouped[(role, source_field, term)])
        digest = hashlib.sha256(
            json.dumps([role, source_field, term, claim_ids], ensure_ascii=False,
                       separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:12]
        proposed = list(dict.fromkeys(proposed_terms.get((role, source_field, term), ())))
        rows.append({
            "entry_id": f"term_{digest}",
            "claim_ids": claim_ids,
            "source_term": term,
            "source_field": source_field,
            "semantic_role": role,
            "proposed_target_terms": proposed,
            "approved_target_terms": [],
            "review_status": "pending",
        })
    return ScriptTerminologyMapV1.model_validate({
        "schema_version": "script-terminology-map/1.0",
        "case_id": case_id,
        "run_id": run_id,
        "facts_sha256": facts_sha256,
        "source_language": source_language,
        "target_language": target_language,
        "review_status": "pending",
        "reviewer": None,
        "reviewed_at": None,
        "entries": rows,
    })


def record_reviewed_script_terminology_map(
    run_dir: Path, value: ScriptTerminologyMapV1 | Mapping[str, Any]
) -> Path:
    """Register an explicitly human-approved map against the run's current Facts.

    This function never upgrades a pending proposal or supplies reviewer data.
    The caller must provide the complete approved artifact.
    """
    from fanglei.artifact_registry import ArtifactRegistry
    from fanglei.models import RunManifest

    run_dir = Path(run_dir)
    manifest = RunManifest.model_validate_json((run_dir / "run.json").read_text(encoding="utf-8"))
    registry = ArtifactRegistry(
        run_dir, manifest,
        human_angle_selection_mode=(run_dir / "angle_selection.json").is_file(),
        script_terminology_mode=True,
    )
    registry.validate("facts.json")
    facts = registry.read_json("facts.json")
    current_case_id = None
    if (run_dir / "research_focus.json").is_file():
        registry.validate("research_focus.json")
        current_case_id = registry.read_json("research_focus.json").get("case_id")
    if current_case_id is None:
        try:
            registry.validate("sources.json")
            policy = registry.read_json("sources.json").get("source_policy")
            current_case_id = policy.get("case_id") if isinstance(policy, Mapping) else None
        except Exception:
            current_case_id = None
    if not isinstance(current_case_id, str) or not current_case_id.strip():
        raise ValueError("TERMINOLOGY_CASE_IDENTITY_UNPROVEN")
    allowed_claim_ids = None
    if (run_dir / "angle_selection.json").is_file():
        registry.validate("angle_selection.json")
        selected_id = registry.read_json("angle_selection.json").get("selected_angle_id")
        angle_rows = registry.read_json("angles.json").get("candidates", [])
        selected_rows = [row for row in angle_rows if row.get("angle_id") == selected_id]
        if len(selected_rows) != 1:
            raise ValueError("TERMINOLOGY_SELECTED_ANGLE_UNPROVEN")
        allowed_claim_ids = set(selected_rows[0].get("supporting_claim_ids", []))
    terminology = validate_script_terminology_map(
        value, facts, expected_run_id=manifest.run_id, expected_case_id=current_case_id,
        facts_sha256=manifest.artifacts["facts.json"].content_hash,
        allowed_claim_ids=allowed_claim_ids,
        require_approved=True,
    )
    registry.write_json(
        "script_terminology.json", terminology.model_dump(mode="json"),
        "script_terminology_review", force=True,
    )
    # A review is a new script input even when the first map has no prior hash
    # to trigger the registry's ordinary content-change invalidation.
    registry.invalidate_descendants("script_terminology.json")
    registry.save_manifest()
    return run_dir / "script_terminology.json"
