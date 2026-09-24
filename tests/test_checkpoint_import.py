from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError
import fanglei.checkpoint_import as checkpoint_import
from test_checkpoint_contract import _checkpoint as _v2_checkpoint

from fanglei.artifact_registry import ARTIFACT_GRAPH
from fanglei.checkpoint_contract import canonical_body_sha256
from fanglei.checkpoint_contract import UnsupportedCheckpointVersionError
from fanglei.checkpoint_import import (
    CheckpointImporter,
    SourceCapture,
    SourceContentChangedError,
)


SOURCE_URL = "https://stats.example.gov/reports/gdp"
SOURCE_BODY = b"GDP was 2.0% in 2025.\n"


class StaticSourceFetcher:
    def __init__(self, body: bytes = SOURCE_BODY):
        self.body = body
        self.calls: list[str] = []

    def fetch(self, url: str) -> SourceCapture:
        self.calls.append(url)
        return SourceCapture(
            url=url,
            content=self.body,
            content_type="text/plain; charset=utf-8",
            title="Example national statistics release",
            published_at="2026-01-15",
            retrieved_at="2026-09-23T09:00:00+08:00",
        )


def _checkpoint() -> dict:
    script_text = (
        "GDP was 2.0% in 2025.\n"
        "This is an annual estimate.\n"
        "The number can be revised.\n"
        "Read the source date."
    )
    encoded = script_text.encode("utf-8")
    texts = [
        "GDP was 2.0% in 2025.",
        "This is an annual estimate.",
        "The number can be revised.",
        "Read the source date.",
    ]
    sentences = []
    previous_end = 0
    for index, sentence_text in enumerate(texts):
        start = encoded.index(sentence_text.encode("utf-8"), previous_end)
        end = start + len(sentence_text.encode("utf-8"))
        previous_end = end
        sentences.append({
            "external_id": f"s_{index + 1:03d}",
            "byte_start": start,
            "byte_end": end,
            "section": "phenomenon" if index == 0 else "mechanism",
            "sentence_type": "verified_fact" if index == 0 else "explanation",
            "claim_ids": ["C-legacy"] if index == 0 else [],
            "evidence_ids": ["E01"] if index == 0 else [],
        })

    return {
        "checkpoint_schema_version": "1.0",
        "checkpoint_id": "approved-checkpoint-example",
        "approval": {
            "status": "approved",
            "reviewer": "reviewer-1",
            "approved_at": "2026-09-23T09:00:00+08:00",
        },
        "runtime_metadata": {"imported_at": "2026-09-23T09:01:00+08:00"},
        "research": {"content": "# Approved research\nExact checkpoint text.\n"},
        "sources": [{
            "external_id": "SRC01",
            "url": SOURCE_URL,
            "official": True,
            "title": "Example national statistics release",
        }],
        "claims": [{
            "external_id": "C-legacy",
            "proposition": "GDP was 2.0% in 2025.",
            "classification": "fact",
            "verification_status": "verified",
            "verification_reason": "The official release reports this value.",
            "allowed_downstream": True,
            "source_ids": ["SRC01"],
            "evidence_ids": ["E01"],
        }],
        "evidence": [{
            "external_id": "E01",
            "claim_ids": ["C-legacy"],
            "source_ids": ["SRC01"],
            "relation": "supports",
            "evidence_rationale": "The cited table row reports the claim value.",
            "excerpt_anchor": "GDP was 2.0% in 2025.",
            "evidence_text": None,
            "source_section": None,
            "paragraph_locator": None,
            "published_at": None,
            "retrieved_at": None,
        }],
        "angle": {
            "external_id": "A-legacy",
            "title": "Approved title",
            "hook": "Approved hook",
            "core_question": "What does the estimate show?",
            "core_insight": "The release reports an annual value.",
            "hook_mechanism": "A cited value",
            "audience_takeaway": "Read the source date",
            "narrative_framing": "economic_data_literacy",
            "supporting_claim_ids": ["C-legacy"],
            "audience_relevance": 4,
            "novelty": 3,
            "hook_strength": 4,
            "visual_potential": 3,
            "explainability": 5,
            "risk_notes": [],
            "evidence_strength": 4,
            "controversy_risk": 0,
            "total_score": 80,
            "eligibility": "eligible",
            "rejection_codes": [],
            "originality": {"status": "passed"},
        },
        "script": {
            "external_id": "SCRIPT-legacy",
            "text": script_text,
            "angle_external_id": "A-legacy",
            "title": "Approved title",
            "target_duration_seconds": 60,
            "speaking_rate_chars_per_second": 4.8,
            "spoken_character_count": len(script_text.replace("\n", "")),
            "estimated_duration_seconds": 60.0,
            "sentences": sentences,
        },
    }


