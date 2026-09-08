"""Search-provider boundary and Tavily discovery adapter."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from fanglei.errors import ProviderError


@dataclass(frozen=True)
class SearchRequest:
    query: str
    max_results: int = 8
    include_domains: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SearchResult:
    url: str
    title: str
    snippet: str
    score: float | None = None
    published_at_hint: str | None = None
    evidence_eligible: bool = False


@dataclass(frozen=True)
class SearchResponse:
    query: str
    provider: str
    results: list[SearchResult]


class SearchProvider(Protocol):
    name: str

    def search(self, request: SearchRequest) -> SearchResponse: ...


class TavilySearchProvider:
    name = "tavily"
    endpoint = "https://api.tavily.com/search"

    def __init__(self, api_key: str, transport: Callable[[dict[str, Any]], dict[str, Any]] | None = None):
        if not api_key:
            raise ProviderError("TAVILY_API_KEY is required")
        self.api_key = api_key
        self._transport = transport or self._post

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            value = json.loads(response.read().decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Tavily returned a non-object response")
        return value

    def search(self, request: SearchRequest) -> SearchResponse:
        payload: dict[str, Any] = {
            "query": request.query,
            "max_results": request.max_results,
            "search_depth": "basic",
            "include_answer": False,
            "include_raw_content": False,
        }
        if request.include_domains:
            payload["include_domains"] = request.include_domains
        try:
            raw = self._transport(payload)
            results = [
                SearchResult(
                    url=item["url"],
                    title=item.get("title") or item["url"],
                    snippet=item.get("content") or "",
                    score=item.get("score"),
                    published_at_hint=item.get("published_date"),
                    evidence_eligible=False,
                )
                for item in raw.get("results", [])
                if isinstance(item, dict) and item.get("url")
            ]
        except Exception as error:
            raise ProviderError(f"Tavily search failed (retryable): {error}") from error
        return SearchResponse(query=request.query, provider=self.name, results=results)
