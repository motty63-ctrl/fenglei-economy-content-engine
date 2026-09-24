from __future__ import annotations

from copy import deepcopy
from io import BytesIO
import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

import fanglei.checkpoint_import as checkpoint_import
from test_checkpoint_authoring_phase2 import (
    CASE_ID,
    CHECKPOINT_ID,
    CLAIM_ID,
    RUN_ID,
    SOURCE_ID,
    SOURCE_TEXT,
    _make_complete_run,
)
from test_checkpoint_authoring_phase3 import APPROVED_AT, _official_reviews
from fanglei.artifacts import sha256_bytes, sha256_text
from fanglei.checkpoint_authoring import (
    approve_checkpoint,
    build_checkpoint_draft,
    seal_checkpoint,
    validate_checkpoint_draft,
)
from fanglei.checkpoint_contract import (
    ApprovalBodyHashMismatch,
    canonical_body_sha256,
    verify_approval_body_hash,
)
from fanglei.checkpoint_import import (
    CheckpointImporter,
    SourceCapture,
    _text_from_capture,
)


SCRIPT_SENTENCES = [
    ("经济增长为百分之五。", "phenomenon", "verified_fact", [CLAIM_ID]),
    ("报告同时说明了统计周期。", "mechanism", "explanation", []),
    ("理解数字要先看指标口径。", "mechanism", "interpretation", []),
    ("最后再判断变化意味着什么。", "core_judgment", "explanation", []),
]
SCRIPT_TEXT = "\n\n".join(item[0] for item in SCRIPT_SENTENCES) + "\n"


class StaticFetcher:
    def __init__(self, body: bytes = SOURCE_TEXT.encode("utf-8"), *, url_suffix: str = "") -> None:
        self.body = body
        self.url_suffix = url_suffix
        self.calls: list[str] = []

    def fetch(self, url: str) -> SourceCapture:
        self.calls.append(url)
        return SourceCapture(
            url=url + self.url_suffix,
            content=self.body,
            content_type="text/plain; charset=utf-8",
            title="Official report",
            published_at="2026-09-20",
            retrieved_at="2026-09-24T09:00:00+08:00",
        )


def _script_artifact() -> dict:
    return {
        "schema_version": "3.0",
        "script_id": "script_phase4",
        "angle_id": "angle_001",
        "title": "增长数字怎么读",
        "target_duration_seconds": 75,
        "speaking_rate_chars_per_second": 4.0,
        "spoken_character_count": len("".join(item[0] for item in SCRIPT_SENTENCES)),
        "estimated_duration_seconds": 75.0,
        "sentences": [
            {
                "sentence_id": f"sentence_{index:03d}",
                "section": section,
                "sentence_type": sentence_type,
                "text": text,
                "claim_ids": claim_ids,
            }
            for index, (text, section, sentence_type, claim_ids) in enumerate(SCRIPT_SENTENCES, 1)
        ],
    }


def _sealed_checkpoint(tmp_path: Path) -> tuple[Path, Path, dict]:
    repository_root = tmp_path
    source_runs_dir = tmp_path / "source-runs"
    source_run_dir = _make_complete_run(
        source_runs_dir,
        script=_script_artifact(),
        script_markdown=SCRIPT_TEXT,
    )
    draft = build_checkpoint_draft(
        RUN_ID, CASE_ID, CHECKPOINT_ID, source_runs_dir, _official_reviews()
    )
    report = validate_checkpoint_draft(draft, source_runs_dir)
    assert report.passed, report.issues
    approval = approve_checkpoint(
        draft,
        report,
        reviewer="human-reviewer-1",
        expected_body_sha256=report.body_sha256,
        approved_at=APPROVED_AT,
    )
    sealed_path = seal_checkpoint(
        draft, approval, repository_root, runs_dir=source_runs_dir
    )
    return repository_root, source_run_dir, json.loads(sealed_path.read_text("utf-8"))


def _approve_mutation(checkpoint: dict) -> dict:
    checkpoint["approval"]["body_sha256"] = canonical_body_sha256(checkpoint)
    return checkpoint


def _importer(
    repository_root: Path,
    fetcher: StaticFetcher | None = None,
    *,
    source_cache_dir: Path | None = None,
) -> CheckpointImporter:
    return CheckpointImporter(
        runs_dir=repository_root / "runs",
        source_cache_dir=source_cache_dir or repository_root / "c",
        source_fetcher=fetcher or StaticFetcher(),
        importer_version="phase4-test-1",
    )