def _importer(tmp_path: Path, fetcher: StaticSourceFetcher | None = None) -> CheckpointImporter:
    return CheckpointImporter(
        runs_dir=tmp_path / "runs",
        source_cache_dir=tmp_path / "source-cache",
        source_fetcher=fetcher or StaticSourceFetcher(),
        importer_version="test-1.0",
    )


def test_legacy_ids_are_canonicalized_and_mapping_is_auditable(tmp_path: Path) -> None:
    result = _importer(tmp_path).stage(_checkpoint())

    mapping = json.loads((result.staging_dir / "materialized" / "id_mapping.json").read_text("utf-8"))
    assert mapping["mappings"]["sentences"][0] == {
        "source_id": "s_001", "canonical_id": "sentence_001", "source_order": 1
    }
    assert mapping["mappings"]["claims"][0]["source_id"] == "C-legacy"
    assert mapping["mappings"]["claims"][0]["canonical_id"] == "claim_001"
    assert mapping["mappings"]["evidence"][0]["source_id"] == "E01"
    assert mapping["bindings"][0]["evidence_ids"] == ["evidence_001"]


def test_id_mapping_and_semantic_hash_ignore_runtime_timestamps(tmp_path: Path) -> None:
    first = _checkpoint()
    second = copy.deepcopy(first)
    second["runtime_metadata"]["imported_at"] = "2030-01-01T00:00:00Z"
    second["runtime_metadata"]["executed_at"] = "2030-01-01T00:00:01Z"
    second["evidence"][0]["retrieved_at"] = "2030-01-02T00:00:00Z"
    fetcher = StaticSourceFetcher()
    first_result = _importer(tmp_path / "first", fetcher).stage(first)
    second_result = _importer(tmp_path / "second", fetcher).stage(second)

    assert first_result.checkpoint_fingerprint == second_result.checkpoint_fingerprint
    assert first_result.mapping_sha256 == second_result.mapping_sha256
    assert first_result.semantic_artifact_hashes == second_result.semantic_artifact_hashes


def test_generated_audit_timestamps_do_not_change_semantic_artifact_hashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    importer = _importer(tmp_path, StaticSourceFetcher())
    checkpoint = _checkpoint()
    monkeypatch.setattr(checkpoint_import, "_now", lambda: "2026-09-23T09:00:00+00:00")
    first = importer.stage(checkpoint)

    monkeypatch.setattr(checkpoint_import, "_now", lambda: "2030-01-01T00:00:00+00:00")
    second = importer.stage(checkpoint)

    assert first.checkpoint_fingerprint == second.checkpoint_fingerprint
    assert first.mapping_sha256 == second.mapping_sha256
    assert first.semantic_artifact_hashes == second.semantic_artifact_hashes


def test_materialized_script_preserves_approved_sentence_bytes(tmp_path: Path) -> None:
    checkpoint = _checkpoint()
    result = _importer(tmp_path).stage(checkpoint)
    script = json.loads((result.staging_dir / "materialized" / "script.json").read_text("utf-8"))

    assert [row["text"] for row in script["sentences"]] == [
        "GDP was 2.0% in 2025.",
        "This is an annual estimate.",
        "The number can be revised.",
        "Read the source date.",
    ]
    assert script["sentences"][0]["sentence_id"] == "sentence_001"
    assert (result.staging_dir / "materialized" / "script.md").read_bytes() == checkpoint["script"]["text"].encode("utf-8")


