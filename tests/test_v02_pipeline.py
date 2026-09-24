import json
from pathlib import Path

import pytest

from fanglei.models import ResearchQuestion
from fanglei.pipeline import run_v02_pipeline
from fanglei.providers.search import SearchRequest, SearchResponse, SearchResult
from fanglei.research import FetchedDocument
from fanglei.stages.analyze import analyze_run
from fanglei.stages.ingest import ingest_text
from fanglei.providers.mock import MockAnalysisProvider


class FakeSearch:
    name = "fake"

    def search(self, request: SearchRequest) -> SearchResponse:
        return SearchResponse(request.query, self.name, [
            SearchResult(f"https://source{i}.example/data", f"Source {i}", "discovery only") for i in range(1, 4)
        ])


class FakeFetcher:
    def fetch(self, source_id: str, url: str, title: str) -> FetchedDocument:
        types = {"source1.example": "official", "source2.example": "international_organization", "source3.example": "company_disclosure"}
        statements = {
            "source1.example": "官方统计公报及核算方法说明。\n2025年GDP同比增长5.0%。",
            "source2.example": "国际组织国民账户数据库。\n2025年国内生产总值同比增幅为5.0%。",
            "source3.example": "公司年度报告宏观环境披露。\n2025年国内生产总值同比增长率为5.0%。",
        }
        host = url.split("/")[2]
        return FetchedDocument(source_id, url, title, statements[host], types[host], "2026-01-17", "2026-09-08T00:00:00+00:00")


def _analyzed_run(tmp_path: Path) -> Path:
    run = ingest_text("# GDP观察\n2025年国内生产总值同比增长5.0%。", tmp_path)
    analyze_run(run.name, tmp_path, MockAnalysisProvider())
    return run


def test_complete_pipeline_has_traceable_artifacts_and_three_independent_sources(tmp_path: Path) -> None:
    run = _analyzed_run(tmp_path)
    run_v02_pipeline(run.name, tmp_path, FakeSearch(), FakeFetcher())
    sources = json.loads((run / "sources.json").read_text(encoding="utf-8"))
    facts = json.loads((run / "facts.json").read_text(encoding="utf-8"))
    research = (run / "research.md").read_text(encoding="utf-8")
    assert sum(s["counts_as_independent"] for s in sources["sources"]) >= 3
    assert sources["schema_version"] == "2.0"
    assert facts["schema_version"] == "2.1"
    assert any(c["verification_status"] == "verified" for c in facts["claims"])
    assert "claim_001" in research and "https://source1.example/data" in research
    manifest = json.loads((run / "run.json").read_text(encoding="utf-8"))
    assert manifest["artifacts"]["research.md"]["owner"] == "research_synthesis"
    assert manifest["artifacts"]["research.md"]["status"] == "valid"


def test_explicit_sources_21_policy_produces_native_facts_22(tmp_path: Path) -> None:
    run = _analyzed_run(tmp_path)
    run_v02_pipeline(
        run.name,
        tmp_path,
        FakeSearch(),
        FakeFetcher(),
        source_policy={"name": "independent_sources", "version": "1.0"},
    )
    sources = json.loads((run / "sources.json").read_text(encoding="utf-8"))
    facts = json.loads((run / "facts.json").read_text(encoding="utf-8"))

    assert sources["schema_version"] == "2.1"
    assert sources["source_policy"] == {"name": "independent_sources", "version": "1.0"}
    assert sources["package_admissibility"] == "admissible"
    assert sources["independent_source_count"] == 3
    assert sources["selection_status"] == "selected"
    assert facts["schema_version"] == "2.2"
    assert all(claim["verification_basis"] in {"independent_corroboration", "none"} for claim in facts["claims"])


def test_explicit_sources_21_policy_rebuilds_legacy_source_stage_only_when_requested(tmp_path: Path) -> None:
    run = _analyzed_run(tmp_path)
    search = FakeSearch()
    fetcher = FakeFetcher()
    run_v02_pipeline(run.name, tmp_path, search, fetcher)
    first_sources = json.loads((run / "sources.json").read_text(encoding="utf-8"))
    assert first_sources["schema_version"] == "2.0"

    run_v02_pipeline(
        run.name,
        tmp_path,
        search,
        fetcher,
        source_policy={"name": "independent_sources", "version": "1.0"},
    )
    upgraded_sources = json.loads((run / "sources.json").read_text(encoding="utf-8"))
    upgraded_facts = json.loads((run / "facts.json").read_text(encoding="utf-8"))

    assert upgraded_sources["schema_version"] == "2.1"
    assert upgraded_facts["schema_version"] == "2.2"


