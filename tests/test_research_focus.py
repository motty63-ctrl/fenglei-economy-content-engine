from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from jsonschema.exceptions import ValidationError

from fanglei.artifact_registry import ArtifactRegistry, ARTIFACT_GRAPH, RESEARCH_FOCUS_ARTIFACT_GRAPH
from fanglei.errors import ArtifactConflictError
from fanglei.models import RunManifest
from fanglei.pipeline import run_v02_pipeline
from fanglei.research_focus import ResearchFocusV1, write_research_focus
from fanglei.providers.search import SearchRequest, SearchResponse, SearchResult
from fanglei.research import FetchedDocument
from fanglei.stages.analyze import analyze_run
from fanglei.stages.ingest import ingest_text
from fanglei.providers.mock import MockAnalysisProvider


ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "research-focus-run"
CREATED_AT = "2026-09-25T10:00:00+08:00"


class FakeSearch:
    name = "focus-test-search"

    def __init__(self):
        self.calls = 0

    def search(self, request: SearchRequest) -> SearchResponse:
        self.calls += 1
        return SearchResponse(request.query, self.name, [
            SearchResult(f"https://source{i}.example/data", f"Source {i}", "discovery only")
            for i in range(1, 4)
        ])


class FakeFetcher:
    def __init__(self):
        self.calls = 0

    def fetch(self, source_id: str, url: str, title: str) -> FetchedDocument:
        self.calls += 1
        host = url.split("/")[2]
        index = int(host.removeprefix("source").split(".")[0])
        kind = {1: "official", 2: "international_organization", 3: "company_disclosure"}[index]
        return FetchedDocument(
            source_id, url, title,
            "Annual economic report.\n2025 GDP growth was 5.0 percent.",
            kind, "2026-01-17", "2026-09-25T00:00:00+00:00",
        )


def _focus(**updates):
    value = {
        "schema_version": "research-focus/1.0",
        "run_id": RUN_ID,
        "case_id": "fed-sep-revisions",
        "primary_question": "What changed between the two published projection sets?",
        "subquestions": ["How did the documented projections compare?"],
        "constraints": ["Do not infer unsupported causality."],
        "created_at": CREATED_AT,
        "created_by": "motty63-ctrl",
    }
    value.update(updates)
    return value


def _run(tmp_path: Path):
    run = ingest_text("# GDP observation\n2025 GDP growth was 5.0 percent.", tmp_path)
    analyze_run(run.name, tmp_path, MockAnalysisProvider())
    search, fetcher = FakeSearch(), FakeFetcher()
    run_v02_pipeline(run.name, tmp_path, search, fetcher)
    return run, search, fetcher


def test_research_focus_contract_is_strict_and_matches_checked_in_schema() -> None:
    focus = ResearchFocusV1.model_validate(_focus())
    schema = json.loads((ROOT / "docs/v0.2/research-focus-1.0.schema.json").read_text("utf-8"))
    jsonschema.validate(focus.model_dump(mode="json"), schema)
    with pytest.raises(ValidationError):
        jsonschema.validate(_focus(primary_question="  "), schema)
    assert focus.created_by == "motty63-ctrl"
    assert focus.schema_version == "research-focus/1.0"


@pytest.mark.parametrize("change", [
    {"schema_version": "research-focus/2.0"},
    {"surprise": "unknown"},
    {"primary_question": "  "},
    {"subquestions": []},
    {"constraints": []},
    {"created_at": "2026-09-25T10:00:00"},
    {"run_id": ""},
    {"case_id": ""},
    {"created_by": ""},
])
def test_research_focus_rejects_malformed_or_incomplete_contract(change) -> None:
    with pytest.raises(Exception):
        ResearchFocusV1.model_validate(_focus(**change))