def test_materialized_artifacts_pass_existing_json_schemas(tmp_path: Path) -> None:
    result = _importer(tmp_path).stage(_checkpoint())
    artifacts = result.staging_dir / "materialized"
    root = Path(__file__).resolve().parents[1]
    facts_schema = json.loads((root / "docs/v0.2/facts.schema.json").read_text("utf-8"))
    script_schema = json.loads((root / "docs/v0.3/script-contract.schema.json").read_text("utf-8"))

    jsonschema.validate(json.loads((artifacts / "facts.json").read_text("utf-8")), facts_schema)
    jsonschema.validate(json.loads((artifacts / "script.json").read_text("utf-8")), script_schema)
    assert result.gates["schema"]["passed"] is True
    assert result.gates["provenance"]["passed"] is True
    assert result.gates["fact_coverage"]["coverage"] == 1.0
    assert result.gates["script_coverage"]["coverage"] == 1.0


def test_unknown_claim_reference_is_never_generated_from_its_name(tmp_path: Path) -> None:
    checkpoint = _checkpoint()
    checkpoint["script"]["sentences"][0]["claim_ids"] = ["C-UNKNOWN"]

    result = _importer(tmp_path).stage(checkpoint)

    assert result.gates["schema"]["passed"] is False
    assert any(issue["code"] == "UNKNOWN_CLAIM_ID" for issue in result.gates["issues"])
    assert not (result.staging_dir / "materialized" / "facts.json").exists()


def test_unrecoverable_evidence_provenance_fails_closed(tmp_path: Path) -> None:
    checkpoint = _checkpoint()
    checkpoint["evidence"][0]["excerpt_anchor"] = "phrase absent from source"

    result = _importer(tmp_path).stage(checkpoint)

    assert result.gates["provenance"]["passed"] is False
    assert any(issue["code"] == "PROVENANCE_EXCERPT_NOT_FOUND" for issue in result.gates["issues"])
    assert not (result.staging_dir / "materialized" / "facts.json").exists()


def test_unapproved_source_is_rejected_before_fetch(tmp_path: Path) -> None:
    checkpoint = _checkpoint()
    checkpoint["sources"][0]["official"] = False
    fetcher = StaticSourceFetcher()

    result = _importer(tmp_path, fetcher).stage(checkpoint)

    assert result.gates["provenance"]["passed"] is False
    assert fetcher.calls == []


def test_missing_approved_angle_schema_fields_fail_before_source_capture(tmp_path: Path) -> None:
    checkpoint = _checkpoint()
    checkpoint["angle"] = {
        "external_id": "A-legacy",
        "title": "Approved title",
        "supporting_claim_ids": ["C-legacy"],
    }
    fetcher = StaticSourceFetcher()

    result = _importer(tmp_path, fetcher).stage(checkpoint)

    assert result.status == "failed"
    assert fetcher.calls == []
    issue = next(item for item in result.gates["issues"] if item["code"] == "ANGLE_FORMAL_FIELDS_MISSING")
    assert "total_score" in issue["message"]
    assert not (result.staging_dir / "materialized" / "facts.json").exists()


def test_native_artifact_graph_is_unchanged_for_imported_runs(tmp_path: Path) -> None:
    native_before = copy.deepcopy(ARTIFACT_GRAPH)
    result = _importer(tmp_path).stage(_checkpoint())
    manifest = json.loads((result.staging_dir / "materialized" / "candidate-run.json").read_text("utf-8"))

    assert ARTIFACT_GRAPH == native_before
    assert manifest["stages"]["checkpoint_import"]["status"] == "succeeded"
    assert result.artifact_graph["facts.json"][1] != ARTIFACT_GRAPH["facts.json"][1]


