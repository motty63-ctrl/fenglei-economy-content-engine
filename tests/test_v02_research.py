from datetime import datetime, timezone

import pytest

from fanglei.errors import ProviderError
from fanglei.providers.search import SearchRequest, TavilySearchProvider
from fanglei.research import (
    FetchedDocument,
    RuleBasedEvidenceExtractor,
    deduplicate_sources,
    verify_claims,
)


def test_tavily_adapter_keeps_snippet_discovery_only() -> None:
    provider = TavilySearchProvider(
        api_key="secret",
        transport=lambda payload: {
            "results": [{"url": "https://stats.gov/x", "title": "GDP", "content": "snippet", "score": 0.9}]
        },
    )
    result = provider.search(SearchRequest(query="GDP", max_results=3))
    assert result.results[0].snippet == "snippet"
    assert result.results[0].evidence_eligible is False


def test_tavily_network_failure_is_retryable_and_does_not_write_artifacts() -> None:
    def fail(_payload):
        raise OSError("offline")

    with pytest.raises(ProviderError, match="retryable"):
        TavilySearchProvider(api_key="x", transport=fail).search(SearchRequest(query="GDP"))


def test_republication_and_uncertain_origin_are_not_independent() -> None:
    docs = [
        FetchedDocument("a", "https://gov.example/release", "Release", "官方发布 GDP 增长 5.0%。", "official", "2026-01-01", "now", None),
        FetchedDocument("b", "https://news.example/copy", "转载", "官方发布 GDP 增长 5.0%。", "mainstream_media", "2026-01-01", "now", "https://gov.example/release"),
        FetchedDocument("c", "https://unknown.example/a", "Unknown", "GDP 增长 5.0%。", "industry_media", None, "now", None),
    ]
    selected = deduplicate_sources(docs)
    assert selected[0]["counts_as_independent"] is True
    assert selected[1]["counts_as_independent"] is False
    assert selected[1]["independence_key"] == selected[0]["independence_key"]
    assert selected[2]["counts_as_independent"] is False


def test_same_institution_pages_count_once() -> None:
    docs = [
        FetchedDocument("a", "https://stats.gov/table", "Table", "GDP 5.0%", "official", None, "now", None),
        FetchedDocument("b", "https://stats.gov/release", "Release", "GDP 5.0%", "official", None, "now", None),
    ]
    selected = deduplicate_sources(docs)
    assert sum(row["counts_as_independent"] for row in selected) == 1


def test_identical_authoritative_copies_count_once_across_domains() -> None:
    docs = [
        FetchedDocument("a", "https://a.gov/release", "A", "identical press release", "official", None, "now", None),
        FetchedDocument("b", "https://b.gov/release", "B", "identical press release", "official", None, "now", None),
    ]
    assert sum(row["counts_as_independent"] for row in deduplicate_sources(docs)) == 1


def test_near_identical_release_with_changed_dateline_counts_once() -> None:
    body = "国家统计机构今日发布年度公报，2025年国内生产总值同比增长5.0%，统计口径与上年一致。"
    docs = [
        FetchedDocument("a", "https://a.gov/release", "A", body, "official", None, "now", None),
        FetchedDocument("b", "https://b.gov/release", "B", "北京9月8日电：" + body, "official", None, "now", None),
    ]
    assert sum(row["counts_as_independent"] for row in deduplicate_sources(docs)) == 1


def test_evidence_points_to_declared_original_url() -> None:
    doc = FetchedDocument(
        "a", "https://aggregator.example/copy", "Copy", "2025年GDP增长5.0%。", "industry_media", None, "now",
        "https://publisher.example/original",
    )
    evidence = RuleBasedEvidenceExtractor().extract([doc], ["GDP增长是多少？"])
    assert evidence[0]["original_url"] == "https://publisher.example/original"


def test_fact_claim_contains_evidence_level_traceability() -> None:
    doc = FetchedDocument(
        "src_001", "https://stats.gov/gdp", "GDP", "2025年国内生产总值同比增长5.0%。", "official",
        "2026-01-17", datetime.now(timezone.utc).isoformat(), None,
    )
    evidence = RuleBasedEvidenceExtractor().extract([doc], ["国内生产总值增长是多少？"])
    assert evidence[0]["evidence_text"] == "2025年国内生产总值同比增长5.0%。"
    facts = verify_claims(evidence, {"src_001": True})
    claim = facts["claims"][0]
    assert claim["claim_id"]
    assert claim["claim_type"] == "fact"
    assert claim["verification_status"] in {"verified", "unverified"}
    ev = claim["evidence"][0]
    for field in ("source_id", "evidence_text", "paragraph_locator", "published_at", "retrieved_at"):
        assert field in ev
    assert claim["verification_reason"]


def test_conflicting_numeric_sources_are_marked_conflicted() -> None:
    docs = [
        FetchedDocument("a", "https://a.gov/x", "A", "2025年GDP增长5.0%。", "official", "2026-01-01", "now", None),
        FetchedDocument("b", "https://b.org/x", "B", "2025年GDP增长4.8%。", "international_organization", "2026-01-01", "now", None),
    ]
    evidence = RuleBasedEvidenceExtractor().extract(docs, ["GDP增长是多少？"])
    facts = verify_claims(evidence, {"a": True, "b": True})
    assert facts["claims"][0]["verification_status"] == "conflicted"
    assert facts["summary"]["conflicted"] == 1


def test_different_periods_are_separate_claims_but_wording_variants_corroborate() -> None:
    docs = [
        FetchedDocument("a", "https://a.gov/x", "A", "2024年GDP增长5.0%。", "official", None, "now", None),
        FetchedDocument("b", "https://b.org/x", "B", "2025年国内生产总值同比增幅为4.8%。", "international_organization", None, "now", None),
        FetchedDocument("c", "https://c.org/x", "C", "2025年GDP同比增长4.8%。", "company_disclosure", None, "now", None),
    ]
    evidence = RuleBasedEvidenceExtractor().extract(docs, ["GDP增长是多少？"])
    facts = verify_claims(evidence, {"a": True, "b": True, "c": True})
    assert len(facts["claims"]) == 2
    claim_2025 = next(c for c in facts["claims"] if "2025" in c["claim_text"])
    assert claim_2025["verification_status"] == "verified"


def test_opinion_and_inference_are_distinguished() -> None:
    doc = FetchedDocument(
        "a", "https://a.example/x", "A", "作者认为利率会下降。\n因此就业可能改善。", "mainstream_media", None, "now", None
    )
    evidence = RuleBasedEvidenceExtractor().extract([doc], ["利率如何变化？"])
    facts = verify_claims(evidence, {"a": False})
    assert {claim["claim_type"] for claim in facts["claims"]} == {"opinion", "inference"}