def _pdf_with_text(text: str) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=400, height=200)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    font_ref = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})
    })
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _checkpoint_with_pdf_snapshot(checkpoint: dict, pdf_bytes: bytes, pdf_text: str) -> dict:
    source = checkpoint["sources"][0]
    source["snapshot"]["source_text_sha256"] = sha256_text(pdf_text)
    source["snapshot"]["raw_capture_bytes_sha256"] = sha256_bytes(pdf_bytes)
    normalized = next(
        item for item in source["snapshot"]["indexed_file_hashes"]
        if item["role"] == "normalized_text"
    )
    normalized["sha256"] = sha256_text(pdf_text)
    source["snapshot"]["indexed_file_hashes"].append({
        "role": "raw_response",
        "path": "source_documents/raw/source.pdf",
        "hash_kind": "file_bytes_sha256",
        "sha256": sha256_bytes(pdf_bytes),
    })
    for evidence in checkpoint["evidence"]:
        evidence["evidence_text"] = pdf_text
        evidence["excerpt_anchor"] = pdf_text
    return _approve_mutation(checkpoint)


def test_sealed_v2_round_trip_promotes_after_source_run_is_removed(tmp_path: Path) -> None:
    repository_root, source_run_dir, checkpoint = _sealed_checkpoint(tmp_path)
    shutil.rmtree(source_run_dir)
    fetcher = StaticFetcher()
    importer = _importer(repository_root, fetcher)

    result = importer.import_checkpoint(checkpoint)

    assert result.status == "promoted"
    assert result.run_dir is not None
    assert not source_run_dir.exists()
    stored_checkpoint = json.loads((result.run_dir / "approved_checkpoint.json").read_text("utf-8"))
    assert verify_approval_body_hash(stored_checkpoint) == checkpoint["approval"]["body_sha256"]
    assert fetcher.calls == [checkpoint["sources"][0]["url"]]
    assert all(result.gates[name]["passed"] for name in (
        "schema", "provenance", "fact_coverage", "script_coverage"
    ))
    imported = result.run_dir
    facts = json.loads((imported / "facts.json").read_text("utf-8"))
    angle = json.loads((imported / "angles.json").read_text("utf-8"))["candidates"][0]
    script = json.loads((imported / "script.json").read_text("utf-8"))
    mapping = json.loads((imported / "id_mapping.json").read_text("utf-8"))
    manifest = json.loads((imported / "import_manifest.json").read_text("utf-8"))

    assert facts["claims"][0]["claim_text"] == checkpoint["claims"][0]["proposition"]
    assert facts["claims"][0]["evidence"][0]["evidence_text"] == checkpoint["evidence"][0]["evidence_text"]
    assert facts["claims"][0]["domain"] == "economic_data"
    assert facts["claims"][0]["risk_level"] == "low"
    assert facts["claims"][0]["script_usage"] == "verified_fact"
    assert angle["angle_id"] == "angle_001"
    assert angle["hook"] == checkpoint["angle"]["hook"]
    assert angle["total_score"] == checkpoint["angle"]["total_score"]
    assert script["sentences"][0]["text"] == checkpoint["script"]["sentences"][0]["text"]
    assert (imported / "script.md").read_bytes() == checkpoint["script"]["text"].encode("utf-8")
    assert (imported / "research.md").read_bytes() == checkpoint["research"]["content"].encode("utf-8")
    assert [
        (row["byte_start"], row["byte_end"])
        for row in mapping["bindings"]
    ] == [
        (row["byte_start"], row["byte_end"])
        for row in checkpoint["script"]["sentences"]
    ]
    assert manifest["checkpoint_content_sha256"] == checkpoint["approval"]["body_sha256"]
    assert manifest["checkpoint_fingerprint"] == result.checkpoint_fingerprint
    assert manifest["source_snapshot_hashes"][checkpoint["sources"][0]["url"]]["source_text_sha256"] == checkpoint["sources"][0]["snapshot"]["source_text_sha256"]
    assert manifest["pinned_capture_hashes"][checkpoint["sources"][0]["url"]] == sha256_bytes(SOURCE_TEXT.encode("utf-8"))
    assert manifest["id_mapping_sha256"] == result.mapping_sha256
    assert manifest["semantic_artifact_hashes"]
    assert manifest["gates"] == result.gates


def test_v2_body_hash_mismatch_fails_before_fetch_or_staging(tmp_path: Path) -> None:
    repository_root, _, checkpoint = _sealed_checkpoint(tmp_path)
    checkpoint["research"]["content"] += "tampered"
    fetcher = StaticFetcher()
    importer = _importer(repository_root, fetcher)

    with pytest.raises(ApprovalBodyHashMismatch):
        importer.stage(checkpoint)

    assert fetcher.calls == []
    assert not importer.staging_root.exists()


