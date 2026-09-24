from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

import fanglei.checkpoint_import as checkpoint_import
from test_checkpoint_contract import _checkpoint_v21, _checkpoint_v21_independent
from test_checkpoint_import_v2 import _pdf_with_text
from fanglei.artifacts import sha256_bytes, sha256_text
from fanglei.checkpoint_contract import ApprovalBodyHashMismatch, canonical_body_sha256
from fanglei.checkpoint_import import CheckpointImporter, SourceCapture
from fanglei.source_contract import authoritative_source_package_sha256


SOURCE_TEXTS = {
    "https://example.gov/report": "The report states a value. June source details.",
    "https://example.gov/report-two": "The second official document reports a distinct value.",
}


class MappingFetcher:
    def __init__(self, contents: dict[str, str] | None = None) -> None:
        self.contents = contents or SOURCE_TEXTS
        self.calls: list[str] = []

    def fetch(self, url: str) -> SourceCapture:
        self.calls.append(url)
        return SourceCapture(
            url=url,
            content=self.contents[url].encode("utf-8"),
            content_type="text/plain; charset=utf-8",
            title="Approved official document",
        )


class CaptureMappingFetcher:
    def __init__(self, captures: dict[str, SourceCapture]) -> None:
        self.captures = captures
        self.calls: list[str] = []

    def fetch(self, url: str) -> SourceCapture:
        self.calls.append(url)
        return self.captures[url]


def _checkpoint_21_for_import(source_texts: dict[str, str] | None = None) -> dict:
    checkpoint = deepcopy(_checkpoint_v21())
    source_texts = source_texts or SOURCE_TEXTS
    checkpoint["case_id"] = "fixture-authority-case"
    checkpoint["source_run_id"] = "fixture-authority-run"
    checkpoint["source_policy"]["case_id"] = checkpoint["case_id"]
    checkpoint["source_policy"]["run_id"] = checkpoint["source_run_id"]
    script_sentences = [
        ("The report states a value.", "hook", "verified_fact", ["claim-1"]),
        ("This is an approved document.", "phenomenon", "explanation", []),
        ("It describes the period.", "mechanism", "interpretation", []),
        ("Read the source date.", "core_judgment", "explanation", []),
    ]
    script_text = "\n\n".join(row[0] for row in script_sentences) + "\n"
    script_bytes = script_text.encode("utf-8")
    sentences = []
    previous_end = 0
    for index, (text, section, sentence_type, claim_ids) in enumerate(script_sentences, 1):
        start = script_bytes.index(text.encode("utf-8"), previous_end)
        end = start + len(text.encode("utf-8"))
        sentences.append({
            "external_id": f"sentence-{index}",
            "section": section,
            "sentence_type": sentence_type,
            "text": text,
            "claim_ids": claim_ids,
            "byte_start": start,
            "byte_end": end,
            "evidence_ids": [],
        })
        previous_end = end
    checkpoint["script"].update({
        "text": script_text,
        "spoken_character_count": len("".join(row[0] for row in script_sentences)),
        "estimated_duration_seconds": 75.0,
        "sentences": sentences,
    })

    text_by_id = {
        "src-1": source_texts["https://example.gov/report"],
        "src-2": source_texts["https://example.gov/report-two"],
    }
    for source in checkpoint["sources"]:
        text_hash = sha256_text(text_by_id[source["external_id"]])
        source["snapshot"]["source_text_sha256"] = text_hash
        normalized = [
            row for row in source["snapshot"]["indexed_file_hashes"]
            if row["role"] == "normalized_text"
        ]
        assert len(normalized) == 1
        normalized[0]["sha256"] = text_hash

    for document in checkpoint["source_policy"]["approved_documents"]:
        document["source_text_sha256"] = sha256_text(text_by_id[document["source_id"]])
    checkpoint["source_policy"]["approval"]["package_sha256"] = authoritative_source_package_sha256(
        checkpoint["source_policy"]
    )
    checkpoint["approval"]["body_sha256"] = canonical_body_sha256(checkpoint)
    return checkpoint