def test_focus_write_invalidates_research_and_content_only(tmp_path: Path) -> None:
    run, _, _ = _run(tmp_path)
    manifest = RunManifest.model_validate(json.loads((run / "run.json").read_text("utf-8")))
    registry = ArtifactRegistry(run, manifest)
    registry.write_json("angles.json", {"angles": []}, "angle_generation")
    registry.write_text("angle.md", "approved angle\n", "angle_selection")
    registry.write_json("script.json", {"sentences": []}, "script_generation")
    registry.write_text("script.md", "approved script\n", "script_render")
    registry.write_json("visual_beats.json", {"beats": []}, "visual_planning")
    registry.save_manifest()

    result = write_research_focus(run.name, tmp_path, _focus(run_id=run.name))
    assert result == run / "research_focus.json"

    after = json.loads((run / "run.json").read_text("utf-8"))
    for name in (
        "questions.json", "search_results.json", "source_documents/index.json",
        "sources.json", "facts.json",
    ):
        assert after["artifacts"][name]["status"] == "valid", name
    for name in ("research.md", "angles.json", "angle.md", "script.json", "script.md", "visual_beats.json"):
        assert after["artifacts"][name]["status"] == "stale", name
    assert ARTIFACT_GRAPH["research.md"] == ("research_synthesis", ("questions.json", "sources.json", "facts.json"))
    assert after["artifacts"]["research_focus.json"]["owner"] == "research_focus"
    assert after["artifacts"]["research_focus.json"]["status"] == "valid"
    assert "research_focus.json" in RESEARCH_FOCUS_ARTIFACT_GRAPH["research.md"][1]
    run_v02_pipeline(run.name, tmp_path, FakeSearch(), FakeFetcher(), force_stage="research_synthesis")
    regenerated = json.loads((run / "run.json").read_text("utf-8"))
    assert regenerated["artifacts"]["research.md"]["dependencies"]["research_focus.json"]
    updated_focus = _focus(run_id=run.name, primary_question="How did the published projections change?")
    write_research_focus(run.name, tmp_path, updated_focus, force=True)
    invalidated = json.loads((run / "run.json").read_text("utf-8"))
    assert invalidated["artifacts"]["research.md"]["status"] == "stale"
    assert invalidated["artifacts"]["sources.json"]["status"] == "valid"
    assert invalidated["artifacts"]["facts.json"]["status"] == "valid"


def test_focus_identity_must_match_run_and_approved_case(tmp_path: Path) -> None:
    run, _, _ = _run(tmp_path)
    with pytest.raises(ArtifactConflictError, match="run_id"):
        write_research_focus(run.name, tmp_path, _focus(run_id="another-run"))


def test_research_focus_rendering_prefers_focus_and_keeps_legacy_dispatch(tmp_path: Path) -> None:
    run, search, fetcher = _run(tmp_path)
    old_questions = json.loads((run / "questions.json").read_text("utf-8"))
    old_question = old_questions["research_questions"][1]["question"]
    old_research = (run / "research.md").read_text("utf-8")
    assert old_question in old_research

    write_research_focus(run.name, tmp_path, _focus(run_id=run.name))
    run_v02_pipeline(run.name, tmp_path, search, fetcher, force_stage="research_synthesis")
    new_research = (run / "research.md").read_text("utf-8")
    assert "What changed between the two published projection sets?" in new_research
    assert "Do not infer unsupported causality." in new_research
    assert old_question not in new_research
    assert search.calls == 1
    assert fetcher.calls == 3


def test_invalid_present_focus_fails_closed_without_legacy_fallback(tmp_path: Path) -> None:
    run, search, fetcher = _run(tmp_path)
    write_research_focus(run.name, tmp_path, _focus(run_id=run.name))
    original = (run / "research.md").read_bytes()
    (run / "research_focus.json").write_text('{"schema_version":"research-focus/99.0"}\n', encoding="utf-8")

    with pytest.raises(ArtifactConflictError):
        run_v02_pipeline(run.name, tmp_path, search, fetcher, force_stage="research_synthesis")
    assert (run / "research.md").read_bytes() == original
    assert search.calls == 1
    assert fetcher.calls == 3