@pytest.mark.parametrize("mutation", ["unknown_field", "naive_approval_time", "wrong_angle_reference"])
def test_v2_malformed_or_inconsistent_checkpoint_fails_preflight(
    tmp_path: Path, mutation: str
) -> None:
    repository_root, _, checkpoint = _sealed_checkpoint(tmp_path)
    if mutation == "unknown_field":
        checkpoint["unexpected"] = "rejected"
    elif mutation == "naive_approval_time":
        checkpoint["approval"]["approved_at"] = "2026-09-24T09:30:00"
        _approve_mutation(checkpoint)
    else:
        checkpoint["script"]["angle_external_id"] = "another-angle"
        _approve_mutation(checkpoint)
    fetcher = StaticFetcher()
    importer = _importer(repository_root, fetcher)

    expected_error = ValidationError if mutation != "wrong_angle_reference" else ValueError
    with pytest.raises(expected_error):
        importer.stage(checkpoint)

    assert fetcher.calls == []
    assert not importer.staging_root.exists()


def test_v2_snapshot_exact_text_passes_and_one_character_change_fails_without_pin(
    tmp_path: Path,
) -> None:
    repository_root, _, checkpoint = _sealed_checkpoint(tmp_path)
    good_fetcher = StaticFetcher()
    good_result = _importer(repository_root / "good", good_fetcher).stage(checkpoint)
    assert good_result.status == "passed", good_result.gates

    bad_root = repository_root / "bad"
    bad_fetcher = StaticFetcher(SOURCE_TEXT.replace("百分之五", "百分之六").encode("utf-8"))
    bad_importer = _importer(bad_root, bad_fetcher)
    bad_result = bad_importer.stage(checkpoint)

    assert bad_result.status == "failed"
    assert any(issue["code"] == "SOURCE_SNAPSHOT_MISMATCH" for issue in bad_result.gates["issues"])
    assert bad_fetcher.calls == [checkpoint["sources"][0]["url"]]
    assert not (bad_result.staging_dir / "materialized").exists()
    assert not list((bad_root / "c").glob("**/pinned.json"))


def test_v2_existing_pinned_snapshot_mismatch_does_not_refresh_or_replace(tmp_path: Path) -> None:
    repository_root, _, checkpoint = _sealed_checkpoint(tmp_path)
    cache = repository_root / "c"
    first = _importer(repository_root, StaticFetcher(), source_cache_dir=cache).stage(checkpoint)
    assert first.status == "passed"
    pinned_path = next(cache.glob("**/*.bin"))
    original_bytes = pinned_path.read_bytes()

    changed = deepcopy(checkpoint)
    changed_snapshot = changed["sources"][0]["snapshot"]
    changed_snapshot["source_text_sha256"] = sha256_text("different text")
    next(item for item in changed_snapshot["indexed_file_hashes"] if item["role"] == "normalized_text")["sha256"] = changed_snapshot["source_text_sha256"]
    _approve_mutation(changed)
    no_refresh_fetcher = StaticFetcher(b"changed capture")
    importer = _importer(repository_root, no_refresh_fetcher, source_cache_dir=cache)
    result = importer.stage(changed)

    assert result.status == "failed"
    assert any(issue["code"] == "SOURCE_SNAPSHOT_MISMATCH" for issue in result.gates["issues"])
    assert no_refresh_fetcher.calls == []
    assert pinned_path.read_bytes() == original_bytes
    assert not (result.staging_dir / "materialized").exists()


def test_v2_pinned_capture_url_mismatch_fails_without_refresh(tmp_path: Path) -> None:
    repository_root, _, checkpoint = _sealed_checkpoint(tmp_path)
    fetcher = StaticFetcher()
    importer = _importer(repository_root, fetcher)
    first = importer.stage(checkpoint)
    assert first.status == "passed"
    pinned_index = next(importer.source_cache_dir.glob("**/pinned.json"))
    metadata = json.loads(pinned_index.read_text("utf-8"))
    metadata["url"] += "?different-identity"
    pinned_index.write_text(json.dumps(metadata), encoding="utf-8")

    no_refresh_fetcher = StaticFetcher()
    result = _importer(
        repository_root, no_refresh_fetcher, source_cache_dir=importer.source_cache_dir
    ).stage(checkpoint)

    assert result.status == "failed"
    assert any(issue["code"] == "SOURCE_CAPTURE_FAILED" for issue in result.gates["issues"])
    assert no_refresh_fetcher.calls == []
    assert not (result.staging_dir / "materialized").exists()
    assert json.loads(pinned_index.read_text("utf-8"))["url"].endswith("different-identity")


