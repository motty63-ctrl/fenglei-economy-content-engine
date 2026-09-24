from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import jsonschema
import pytest

from fanglei.artifacts import sha256_bytes, sha256_text
from fanglei.research import (
    FetchedDocument,
    RuleBasedEvidenceExtractor,
    deduplicate_sources,
    evidence_claim_key,
    verify_claims_v22,
)
from fanglei.source_contract import (
    authoritative_source_package_sha256,
    build_sources_artifact_v21,
    validate_sources_artifact_v21,
)


ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "run-authority-1"
CASE_ID = "case-authority-1"
CHECKED_AT = "2026-09-24T10:00:00+08:00"


def _documents(*, federal: bool = True) -> list[FetchedDocument]:
    host = "www.federalreserve.gov" if federal else None
    rows = []
    contents = [
        "Federal Reserve 2026 median real GDP growth projection is 2.2 percent.",
        "Federal Reserve 2026 median real GDP growth projection is 2.3 percent.",
        "Federal Reserve statement says inflation remains elevated in 2026.",
        "Federal Reserve second statement says inflation remains elevated in 2026.",
    ]
    if not federal:
        contents = [
            "National statistical office release: 2026 GDP growth estimate equals 2.2 percent.",
            "International organization database: annual output series records 2.2 percent for 2026.",
            "Corporate annual filing: macroeconomic outlook section cites 2.2 percent GDP growth for 2026.",
            "Independent research institute report: its 2026 GDP table records a 2.2 percent estimate.",
        ]
    paths = [
        "/sep/june.html",
        "/sep/september.html",
        "/statement/june.html",
        "/statement/september.html",
    ]
    dates = ["2026-06-17", "2026-09-16", "2026-06-17", "2026-09-16"]
    for index, (content, path, published_at) in enumerate(zip(contents, paths, dates), 1):
        domain = host if federal else f"source{index}.example"
        url = f"https://{domain}{path}"
        raw = f'{{"source": {index}}}'
        rows.append(FetchedDocument(
            source_id=f"src-{index}",
            url=url,
            title=f"Federal Reserve source {index}" if federal else f"Source {index}",
            text=content,
            source_type="official",
            published_at=published_at,
            retrieved_at=CHECKED_AT,
            original_url=url,
            document_hash=sha256_text(content),
            raw_content=raw,
        ))
    return rows


def _index(documents: list[FetchedDocument]) -> dict:
    indexed = []
    for doc in documents:
        text_hash = sha256_text(doc.text)
        indexed.append({
            "source_id": doc.source_id,
            "url": doc.url,
            "original_url": doc.original_url,
            "document_hash": doc.document_hash,
            "path": f"source_documents/{doc.source_id}.md",
            "content_hash": text_hash,
            "files": [
                {"role": "normalized_text", "path": f"source_documents/{doc.source_id}.md", "content_hash": text_hash},
                {"role": "raw_response", "path": f"source_documents/raw/{doc.source_id}.json", "content_hash": sha256_text(doc.raw_content or "")},
            ],
        })
    return {"schema_version": "2.1", "fetch_errors": [], "documents": indexed}


def _policy(documents: list[FetchedDocument]) -> dict:
    roles = ["june_sep", "september_sep", "june_statement", "september_statement"]
    body = {
        "name": "authoritative_primary_set",
        "version": "1.0",
        "run_id": RUN_ID,
        "case_id": CASE_ID,
        "institution": {"institution_id": "federal-reserve", "display_name": "Federal Reserve"},
        "approved_documents": [
            {
                "source_id": doc.source_id,
                "url": doc.url,
                "document_identity": f"fed-doc-{index}",
                "evidence_role": roles[index - 1],
                "release_date": doc.published_at,
                "classification": "official_primary",
                "source_text_sha256": sha256_text(doc.text),
                "raw_capture_bytes_sha256": sha256_text(doc.raw_content or ""),
            }
            for index, doc in enumerate(documents, 1)
        ],
    }
    return {
        **body,
        "approval": {
            "status": "approved",
            "reviewer": "reviewer-1",
            "approved_at": CHECKED_AT,
            "rationale": "Exact official primary document package for this run.",
            "package_sha256": authoritative_source_package_sha256(body),
        },
    }


