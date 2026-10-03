from __future__ import annotations

from copy import deepcopy

import pytest

from fanglei.authority_safety import authority_text_issues
from fanglei.angle_policy import score_angles
from fanglei.content_models import AngleProposal, ScriptReadyClaim
from fanglei.evidence_targets import atomic_proposition_spans


ATTRIBUTION = "National Statistical Office"
PARAGRAPH = (
    "Retail sales rose by 2.4 percent in June, and inventory declined by 0.7 percent in June."
)
SCOPE_RETAIL = {
    "subject": "retail sales",
    "measure": "sales",
    "period": "June",
    "unit": "percent",
    "statistic": None,
    "certainty": "rose",
}
SCOPE_INVENTORY = {
    "subject": "inventory",
    "measure": "inventory",
    "period": "June",
    "unit": "percent",
    "statistic": None,
    "certainty": "declined",
}


def _atomic_claim(
    claim_id: str,
    evidence_text: str = PARAGRAPH,
    *,
    proposition_index: int = 0,
    scope: dict | None = None,
    status: str = "verified",
    allowed_downstream: bool = True,
) -> dict:
    spans = atomic_proposition_spans(evidence_text)
    proposition_span = spans[proposition_index]
    selected_scope = deepcopy(scope or (SCOPE_RETAIL if proposition_index == 0 else SCOPE_INVENTORY))
    evidence = {
        "source_id": "src_001",
        "evidence_eligible": True,
        "evidence_text": evidence_text,
        "original_url": "https://example.test/release",
        "document_hash": "a" * 64,
        "paragraph_locator": "line:12-13",
        "source_section_locator": "line:12",
        "evidence_target_id": f"target-{claim_id}",
        "evidence_kind": "narrative_sentence",
        "authority_scope_candidate": deepcopy(selected_scope),
        "proposition_span": deepcopy(proposition_span),
    }
    return {
        "claim_id": claim_id,
        "claim_text": f'{ATTRIBUTION}: "{proposition_span["text"]}"',
        "verification_status": status,
        "verification_basis": "authoritative_primary_attestation",
        "allowed_downstream": allowed_downstream,
        "source_ids": ["src_001"],
        "evidence": [evidence],
        "authority_attestation": {
            "kind": "document_report",
            "source_ids": ["src_001"],
            "attribution": ATTRIBUTION,
            "scope": deepcopy(selected_scope),
        },
    }


def _attributed(claim: dict) -> str:
    return claim["claim_text"]


def test_atomic_document_report_uses_verified_proposition_not_full_context() -> None:
    claim = _atomic_claim("claim_retail")

    assert claim["evidence"][0]["evidence_text"] not in _attributed(claim)
    assert authority_text_issues(_attributed(claim), claim) == ()


def test_unapproved_neighboring_clause_is_rejected() -> None:
    retail = _atomic_claim("claim_retail")
    inventory = _atomic_claim("claim_inventory", proposition_index=1)
    downstream = f'{_attributed(retail)}; {inventory["evidence"][0]["proposition_span"]["text"]}'

    assert "AUTHORITY_SCOPE_MISMATCH" in authority_text_issues(downstream, retail)


def test_independently_verified_neighboring_claim_can_be_used_together() -> None:
    retail = _atomic_claim("claim_retail")
    inventory = _atomic_claim("claim_inventory", proposition_index=1)
    downstream = f'{_attributed(retail)}; {inventory["claim_text"]}'

    assert authority_text_issues(downstream, retail, related_claims=[inventory]) == ()


def test_two_atomic_claims_sharing_one_locator_work_independently() -> None:
    july_text = (
        "The June estimate was revised up by 11,000 jobs, from +20,000 to +31,000, "
        "and the July estimate was revised up by 44,000 jobs, from -23,000 to +21,000."
    )
    spans = atomic_proposition_spans(july_text)
    june = _atomic_claim("claim_june_revision", july_text, proposition_index=0, scope={
        "subject": "June", "measure": "payroll revision", "period": "June",
        "unit": "jobs", "statistic": None, "certainty": "revised up",
    })
    july = _atomic_claim("claim_july_revision", july_text, proposition_index=1, scope={
        "subject": "July", "measure": "payroll revision", "period": "July",
        "unit": "jobs", "statistic": None, "certainty": "revised up",
    })

    assert len(spans) == 2
    assert authority_text_issues(_attributed(june), june) == ()
    assert authority_text_issues(_attributed(july), july) == ()


