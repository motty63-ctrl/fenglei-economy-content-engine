from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from fanglei.artifacts import sha256_text
from fanglei.evidence_policy import gate_evidence
from fanglei.research import FetchedDocument, RuleBasedEvidenceExtractor, verify_claims


ROOT = Path(__file__).resolve().parents[1]


def _evidence() -> dict:
    return {
        "source_id": "src-1",
        "evidence_text": "The September SEP reports the projection.",
        "source_section": "Table 1",
        "paragraph_locator": "row 1",
        "published_at": "2026-09-16",
        "retrieved_at": "2026-09-24T10:00:00+08:00",
        "original_url": "https://www.federalreserve.gov/example",
        "relation": "supports",
        "document_hash": "a" * 64,
        "document_format": "html",
        "evidence_origin": "original_document",
        "evidence_eligible": True,
        "eligibility_reason": "document_text_resolved",
    }


def _claim(*, status="verified", basis=None, allowed=True, claim_type="fact") -> dict:
    script_state = {
        "verified": {"status": "assertion_allowed", "reason": "verified economic fact"},
        "conflicted": {"status": "blocked", "reason": "independent sources disagree"},
        "unverified": {"status": "disclosure_only", "required_label": "待确认", "reason": "insufficient eligible evidence"},
    }[status]
    claim = {
        "claim_id": "claim_001",
        "claim_text": "The September SEP reports the projection.",
        "claim_type": claim_type,
        "verification_status": status,
        "domain": "economic_data",
        "risk_level": "high",
        "source_ids": ["src-1"],
        "evidence": [_evidence()],
        "verification_reason": "Directly supported by the approved source.",
        "allowed_downstream": allowed,
        "script_usage": script_state,
    }
    if basis is not None:
        claim["verification_basis"] = basis
        claim["authority_attestation"] = None
    if basis == "authoritative_primary_attestation":
        claim["authority_attestation"] = {
            "kind": "document_report",
            "source_ids": ["src-1"],
            "attribution": "The September SEP reports",
            "scope": {
                "subject": "US real GDP growth projection",
                "measure": "real GDP growth",
                "period": "2026",
                "unit": "percent",
                "statistic": "median participant projection",
                "certainty": "projected",
            },
        }
    return claim


def _facts(version: str, claim: dict) -> dict:
    return {
        "schema_version": version,
        "run_id": "run-1",
        "checked_at": "2026-09-24T10:00:00+08:00",
        "policy_version": "economics-v1.1",
        "summary": {"verified": 1, "conflicted": 0, "unverified": 0},
        "claims": [claim],
    }


def _schema(name: str) -> dict:
    return json.loads((ROOT / "docs" / "v0.2" / name).read_text("utf-8"))


def test_native_facts_21_schema_matches_current_runtime_shape() -> None:
    facts = _facts("2.1", _claim())

    jsonschema.validate(facts, _schema("native-facts-2.1.schema.json"))


def test_native_facts_21_schema_validates_actual_current_verifier_output() -> None:
    text = "GDP grew 2.8% in 2024."
    document = FetchedDocument(
        "src-1",
        "https://example.gov/gdp",
        "GDP release",
        text,
        "official",
        "2024-12-31",
        "2026-09-24T10:00:00+08:00",
        "https://example.gov/gdp",
        document_hash=sha256_text(text),
    )
    evidence = RuleBasedEvidenceExtractor().extract([document], ["GDP in 2024"])
    gated = gate_evidence(evidence, [document])
    facts = verify_claims(gated, {"src-1": True}, minimum_sources_met=False)
    facts.update({"run_id": "run-1", "checked_at": "2026-09-24T10:00:00+08:00"})

    jsonschema.validate(facts, _schema("native-facts-2.1.schema.json"))


def test_native_facts_21_does_not_silently_accept_new_basis() -> None:
    facts = _facts("2.1", _claim(basis="independent_corroboration"))

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(facts, _schema("native-facts-2.1.schema.json"))