def _source_artifact(documents: list[FetchedDocument] | None = None, *, source_policy=None) -> tuple[dict, list[FetchedDocument], dict]:
    documents = documents or _documents()
    rows = deduplicate_sources(documents)
    index = _index(documents)
    artifact = build_sources_artifact_v21(
        rows,
        documents=documents,
        document_index=index,
        run_id=RUN_ID,
        case_id=CASE_ID if source_policy and source_policy.get("name") == "authoritative_primary_set" else None,
        source_policy=source_policy,
    )
    return artifact, documents, index


def _scope() -> dict:
    return {
        "subject": "Federal Reserve 2026 median real GDP growth projection",
        "measure": "real GDP growth",
        "period": "2026",
        "unit": "percent",
        "statistic": "median",
        "certainty": "projection",
    }


def _evidence(doc: FetchedDocument, text: str, claim_key: str, *, role="supports") -> dict:
    return {
        "source_id": doc.source_id,
        "claim_key": claim_key,
        "claim_type": "fact",
        "evidence_text": text,
        "source_section": "Table 1",
        "paragraph_locator": "row 1",
        "published_at": doc.published_at,
        "retrieved_at": doc.retrieved_at,
        "original_url": doc.url,
        "relation": role,
        "document_hash": doc.document_hash,
        "document_format": "html",
        "evidence_origin": "original_document",
        "evidence_eligible": True,
        "eligibility_reason": "document_text_resolved",
    }


def _authority_candidate(claim_text: str, source_ids: list[str], kind="document_report") -> dict:
    return {
        "claim_text": claim_text,
        "claim_type": "fact",
        "authority_attestation": {
            "kind": kind,
            "source_ids": source_ids,
            "attribution": "Federal Reserve",
            "scope": _scope(),
        },
    }


def _verify_authority(evidence, artifact, documents, index, claims):
    return verify_claims_v22(
        evidence,
        {row["source_id"]: row for row in artifact["sources"]},
        artifact,
        documents,
        index,
        run_id=RUN_ID,
        case_id=CASE_ID,
        authority_claims=claims,
        checked_at=CHECKED_AT,
    )


def test_default_sources_21_keeps_three_independent_source_threshold() -> None:
    documents = _documents(federal=False)[:3]
    artifact, _, _ = _source_artifact(documents)

    assert artifact["source_policy"] == {"name": "independent_sources", "version": "1.0"}
    assert artifact["package_admissibility"] == "admissible"
    assert artifact["independent_source_count"] == 3
    assert artifact["selection_status"] == "selected"


def test_authority_package_is_admissible_without_inflating_independence() -> None:
    documents = _documents()
    artifact, _, _ = _source_artifact(documents, source_policy=_policy(documents))
    schema = json.loads((ROOT / "docs/v0.2/sources-2.1.schema.json").read_text("utf-8"))
    jsonschema.validate(artifact, schema)

    assert artifact["package_admissibility"] == "admissible"
    assert artifact["independent_source_count"] == 1
    assert artifact["selection_status"] == "insufficient_sources"


def test_runtime_recomputes_independence_rows_without_changing_deduplication() -> None:
    artifact, documents, index = _source_artifact(source_policy=_policy(_documents()))
    forged = deepcopy(artifact)
    forged["sources"][1]["counts_as_independent"] = True
    forged["sources"][1]["independence_key"] = "institution:federalreserve.gov:forged"
    forged["independent_source_count"] = 2
    forged["selection_status"] = "insufficient_sources"

    with pytest.raises(ValueError, match="deduplication algorithm"):
        verify_claims_v22(
            [],
            {row["source_id"]: row for row in forged["sources"]},
            forged,
            documents,
            index,
            run_id=RUN_ID,
            case_id=CASE_ID,
            checked_at=CHECKED_AT,
        )


@pytest.mark.parametrize("identity_field", ["run_id", "case_id"])
def test_authority_package_wrong_run_or_case_fails_closed(identity_field: str) -> None:
    documents = _documents()
    policy = _policy(documents)
    policy[identity_field] = "other-identity"
    policy["approval"]["package_sha256"] = authoritative_source_package_sha256(
        {key: value for key, value in policy.items() if key != "approval"}
    )

    with pytest.raises(ValueError):
        _source_artifact(documents, source_policy=policy)