def test_pinned_capture_is_reused_on_repeat_import(tmp_path: Path) -> None:
    fetcher = StaticSourceFetcher()
    importer = _importer(tmp_path, fetcher)
    checkpoint = _checkpoint()

    first = importer.import_checkpoint(checkpoint)
    second = importer.import_checkpoint(checkpoint)

    assert first.run_dir == second.run_dir
    assert fetcher.calls == [SOURCE_URL]
    assert first.semantic_artifact_hashes == second.semantic_artifact_hashes


def test_changed_source_capture_is_reported_without_overwriting_pinned_bytes(tmp_path: Path) -> None:
    original_fetcher = StaticSourceFetcher()
    importer = _importer(tmp_path, original_fetcher)
    importer.stage(_checkpoint())
    capture_path = next((tmp_path / "source-cache").glob("**/*.bin"))
    original_bytes = capture_path.read_bytes()

    with pytest.raises(SourceContentChangedError, match="SOURCE_CONTENT_CHANGED"):
        importer.refresh_source(SOURCE_URL, StaticSourceFetcher(b"GDP was 9.9% in 2025.\n"))

    assert capture_path.read_bytes() == original_bytes


def test_failed_stage_leaves_gate_report_but_no_partial_production_run(tmp_path: Path) -> None:
    checkpoint = _checkpoint()
    checkpoint["evidence"][0]["excerpt_anchor"] = "not in source"
    importer = _importer(tmp_path)

    result = importer.import_checkpoint(checkpoint)

    assert result.run_dir is None
    assert not list((tmp_path / "runs").glob("20??-??-??-???-*"))
    assert (result.staging_dir / "gates.json").is_file()
    assert result.status == "failed"


def test_v2_import_dispatches_to_strict_preflight_without_staging(tmp_path: Path) -> None:
    importer = _importer(tmp_path)

    with pytest.raises(ValidationError):
        importer.stage({"checkpoint_schema_version": "approved-checkpoint/2.0"})

    assert not importer.staging_root.exists()


def test_checkpoint_v21_is_not_misrouted_to_legacy_materialization(tmp_path: Path) -> None:
    importer = _importer(tmp_path)

    with pytest.raises(UnsupportedCheckpointVersionError, match="2.1.*not implemented"):
        importer.stage({"checkpoint_schema_version": "approved-checkpoint/2.1"})

    assert not importer.staging_root.exists()


def test_approved_checkpoint_v1_label_stays_on_legacy_import_path(tmp_path: Path) -> None:
    checkpoint = _checkpoint()
    checkpoint["checkpoint_schema_version"] = "approved-checkpoint/1.0"

    result = _importer(tmp_path).stage(checkpoint)

    assert result.status == "passed"


def test_valid_v2_dispatch_reaches_snapshot_verification(tmp_path: Path) -> None:
    importer = _importer(tmp_path)
    checkpoint = _v2_checkpoint()
    for sentence in checkpoint["script"]["sentences"]:
        sentence["evidence_ids"] = []
    checkpoint["approval"]["body_sha256"] = canonical_body_sha256(checkpoint)

    result = importer.stage(checkpoint)

    assert result.status == "failed"
    assert any(issue["code"] == "SOURCE_SNAPSHOT_MISMATCH" for issue in result.gates["issues"])
    assert not (result.staging_dir / "materialized").exists()


def test_legacy_fingerprint_values_remain_unchanged() -> None:
    checkpoint = _checkpoint()
    content_sha = checkpoint_import._digest_json(checkpoint_import._without_runtime(checkpoint))
    fingerprint = checkpoint_import._digest_json({
        "checkpoint_content_sha256": content_sha,
        "checkpoint_schema_version": "1.0",
        "importer_version": "test-1.0",
    })

    assert content_sha == "80d1b7b450fe51b532d188a31aea949eae8a7fb70769953ed93d9f94c287f669"
    assert fingerprint == "38e86ec44b6fd8229e81391e7b3fd7f35d6800cf459b0be90b5a0818975e2f50"