def test_atomic_comparison_reads_selected_cell_span_not_neighboring_row_values() -> None:
    scope = {
        "subject": "retail sales", "measure": "median projection", "period": "2026",
        "unit": "percent", "statistic": "median", "certainty": "projection",
    }
    evidence = []
    for source_id, release, value, neighbor in (
        ("src_june", "June", "2.2", "99.0"),
        ("src_september", "September", "2.4", "88.0"),
    ):
        evidence_text = f"{release} 2026 median retail sales projection: {value} percent; other row: {neighbor} percent"
        start = evidence_text.index(value)
        evidence.append({
            "source_id": source_id,
            "evidence_eligible": True,
            "evidence_text": evidence_text,
            "original_url": f"https://example.test/{release.lower()}",
            "document_hash": ("b" if source_id == "src_june" else "c") * 64,
            "paragraph_locator": f"table:{release}:row-2026",
            "source_section_locator": f"table:{release}",
            "evidence_target_id": f"retail-sales-{release.lower()}",
            "evidence_kind": "table_cell",
            "authority_scope_candidate": deepcopy(scope),
            "proposition_span": {"start": start, "end": start + len(value), "text": value},
        })
    claim = {
        "claim_id": "claim_retail_projection_change",
        "claim_text": (
            "National Statistical Office median projection for retail sales in 2026 "
            "changed from 2.2 percent to 2.4 percent."
        ),
        "verification_status": "verified",
        "verification_basis": "authoritative_primary_attestation",
        "allowed_downstream": True,
        "source_ids": ["src_june", "src_september"],
        "evidence": evidence,
        "authority_attestation": {
            "kind": "deterministic_document_comparison",
            "source_ids": ["src_june", "src_september"],
            "attribution": "National Statistical Office",
            "scope": deepcopy(scope),
        },
    }

    assert authority_text_issues(claim["claim_text"], claim) == ()


def test_historical_comparison_tail_cannot_enter_atomic_claim() -> None:
    evidence_text = (
        "Sector employment rose by 5,000 jobs in August, "
        "compared with an average gain of 1,200 jobs over the prior 12 months."
    )
    claim = _atomic_claim("claim_sector", evidence_text, scope={
        "subject": "sector employment", "measure": "employment", "period": "August",
        "unit": "jobs", "statistic": None, "certainty": "rose",
    })
    downstream = f'{_attributed(claim)}, {evidence_text[claim["evidence"][0]["proposition_span"]["end"]:].strip()}'

    assert "AUTHORITY_SCOPE_MISMATCH" in authority_text_issues(downstream, claim)


@pytest.mark.parametrize("status,basis,allowed", [
    ("unverified", "authoritative_primary_attestation", True),
    ("conflicted", "none", True),
    ("verified", "none", True),
    ("verified", "authoritative_primary_attestation", False),
    (None, "authoritative_primary_attestation", True),
])
def test_ineligible_atomic_claim_fails_closed(status: str | None, basis: str, allowed: bool) -> None:
    claim = _atomic_claim("claim_retail", status=status, allowed_downstream=allowed)
    claim["verification_basis"] = basis
    if status is None:
        claim.pop("verification_status")

    assert "AUTHORITY_SCOPE_MISMATCH" in authority_text_issues(_attributed(claim), claim)


def test_corrupted_atomic_span_fails_closed() -> None:
    claim = _atomic_claim("claim_retail")
    claim["evidence"][0]["proposition_span"]["text"] = "Retail sales rose by 2.4 percent"

    assert "AUTHORITY_SCOPE_MISMATCH" in authority_text_issues(_attributed(claim), claim)