def test_v2_raw_pdf_hash_is_checked_before_text_hash_and_pinning(tmp_path: Path) -> None:
    repository_root, _, checkpoint = _sealed_checkpoint(tmp_path)
    pdf_text = "Official report states the GDP value."
    pdf_bytes = _pdf_with_text(pdf_text)
    capture = SourceCapture(
        url=checkpoint["sources"][0]["url"],
        content=pdf_bytes,
        content_type="application/pdf",
    )
    assert _text_from_capture(capture) == pdf_text
    checkpoint = _checkpoint_with_pdf_snapshot(checkpoint, pdf_bytes, pdf_text)
    class PdfFetcher(StaticFetcher):
        def fetch(self, url: str) -> SourceCapture:
            self.calls.append(url)
            return SourceCapture(url, self.body, "application/pdf")

    matching_fetcher = PdfFetcher(pdf_bytes)
    matched = _importer(repository_root / "matched", matching_fetcher).stage(checkpoint)
    assert not any(issue["code"] == "SOURCE_SNAPSHOT_MISMATCH" for issue in matched.gates["issues"])
    assert matched.status == "passed", matched.gates

    changed_pdf = bytearray(pdf_bytes)
    changed_pdf[-1] ^= 1
    mismatch_fetcher = PdfFetcher(bytes(changed_pdf))
    mismatch = _importer(repository_root / "mismatch", mismatch_fetcher).stage(checkpoint)
    assert mismatch.status == "failed"
    assert any(issue["code"] == "SOURCE_SNAPSHOT_MISMATCH" for issue in mismatch.gates["issues"])
    assert not (mismatch.staging_dir / "materialized").exists()
    assert not list((repository_root / "mismatch" / "c").glob("**/pinned.json"))


def test_v2_fetcher_url_mismatch_fails_closed_without_pin(tmp_path: Path) -> None:
    repository_root, _, checkpoint = _sealed_checkpoint(tmp_path)
    fetcher = StaticFetcher(url_suffix="?redirected=true")
    result = _importer(repository_root, fetcher).stage(checkpoint)

    assert result.status == "failed"
    assert any(issue["code"] == "SOURCE_CAPTURE_FAILED" for issue in result.gates["issues"])
    assert not list((repository_root / "c").glob("**/pinned.json"))
    assert not (result.staging_dir / "materialized").exists()


def test_v2_prefix_collision_preserves_existing_package_and_does_not_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository_root, _, checkpoint = _sealed_checkpoint(tmp_path)
    fetcher = StaticFetcher()
    importer = _importer(repository_root, fetcher)
    prefix = "0123456789abcdefabcd"
    existing_fingerprint = prefix + "0" * 44
    current_fingerprint = prefix + "1" * 44
    staging = importer.staging_root / f"cp-{prefix}"
    materialized = staging / "materialized"
    materialized.mkdir(parents=True)
    (materialized / "marker.txt").write_text("keep-materialized", encoding="utf-8")
    (staging / "gates.json").write_text('{"marker":"keep-gates"}\n', encoding="utf-8")
    (staging / "checkpoint_fingerprint.json").write_text(
        json.dumps({"checkpoint_fingerprint": existing_fingerprint, "marker": "keep-fingerprint"}),
        encoding="utf-8",
    )
    original_contents = {
        path.relative_to(staging): path.read_bytes()
        for path in staging.rglob("*")
        if path.is_file()
    }
    original_digest_json = checkpoint_import._digest_json

    def colliding_digest(value: dict) -> str:
        if set(value) == {"checkpoint_content_sha256", "checkpoint_schema_version", "importer_version"}:
            return current_fingerprint
        return original_digest_json(value)

    monkeypatch.setattr(checkpoint_import, "_digest_json", colliding_digest)

    with pytest.raises(RuntimeError, match="fingerprint prefix collision"):
        importer.stage(checkpoint)

    assert {
        path.relative_to(staging): path.read_bytes()
        for path in staging.rglob("*")
        if path.is_file()
    } == original_contents
    assert fetcher.calls == []


def test_v2_pin_rejects_resolved_directory_escape_before_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    url = "https://example.test/source"
    pin_dir = cache_dir / checkpoint_import._source_cache_key(url)
    pin_dir.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    resolved_outside = outside_dir.resolve(strict=True)
    original_resolve = Path.resolve

    def resolve_with_escape(path: Path, *args: object, **kwargs: object) -> Path:
        if path == pin_dir:
            return resolved_outside
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve_with_escape)
    capture = SourceCapture(url, b"approved source bytes", "text/plain; charset=utf-8")

    with pytest.raises(checkpoint_import.SourceFetchError, match="escapes.*configured cache root"):
        checkpoint_import._pin_capture_v2(cache_dir, capture)

    assert list(pin_dir.iterdir()) == []
    assert list(outside_dir.iterdir()) == []