def test_authority_package_hash_url_and_capture_mismatches_fail_closed() -> None:
    documents = _documents()
    artifact, _, index = _source_artifact(documents, source_policy=_policy(documents))
    altered = deepcopy(artifact)
    altered["source_policy"]["approved_documents"][0]["url"] += "?changed=1"
    with pytest.raises(Exception):
        validate_sources_artifact_v21(altered, documents=documents, document_index=index, run_id=RUN_ID, case_id=CASE_ID)

    changed_documents = list(documents)
    changed_documents[0] = FetchedDocument(**{
        **documents[0].__dict__,
        "text": documents[0].text + " changed",
    })
    with pytest.raises(ValueError, match="hash|capture|snapshot|content"):
        validate_sources_artifact_v21(artifact, documents=changed_documents, document_index=index, run_id=RUN_ID, case_id=CASE_ID)

    bad_hash = deepcopy(artifact)
    bad_hash["source_policy"]["approval"]["package_sha256"] = "0" * 64
    with pytest.raises(Exception):
        validate_sources_artifact_v21(bad_hash, documents=documents, document_index=index, run_id=RUN_ID, case_id=CASE_ID)

    changed_url_policy = _policy(documents)
    changed_url_policy["approved_documents"][0]["url"] += "?different-document"
    changed_url_policy["approval"]["package_sha256"] = authoritative_source_package_sha256(
        {key: value for key, value in changed_url_policy.items() if key != "approval"}
    )
    with pytest.raises(Exception):
        _source_artifact(documents, source_policy=changed_url_policy)


def test_duplicate_approved_normalized_text_is_rejected_even_with_distinct_urls() -> None:
    documents = _documents()
    policy = _policy(documents)
    policy["approved_documents"][1]["source_text_sha256"] = policy["approved_documents"][0]["source_text_sha256"]
    policy["approval"]["package_sha256"] = authoritative_source_package_sha256(
        {key: value for key, value in policy.items() if key != "approval"}
    )

    with pytest.raises(Exception, match="source_text_sha256"):
        _source_artifact(documents, source_policy=policy)


def test_normal_independent_verified_claim_gets_independent_basis() -> None:
    documents = _documents(federal=False)[:3]
    artifact, documents, index = _source_artifact(documents)
    rows = [
        _evidence(doc, "2026 GDP growth was 2.2 percent.", "gdp-2026")
        for doc in documents
    ]
    facts = verify_claims_v22(
        rows,
        {row["source_id"]: row for row in artifact["sources"]},
        artifact,
        documents,
        index,
        run_id=RUN_ID,
        checked_at=CHECKED_AT,
    )

    assert facts["schema_version"] == "2.2"
    assert facts["claims"][0]["verification_status"] == "verified"
    assert facts["claims"][0]["verification_basis"] == "independent_corroboration"
    assert facts["claims"][0]["authority_attestation"] is None
    schema = json.loads((ROOT / "docs/v0.2/native-facts-2.2.schema.json").read_text("utf-8"))
    jsonschema.validate(facts, schema)


def test_authority_document_report_is_verified_only_as_attributed_exact_quote() -> None:
    artifact, documents, index = _source_artifact(source_policy=_policy(_documents()))
    doc = documents[0]
    excerpt = doc.text
    claim = f'Federal Reserve: "{excerpt}"'
    facts = _verify_authority(
        [_evidence(doc, excerpt, "report-claim")],
        artifact,
        documents,
        index,
        {"report-claim": _authority_candidate(claim, [doc.source_id])},
    )

    result = facts["claims"][0]
    assert result["verification_status"] == "verified"
    assert result["verification_basis"] == "authoritative_primary_attestation"
    assert result["allowed_downstream"] is True
    assert result["authority_attestation"]["source_ids"] == [doc.source_id]
    assert artifact["independent_source_count"] == 1
    schema = json.loads((ROOT / "docs/v0.2/native-facts-2.2.schema.json").read_text("utf-8"))
    jsonschema.validate(facts, schema)


