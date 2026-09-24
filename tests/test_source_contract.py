from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from fanglei.source_contract import (
    SourcesV21,
    authoritative_source_package_sha256,
    parse_sources_artifact,
)


ROOT = Path(__file__).resolve().parents[1]


def _rows() -> list[dict]:
    urls = [
        "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20260617.htm",
        "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20260916.htm",
        "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260617a.htm",
        "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916a.htm",
    ]
    return [
        {
            "source_id": f"src-{index}",
            "url": url,
            "title": f"Federal Reserve document {index}",
            "published_at": "2026-06-17" if index in (1, 3) else "2026-09-16",
            "retrieved_at": "2026-09-24T10:00:00+08:00",
            "source_type": "official",
            "credibility_tier": "A",
            "independence_key": "institution:federalreserve.gov",
            "counts_as_independent": index == 1,
            "independence_reason": "official materials from one institution",
            "origin_chain": [url],
        }
        for index, url in enumerate(urls, 1)
    ]


def _authority_policy() -> dict:
    source_rows = _rows()
    roles = ["june_sep_baseline", "september_sep_target", "june_statement_context", "september_statement_context"]
    dates = ["2026-06-17", "2026-09-16", "2026-06-17", "2026-09-16"]
    policy_body = {
        "name": "authoritative_primary_set",
        "version": "1.0",
        "run_id": "2026-09-24-001-fed-sep-case-2-source-inventory",
        "case_id": "fed-sep-revisions",
        "institution": {"institution_id": "federal-reserve", "display_name": "Federal Reserve"},
        "approved_documents": [
            {
                "source_id": row["source_id"],
                "url": row["url"],
                "document_identity": f"fed-document-{index}",
                "evidence_role": roles[index - 1],
                "release_date": dates[index - 1],
                "classification": "official_primary",
                "source_text_sha256": f"{index:064x}",
                "raw_capture_bytes_sha256": f"{index + 10:064x}",
            }
            for index, row in enumerate(source_rows, 1)
        ],
    }
    return {
        **policy_body,
        "approval": {
            "status": "approved",
            "reviewer": "reviewer-1",
            "approved_at": "2026-09-24T10:00:00+08:00",
            "rationale": "These are the exact official primary documents for the comparison.",
            "package_sha256": authoritative_source_package_sha256(policy_body),
        },
    }


def _authority_sources() -> dict:
    return {
        "schema_version": "2.1",
        "source_policy": _authority_policy(),
        "package_admissibility": "admissible",
        "independent_source_count": 1,
        "selection_status": "insufficient_sources",
        "sources": _rows(),
    }


def test_sources_20_legacy_artifact_parses_without_migration() -> None:
    legacy = {
        "schema_version": "2.0",
        "selection_status": "insufficient_sources",
        "sources": _rows(),
    }

    parsed = parse_sources_artifact(legacy)

    assert parsed.schema_version == "2.0"
    assert parsed.selection_status == "insufficient_sources"
    assert len(parsed.sources) == 4
    assert not hasattr(parsed, "source_policy")


def test_sources_21_default_policy_is_explicit_without_authority_approval() -> None:
    sources = _rows()[:3]
    for index, row in enumerate(sources, 1):
        row["counts_as_independent"] = True
        row["independence_key"] = f"institution:source-{index}.example"
        row["url"] = f"https://source-{index}.example/report"
        row["origin_chain"] = [row["url"]]
    artifact = {
        "schema_version": "2.1",
        "source_policy": {"name": "independent_sources", "version": "1.0"},
        "package_admissibility": "admissible",
        "independent_source_count": 3,
        "selection_status": "selected",
        "sources": sources,
    }

    parsed = SourcesV21.model_validate(artifact)
    schema = json.loads((ROOT / "docs/v0.2/sources-2.1.schema.json").read_text("utf-8"))
    jsonschema.validate(artifact, schema)

    assert parsed.source_policy.name == "independent_sources"
    assert parsed.selection_status == "selected"


def test_sources_21_default_policy_cannot_admit_fewer_than_three_independent_sources() -> None:
    artifact = {
        "schema_version": "2.1",
        "source_policy": {"name": "independent_sources", "version": "1.0"},
        "package_admissibility": "admissible",
        "independent_source_count": 0,
        "selection_status": "insufficient_sources",
        "sources": [],
    }
    schema = json.loads((ROOT / "docs/v0.2/sources-2.1.schema.json").read_text("utf-8"))

    with pytest.raises(ValidationError):
        SourcesV21.model_validate(artifact)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(artifact, schema)