def _with_approved_pdf_capture(checkpoint: dict) -> tuple[dict, bytes]:
    checkpoint = deepcopy(checkpoint)
    first = checkpoint["sources"][0]
    source_text = SOURCE_TEXTS[first["url"]]
    pdf_bytes = _pdf_with_text(source_text)
    raw_hash = sha256_bytes(pdf_bytes)
    first["snapshot"]["raw_capture_bytes_sha256"] = raw_hash
    first["snapshot"]["indexed_file_hashes"].append({
        "role": "raw_response",
        "path": "source_documents/raw/source-one.pdf",
        "hash_kind": "file_bytes_sha256",
        "sha256": raw_hash,
    })
    approved = next(
        document for document in checkpoint["source_policy"]["approved_documents"]
        if document["source_id"] == first["external_id"]
    )
    approved["raw_capture_bytes_sha256"] = raw_hash
    checkpoint["source_policy"]["approval"]["package_sha256"] = authoritative_source_package_sha256(
        checkpoint["source_policy"]
    )
    checkpoint["approval"]["body_sha256"] = canonical_body_sha256(checkpoint)
    return checkpoint, pdf_bytes


def _importer(tmp_path: Path, fetcher: MappingFetcher | None = None) -> CheckpointImporter:
    return CheckpointImporter(
        runs_dir=tmp_path / "runs",
        source_cache_dir=tmp_path / "source-cache",
        source_fetcher=fetcher or MappingFetcher(),
        importer_version="phase2-test-1",
    )