def test_authority_deterministic_comparison_requires_two_distinct_captures() -> None:
    documents = _documents()
    policy = _policy(documents)
    artifact, documents, index = _source_artifact(documents, source_policy=policy)
    first, second = documents[:2]
    first_text = first.text
    second_text = second.text
    evidence = [
        _evidence(first, first_text, "projection-change"),
        _evidence(second, second_text, "projection-change"),
    ]
    attestation = _authority_candidate("", [first.source_id, second.source_id], "deterministic_document_comparison")
    values = {first.source_id: "2.2", second.source_id: "2.3"}
    # The runtime's canonical comparison wording is generated from the exact approved documents and values.
    claim_text = (
        "Federal Reserve: published median real GDP growth for Federal Reserve 2026 median real GDP growth "
        "projection (2026) changed from 2.2 percent in fed-doc-1 (2026-06-17) "
        "to 2.3 percent in fed-doc-2 (2026-09-16)."
    )
    attestation["claim_text"] = claim_text
    attestation["comparison"] = {"values": values}
    facts = _verify_authority(evidence, artifact, documents, index, {"projection-change": attestation})

    result = facts["claims"][0]
    assert result["verification_status"] == "verified"
    assert result["verification_basis"] == "authoritative_primary_attestation"
    assert result["authority_attestation"]["kind"] == "deterministic_document_comparison"
    assert result["allowed_downstream"] is True
    assert all("table_context" not in item for item in result["evidence"])
    assert artifact["independent_source_count"] == 1
    schema = json.loads((ROOT / "docs/v0.2/native-facts-2.2.schema.json").read_text("utf-8"))
    jsonschema.validate(facts, schema)


def test_table_authority_comparison_uses_reparsed_median_2026_cells() -> None:
    baseline_text = "\n".join([
        "Table 1. Economic projections for June 2026",
        "Percent", "Variable", "Median1", "Range2", "2026", "2027", "2026", "2027",
        "Real GDP growth", "2.2", "2.5", "2.0-2.4", "2.2-2.8",
    ])
    target_text = baseline_text.replace("June 2026", "September 2026").replace("2.2\n2.5", "2.3\n2.6", 1)
    original = _documents()
    documents = [
        replace(original[0], text=baseline_text, document_hash=sha256_text(baseline_text)),
        replace(original[1], text=target_text, document_hash=sha256_text(target_text)),
        *original[2:],
    ]
    artifact, documents, index = _source_artifact(
        documents,
        source_policy=_policy(documents),
    )
    evidence = RuleBasedEvidenceExtractor().extract(documents, ["What changed?"])
    table_items = [
        item for item in evidence
        if item.get("table_context", {}).get("row_label") == "Real GDP growth"
        and item.get("table_context", {}).get("statistic") == "Median"
        and item.get("table_context", {}).get("period") == "2026"
    ]
    assert {item["source_id"] for item in table_items} == {"src-1", "src-2"}
    assert {item["table_context"]["value"] for item in table_items} == {"2.2", "2.3"}

    key = evidence_claim_key(table_items[0])
    scope = {
        "subject": "Real GDP growth",
        "measure": "projection",
        "period": "2026",
        "unit": "Percent",
        "statistic": "Median",
        "certainty": "projection",
    }
    source_ids = ["src-1", "src-2"]
    values = {item["source_id"]: item["table_context"]["value"] for item in table_items}
    claim_text = (
        "Federal Reserve FOMC participants (SEP): published Median projection for Real GDP growth "
        "(2026) changed from 2.2 Percent in fed-doc-1 (2026-06-17) to 2.3 Percent "
        "in fed-doc-2 (2026-09-16)."
    )
    candidate = {
        "claim_text": claim_text,
        "claim_type": "fact",
        "authority_attestation": {
            "kind": "deterministic_document_comparison",
            "source_ids": source_ids,
            "attribution": "Federal Reserve FOMC participants (SEP)",
            "scope": scope,
        },
        "comparison": {"values": values},
    }
    facts = verify_claims_v22(
        evidence,
        {row["source_id"]: row for row in artifact["sources"]},
        artifact,
        documents,
        index,
        run_id=RUN_ID,
        case_id=CASE_ID,
        authority_claims={key: candidate},
        checked_at=CHECKED_AT,
    )
    result = next(row for row in facts["claims"] if row["claim_id"])
    assert result["verification_status"] == "verified"
    assert result["verification_basis"] == "authoritative_primary_attestation"
    assert result["authority_attestation"]["kind"] == "deterministic_document_comparison"
    assert result["allowed_downstream"] is True

    tampered = deepcopy(evidence)
    target_item = next(item for item in tampered if item.get("source_id") == "src-2" and item.get("table_context", {}).get("period") == "2026")
    target_item["table_context"]["value"] = "2.6"
    rejected = verify_claims_v22(
        tampered,
        {row["source_id"]: row for row in artifact["sources"]},
        artifact,
        documents,
        index,
        run_id=RUN_ID,
        case_id=CASE_ID,
        authority_claims={key: candidate},
        checked_at=CHECKED_AT,
    )
    rejected_claim = next(row for row in rejected["claims"] if row["source_ids"] == source_ids)
    assert rejected_claim["verification_status"] == "unverified"
    assert rejected_claim["verification_basis"] == "none"
    assert rejected_claim["allowed_downstream"] is False