def test_sources_21_authority_package_and_independent_gate_are_distinct() -> None:
    artifact = _authority_sources()

    parsed = SourcesV21.model_validate(artifact)
    schema = json.loads((ROOT / "docs/v0.2/sources-2.1.schema.json").read_text("utf-8"))
    jsonschema.validate(artifact, schema)

    assert parsed.package_admissibility == "admissible"
    assert parsed.independent_source_count == 1
    assert parsed.selection_status == "insufficient_sources"


def test_sources_21_authority_policy_is_bound_to_exact_package_hash() -> None:
    artifact = _authority_sources()
    artifact["source_policy"]["approved_documents"][0]["source_text_sha256"] = "f" * 64

    with pytest.raises(ValidationError):
        SourcesV21.model_validate(artifact)


@pytest.mark.parametrize("identity_field", ["run_id", "case_id"])
def test_sources_21_authority_approval_hash_binds_run_and_case(identity_field: str) -> None:
    artifact = _authority_sources()
    artifact["source_policy"][identity_field] += "-other"

    with pytest.raises(ValidationError):
        SourcesV21.model_validate(artifact)


def test_sources_21_authority_approval_time_must_be_timezone_aware() -> None:
    artifact = _authority_sources()
    artifact["source_policy"]["approval"]["approved_at"] = "2026-09-24T10:00:00"

    with pytest.raises(ValidationError):
        SourcesV21.model_validate(artifact)


def test_sources_21_authority_documents_must_have_distinct_identities_roles_and_dates() -> None:
    artifact = _authority_sources()
    artifact["source_policy"]["approved_documents"][1]["document_identity"] = \
        artifact["source_policy"]["approved_documents"][0]["document_identity"]
    policy_body = {key: value for key, value in artifact["source_policy"].items() if key != "approval"}
    artifact["source_policy"]["approval"]["package_sha256"] = authoritative_source_package_sha256(policy_body)

    with pytest.raises(ValidationError):
        SourcesV21.model_validate(artifact)


def test_sources_21_authority_documents_require_distinct_normalized_text_hashes() -> None:
    artifact = _authority_sources()
    documents = artifact["source_policy"]["approved_documents"]
    documents[1]["source_text_sha256"] = documents[0]["source_text_sha256"]
    body = {key: value for key, value in artifact["source_policy"].items() if key != "approval"}
    artifact["source_policy"]["approval"]["package_sha256"] = authoritative_source_package_sha256(body)

    with pytest.raises(ValidationError, match="source_text_sha256"):
        SourcesV21.model_validate(artifact)


def test_sources_21_authority_allowlist_must_match_source_rows() -> None:
    artifact = _authority_sources()
    artifact["source_policy"]["approved_documents"].pop()
    body = {key: value for key, value in artifact["source_policy"].items() if key != "approval"}
    artifact["source_policy"]["approval"]["package_sha256"] = authoritative_source_package_sha256(body)

    with pytest.raises(ValidationError):
        SourcesV21.model_validate(artifact)


def test_sources_21_rejects_independence_count_mismatch() -> None:
    artifact = _authority_sources()
    artifact["independent_source_count"] = 4

    with pytest.raises(ValidationError):
        SourcesV21.model_validate(artifact)


def test_sources_21_rejects_two_independent_rows_with_the_same_key() -> None:
    artifact = _authority_sources()
    artifact["sources"][1]["counts_as_independent"] = True
    artifact["independent_source_count"] = 2

    with pytest.raises(ValidationError, match="independence_key"):
        SourcesV21.model_validate(artifact)


def test_sources_21_distinct_source_ids_do_not_inflate_same_independence_key() -> None:
    artifact = _authority_sources()
    first, second = artifact["sources"][:2]
    first["counts_as_independent"] = True
    second["counts_as_independent"] = True
    first["independence_key"] = second["independence_key"] = "institution:one.example"
    artifact["independent_source_count"] = 2

    with pytest.raises(ValidationError, match="independence_key"):
        SourcesV21.model_validate(artifact)


def test_sources_21_rejects_unknown_policy_and_non_https_sources() -> None:
    artifact = _authority_sources()
    artifact["source_policy"]["name"] = "fed_exception"
    with pytest.raises(ValidationError):
        SourcesV21.model_validate(artifact)

    artifact = _authority_sources()
    artifact["sources"][0]["url"] = artifact["sources"][0]["url"].replace("https://", "http://")
    with pytest.raises(ValidationError):
        SourcesV21.model_validate(artifact)
