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