@pytest.mark.parametrize(
    ("status", "basis", "allowed", "claim_type"),
    [
        ("verified", "independent_corroboration", True, "fact"),
        ("verified", "authoritative_primary_attestation", True, "fact"),
        ("verified", "authoritative_primary_attestation", False, "fact"),
        ("conflicted", "none", False, "fact"),
        ("unverified", "none", False, "fact"),
    ],
)
def test_native_facts_22_accepts_valid_status_basis_combinations(
    status: str, basis: str, allowed: bool, claim_type: str
) -> None:
    facts = _facts("2.2", _claim(status=status, basis=basis, allowed=allowed, claim_type=claim_type))

    jsonschema.validate(facts, _schema("native-facts-2.2.schema.json"))


@pytest.mark.parametrize(
    ("status", "basis", "allowed", "claim_type"),
    [
        ("verified", "none", False, "fact"),
        ("conflicted", "independent_corroboration", False, "fact"),
        ("unverified", "authoritative_primary_attestation", False, "fact"),
        ("unverified", "none", True, "fact"),
        ("verified", "independent_corroboration", True, "inference"),
    ],
)
def test_native_facts_22_rejects_invalid_status_basis_combinations(
    status: str, basis: str, allowed: bool, claim_type: str
) -> None:
    facts = _facts("2.2", _claim(status=status, basis=basis, allowed=allowed, claim_type=claim_type))

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(facts, _schema("native-facts-2.2.schema.json"))


def test_native_facts_22_requires_machine_readable_authority_attestation() -> None:
    facts = _facts("2.2", _claim(basis="authoritative_primary_attestation"))
    del facts["claims"][0]["authority_attestation"]

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(facts, _schema("native-facts-2.2.schema.json"))


def test_native_facts_22_rejects_authority_attestation_under_another_basis() -> None:
    facts = _facts("2.2", _claim(basis="authoritative_primary_attestation"))
    facts["claims"][0]["verification_basis"] = "independent_corroboration"

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(facts, _schema("native-facts-2.2.schema.json"))


def test_checkpoint_import_formal_facts_21_preserves_basis_and_legacy_formal_20_stays_frozen() -> None:
    imported = {
        "schema_version": "checkpoint-import-facts/2.1",
        "run_id": "checkpoint-import-staging",
        "checked_at": "2026-09-24T10:00:00+08:00",
        "policy_version": "approved-checkpoint-import/2.1",
        "summary": {"source": "approved_checkpoint", "claim_count": 1},
        "claims": [{
            "claim_id": "claim_001",
            "claim_external_id": "C-1",
            "claim_text": "The September SEP reports the projection.",
            "claim_type": "fact",
            "verification_status": "verified",
            "verification_basis": "authoritative_primary_attestation",
            "authority_attestation": {
                "kind": "document_report",
                "source_ids": ["src-1"],
                "attribution": "The September SEP reports",
                "scope": {
                    "subject": "US real GDP growth projection",
                    "measure": "real GDP growth",
                    "period": "2026",
                    "unit": "percent",
                    "statistic": "median participant projection",
                    "certainty": "projected",
                },
            },
            "source_ids": ["src-1"],
            "evidence": [{
                "source_id": "src-1",
                "evidence_text": "The September SEP reports the projection.",
                "source_section": "Table 1",
                "paragraph_locator": "row 1",
                "published_at": "2026-09-16",
                "retrieved_at": "2026-09-24T10:00:00+08:00",
                "original_url": "https://www.federalreserve.gov/example",
                "relation": "supports",
            }],
            "verification_reason": "The approved primary document directly reports this projection.",
            "allowed_downstream": True,
        }],
    }
    formal_20_schema = _schema("facts.schema.json")
    formal_21_schema = _schema("checkpoint-import-facts-2.1.schema.json")

    assert formal_20_schema["properties"]["schema_version"]["const"] == "2.0"
    jsonschema.validate(imported, formal_21_schema)

    imported["claims"][0]["verification_basis"] = "none"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(imported, formal_21_schema)
