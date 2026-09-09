"""Deterministic official-source routing; adapters never infer missing API parameters."""

from __future__ import annotations

import hashlib
import re
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fanglei.providers.document import FetchContext, RetrievalTarget
from fanglei.security import sanitize_url


def _fingerprint(url: str) -> str:
    canonical = f"GET\n{sanitize_url(url)}\naccept:application/json"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _target(url: str, adapter: str, credential_ref: str | None = None) -> RetrievalTarget:
    safe_url = sanitize_url(url)
    return RetrievalTarget("api", url, safe_url, adapter, _fingerprint(safe_url), credential_ref)


class SourceAdapter(Protocol):
    name: str

    def build_plan(self, discovery_url: str, context: FetchContext) -> list[RetrievalTarget]: ...


class WorldBankAdapter:
    name = "world_bank"

    def build_plan(self, discovery_url: str, context: FetchContext) -> list[RetrievalTarget]:
        parsed = urlsplit(discovery_url)
        if parsed.hostname != "data.worldbank.org" or not parsed.path.startswith("/indicator/"):
            return []
        indicator = parsed.path.removeprefix("/indicator/").strip("/").upper()
        locations = dict(parse_qsl(parsed.query, keep_blank_values=True)).get("locations")
        country_map = {"US": "USA", "USA": "USA", "CN": "CHN", "CHN": "CHN"}
        country = country_map.get((locations or "").upper())
        if not indicator or not country or not context.years or context.country != country:
            return []
        if any(not re.fullmatch(r"(?:19|20)\d{2}", year) for year in context.years):
            return []
        start, end = min(context.years), max(context.years)
        query = urlencode({"format": "json", "date": f"{start}:{end}", "per_page": "100"})
        url = f"https://api.worldbank.org/v2/country/{country}/indicator/{indicator}?{query}"
        return [_target(url, self.name)]


class BeaAdapter:
    name = "bea"

    def build_plan(self, discovery_url: str, context: FetchContext) -> list[RetrievalTarget]:
        parsed = urlsplit(discovery_url)
        if parsed.hostname != "apps.bea.gov" or parsed.path.rstrip("/").lower() != "/api/data":
            return []
        pairs = parse_qsl(parsed.query, keep_blank_values=True)
        values = {name.lower(): value for name, value in pairs}
        required = ("datasetname", "tablename", "year")
        if context.country != "USA" or any(not values.get(name) for name in required):
            return []
        requested_years = {item.strip() for item in values["year"].split(",")}
        if not set(context.years).issubset(requested_years):
            return []
        safe_pairs = [(name, value) for name, value in pairs if name.lower() not in {"userid", "api_key", "apikey"}]
        safe_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(safe_pairs), parsed.fragment))
        return [_target(safe_url, self.name, "BEA_API_KEY")]


class ImfAdapter:
    name = "imf"
    _path = re.compile(r"^/external/datamapper/(?P<indicator>[A-Z0-9_]+)@WEO/(?P<country>[A-Z]{3})/?$")

    def build_plan(self, discovery_url: str, context: FetchContext) -> list[RetrievalTarget]:
        parsed = urlsplit(discovery_url)
        match = self._path.match(parsed.path)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        year = query.get("year")
        if parsed.hostname not in {"imf.org", "www.imf.org"} or not match or not year:
            return []
        if match["country"] != context.country or tuple(context.years) != (year,):
            return []
        url = f"https://www.imf.org/external/datamapper/api/v1/{match['indicator']}/{match['country']}?periods={year}"
        return [_target(url, self.name)]


class OecdAdapter:
    name = "oecd"

    def build_plan(self, discovery_url: str, context: FetchContext) -> list[RetrievalTarget]:
        parsed = urlsplit(discovery_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        is_data_endpoint = (
            parsed.hostname == "sdmx.oecd.org"
            and parsed.path.startswith("/public/rest/v1/data/")
            and len(parsed.path.removeprefix("/public/rest/v1/data/").split("/")) >= 2
        )
        if not is_data_endpoint or not query.get("startPeriod") or not query.get("endPeriod"):
            return []
        if not context.years or min(context.years) < query["startPeriod"] or max(context.years) > query["endPeriod"]:
            return []
        return [_target(discovery_url, self.name)]


class OfficialSourceRouter:
    def __init__(self, adapters: tuple[SourceAdapter, ...] | None = None):
        self.adapters = adapters or (WorldBankAdapter(), BeaAdapter(), ImfAdapter(), OecdAdapter())

    def plan(self, discovery_url: str, context: FetchContext) -> list[RetrievalTarget]:
        for adapter in self.adapters:
            plan = adapter.build_plan(discovery_url, context)
            if plan:
                return plan
        return []
