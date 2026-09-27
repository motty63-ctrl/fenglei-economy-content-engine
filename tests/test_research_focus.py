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


def test_force_rebinds_unchanged_focus_after_facts_are_rebuilt(tmp_path: Path) -> None:
    run, _, _ = _run(tmp_path)
    focus = _focus(run_id=run.name)
    write_research_focus(run.name, tmp_path, focus)

    manifest = RunManifest.model_validate(json.loads((run / "run.json").read_text("utf-8")))
    registry = ArtifactRegistry(run, manifest, research_focus_mode=True)
    facts = registry.read_json("facts.json")
    facts["checked_at"] = "2026-09-26T12:00:00+00:00"
    registry.write_json("facts.json", facts, "factcheck", force=True)
    registry.save_manifest()
    stale = json.loads((run / "run.json").read_text("utf-8"))
    assert stale["artifacts"]["research_focus.json"]["status"] == "stale"

    write_research_focus(run.name, tmp_path, focus, force=True)
    rebound = json.loads((run / "run.json").read_text("utf-8"))
    assert rebound["artifacts"]["research_focus.json"]["status"] == "valid"
    assert rebound["artifacts"]["research_focus.json"]["dependencies"]["facts.json"] == rebound[
        "artifacts"
    ]["facts.json"]["content_hash"]


def test_focus_identity_must_match_run_and_approved_case(tmp_path: Path) -> None:
    run, _, _ = _run(tmp_path)
    with pytest.raises(ArtifactConflictError, match="run_id"):
        write_research_focus(run.name, tmp_path, _focus(run_id="another-run"))


def test_research_focus_rendering_prefers_focus_and_keeps_legacy_dispatch(tmp_path: Path) -> None:
    run, search, fetcher = _run(tmp_path)
    search_calls_before_synthesis = search.calls
    fetch_calls_before_synthesis = fetcher.calls
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
    assert search.calls == search_calls_before_synthesis
    assert fetcher.calls == fetch_calls_before_synthesis


def test_invalid_present_focus_fails_closed_without_legacy_fallback(tmp_path: Path) -> None:
    run, search, fetcher = _run(tmp_path)
    search_calls_before_dispatch = search.calls
    fetch_calls_before_dispatch = fetcher.calls
    write_research_focus(run.name, tmp_path, _focus(run_id=run.name))
    original = (run / "research.md").read_bytes()
    (run / "research_focus.json").write_text('{"schema_version":"research-focus/99.0"}\n', encoding="utf-8")

    with pytest.raises(ArtifactConflictError):
        run_v02_pipeline(run.name, tmp_path, search, fetcher, force_stage="research_synthesis")
    assert (run / "research.md").read_bytes() == original
    assert search.calls == search_calls_before_dispatch
    assert fetcher.calls == fetch_calls_before_dispatch


def test_unregistered_focus_file_fails_closed_before_pipeline_stage_dispatch(tmp_path: Path) -> None:
    run, search, fetcher = _run(tmp_path)
    search_calls_before_dispatch = search.calls
    fetch_calls_before_dispatch = fetcher.calls
    original = (run / "research.md").read_bytes()
    (run / "research_focus.json").write_text('{"schema_version":"research-focus/99.0"}\n', encoding="utf-8")

    with pytest.raises(ArtifactConflictError, match="research_focus"):
        run_v02_pipeline(run.name, tmp_path, search, fetcher, force_stage="research_synthesis")
    assert (run / "research.md").read_bytes() == original
    assert search.calls == search_calls_before_dispatch
    assert fetcher.calls == fetch_calls_before_dispatch


def test_deleted_registered_focus_fails_closed_without_legacy_fallback(tmp_path: Path) -> None:
    run, search, fetcher = _run(tmp_path)
    search_calls_before_dispatch = search.calls
    fetch_calls_before_dispatch = fetcher.calls
    write_research_focus(run.name, tmp_path, _focus(run_id=run.name))
    original = (run / "research.md").read_bytes()
    (run / "research_focus.json").unlink()

    with pytest.raises(ArtifactConflictError, match="research_focus"):
        run_v02_pipeline(run.name, tmp_path, search, fetcher, force_stage="research_synthesis")
    assert (run / "research.md").read_bytes() == original
    assert search.calls == search_calls_before_dispatch
    assert fetcher.calls == fetch_calls_before_dispatch


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
    assert focus.primary_question in rendered
    assert "baseline-sep" in rendered and "target-sep" in rendered
    assert "target-meeting-context" in rendered
    assert "claim_001" in rendered and "claim_002" in rendered
    assert "claim_003" not in rendered and "claim_004" not in rendered


