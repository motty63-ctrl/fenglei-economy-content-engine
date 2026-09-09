"""Opt-in real World Bank API retrieval; no credential is required."""

import os

import pytest

from fanglei.evidence_policy import gate_evidence
from fanglei.providers.document import FetchContext
from fanglei.providers.http_fetch import HttpDocumentFetcher
from fanglei.research import RuleBasedEvidenceExtractor


@pytest.mark.integration
def test_world_bank_live_api_has_exact_traceable_observation() -> None:
    if os.environ.get("RUN_OFFICIAL_INTEGRATION") != "1":
        pytest.skip("set RUN_OFFICIAL_INTEGRATION=1 to run official-source integration")
    context = FetchContext(
        country="USA", years=("2024",), indicators=("real_gdp_growth",),
        questions=("What was United States real GDP growth in 2024?",),
    )
    document = HttpDocumentFetcher().with_context(context).fetch(
        "src_live",
        "https://data.worldbank.org/indicator/NY.GDP.MKTP.KD.ZG?locations=US",
        "GDP growth (annual %) - United States",
    )
    evidence = RuleBasedEvidenceExtractor().extract([document], list(context.questions))
    gated = gate_evidence(evidence, [document])
    target = next(item for item in gated if item.get("json_pointer") == "/1/0/value")
    assert target["evidence_eligible"] is True
    assert target["observation"] is not None
    assert target["api_endpoint"].startswith("https://api.worldbank.org/")
    assert len(target["request_fingerprint"]) == 64
    assert target["document_hash"] == document.document_hash