def test_unregistered_focus_file_fails_closed_before_pipeline_stage_dispatch(tmp_path: Path) -> None:
    run, search, fetcher = _run(tmp_path)
    original = (run / "research.md").read_bytes()
    (run / "research_focus.json").write_text('{"schema_version":"research-focus/99.0"}\n', encoding="utf-8")

    with pytest.raises(ArtifactConflictError, match="research_focus"):
        run_v02_pipeline(run.name, tmp_path, search, fetcher, force_stage="research_synthesis")
    assert (run / "research.md").read_bytes() == original
    assert search.calls == 1
    assert fetcher.calls == 3


def test_deleted_registered_focus_fails_closed_without_legacy_fallback(tmp_path: Path) -> None:
    run, search, fetcher = _run(tmp_path)
    write_research_focus(run.name, tmp_path, _focus(run_id=run.name))
    original = (run / "research.md").read_bytes()
    (run / "research_focus.json").unlink()

    with pytest.raises(ArtifactConflictError, match="research_focus"):
        run_v02_pipeline(run.name, tmp_path, search, fetcher, force_stage="research_synthesis")
    assert (run / "research.md").read_bytes() == original
    assert search.calls == 1
    assert fetcher.calls == 3


def test_renderer_uses_only_allowed_verified_claims_and_separates_evidence_layers() -> None:
    from fanglei.pipeline import _render_research_focus

    focus = ResearchFocusV1.model_validate(_focus())
    sources = {
        "schema_version": "2.1",
        "source_policy": {
            "approved_documents": [
                {"source_id": "sep-june", "document_identity": "federal-reserve-sep-june", "evidence_role": "baseline-sep"},
                {"source_id": "sep-september", "document_identity": "federal-reserve-sep-september", "evidence_role": "target-sep"},
                {"source_id": "statement-september", "document_identity": "federal-reserve-fomc-statement-september", "evidence_role": "target-meeting-context"},
            ]
        },
        "sources": [
            {"source_id": "sep-june", "title": "June SEP", "url": "https://example.test/june", "credibility_tier": "A"},
            {"source_id": "sep-september", "title": "September SEP", "url": "https://example.test/september", "credibility_tier": "A"},
            {"source_id": "statement-september", "title": "September Statement", "url": "https://example.test/statement", "credibility_tier": "A"},
        ],
    }
    facts = {"claims": [
        {
            "claim_id": "claim_001", "claim_text": "FOMC participants (SEP) projection changed from 2.2 to 2.3.",
            "verification_status": "verified", "verification_basis": "authoritative_primary_attestation", "allowed_downstream": True,
            "source_ids": ["sep-june", "sep-september"], "evidence": [{"source_id": "sep-june", "evidence_text": "Median: 2.2"}],
            "authority_attestation": {"kind": "deterministic_document_comparison", "source_ids": ["sep-june", "sep-september"]},
        },
        {
            "claim_id": "claim_002", "claim_text": 'Federal Reserve September FOMC statement says: "Inflation remains elevated."',
            "verification_status": "verified", "verification_basis": "authoritative_primary_attestation", "allowed_downstream": True,
            "source_ids": ["statement-september"], "evidence": [{"source_id": "statement-september", "evidence_text": "Inflation remains elevated."}],
            "authority_attestation": {"kind": "document_report", "source_ids": ["statement-september"]},
        },
        {
            "claim_id": "claim_003", "claim_text": "Unverified causal claim", "verification_status": "unverified",
            "verification_basis": "none", "allowed_downstream": False, "source_ids": [], "evidence": [], "authority_attestation": None,
        },
        {
            "claim_id": "claim_004", "claim_text": "Not allowed despite verified label", "verification_status": "verified",
            "verification_basis": "authoritative_primary_attestation", "allowed_downstream": False, "source_ids": [], "evidence": [], "authority_attestation": None,
        },
    ]}

    rendered = _render_research_focus(RUN_ID, focus, sources, facts)
    assert "A. June-to-September SEP revisions" in rendered
    assert "B. September FOMC statement context" in rendered
    assert "claim_001" in rendered and "claim_002" in rendered
    assert "claim_003" not in rendered and "claim_004" not in rendered
    assert "does not infer a causal relationship" in rendered