def test_research_focus_renderer_uses_synthetic_non_fed_roles_without_case_framing() -> None:
    from fanglei.pipeline import _render_research_focus

    focus = ResearchFocusV1.model_validate(_focus(
        case_id="synthetic-retail-sales",
        primary_question="How did monthly retail sales change between period 1 and period 2?",
        subquestions=["Which category recorded the largest change?", "What does the release say about coverage?"],
        constraints=["Describe reported changes; do not infer causes."],
    ))
    sources = {
        "schema_version": "2.1",
        "source_policy": {"approved_documents": [
            {"source_id": "retail-period-1", "document_identity": "synthetic-retail-release-p1",
             "evidence_role": "baseline-monthly-retail-release-period-1"},
            {"source_id": "retail-period-2", "document_identity": "synthetic-retail-release-p2",
             "evidence_role": "target-monthly-retail-release-period-2"},
        ]},
        "sources": [
            {"source_id": "retail-period-1", "title": "Synthetic Retail Release Period 1",
             "url": "https://example.test/retail/p1", "credibility_tier": "A"},
            {"source_id": "retail-period-2", "title": "Synthetic Retail Release Period 2",
             "url": "https://example.test/retail/p2", "credibility_tier": "A"},
        ],
    }
    facts = {"claims": [{
        "claim_id": "synthetic_claim_001",
        "claim_text": "The synthetic release reports retail sales volume rose from 100 to 103 units.",
        "verification_status": "verified",
        "verification_basis": "authoritative_primary_attestation",
        "allowed_downstream": True,
        "source_ids": ["retail-period-1", "retail-period-2"],
        "evidence": [
            {"source_id": "retail-period-1", "relation": "supports", "evidence_eligible": True,
             "evidence_text": "Period 1 index: 100 units."},
            {"source_id": "retail-period-2", "relation": "supports", "evidence_eligible": True,
             "evidence_text": "Period 2 index: 103 units."},
        ],
        "authority_attestation": {
            "kind": "deterministic_document_comparison", "source_ids": ["retail-period-1", "retail-period-2"],
        },
    }]}

    rendered = _render_research_focus(RUN_ID, focus, sources, facts)
    assert focus.primary_question in rendered
    assert all(question in rendered for question in focus.subquestions)
    assert all(constraint in rendered for constraint in focus.constraints)
    assert "baseline-monthly-retail-release-period-1" in rendered
    assert "target-monthly-retail-release-period-2" in rendered
    assert "synthetic_claim_001" in rendered
    assert "Period 1 index: 100 units." in rendered
    assert "Period 2 index: 103 units." in rendered
    for case_framing in ("SEP", "FOMC", "June-to-September", "Federal Reserve"):
        assert case_framing not in rendered


def test_research_focus_renders_atomic_proposition_instead_of_full_evidence_span() -> None:
    from fanglei.pipeline import _render_research_focus

    focus = ResearchFocusV1.model_validate(_focus(
        case_id="synthetic-retail-sales",
        primary_question="What did the first synthetic metric report?",
        subquestions=["What value was reported?"],
        constraints=["Keep each assertion within its bound evidence scope."],
    ))
    full_evidence = "Metric A rose to 10 units in Period 1, while Metric B remained at 5 units in Period 1."
    proposition = "Metric A rose to 10 units in Period 1"
    sources = {
        "sources": [{"source_id": "synthetic-source", "title": "Synthetic release",
                     "url": "https://example.test/release", "credibility_tier": "A"}],
        "source_policy": {"approved_documents": []},
    }
    facts = {"claims": [{
        "claim_id": "synthetic_claim_a",
        "claim_text": f'Synthetic Statistical Office: "{proposition}"',
        "verification_status": "verified",
        "verification_basis": "authoritative_primary_attestation",
        "allowed_downstream": True,
        "source_ids": ["synthetic-source"],
        "authority_attestation": {"kind": "document_report", "source_ids": ["synthetic-source"]},
        "evidence": [{
            "source_id": "synthetic-source",
            "relation": "supports",
            "evidence_eligible": True,
            "paragraph_locator": "line:1",
            "evidence_text": full_evidence,
            "proposition_span": {"start": 0, "end": len(proposition), "text": proposition},
        }],
    }]}

    rendered = _render_research_focus(RUN_ID, focus, sources, facts)

    assert proposition in rendered
    assert full_evidence not in rendered
    assert "Metric B remained" not in rendered


def test_research_focus_groups_same_fallback_roles_independent_of_source_order() -> None:
    from fanglei.pipeline import _render_research_focus

    focus = ResearchFocusV1.model_validate(_focus(
        case_id="synthetic-retail-sales",
        primary_question="What do the two synthetic releases report?",
        subquestions=["Compare the release values."],
        constraints=["Do not infer causes."],
    ))
    sources = {
        "sources": [
            {"source_id": "source-a", "title": "Synthetic release A", "source_type": "baseline_release",
             "url": "https://example.test/a"},
            {"source_id": "source-b", "title": "Synthetic release B", "source_type": "target_release",
             "url": "https://example.test/b"},
        ],
        "source_policy": {"approved_documents": []},
    }
    facts = {"claims": [
        {
            "claim_id": claim_id,
            "claim_text": claim_id,
            "verification_status": "verified",
            "allowed_downstream": True,
            "source_ids": source_ids,
            "evidence": [],
        }
        for claim_id, source_ids in (
            ("claim_ab", ["source-a", "source-b"]),
            ("claim_ba", ["source-b", "source-a"]),
        )
    ]}

    rendered = _render_research_focus(RUN_ID, focus, sources, facts)

    assert rendered.count("### Evidence group") == 1
    assert "claim_ab" in rendered
    assert "claim_ba" in rendered
