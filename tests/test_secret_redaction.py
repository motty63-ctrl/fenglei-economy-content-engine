import json
from pathlib import Path

import pytest

from fanglei.cli import _fail
from fanglei.errors import ProviderError
from fanglei.pipeline import run_v02_pipeline
from fanglei.providers.mock_research import MockDocumentFetcher
from fanglei.providers.mock import MockAnalysisProvider
from fanglei.providers.search import SearchRequest, TavilySearchProvider
from fanglei.security import redact_text, sanitize_url
from fanglei.stages.analyze import analyze_run
from fanglei.stages.ingest import ingest_text


SENTINEL = "super-secret-test-value-123"


def test_redacts_auth_headers_secret_query_values_and_environment_values(monkeypatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", SENTINEL)
    value = (
        f"Authorization: Bearer {SENTINEL}; X-API-Key={SENTINEL}; "
        f"https://api.example/data?locations=US&api_key={SENTINEL}&token={SENTINEL}"
    )
    redacted = redact_text(value)
    assert SENTINEL not in redacted
    assert "locations=US" in redacted
    replacements = redacted.count("[REDACTED]") + redacted.count("%5BREDACTED%5D")
    assert replacements >= 4


def test_sanitized_url_keeps_research_parameters_but_removes_credentials() -> None:
    safe = sanitize_url(
        f"https://api.example/data?country=US&year=2024&UserID={SENTINEL}&access_token={SENTINEL}"
    )
    assert SENTINEL not in safe
    assert "country=US" in safe and "year=2024" in safe
    assert "UserID=%5BREDACTED%5D" in safe


def test_provider_error_suppresses_secret_and_raw_exception_chain() -> None:
    def fail(_payload):
        raise RuntimeError(f"Authorization: Bearer {SENTINEL}")

    with pytest.raises(ProviderError) as captured:
        TavilySearchProvider(SENTINEL, transport=fail).search(SearchRequest(query="GDP"))
    assert SENTINEL not in str(captured.value)
    assert captured.value.__cause__ is None


def test_redacts_quoted_header_mapping_without_environment_secret(monkeypatch) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    request = {
        "headers": {
            "Authorization": f"Bearer {SENTINEL}",
            "X-API-Key": SENTINEL,
        }
    }
    redacted = redact_text(request)
    assert SENTINEL not in redacted
    assert redacted.count("[REDACTED]") == 2


def test_stage_error_and_cli_stderr_are_redacted(tmp_path: Path, capsys) -> None:
    run = ingest_text("GDP 2024", tmp_path)
    analyze_run(run.name, tmp_path, MockAnalysisProvider())

    class BrokenSearch:
        name = "broken"

        def search(self, _request):
            raise ProviderError(f"endpoint?api_key={SENTINEL}")

    with pytest.raises(ProviderError):
        run_v02_pipeline(run.name, tmp_path, BrokenSearch(), MockDocumentFetcher())
    manifest_text = (run / "run.json").read_text(encoding="utf-8")
    assert SENTINEL not in manifest_text
    assert "[REDACTED]" in manifest_text

    with pytest.raises(Exception):
        _fail(ProviderError(f"Authorization: Bearer {SENTINEL}"))
    captured = capsys.readouterr()
    assert SENTINEL not in captured.err