def test_v21_import_promotes_formal_facts_and_preserves_authority_audit_data(
    tmp_path: Path,
) -> None:
    checkpoint = _checkpoint_21_for_import()
    fetcher = MappingFetcher()
    importer = _importer(tmp_path, fetcher)

    result = importer.import_checkpoint(checkpoint)

    assert result.status == "promoted", result.gates
    assert result.run_dir is not None
    facts = json.loads((result.run_dir / "facts.json").read_text("utf-8"))
    manifest = json.loads((result.run_dir / "import_manifest.json").read_text("utf-8"))
    fingerprint = json.loads((result.staging_dir / "checkpoint_fingerprint.json").read_text("utf-8"))
    materialized_checkpoint = json.loads(
        (result.run_dir / "approved_checkpoint.json").read_text("utf-8")
    )
    id_mapping = json.loads((result.run_dir / "id_mapping.json").read_text("utf-8"))
    claim = facts["claims"][0]
    assert facts["schema_version"] == "checkpoint-import-facts/2.1"
    assert claim["verification_status"] == "verified"
    assert claim["verification_basis"] == "authoritative_primary_attestation"
    expected_attestation = deepcopy(checkpoint["claims"][0]["authority_attestation"])
    expected_attestation["source_ids"] = ["source_001"]
    assert claim["authority_attestation"] == expected_attestation
    assert claim["claim_text"] == checkpoint["claims"][0]["proposition"]
    assert claim["allowed_downstream"] is True
    assert claim["domain"] == checkpoint["claims"][0]["native_metadata"]["domain"]
    assert claim["risk_level"] == checkpoint["claims"][0]["native_metadata"]["risk_level"]
    assert claim["source_ids"] == ["source_001"]
    assert claim["evidence"][0]["evidence_text"] == checkpoint["evidence"][0]["evidence_text"]
    assert manifest["source_policy"] == checkpoint["source_policy"]
    assert manifest["source_selection"] == checkpoint["source_selection"]
    assert manifest["source_policy"]["approval"]["package_sha256"] == checkpoint[
        "source_policy"
    ]["approval"]["package_sha256"]
    assert fingerprint["checkpoint_schema_version"] == "approved-checkpoint/2.1"
    assert fingerprint["source_policy"] == checkpoint["source_policy"]
    fingerprint_input = json.dumps({
        "checkpoint_content_sha256": checkpoint["approval"]["body_sha256"],
        "checkpoint_schema_version": "approved-checkpoint/2.1",
        "importer_version": "phase2-test-1",
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    assert result.checkpoint_fingerprint == hashlib.sha256(fingerprint_input).hexdigest()
    snapshot = manifest["source_snapshot_hashes"][checkpoint["sources"][0]["url"]]
    assert snapshot["source_text_sha256"] == checkpoint["sources"][0]["snapshot"]["source_text_sha256"]
    assert snapshot["indexed_file_hashes"] == checkpoint["sources"][0]["snapshot"]["indexed_file_hashes"]
    assert materialized_checkpoint["checkpoint_schema_version"] == "approved-checkpoint/2.1"
    assert (result.run_dir / "research.md").read_bytes() == checkpoint["research"]["content"].encode("utf-8")
    assert (result.run_dir / "script.md").read_bytes() == checkpoint["script"]["text"].encode("utf-8")
    assert [
        (row["byte_start"], row["byte_end"]) for row in id_mapping["bindings"]
    ] == [
        (row["byte_start"], row["byte_end"]) for row in checkpoint["script"]["sentences"]
    ]
    assert fetcher.calls == list(SOURCE_TEXTS)
    assert all(result.gates[name]["passed"] for name in (
        "schema", "provenance", "fact_coverage", "script_coverage"
    ))


def test_v21_source_snapshot_mismatch_fails_before_materialization_or_pin(
    tmp_path: Path,
) -> None:
    checkpoint = _checkpoint_21_for_import()
    changed_texts = dict(SOURCE_TEXTS)
    changed_texts[checkpoint["sources"][0]["url"]] += " altered"
    fetcher = MappingFetcher(changed_texts)
    importer = _importer(tmp_path, fetcher)

    result = importer.stage(checkpoint)

    assert result.status == "failed"
    assert any(issue["code"] == "SOURCE_SNAPSHOT_MISMATCH" for issue in result.gates["issues"])
    assert all(result.gates[name]["passed"] is False for name in (
        "schema", "provenance", "fact_coverage", "script_coverage"
    ))
    assert fetcher.calls == list(SOURCE_TEXTS)
    assert not (result.staging_dir / "materialized").exists()
    assert not list((tmp_path / "source-cache").glob("**/pinned.json"))


def test_v21_raw_pdf_hash_mismatch_fails_even_when_extracted_text_is_unchanged(
    tmp_path: Path,
) -> None:
    checkpoint, approved_pdf = _with_approved_pdf_capture(_checkpoint_21_for_import())
    first_url = checkpoint["sources"][0]["url"]
    second_url = checkpoint["sources"][1]["url"]
    changed_pdf = approved_pdf + b"\n% alternate byte representation\n"
    fetcher = CaptureMappingFetcher({
        first_url: SourceCapture(first_url, changed_pdf, "application/pdf"),
        second_url: SourceCapture(
            second_url,
            SOURCE_TEXTS[second_url].encode("utf-8"),
            "text/plain; charset=utf-8",
        ),
    })
    importer = _importer(tmp_path, fetcher)

    result = importer.stage(checkpoint)

    assert result.status == "failed"
    assert any(issue["code"] == "SOURCE_SNAPSHOT_MISMATCH" for issue in result.gates["issues"])
    assert not (result.staging_dir / "materialized").exists()
    assert not list((tmp_path / "source-cache").glob("**/pinned.json"))


def test_v21_matching_raw_pdf_and_extracted_text_pass_snapshot_verification(
    tmp_path: Path,
) -> None:
    checkpoint, approved_pdf = _with_approved_pdf_capture(_checkpoint_21_for_import())
    first_url = checkpoint["sources"][0]["url"]
    second_url = checkpoint["sources"][1]["url"]
    fetcher = CaptureMappingFetcher({
        first_url: SourceCapture(first_url, approved_pdf, "application/pdf"),
        second_url: SourceCapture(
            second_url,
            SOURCE_TEXTS[second_url].encode("utf-8"),
            "text/plain; charset=utf-8",
        ),
    })

    result = _importer(tmp_path, fetcher).stage(checkpoint)

    assert result.status == "passed", result.gates
    assert result.gates["provenance"]["passed"] is True
    assert all(issue["code"] != "SOURCE_SNAPSHOT_MISMATCH" for issue in result.gates["issues"])


def test_v21_body_hash_mismatch_fails_before_fetch_or_staging(tmp_path: Path) -> None:
    checkpoint = _checkpoint_21_for_import()
    checkpoint["approval"]["body_sha256"] = "f" * 64
    fetcher = MappingFetcher()
    importer = _importer(tmp_path, fetcher)

    with pytest.raises(ApprovalBodyHashMismatch):
        importer.stage(checkpoint)

    assert fetcher.calls == []
    assert not importer.staging_root.exists()


@pytest.mark.parametrize("mutation", ["package_hash", "run_binding", "case_binding", "off_package", "status_basis"])
def test_v21_invalid_authority_contract_fails_before_fetch_or_staging(
    tmp_path: Path, mutation: str
) -> None:
    checkpoint = _checkpoint_21_for_import()
    if mutation == "package_hash":
        checkpoint["source_policy"]["approval"]["package_sha256"] = "f" * 64
        checkpoint["approval"]["body_sha256"] = canonical_body_sha256(checkpoint)
    elif mutation in {"run_binding", "case_binding"}:
        key = "run_id" if mutation == "run_binding" else "case_id"
        checkpoint["source_policy"][key] += "-other"
        checkpoint["source_policy"]["approval"]["package_sha256"] = authoritative_source_package_sha256(
            checkpoint["source_policy"]
        )
        checkpoint["approval"]["body_sha256"] = canonical_body_sha256(checkpoint)
    elif mutation == "off_package":
        checkpoint["claims"][0]["authority_attestation"]["source_ids"] = ["outside-package"]
        checkpoint["approval"]["body_sha256"] = canonical_body_sha256(checkpoint)
    else:
        checkpoint["claims"][0]["verification_basis"] = "none"
        checkpoint["approval"]["body_sha256"] = canonical_body_sha256(checkpoint)
    fetcher = MappingFetcher()
    importer = _importer(tmp_path, fetcher)

    with pytest.raises(ValidationError):
        importer.stage(checkpoint)

    assert fetcher.calls == []
    assert not importer.staging_root.exists()


def test_v21_schema_gate_still_blocks_promotion(tmp_path: Path) -> None:
    checkpoint = _checkpoint_21_for_import()
    checkpoint["script"]["title"] = "x" * 41
    checkpoint["approval"]["body_sha256"] = canonical_body_sha256(checkpoint)
    importer = _importer(tmp_path)

    result = importer.import_checkpoint(checkpoint)

    assert result.status == "failed"
    assert result.run_dir is None
    assert result.gates["schema"]["passed"] is False
    assert result.gates["provenance"]["passed"] is True
    assert result.gates["fact_coverage"]["passed"] is True
    assert result.gates["script_coverage"]["passed"] is True
    assert not list((tmp_path / "runs").glob("20??-??-??-???-*"))


def test_v21_independent_corroboration_keeps_distinct_key_basis(tmp_path: Path) -> None:
    checkpoint = deepcopy(_checkpoint_v21_independent())
    checkpoint["case_id"] = "fixture-independent-case"
    checkpoint["source_run_id"] = "fixture-independent-run"
    checkpoint["script"] = _checkpoint_21_for_import()["script"]
    source_texts = {
        "src-1": "The 2026 value is 4.2.",
        "src-2": "The 2026 value is 4.2.",
        "src-3": "An unrelated official context paragraph.",
    }
    urls = {row["external_id"]: row["url"] for row in checkpoint["sources"]}
    fetch_texts = {urls[source_id]: text for source_id, text in source_texts.items()}
    for source in checkpoint["sources"]:
        digest = sha256_text(source_texts[source["external_id"]])
        source["snapshot"]["source_text_sha256"] = digest
        next(row for row in source["snapshot"]["indexed_file_hashes"] if row["role"] == "normalized_text")["sha256"] = digest

    checkpoint["claims"][0]["source_ids"] = ["src-1", "src-2"]
    checkpoint["claims"][0]["evidence_ids"] = ["evidence-1", "evidence-2"]
    checkpoint["evidence"][0].update({
        "source_ids": ["src-1"],
        "evidence_text": source_texts["src-1"],
        "excerpt_anchor": source_texts["src-1"],
        "original_url": urls["src-1"],
    })
    second_evidence = deepcopy(checkpoint["evidence"][0])
    second_evidence.update({
        "external_id": "evidence-2",
        "source_ids": ["src-2"],
        "evidence_text": source_texts["src-2"],
        "excerpt_anchor": source_texts["src-2"],
        "original_url": urls["src-2"],
    })
    checkpoint["evidence"].append(second_evidence)
    checkpoint["approval"]["body_sha256"] = canonical_body_sha256(checkpoint)
    result = _importer(tmp_path, MappingFetcher(fetch_texts)).import_checkpoint(checkpoint)

    assert result.status == "promoted", result.gates
    assert result.run_dir is not None
    facts = json.loads((result.run_dir / "facts.json").read_text("utf-8"))
    manifest = json.loads((result.run_dir / "import_manifest.json").read_text("utf-8"))
    assert facts["claims"][0]["verification_status"] == "verified"
    assert facts["claims"][0]["verification_basis"] == "independent_corroboration"
    assert facts["claims"][0]["authority_attestation"] is None
    assert manifest["source_selection"]["independent_source_count"] == 3
    assert manifest["source_selection"]["selection_status"] == "selected"


def test_v21_deterministic_document_comparison_keeps_mapped_attestation_sources(
    tmp_path: Path,
) -> None:
    comparison_texts = {
        "https://example.gov/report": "The 2026 median GDP projection is 2.2 percent.",
        "https://example.gov/report-two": "The 2026 median GDP projection is 2.3 percent.",
    }
    checkpoint = _checkpoint_21_for_import(comparison_texts)
    claim = checkpoint["claims"][0]
    claim["proposition"] = (
        "Example Institution: the published median GDP projection for 2026 changed from "
        "2.2 percent in example-report-1 (2026-06-17) to 2.3 percent in "
        "example-report-2 (2026-09-23)."
    )
    claim["source_ids"] = ["src-1", "src-2"]
    claim["evidence_ids"] = ["evidence-1", "evidence-2"]
    claim["authority_attestation"] = {
        "kind": "deterministic_document_comparison",
        "source_ids": ["src-1", "src-2"],
        "attribution": "Example Institution",
        "scope": {
            "subject": "GDP",
            "measure": "projection",
            "period": "2026",
            "unit": "percent",
            "statistic": "median",
            "certainty": "reported",
        },
    }
    first_url = checkpoint["sources"][0]["url"]
    second_url = checkpoint["sources"][1]["url"]
    checkpoint["evidence"][0].update({
        "source_ids": ["src-1"],
        "evidence_text": comparison_texts[first_url],
        "excerpt_anchor": comparison_texts[first_url],
        "original_url": first_url,
    })
    second_evidence = deepcopy(checkpoint["evidence"][0])
    second_evidence.update({
        "external_id": "evidence-2",
        "source_ids": ["src-2"],
        "evidence_text": comparison_texts[second_url],
        "excerpt_anchor": comparison_texts[second_url],
        "original_url": second_url,
    })
    checkpoint["evidence"].append(second_evidence)

    script = checkpoint["script"]
    sentence_texts = [row["text"] for row in script["sentences"]]
    sentence_texts[0] = (
        "Example Institution reports the published GDP projection changed from 2.2 to 2.3."
    )
    script["text"] = "\n\n".join(sentence_texts) + "\n"
    script_bytes = script["text"].encode("utf-8")
    previous_end = 0
    for row, text in zip(script["sentences"], sentence_texts):
        start = script_bytes.index(text.encode("utf-8"), previous_end)
        end = start + len(text.encode("utf-8"))
        row.update({"text": text, "byte_start": start, "byte_end": end})
        previous_end = end
    script["spoken_character_count"] = len("".join(sentence_texts))
    checkpoint["approval"]["body_sha256"] = canonical_body_sha256(checkpoint)
    fetcher = MappingFetcher(comparison_texts)

    result = _importer(tmp_path, fetcher).import_checkpoint(checkpoint)

    assert result.status == "promoted", result.gates
    assert result.run_dir is not None
    facts = json.loads((result.run_dir / "facts.json").read_text("utf-8"))
    manifest = json.loads((result.run_dir / "import_manifest.json").read_text("utf-8"))
    attestation = facts["claims"][0]["authority_attestation"]
    assert facts["claims"][0]["verification_basis"] == "authoritative_primary_attestation"
    assert attestation["kind"] == "deterministic_document_comparison"
    assert attestation["source_ids"] == ["source_001", "source_002"]
    assert attestation["attribution"] == "Example Institution"
    assert attestation["scope"]["measure"] == "projection"
    assert manifest["source_selection"]["independent_source_count"] == 1
    assert manifest["source_selection"]["selection_status"] == "insufficient_sources"


def test_v21_staging_prefix_collision_preserves_existing_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint = _checkpoint_21_for_import()
    fetcher = MappingFetcher()
    importer = _importer(tmp_path, fetcher)
    prefix = "0123456789abcdefabcd"
    existing_fingerprint = prefix + "0" * 44
    current_fingerprint = prefix + "1" * 44
    staging = importer.staging_root / f"cp-{prefix}"
    materialized = staging / "materialized"
    materialized.mkdir(parents=True)
    (materialized / "marker.txt").write_text("keep-materialized", encoding="utf-8")
    (staging / "gates.json").write_text('{"marker":"keep-gates"}\n', encoding="utf-8")
    (staging / "checkpoint_fingerprint.json").write_text(json.dumps({
        "checkpoint_content_sha256": "a" * 64,
        "checkpoint_schema_version": "approved-checkpoint/2.1",
        "importer_version": importer.importer_version,
        "checkpoint_fingerprint": existing_fingerprint,
    }), encoding="utf-8")
    before = {path.relative_to(staging): path.read_bytes() for path in staging.rglob("*") if path.is_file()}
    real_digest = checkpoint_import._digest_json

    def colliding_digest(value: dict) -> str:
        if set(value) == {"checkpoint_content_sha256", "checkpoint_schema_version", "importer_version"}:
            return current_fingerprint
        return real_digest(value)

    monkeypatch.setattr(checkpoint_import, "_digest_json", colliding_digest)

    with pytest.raises(RuntimeError, match="fingerprint prefix collision"):
        importer.stage(checkpoint)

    assert {path.relative_to(staging): path.read_bytes() for path in staging.rglob("*") if path.is_file()} == before
    assert fetcher.calls == []


@pytest.mark.parametrize("mutation", [
    "missing_source_policy",
    "stale_source_policy",
    "wrong_type_source_policy",
    "missing_source_selection",
    "stale_source_selection",
    "wrong_type_source_selection",
    "missing_source_snapshot_hashes",
    "stale_source_snapshot_hashes",
    "wrong_type_source_snapshot_hashes",
    "missing_fingerprint_file",
    "malformed_json",
    "wrong_root_type",
    "malformed_imported_at",
    "wrong_type_pinned_capture_hashes",
    "partial_pinned_capture_hashes",
])
def test_v21_same_fingerprint_invalid_audit_metadata_fails_without_mutation(
    tmp_path: Path, mutation: str
) -> None:
    checkpoint = _checkpoint_21_for_import()
    fetcher = MappingFetcher()
    importer = _importer(tmp_path, fetcher)
    initial = importer.stage(checkpoint)
    assert initial.status == "passed"
    staging = initial.staging_dir
    metadata_path = staging / "checkpoint_fingerprint.json"
    if mutation == "missing_fingerprint_file":
        metadata_path.unlink()
    elif mutation == "malformed_json":
        metadata_path.write_text("{not-json", encoding="utf-8")
    elif mutation == "wrong_root_type":
        metadata_path.write_text("[]", encoding="utf-8")
    else:
        metadata = json.loads(metadata_path.read_text("utf-8"))
        if mutation == "malformed_imported_at":
            metadata["imported_at"] = None
        elif mutation == "wrong_type_pinned_capture_hashes":
            metadata["pinned_capture_hashes"] = []
        elif mutation == "partial_pinned_capture_hashes":
            url = next(iter(metadata["source_snapshot_hashes"]))
            metadata["pinned_capture_hashes"] = {url: "a" * 64}
        else:
            operation = next(
                prefix[:-1] for prefix in ("missing_", "stale_", "wrong_type_")
                if mutation.startswith(prefix)
            )
            field = mutation.removeprefix(f"{operation}_")
            if operation == "missing":
                metadata.pop(field)
            elif operation == "stale":
                metadata[field] = {"stale": True}
            else:
                metadata[field] = []
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    shutil.rmtree(tmp_path / "source-cache")
    fetcher.calls.clear()
    before = {
        path.relative_to(staging): path.read_bytes()
        for path in staging.rglob("*")
        if path.is_file()
    }

    with pytest.raises(RuntimeError):
        importer.stage(checkpoint)

    assert fetcher.calls == []
    assert (staging / "materialized").is_dir()
    assert (staging / "gates.json").is_file()
    assert metadata_path.is_file() == (Path("checkpoint_fingerprint.json") in before)
    assert {
        path.relative_to(staging): path.read_bytes()
        for path in staging.rglob("*")
        if path.is_file()
    } == before