def test_missing_attribution_outside_package_and_scope_expansion_stay_unverified() -> None:
    artifact, documents, index = _source_artifact(source_policy=_policy(_documents()))
    doc = documents[0]
    excerpt = doc.text
    evidence = [_evidence(doc, excerpt, "report-claim")]

    missing_attribution = _authority_candidate(f'"{excerpt}"', [doc.source_id])
    facts = _verify_authority(evidence, artifact, documents, index, {"report-claim": missing_attribution})
    assert facts["claims"][0]["verification_status"] == "unverified"
    assert facts["claims"][0]["verification_basis"] == "none"
    assert facts["claims"][0]["allowed_downstream"] is False

    outside = _authority_candidate(f'Federal Reserve: "{excerpt}"', ["src-outside"])
    facts = _verify_authority(evidence, artifact, documents, index, {"report-claim": outside})
    assert facts["claims"][0]["verification_status"] == "unverified"
    assert facts["claims"][0]["authority_attestation"] is None

    causal = _authority_candidate(
        'Federal Reserve: "Inflation caused the Fed to raise its rate path because prices worsened."',
        [doc.source_id],
    )
    facts = _verify_authority(evidence, artifact, documents, index, {"report-claim": causal})
    assert facts["claims"][0]["verification_status"] == "unverified"
    assert facts["claims"][0]["verification_basis"] == "none"


def test_authority_capture_hash_mismatch_raises_before_any_claim_is_verified() -> None:
    artifact, documents, index = _source_artifact(source_policy=_policy(_documents()))
    altered = list(documents)
    altered[0] = FetchedDocument(**{**documents[0].__dict__, "text": documents[0].text + " tampered"})
    doc = documents[0]
    candidate = _authority_candidate(f'Federal Reserve: "{doc.text}"', [doc.source_id])

    with pytest.raises(ValueError, match="hash|capture|snapshot|content"):
        _verify_authority([_evidence(doc, doc.text, "report-claim")], artifact, altered, index, {"report-claim": candidate})


def test_authority_evidence_hash_mismatch_cannot_be_marked_eligible() -> None:
    artifact, documents, index = _source_artifact(source_policy=_policy(_documents()))
    doc = documents[0]
    evidence = _evidence(doc, doc.text, "report-claim")
    evidence["document_hash"] = "0" * 64
    candidate = _authority_candidate(f'Federal Reserve: "{doc.text}"', [doc.source_id])

    facts = _verify_authority([evidence], artifact, documents, index, {"report-claim": candidate})

    assert facts["claims"][0]["verification_status"] == "unverified"
    assert facts["claims"][0]["verification_basis"] == "none"
    assert facts["claims"][0]["allowed_downstream"] is False


def test_authority_verification_requires_admissible_approved_package() -> None:
    documents = _documents(federal=False)[:2]
    artifact, documents, index = _source_artifact(documents)

    with pytest.raises(ValueError, match="admissible"):
        verify_claims_v22(
            [_evidence(documents[0], documents[0].text, "claim")],
            {row["source_id"]: row for row in artifact["sources"]},
            artifact,
            documents,
            index,
            run_id=RUN_ID,
            checked_at=CHECKED_AT,
        )


def test_unverified_claims_have_none_basis_and_cannot_be_unlocked_by_basis() -> None:
    documents = _documents(federal=False)[:3]
    artifact, documents, index = _source_artifact(documents)
    rows = [_evidence(doc, "2026 GDP growth was 2.2 percent.", "claim") for doc in documents]
    rows[1]["evidence_text"] = "2026 GDP growth was 2.5 percent."
    facts = verify_claims_v22(
        rows,
        {row["source_id"]: row for row in artifact["sources"]},
        artifact,
        documents,
        index,
        run_id=RUN_ID,
        checked_at=CHECKED_AT,
    )

    for claim in facts["claims"]:
        assert claim["verification_basis"] == "none"
        assert claim["authority_attestation"] is None
        assert claim["allowed_downstream"] is False
