"""Deterministic offline research adapters for tests and demos."""

from fanglei.providers.search import SearchRequest, SearchResponse, SearchResult
from fanglei.research import FetchedDocument


class MockSearchProvider:
    name = "mock-research"

    def search(self, request: SearchRequest) -> SearchResponse:
        return SearchResponse(request.query, self.name, [
            SearchResult("https://stats.example.gov/gdp", "国家统计公报", "discovery only"),
            SearchResult("https://data.worldbank.example/gdp", "国际组织数据", "discovery only"),
            SearchResult("https://disclosure.example.com/report", "公司原始披露", "discovery only"),
        ])


class MockDocumentFetcher:
    _types = {
        "stats.example.gov": "official",
        "data.worldbank.example": "international_organization",
        "disclosure.example.com": "company_disclosure",
    }

    def fetch(self, source_id: str, url: str, title: str) -> FetchedDocument:
        host = url.split("/")[2]
        statements = {
            "stats.example.gov": "官方统计公报及核算方法说明。\n2025年GDP同比增长5.0%。",
            "data.worldbank.example": "国际组织国民账户数据库。\n2025年国内生产总值同比增幅为5.0%。",
            "disclosure.example.com": "公司年度报告宏观环境披露。\n2025年国内生产总值同比增长率为5.0%。",
        }
        return FetchedDocument(
            source_id, url, title, statements[host], self._types[host],
            "2026-01-17", "2026-09-08T12:00:00+08:00",
        )
