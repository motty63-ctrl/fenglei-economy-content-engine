import json

from fanglei.artifacts import sha256_bytes, sha256_text
from fanglei.evidence_policy import gate_evidence, is_script_ready
from fanglei.providers.official import request_fingerprint
from fanglei.research import FetchedDocument, verify_claims


def _api_document() -> FetchedDocument:
    raw = json.dumps([
        {"page": 1},
        [{"date": "2024", "value": 2.79318715363841}],
    ])
    text = "World Bank reports United States real GDP growth was 2.8% in 2024."
    return FetchedDocument(
        "src_api", "https://data.worldbank.org/x", "World Bank", text,
        "international_organization", None, "2026-09-09T00:00:00+08:00",
        "https://api.worldbank.org/v2/x", document_format="api", retrieval_method="api",
        document_hash=sha256_text(raw), api_endpoint="https://api.worldbank.org/v2/x",
        request_fingerprint=request_fingerprint("https://api.worldbank.org/v2/x"),
        api_observations=[{"json_pointer": "/1/0/value", "observation": 2.79318715363841}],
        raw_content=raw,
    )


def _api_evidence() -> dict:
    doc = _api_document()
    return {
        "source_id": doc.source_id,
        "evidence_text": doc.text,
        "evidence_origin": "official_api",
        "document_hash": doc.document_hash,
        "api_endpoint": doc.api_endpoint,
        "request_fingerprint": doc.request_fingerprint,
        "json_pointer": "/1/0/value",
        "observation": 2.79318715363841,
        "claim_type": "fact",
        "claim_key": "us|annual_real_gdp_growth|2024",
        "claim_values": ["2.8"],
        "retrieved_at": doc.retrieved_at,
        "original_url": doc.original_url,
    }


def test_api_evidence_resolves_to_exact_json_observation() -> None:
    gated = gate_evidence([_api_evidence()], [_api_document()])
    assert gated[0]["evidence_eligible"] is True
    assert gated[0]["eligibility_reason"] == "api_observation_resolved"


def test_wrong_api_pointer_or_observation_cannot_verify() -> None:
    evidence = _api_evidence()
    evidence["observation"] = 2.9
    gated = gate_evidence([evidence], [_api_document()])
    assert gated[0]["evidence_eligible"] is False
    facts = verify_claims(gated, {"src_api": True}, minimum_sources_met=True)
    assert facts["claims"][0]["verification_status"] == "unverified"
    assert facts["claims"][0]["allowed_downstream"] is False


def test_api_request_fingerprint_must_match_sanitized_endpoint() -> None:
    evidence = _api_evidence()
    evidence["request_fingerprint"] = "0" * 64
    gated = gate_evidence([evidence], [_api_document()])
    assert gated[0]["evidence_eligible"] is False
    assert gated[0]["eligibility_reason"] == "api_observation_unresolved"


def test_search_snippet_can_never_become_evidence() -> None:
    evidence = _api_evidence()
    evidence["evidence_origin"] = "search_snippet"
    gated = gate_evidence([evidence], [_api_document()])
    assert gated[0]["evidence_eligible"] is False
    assert gated[0]["eligibility_reason"] == "search_snippet_ineligible"


def test_pdf_evidence_requires_matching_page_text_and_hash() -> None:
    page_text = "Real GDP grew 2.8 percent in 2024."
    raw = b"%PDF-test"
    doc = FetchedDocument(
        "src_pdf", "https://oecd.org/report.pdf", "OECD", page_text,
        "international_organization", None, "now", None, document_format="pdf",
        retrieval_method="pdf", document_hash=sha256_bytes(raw),
        pages=[{"page_number": 7, "text": page_text, "content_hash": sha256_text(page_text)}],
        raw_bytes=raw,
    )
    evidence = {
        "source_id": "src_pdf", "evidence_text": page_text, "evidence_origin": "original_document",
        "document_hash": doc.document_hash, "page_number": 7,
        "page_content_hash": sha256_text(page_text), "claim_type": "fact",
    }
    assert gate_evidence([evidence], [doc])[0]["evidence_eligible"] is True
    evidence["page_number"] = 8
    assert gate_evidence([evidence], [doc])[0]["evidence_eligible"] is False


def test_script_ready_contract_blocks_unverified_conflicted_and_legacy_claims() -> None:
    assert is_script_ready({"verification_status": "verified", "allowed_downstream": True}) is True
    assert is_script_ready({"verification_status": "unverified", "allowed_downstream": False}) is False
    assert is_script_ready({"verification_status": "conflicted", "allowed_downstream": False}) is False
    assert is_script_ready({"verification_status": "verified"}) is False


def test_conflicted_claim_is_blocked_for_factual_assertion() -> None:
    evidence = [
        {"source_id": "a", "evidence_text": "Real GDP grew 2.8% in 2024.", "claim_type": "fact", "claim_key": "gdp-2024", "claim_values": ["2.8"], "evidence_eligible": True},
        {"source_id": "b", "evidence_text": "Real GDP grew 2.9% in 2024.", "claim_type": "fact", "claim_key": "gdp-2024", "claim_values": ["2.9"], "evidence_eligible": True},
    ]
    facts = verify_claims(evidence, {"a": True, "b": True})
    assert facts["schema_version"] == "2.1"
    claim = facts["claims"][0]
    assert claim["verification_status"] == "conflicted"
    assert claim["allowed_downstream"] is False
    assert claim["script_usage"]["status"] == "blocked"
