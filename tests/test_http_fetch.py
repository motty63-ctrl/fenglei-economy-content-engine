import pytest

from fanglei.errors import ProviderError
from fanglei.providers.http_fetch import HttpDocumentFetcher


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