def test_provider_failure_records_failed_stage_and_can_resume(tmp_path: Path) -> None:
    run = _analyzed_run(tmp_path)

    class Broken:
        name = "broken"
        def search(self, request):
            raise RuntimeError("network down")

    with pytest.raises(RuntimeError):
        run_v02_pipeline(run.name, tmp_path, Broken(), FakeFetcher())
    manifest = json.loads((run / "run.json").read_text(encoding="utf-8"))
    assert manifest["stages"]["search"]["status"] == "failed"
    assert not (run / "search_results.json").exists()

    run_v02_pipeline(run.name, tmp_path, FakeSearch(), FakeFetcher())
    manifest = json.loads((run / "run.json").read_text(encoding="utf-8"))
    assert manifest["stages"]["search"]["attempts"] == 2
    assert manifest["artifacts"]["research.md"]["status"] == "valid"


def test_fetch_network_failure_resumes_without_repeating_search(tmp_path: Path) -> None:
    run = _analyzed_run(tmp_path)

    class BrokenFetcher:
        def fetch(self, source_id, url, title):
            raise RuntimeError("fetch timeout")

    with pytest.raises(RuntimeError, match="timeout"):
        run_v02_pipeline(run.name, tmp_path, FakeSearch(), BrokenFetcher())
    failed = json.loads((run / "run.json").read_text(encoding="utf-8"))
    assert failed["stages"]["search"]["attempts"] == 1
    assert failed["stages"]["source_fetch"]["status"] == "failed"
    assert not (run / "source_documents" / "index.json").exists()

    run_v02_pipeline(run.name, tmp_path, FakeSearch(), FakeFetcher())
    recovered = json.loads((run / "run.json").read_text(encoding="utf-8"))
    assert recovered["stages"]["search"]["attempts"] == 1
    assert recovered["stages"]["source_fetch"]["attempts"] == 2


def test_source_fetch_records_one_bad_url_and_keeps_successful_pages(tmp_path: Path) -> None:
    run = _analyzed_run(tmp_path)

    class PartiallyBrokenFetcher(FakeFetcher):
        def fetch(self, source_id, url, title):
            if "source1.example" in url:
                raise RuntimeError("HTTP 404")
            return super().fetch(source_id, url, title)

    run_v02_pipeline(run.name, tmp_path, FakeSearch(), PartiallyBrokenFetcher(), stop_after="source_fetch")
    index = json.loads((run / "source_documents" / "index.json").read_text(encoding="utf-8"))
    assert len(index["documents"]) == 2
    assert index["fetch_errors"][0]["url"] == "https://source1.example/data"


def test_source_fetch_records_stable_dynamic_html_failure_code(tmp_path: Path) -> None:
    run = _analyzed_run(tmp_path)

    class DynamicFetcher(FakeFetcher):
        def fetch(self, source_id, url, title):
            if "source1.example" in url:
                raise RuntimeError("dynamic_content_unavailable: application shell")
            return super().fetch(source_id, url, title)

    run_v02_pipeline(run.name, tmp_path, FakeSearch(), DynamicFetcher(), stop_after="source_fetch")
    index = json.loads((run / "source_documents" / "index.json").read_text(encoding="utf-8"))
    assert index["fetch_errors"][0]["failure_code"] == "dynamic_content_unavailable"


def test_force_upstream_stage_rebuilds_stale_descendants(tmp_path: Path) -> None:
    run = _analyzed_run(tmp_path)
    class ChangingSearch(FakeSearch):
        def __init__(self):
            self.calls = 0

        def search(self, request: SearchRequest) -> SearchResponse:
            self.calls += 1
            response = super().search(request)
            return SearchResponse(response.query, response.provider, [
                SearchResult(item.url, f"{item.title} call-{self.calls}", item.snippet) for item in response.results
            ])

    provider = ChangingSearch()
    run_v02_pipeline(run.name, tmp_path, provider, FakeFetcher())
    before = json.loads((run / "run.json").read_text(encoding="utf-8"))
    run_v02_pipeline(run.name, tmp_path, provider, FakeFetcher(), force_stage="search")
    after = json.loads((run / "run.json").read_text(encoding="utf-8"))
    for stage in ("search", "source_fetch", "source_selection", "factcheck", "research_synthesis"):
        assert after["stages"][stage]["attempts"] == before["stages"][stage]["attempts"] + 1
    assert all(after["artifacts"][name]["status"] == "valid" for name in (
        "search_results.json", "source_documents/index.json", "sources.json", "facts.json", "research.md"
    ))


