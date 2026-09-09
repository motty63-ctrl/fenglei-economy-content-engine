import pytest
import json

from fanglei.errors import ProviderError
from fanglei.providers.http_fetch import HttpDocumentFetcher
from fanglei.providers.document import FetchContext


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "http://127.0.0.1/admin",
    "http://169.254.169.254/latest/meta-data",
    "http://localhost/private",
])
def test_fetcher_rejects_non_http_and_private_targets(url: str) -> None:
    with pytest.raises(ProviderError, match="blocked"):
        HttpDocumentFetcher().fetch("src", url, "bad")


def test_authority_classification_requires_exact_domain_boundary() -> None:
    classify = HttpDocumentFetcher._classify_source_type
    assert classify("data.worldbank.org") == "international_organization"
    assert classify("worldbank.org.evil.example") == "mainstream_media"
    assert classify("evil-imf.org") == "mainstream_media"


def test_request_target_percent_encodes_unicode_path() -> None:
    target = HttpDocumentFetcher._request_target("https://example.com/经济数据?q=实际 GDP")
    assert target == "/%E7%BB%8F%E6%B5%8E%E6%95%B0%E6%8D%AE?q=%E5%AE%9E%E9%99%85%20GDP"


def test_only_textual_content_types_are_evidence_eligible() -> None:
    supports = HttpDocumentFetcher._supports_content_type
    assert supports("text/html; charset=utf-8") is True
    assert supports("text/plain") is True
    assert supports("application/pdf") is False
    assert supports("application/octet-stream") is False


def test_world_bank_indicator_page_resolves_to_official_api() -> None:
    page = "https://data.worldbank.org/indicator/NY.GDP.MKTP.KD.ZG?locations=US"
    api_url = HttpDocumentFetcher._official_data_url(page)
    assert api_url is not None
    assert api_url.startswith("https://api.worldbank.org/v2/country/USA/indicator/NY.GDP.MKTP.KD.ZG")


def test_world_bank_api_is_normalized_without_losing_raw_value() -> None:
    payload = [
        {"page": 1},
        [{
            "indicator": {"value": "GDP growth (annual %)"},
            "country": {"value": "United States"},
            "date": "2024",
            "value": 2.79318715363841,
        }],
    ]
    text = HttpDocumentFetcher._world_bank_text(payload)
    assert "2.8% in 2024" in text
    assert "raw value 2.79318715363841" in text


def test_world_bank_normalizer_does_not_relabel_per_capita_as_real_gdp() -> None:
    payload = [
        {"page": 1},
        [{
            "indicator": {"id": "NY.GDP.PCAP.KD.ZG", "value": "GDP per capita growth (annual %)"},
            "country": {"value": "United States"},
            "date": "2024",
            "value": 1.81099561417319,
        }],
    ]
    text = HttpDocumentFetcher._world_bank_text(payload)
    assert "GDP per capita growth (annual %) was 1.8% in 2024" in text
    assert "real GDP growth" not in text


def test_official_api_fetch_retains_exact_json_observation_and_fingerprint() -> None:
    payload = [
        {"page": 1, "lastupdated": "2026-09-01"},
        [{
            "indicator": {"id": "NY.GDP.MKTP.KD.ZG", "value": "GDP growth (annual %)"},
            "country": {"id": "US", "value": "United States"},
            "date": "2024",
            "value": 2.79318715363841,
        }],
    ]

    class Headers:
        def get_content_charset(self):
            return "utf-8"

    class Response:
        status = 200
        headers = Headers()

        def getheader(self, name, default=""):
            return "application/json" if name == "Content-Type" else default

        def read(self, _limit):
            return json.dumps(payload).encode("utf-8")

    class Connection:
        def close(self):
            pass

    class StubFetcher(HttpDocumentFetcher):
        def _request_once(self, url):
            self.requested_url = url
            return Response(), Connection()

    fetcher = StubFetcher().with_context(
        FetchContext(country="USA", years=("2024",), indicators=("real_gdp_growth",), questions=())
    )
    doc = fetcher.fetch(
        "src_001",
        "https://data.worldbank.org/indicator/NY.GDP.MKTP.KD.ZG?locations=US",
        "GDP growth",
    )
    assert doc.document_format == "api"
    assert doc.api_endpoint == fetcher.requested_url
    assert len(doc.request_fingerprint or "") == 64
    assert doc.document_hash
    observation = doc.api_observations[0]
    assert observation["json_pointer"] == "/1/0/value"
    assert observation["observation"] == 2.79318715363841
    assert observation["year"] == "2024"
    assert doc.raw_content and "2.79318715363841" in doc.raw_content


@pytest.mark.parametrize(
    ("html", "code"),
    [
        ("<html><body></body></html>", "empty_body"),
        ("<html><body>IMF Data Mapper { indicator.label } { related.length }</body></html>", "dynamic_content_unavailable"),
    ],
)
def test_empty_or_dynamic_html_is_not_reported_as_success(html: str, code: str) -> None:
    class Headers:
        def get_content_charset(self):
            return "utf-8"

    class Response:
        status = 200
        headers = Headers()

        def getheader(self, name, default=""):
            return "text/html" if name == "Content-Type" else default

        def read(self, _limit):
            return html.encode("utf-8")

    class Connection:
        def close(self):
            pass

    class StubFetcher(HttpDocumentFetcher):
        def _request_once(self, _url):
            return Response(), Connection()

    with pytest.raises(ProviderError, match=code):
        StubFetcher().fetch("src", "https://www.imf.org/data", "IMF")