def test_missing_span_on_targeted_atomic_evidence_fails_closed() -> None:
    claim = _atomic_claim("claim_retail")
    claim["evidence"][0].pop("proposition_span")

    assert "AUTHORITY_SCOPE_MISMATCH" in authority_text_issues(_attributed(claim), claim)


def test_atomic_scope_candidate_must_match_attestation() -> None:
    claim = _atomic_claim("claim_retail")
    claim["evidence"][0]["authority_scope_candidate"]["period"] = "July"

    assert "AUTHORITY_SCOPE_MISMATCH" in authority_text_issues(_attributed(claim), claim)


def test_atomic_claim_requires_stable_locator_and_source_hash() -> None:
    claim = _atomic_claim("claim_retail")
    claim["evidence"][0].pop("paragraph_locator")
    claim["evidence"][0].pop("source_section_locator")
    claim["evidence"][0].pop("document_hash")

    assert "AUTHORITY_SCOPE_MISMATCH" in authority_text_issues(_attributed(claim), claim)


def test_legacy_claim_without_atomic_metadata_keeps_full_excerpt_rule() -> None:
    legacy = _atomic_claim("claim_legacy")
    evidence = legacy["evidence"][0]
    evidence.pop("proposition_span")
    evidence.pop("evidence_target_id")
    evidence.pop("evidence_kind")
    legacy["claim_text"] = f'{ATTRIBUTION}: "{PARAGRAPH}"'

    assert authority_text_issues(legacy["claim_text"], legacy) == ()
    assert "AUTHORITY_SCOPE_MISMATCH" in authority_text_issues(
        'National Statistical Office: "Retail sales rose by 2.4 percent in June"', legacy
    )


def test_angle_supporting_claims_authorize_only_their_own_atomic_propositions() -> None:
    retail = _atomic_claim("claim_retail")
    inventory = _atomic_claim("claim_inventory", proposition_index=1)
    claims = [ScriptReadyClaim.model_validate(retail), ScriptReadyClaim.model_validate(inventory)]
    proposal = AngleProposal(
        angle_id="angle_001",
        title="Two measures in one release",
        hook="What did the report record?",
        core_question="What changed in the report?",
        core_insight=f'{retail["claim_text"]}\n{inventory["claim_text"]}',
        hook_mechanism="paired_record_reading",
        audience_takeaway="Keep each reported measure in its documented scope.",
        narrative_framing="paired_document_reports",
        supporting_claim_ids=["claim_retail", "claim_inventory"],
        audience_relevance=4,
        novelty=3,
        hook_strength=3,
        visual_potential=3,
        explainability=4,
    )
    scored = score_angles([proposal], tuple(claims), "unrelated source text")[0]

    assert scored.eligibility == "eligible"
    assert "AUTHORITY_SCOPE_MISMATCH" not in scored.rejection_codes


def test_angle_cannot_use_neighbor_atom_without_its_claim_reference() -> None:
    retail = _atomic_claim("claim_retail")
    inventory = _atomic_claim("claim_inventory", proposition_index=1)
    claims = [ScriptReadyClaim.model_validate(retail), ScriptReadyClaim.model_validate(inventory)]
    proposal = AngleProposal(
        angle_id="angle_001",
        title="Retail sales in June",
        hook="What did the report record?",
        core_question="What changed in the report?",
        core_insight=f'{retail["claim_text"]}\n{inventory["evidence"][0]["proposition_span"]["text"]}',
        hook_mechanism="single_record_reading",
        audience_takeaway="Stay within the verified record.",
        narrative_framing="document_report",
        supporting_claim_ids=["claim_retail"],
        audience_relevance=4,
        novelty=3,
        hook_strength=3,
        visual_potential=3,
        explainability=4,
    )
    scored = score_angles([proposal], tuple(claims), "unrelated source text")[0]

    assert scored.eligibility == "rejected"
    assert "AUTHORITY_SCOPE_MISMATCH" in scored.rejection_codes