def test_v2_schema_gate_failure_does_not_promote_when_other_gates_pass(tmp_path: Path) -> None:
    repository_root, _, checkpoint = _sealed_checkpoint(tmp_path)
    changed = deepcopy(checkpoint)
    changed["script"]["title"] = "x" * 41
    _approve_mutation(changed)

    result = _importer(repository_root, StaticFetcher()).import_checkpoint(changed)

    assert result.status == "failed"
    assert result.run_dir is None
    assert result.gates["schema"]["passed"] is False
    assert result.gates["provenance"]["passed"] is True
    assert result.gates["fact_coverage"]["passed"] is True
    assert result.gates["script_coverage"]["passed"] is True
    assert not list((repository_root / "runs").glob("20??-??-??-???-*"))


def test_v2_provenance_failure_does_not_promote(tmp_path: Path) -> None:
    repository_root, _, checkpoint = _sealed_checkpoint(tmp_path)
    changed = deepcopy(checkpoint)
    changed["evidence"][0]["excerpt_anchor"] = "a phrase not present in the source"
    _approve_mutation(changed)

    result = _importer(repository_root, StaticFetcher()).import_checkpoint(changed)

    assert result.status == "failed"
    assert result.run_dir is None
    assert result.gates["schema"]["passed"] is True
    assert result.gates["provenance"]["passed"] is False
    assert result.gates["fact_coverage"]["passed"] is False
    assert not list((repository_root / "runs").glob("20??-??-??-???-*"))


def test_v2_fact_coverage_failure_is_coupled_to_missing_provenance(tmp_path: Path) -> None:
    repository_root, _, checkpoint = _sealed_checkpoint(tmp_path)
    changed = deepcopy(checkpoint)
    for evidence in changed["evidence"]:
        evidence["excerpt_anchor"] = "a phrase not present in the source"
    _approve_mutation(changed)

    result = _importer(repository_root, StaticFetcher()).import_checkpoint(changed)

    assert result.status == "failed"
    assert result.run_dir is None
    assert result.gates["schema"]["passed"] is True
    assert result.gates["provenance"]["passed"] is False
    assert result.gates["fact_coverage"] == {"passed": False, "coverage": 0.0}
    assert result.gates["script_coverage"]["passed"] is True
    assert not list((repository_root / "runs").glob("20??-??-??-???-*"))


def test_v2_invalid_script_reference_fails_preflight_before_any_gate_or_promotion(
    tmp_path: Path,
) -> None:
    # Strict V2 preflight rejects unknown sentence claims, while every accepted
    # claim ID is mapped by the materializer. Therefore script_coverage cannot
    # be false for a checkpoint that reaches materialization; this is a preflight
    # rejection test, not a script_coverage gate fixture.
    repository_root, _, checkpoint = _sealed_checkpoint(tmp_path)
    changed = deepcopy(checkpoint)
    changed["script"]["sentences"][0]["claim_ids"] = ["missing-claim"]
    _approve_mutation(changed)
    fetcher = StaticFetcher()
    importer = _importer(repository_root, fetcher)

    with pytest.raises(ValueError, match="CHECKPOINT_REFERENCE_INVALID"):
        importer.import_checkpoint(changed)

    assert fetcher.calls == []
    assert not importer.staging_root.exists()
    assert not list((repository_root / "runs").glob("20??-??-??-???-*"))


def test_v2_fingerprint_uses_approval_body_hash_and_v1_path_is_untouched(tmp_path: Path) -> None:
    repository_root, _, checkpoint = _sealed_checkpoint(tmp_path)
    result = _importer(repository_root, StaticFetcher()).stage(checkpoint)
    fingerprint = json.loads((result.staging_dir / "checkpoint_fingerprint.json").read_text("utf-8"))

    assert fingerprint["checkpoint_content_sha256"] == checkpoint["approval"]["body_sha256"]
    assert fingerprint["checkpoint_schema_version"] == "approved-checkpoint/2.0"
    assert fingerprint["checkpoint_fingerprint"] == result.checkpoint_fingerprint
    assert fingerprint["source_snapshot_hashes"][checkpoint["sources"][0]["url"]]["source_text_sha256"] == checkpoint["sources"][0]["snapshot"]["source_text_sha256"]
    assert fingerprint["pinned_capture_hashes"][checkpoint["sources"][0]["url"]] == sha256_bytes(SOURCE_TEXT.encode("utf-8"))