def test_rebuilt_source_fetch_removes_files_owned_by_previous_index(tmp_path: Path) -> None:
    run = _analyzed_run(tmp_path)
    run_v02_pipeline(run.name, tmp_path, FakeSearch(), FakeFetcher(), stop_after="source_fetch")
    assert (run / "source_documents" / "src_003.md").is_file()

    class TwoSearch(FakeSearch):
        def search(self, request):
            response = super().search(request)
            return SearchResponse(response.query, response.provider, response.results[:2])

    run_v02_pipeline(
        run.name, tmp_path, TwoSearch(), FakeFetcher(), force_stage="search", stop_after="source_fetch"
    )
    assert not (run / "source_documents" / "src_003.md").exists()


def test_source_document_tamper_stales_index_and_descendants(tmp_path: Path) -> None:
    run = _analyzed_run(tmp_path)
    run_v02_pipeline(run.name, tmp_path, FakeSearch(), FakeFetcher())
    (run / "source_documents" / "src_001.md").write_text("tampered", encoding="utf-8")
    from fanglei.artifact_registry import ArtifactRegistry
    from fanglei.models import RunManifest
    manifest = RunManifest.model_validate(json.loads((run / "run.json").read_text(encoding="utf-8")))
    registry = ArtifactRegistry(run, manifest)
    with pytest.raises(Exception, match="source document"):
        registry.validate("facts.json")
    assert manifest.artifacts["source_documents/index.json"].status == "stale"
    assert manifest.artifacts["facts.json"].status == "stale"


def test_insufficient_run_sources_never_verify_high_risk_claim(tmp_path: Path) -> None:
    run = _analyzed_run(tmp_path)

    class TwoSearch(FakeSearch):
        def search(self, request):
            response = super().search(request)
            return SearchResponse(response.query, response.provider, response.results[:2])

    run_v02_pipeline(run.name, tmp_path, TwoSearch(), FakeFetcher())
    facts = json.loads((run / "facts.json").read_text(encoding="utf-8"))
    assert all(c["verification_status"] == "unverified" for c in facts["claims"])


def test_search_query_includes_verification_claim_and_named_authorities(tmp_path: Path) -> None:
    run = ingest_text(
        "2024 US Real GDP Growth\nWhat was the rate, and do BEA, World Bank, IMF, and OECD data agree?",
        tmp_path,
    )
    analyze_run(run.name, tmp_path, MockAnalysisProvider())

    class CapturingSearch:
        name = "capture"
        def __init__(self):
            self.requests = []
        def search(self, request):
            self.requests.append(request)
            return SearchResponse(request.query, self.name, [])

    provider = CapturingSearch()
    run_v02_pipeline(run.name, tmp_path, provider, FakeFetcher(), stop_after="search")
    assert all("2024 US Real GDP Growth" in request.query for request in provider.requests)
    assert all("annual real GDP growth rate" in request.query for request in provider.requests)
    assert all("The research question is:" not in request.query for request in provider.requests)
    bea_request = next(request for request in provider.requests if request.include_domains == ["bea.gov"])
    world_bank_request = next(request for request in provider.requests if request.include_domains == ["data.worldbank.org"])
    assert "fourth quarter and year 2024" in bea_request.query
    assert "GDP growth (annual %)" in world_bank_request.query
    assert {tuple(request.include_domains) for request in provider.requests} == {
        ("bea.gov",), ("data.worldbank.org",), ("imf.org",), ("oecd.org",)
    }


def test_pipeline_passes_deterministic_research_context_to_fetcher(tmp_path: Path) -> None:
    run = ingest_text(
        "2024 US Real GDP Growth\nWhat was the rate, and do BEA and World Bank data agree?",
        tmp_path,
    )
    analyze_run(run.name, tmp_path, MockAnalysisProvider())

    class ContextFetcher(FakeFetcher):
        context = None

        def with_context(self, context):
            self.context = context
            return self

    fetcher = ContextFetcher()
    run_v02_pipeline(run.name, tmp_path, FakeSearch(), fetcher, stop_after="source_fetch")
    assert fetcher.context.country == "USA"
    assert fetcher.context.years == ("2024",)
    assert fetcher.context.indicators == ("real_gdp_growth",)
