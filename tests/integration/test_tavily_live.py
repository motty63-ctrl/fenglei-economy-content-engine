"""Opt-in live smoke test: explicitly enable it and provide TAVILY_API_KEY."""

import os

import pytest

from fanglei.providers.search import SearchRequest, TavilySearchProvider


@pytest.mark.integration
def test_tavily_live_discovery_returns_urls_not_evidence() -> None:
    if os.environ.get("RUN_TAVILY_INTEGRATION") != "1":
        pytest.skip("set RUN_TAVILY_INTEGRATION=1 to run the live Tavily test")
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        pytest.skip("TAVILY_API_KEY is not configured")
    response = TavilySearchProvider(api_key).search(
        SearchRequest(query="World Bank official GDP data", max_results=3, include_domains=["worldbank.org"])
    )
    assert response.results
    assert all(result.url.startswith("http") for result in response.results)
    assert all(result.evidence_eligible is False for result in response.results)
