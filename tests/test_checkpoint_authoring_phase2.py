from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from fanglei.artifact_registry import ArtifactRegistry
from fanglei.artifacts import atomic_write_bytes, atomic_write_json, atomic_write_text, read_json, sha256_bytes, sha256_text
from fanglei.checkpoint_authoring import bind_source_run_to_case
from fanglei.models import RunManifest


RUN_ID = "2026-09-23-001-research"
CASE_ID = "phase2-test-case"
CHECKPOINT_ID = "phase2-checkpoint-001"
SOURCE_ID = "src_001"
SOURCE_URL = "https://example.gov/report"
CLAIM_ID = "claim_001"
ANGLE_ID = "angle_001"
SCRIPT_ID = "script_001"
SENTENCE_1 = "经济增长为百分之五。"
SENTENCE_2 = "这说明经济正在扩张。"
SOURCE_TEXT = "官方报告显示经济增长为百分之五。\n第二段保留原文。\n"
RESEARCH_TEXT = "研究原文第一行。\n研究原文第二行。\n"
SCRIPT_TEXT = f"{SENTENCE_1}\n\n{SENTENCE_2}\n"


def _candidate(**overrides: Any) -> dict[str, Any]:
    value = {
        "angle_id": ANGLE_ID,
        "title": "经济增长的真实含义",
        "hook": "一个增长数字意味着什么？",
        "core_question": "增长数字如何解读？",
        "core_insight": "口径决定数字含义。",
        "hook_mechanism": "question",
        "audience_takeaway": "先看统计口径。",
        "narrative_framing": "evidence-first",
        "supporting_claim_ids": [CLAIM_ID],
        "audience_relevance": 4,
        "novelty": 3,
        "hook_strength": 4,
        "visual_potential": 3,
        "explainability": 5,
        "risk_notes": [],
        "evidence_strength": 4,
        "controversy_risk": 1,
        "total_score": 82,
        "eligibility": "eligible",
        "rejection_codes": [],
        "originality": {"basis": "source-specific"},
    }
    value.update(overrides)
    return value


def _evidence(**overrides: Any) -> dict[str, Any]:
    value = {
        "source_id": SOURCE_ID,
        "evidence_text": "官方报告显示经济增长为百分之五。",
        "source_section": "摘要",
        "paragraph_locator": "paragraph:1",
        "published_at": "2026-09-20",
        "retrieved_at": "2026-09-23T09:00:00+08:00",
        "original_url": SOURCE_URL,
        "relation": "supports",
        "document_hash": "fetcher-specific-value",
    }
    value.update(overrides)
    return value


def _facts(**overrides: Any) -> dict[str, Any]:
    claim = {
        "claim_id": CLAIM_ID,
        "claim_text": "经济增长为百分之五。",
        "claim_type": "fact",
        "verification_status": "verified",
        "domain": "economic_data",
        "risk_level": "low",
        "source_ids": [SOURCE_ID],
        "evidence": [_evidence(), _evidence()],
        "verification_reason": "由来源直接支持。",
        "allowed_downstream": True,
        "script_usage": "verified_fact",
    }
    value = {
        "schema_version": "2.1",
        "policy_version": "economics-v1.1",
        "run_id": RUN_ID,
        "summary": {"verified": 1, "conflicted": 0, "unverified": 0},
        "claims": [claim],
    }
    value.update(overrides)
    return value


def _script(**overrides: Any) -> dict[str, Any]:
    value = {
        "schema_version": "3.0",
        "script_id": SCRIPT_ID,
        "angle_id": ANGLE_ID,
        "title": "增长数字怎么读",
        "target_duration_seconds": 75,
        "speaking_rate_chars_per_second": 4.0,
        "spoken_character_count": len(SENTENCE_1 + SENTENCE_2),
        "estimated_duration_seconds": 60.0,
        "sentences": [
            {"sentence_id": "sentence_001", "section": "hook", "sentence_type": "verified_fact",
             "text": SENTENCE_1, "claim_ids": [CLAIM_ID]},
            {"sentence_id": "sentence_002", "section": "phenomenon", "sentence_type": "explanation",
             "text": SENTENCE_2, "claim_ids": []},
        ],
    }
    value.update(overrides)
    return value


def _make_complete_run(
    runs_dir: Path,
    *,
    angle_candidate: dict[str, Any] | None = None,
    angle_candidates: list[dict[str, Any]] | None = None,
    facts: dict[str, Any] | None = None,
    script: dict[str, Any] | None = None,
    angle_run_id: str = RUN_ID,
    angle_markdown: str | None = None,
    script_markdown: str = SCRIPT_TEXT,
    source_text: str = SOURCE_TEXT,
    source_row_url: str | None = None,
    source_document_url: str = SOURCE_URL,
    source_original_url: str | None = None,
    include_raw_assets: bool = False,
) -> Path:
    run_dir = runs_dir / RUN_ID
    run_dir.mkdir(parents=True)
    manifest = RunManifest(
        run_id=RUN_ID,
        created_at="2026-09-23T09:00:00+08:00",
        updated_at="2026-09-23T09:00:00+08:00",
    )
    atomic_write_json(run_dir / "run.json", manifest.model_dump(mode="json"))
    bind_source_run_to_case(RUN_ID, CASE_ID, runs_dir)
    manifest = RunManifest.model_validate(read_json(run_dir / "run.json"))
    registry = ArtifactRegistry(run_dir, manifest)

    registry.write_text("source.md", "本轮研究主题。\n", "ingest")
    registry.write_json("questions.json", {"core_topic": "经济增长", "research_questions": []}, "analyze")
    registry.write_json("search_results.json", {"results": [{"url": SOURCE_URL}]}, "search")

    source_path = run_dir / "source_documents" / f"{SOURCE_ID}.md"
    atomic_write_text(source_path, source_text)
    source_hash = sha256_text(source_text)
    source_files = [{"role": "normalized_text", "path": f"source_documents/{SOURCE_ID}.md",
                     "content_hash": source_hash}]
    pages: list[dict[str, Any]] = []
    document_format = "html"
    if include_raw_assets:
        document_format = "pdf"
        raw_response = '{"source":"official"}\n'
        raw_json_path = run_dir / "source_documents" / "raw" / f"{SOURCE_ID}.json"
        atomic_write_text(raw_json_path, raw_response)
        source_files.append({"role": "raw_response", "path": f"source_documents/raw/{SOURCE_ID}.json",
                             "content_hash": sha256_text(raw_response)})
        raw_pdf = b"%PDF-1.7\nsource bytes\n"
        raw_pdf_path = run_dir / "source_documents" / "raw" / f"{SOURCE_ID}.pdf"
        atomic_write_bytes(raw_pdf_path, raw_pdf)
        source_files.append({"role": "raw_response", "path": f"source_documents/raw/{SOURCE_ID}.pdf",
                             "content_hash": sha256_bytes(raw_pdf)})
        pages = [{"page_number": 1, "text": source_text}]
        page_index_path = run_dir / "source_documents" / f"{SOURCE_ID}.pages.json"
        atomic_write_json(page_index_path, {
            "source_id": SOURCE_ID,
            "document_hash": source_hash,
            "pages": pages,
        })
        source_files.append({"role": "page_index", "path": f"source_documents/{SOURCE_ID}.pages.json",
                             "content_hash": sha256_bytes(page_index_path.read_bytes())})
    source_row_url = source_row_url or source_document_url
    document = {
        "source_id": SOURCE_ID,
        "url": source_document_url,
        "title": "官方经济报告",
        "text": source_text,
        "source_type": "official",
        "published_at": "2026-09-20",
        "retrieved_at": "2026-09-23T09:00:00+08:00",
        "original_url": source_original_url,
        "document_format": document_format,
        "retrieval_method": "html",
        "evidence_eligible": True,
        "eligibility_reason": "original_document",
        "document_hash": source_hash,
        "api_endpoint": None,
        "request_fingerprint": None,
        "api_observations": [],
        "pages": pages,
        "path": f"source_documents/{SOURCE_ID}.md",
        "content_hash": source_hash,
        "files": source_files,
    }
    registry.write_json("source_documents/index.json", {
        "schema_version": "2.1", "fetch_errors": [], "documents": [document],
    }, "source_fetch")
    registry.write_json("sources.json", {
        "schema_version": "2.0",
        "selection_status": "selected",
        "sources": [{
            "source_id": SOURCE_ID,
            "url": source_row_url,
            "title": "官方经济报告",
            "published_at": "2026-09-20",
            "retrieved_at": "2026-09-23T09:00:00+08:00",
            "source_type": "official",
            "credibility_tier": "A",
            "independence_key": "institution:example.gov",
            "counts_as_independent": True,
            "independence_reason": "traceable original source",
            "origin_chain": [source_original_url, source_row_url] if source_original_url else [source_row_url],
        }],
    }, "source_selection")
    registry.write_json("facts.json", facts or _facts(), "factcheck")
    registry.write_text("research.md", RESEARCH_TEXT, "research_synthesis")
    registry.write_json("angles.json", {
        "schema_version": "3.0",
        "run_id": angle_run_id,
        "recommended_angle_id": ANGLE_ID,
        "candidates": angle_candidates if angle_candidates is not None else [angle_candidate or _candidate()],
    }, "angle_generation")
    registry.write_text("angle.md", angle_markdown if angle_markdown is not None else f"# 角度\n\nselected_angle_id: `{ANGLE_ID}`\n", "angle_selection")
    registry.write_json("script.json", script or _script(), "script_generation")
    registry.write_text("script.md", script_markdown, "script_render")
    registry.save_manifest()
    return run_dir


class CheckpointAuthoringPhase2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.runs_dir = Path(self.temp.name) / "runs"
        self.run_dir = _make_complete_run(self.runs_dir)
        self.official_reviews = {
            SOURCE_ID: {
                "official": True,
                "official_review": {
                    "decision": "approved_official",
                    "reviewer": "source-reviewer-1",
                    "reviewed_at": "2026-09-23T10:00:00+08:00",
                    "basis": "Official institution publication record.",
                },
            }
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def build(self, reviews: dict[str, Any] | None = None, checkpoint_id: str = CHECKPOINT_ID):
        from fanglei.checkpoint_authoring import build_checkpoint_draft
        return build_checkpoint_draft(RUN_ID, CASE_ID, checkpoint_id, self.runs_dir,
                                      self.official_reviews if reviews is None else reviews)

    def test_builder_maps_all_inputs_preserves_text_and_computes_utf8_offsets(self) -> None:
        draft = self.build()
        body = draft.model_dump(mode="json", by_alias=True)

        self.assertEqual(body["checkpoint_schema_version"], "approved-checkpoint/2.0")
        self.assertEqual(body["checkpoint_id"], CHECKPOINT_ID)
        self.assertEqual(body["case_id"], CASE_ID)
        self.assertEqual(body["source_run_id"], RUN_ID)
        self.assertEqual(body["research"]["content"].encode("utf-8"), RESEARCH_TEXT.encode("utf-8"))
        self.assertEqual(body["facts_source"], {
            "schema_version": "2.1", "policy_version": "economics-v1.1",
            "summary": {"verified": 1, "conflicted": 0, "unverified": 0},
        })
        self.assertEqual(body["angle"]["external_id"], ANGLE_ID)
        self.assertEqual(body["angle"]["total_score"], 82)
        self.assertEqual(body["angle"]["core_insight"], "口径决定数字含义。")
        self.assertEqual(body["sources"][0]["official"], True)
        self.assertEqual(body["sources"][0]["official_review"]["reviewer"], "source-reviewer-1")
        self.assertEqual(body["sources"][0]["snapshot"]["source_text_sha256"], sha256_text(SOURCE_TEXT))
        self.assertIsNone(body["sources"][0]["snapshot"]["raw_capture_bytes_sha256"])
        self.assertEqual(body["sources"][0]["snapshot"]["indexed_file_hashes"][0], {
            "role": "normalized_text", "path": f"source_documents/{SOURCE_ID}.md",
            "hash_kind": "utf8_text_sha256", "sha256": sha256_text(SOURCE_TEXT),
        })
        self.assertEqual([row["external_id"] for row in body["evidence"]],
                         [f"{CLAIM_ID}:evidence:001", f"{CLAIM_ID}:evidence:002"])
        self.assertEqual(body["claims"][0]["evidence_ids"],
                         [f"{CLAIM_ID}:evidence:001", f"{CLAIM_ID}:evidence:002"])
        self.assertEqual(body["evidence"][0]["evidence_text"], _evidence()["evidence_text"])
        self.assertEqual(body["script"]["text"].encode("utf-8"), SCRIPT_TEXT.encode("utf-8"))
        sentence_rows = body["script"]["sentences"]
        first = SENTENCE_1.encode("utf-8")
        second = SENTENCE_2.encode("utf-8")
        self.assertEqual(sentence_rows[0]["byte_start"], 0)
        self.assertEqual(sentence_rows[0]["byte_end"], len(first))
        self.assertEqual(sentence_rows[1]["byte_start"], len(first) + 2)
        self.assertEqual(sentence_rows[1]["byte_end"], len(first) + 2 + len(second))
        self.assertEqual(sentence_rows[0]["evidence_ids"], [])
        self.assertEqual(body["protected_artifact_hashes"]["checkpoint_authoring_binding.json"],
                         RunManifest.model_validate(read_json(self.run_dir / "run.json")).artifacts[
                             "checkpoint_authoring_binding"].content_hash)

    def test_builder_is_deterministic_and_validation_is_pure(self) -> None:
        from fanglei.checkpoint_authoring import validate_checkpoint_draft
        before = (self.run_dir / "run.json").read_bytes()
        first = self.build().model_dump(mode="json", by_alias=True)
        second = self.build().model_dump(mode="json", by_alias=True)

        self.assertEqual(first, second)
        report = validate_checkpoint_draft(self.build(), self.runs_dir)
        self.assertTrue(report.passed)
        self.assertEqual(len(report.body_sha256), 64)
        self.assertEqual((self.run_dir / "run.json").read_bytes(), before)

    def test_validation_rejects_a_modified_body(self) -> None:
        from fanglei.checkpoint_authoring import validate_checkpoint_draft
        draft = self.build()
        draft.research.content += "未批准的修改。"

        report = validate_checkpoint_draft(draft, self.runs_dir)

        self.assertFalse(report.passed)
        self.assertIsNone(report.body_sha256)
        self.assertEqual(report.issues[0].code, "CHECKPOINT_DRAFT_MISMATCH")

    def test_validation_reports_unreadable_manifest_without_writing(self) -> None:
        from fanglei.checkpoint_authoring import validate_checkpoint_draft
        draft = self.build()
        manifest_path = self.run_dir / "run.json"
        manifest_path.write_bytes(b"not json")
        before = manifest_path.read_bytes()

        report = validate_checkpoint_draft(draft, self.runs_dir)

        self.assertFalse(report.passed)
        self.assertEqual(report.issues[0].code, "CASE_BINDING_INVALID")
        self.assertEqual(manifest_path.read_bytes(), before)

    def test_non_finite_body_value_fails_canonical_contract(self) -> None:
        from fanglei.checkpoint_authoring import build_checkpoint_draft
        runs = Path(self.temp.name) / "non-finite-runs"
        _make_complete_run(runs, angle_candidate=_candidate(originality={"score": float("nan")}))

        with self.assertRaisesRegex(ValueError, "CHECKPOINT_CONTRACT_INVALID"):
            build_checkpoint_draft(RUN_ID, CASE_ID, CHECKPOINT_ID, runs, self.official_reviews)

    def test_snapshot_distinguishes_text_hashes_and_file_byte_hashes(self) -> None:
        from fanglei.checkpoint_authoring import build_checkpoint_draft
        runs = Path(self.temp.name) / "file-hash-runs"
        run_dir = _make_complete_run(runs, include_raw_assets=True)

        draft = build_checkpoint_draft(RUN_ID, CASE_ID, CHECKPOINT_ID, runs, self.official_reviews)
        snapshot = draft.sources[0].snapshot

        self.assertEqual(snapshot.raw_capture_bytes_sha256, sha256_bytes(b"%PDF-1.7\nsource bytes\n"))
        self.assertEqual([item.hash_kind for item in snapshot.indexed_file_hashes], [
            "utf8_text_sha256", "utf8_text_sha256", "file_bytes_sha256", "file_bytes_sha256",
        ])
        self.assertEqual(snapshot.indexed_file_hashes[1].path, f"source_documents/raw/{SOURCE_ID}.json")
        self.assertEqual(snapshot.indexed_file_hashes[2].path, f"source_documents/raw/{SOURCE_ID}.pdf")
        self.assertEqual(snapshot.indexed_file_hashes[3].path, f"source_documents/{SOURCE_ID}.pages.json")
        self.assertTrue((run_dir / "run.json").is_file())

    def test_original_url_identity_is_checked_and_preserved(self) -> None:
        from fanglei.checkpoint_authoring import build_checkpoint_draft
        original_url = "https://example.gov/original-report"
        facts = _facts(claims=[{
            **_facts()["claims"][0],
            "evidence": [_evidence(original_url=original_url), _evidence(original_url=original_url)],
        }])
        runs = Path(self.temp.name) / "original-url-runs"
        _make_complete_run(runs, source_original_url=original_url, facts=facts)

        draft = build_checkpoint_draft(RUN_ID, CASE_ID, CHECKPOINT_ID, runs, self.official_reviews)

        self.assertEqual(draft.evidence[0].original_url, original_url)
        self.assertEqual(draft.sources[0].url, SOURCE_URL)

    def test_source_and_index_identity_mismatch_fails_closed(self) -> None:
        from fanglei.checkpoint_authoring import build_checkpoint_draft
        runs = Path(self.temp.name) / "url-mismatch-runs"
        _make_complete_run(runs, source_row_url="https://example.gov/other-report")

        with self.assertRaisesRegex(ValueError, "CHECKPOINT_IDENTITY_MISMATCH"):
            build_checkpoint_draft(RUN_ID, CASE_ID, CHECKPOINT_ID, runs, self.official_reviews)

        http_runs = Path(self.temp.name) / "http-source-runs"
        _make_complete_run(http_runs, source_row_url="http://example.gov/report",
                           source_document_url="http://example.gov/report")
        with self.assertRaisesRegex(ValueError, "SOURCE_NOT_ALLOWLISTABLE"):
            build_checkpoint_draft(RUN_ID, CASE_ID, CHECKPOINT_ID, http_runs, self.official_reviews)

    def test_missing_explicit_official_review_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "SOURCE_OFFICIAL_REVIEW_MISSING"):
            self.build({})

        false_status = {
            SOURCE_ID: {
                "official": False,
                "official_review": self.official_reviews[SOURCE_ID]["official_review"],
            }
        }
        with self.assertRaisesRegex(ValueError, "SOURCE_OFFICIAL_REVIEW_MISSING"):
            self.build(false_status)

        naive_review = {
            SOURCE_ID: {
                "official": True,
                "official_review": {
                    **self.official_reviews[SOURCE_ID]["official_review"],
                    "reviewed_at": "2026-09-23T10:00:00",
                },
            }
        }
        with self.assertRaisesRegex(ValueError, "SOURCE_OFFICIAL_REVIEW_MISSING"):
            self.build(naive_review)

        with self.assertRaisesRegex(ValueError, "SOURCE_OFFICIAL_REVIEW_MISSING"):
            self.build({**self.official_reviews, "unrelated-source": self.official_reviews[SOURCE_ID]})

    def test_explicit_case_binding_mismatch_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "CHECKPOINT_IDENTITY_MISMATCH|CASE_BINDING_MISSING"):
            from fanglei.checkpoint_authoring import build_checkpoint_draft
            build_checkpoint_draft(RUN_ID, "wrong-case", CHECKPOINT_ID, self.runs_dir, self.official_reviews)

        with self.assertRaisesRegex(ValueError, "CHECKPOINT_IDENTITY_MISMATCH"):
            self.build(checkpoint_id="../unsafe-checkpoint")

    def test_stale_protected_artifact_fails_without_repair_or_manifest_write(self) -> None:
        before_manifest = (self.run_dir / "run.json").read_bytes()
        research = self.run_dir / "research.md"
        research.write_bytes(research.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "AUTHORING_ARTIFACT_STALE|UPSTREAM_ARTIFACT_HASH_MISMATCH"):
            self.build()
        self.assertEqual((self.run_dir / "run.json").read_bytes(), before_manifest)

    def test_index_path_traversal_fails_before_registry_reads_outside_run(self) -> None:
        from fanglei.checkpoint_authoring import build_checkpoint_draft
        run_dir = _make_complete_run(self.runs_dir.parent / "traversal-runs")
        index = read_json(run_dir / "source_documents" / "index.json")
        index["documents"][0]["path"] = "../outside.md"
        index["documents"][0]["files"][0]["path"] = "../outside.md"
        atomic_write_json(run_dir / "source_documents" / "index.json", index)

        with self.assertRaisesRegex(ValueError, "UNSAFE_SOURCE_PATH"):
            build_checkpoint_draft(RUN_ID, CASE_ID, CHECKPOINT_ID, run_dir.parent, self.official_reviews)

    def test_selected_angle_marker_duplicate_incomplete_and_ineligible_fail(self) -> None:
        from fanglei.checkpoint_authoring import build_checkpoint_draft
        cases = [
            ("missing-marker", None, "", "ANGLE_INVALID"),
            ("incomplete", {k: v for k, v in _candidate().items() if k != "hook"}, None,
             "ANGLE_FORMAL_FIELDS_MISSING"),
            ("ineligible", _candidate(eligibility="rejected"), None, "ANGLE_NOT_ELIGIBLE"),
            ("unknown-field", _candidate(uncontracted="x"), None, "ANGLE_INVALID"),
        ]
        for label, candidate, marker, expected in cases:
            with self.subTest(label=label):
                runs = Path(self.temp.name) / label
                _make_complete_run(runs, angle_candidate=candidate or _candidate(), angle_markdown=marker)
                with self.assertRaisesRegex(ValueError, expected):
                    build_checkpoint_draft(RUN_ID, CASE_ID, CHECKPOINT_ID, runs, self.official_reviews)

        duplicate_dir = Path(self.temp.name) / "duplicate-angle"
        _make_complete_run(duplicate_dir, angle_candidates=[_candidate(), _candidate()])
        with self.assertRaisesRegex(ValueError, "ANGLE_INVALID"):
            build_checkpoint_draft(RUN_ID, CASE_ID, CHECKPOINT_ID, duplicate_dir, self.official_reviews)

    def test_script_angle_mismatch_and_uncovered_text_fail(self) -> None:
        from fanglei.checkpoint_authoring import build_checkpoint_draft
        mismatch_dir = Path(self.temp.name) / "script-angle"
        _make_complete_run(mismatch_dir, script=_script(angle_id="angle_999"))
        with self.assertRaisesRegex(ValueError, "CHECKPOINT_IDENTITY_MISMATCH"):
            build_checkpoint_draft(RUN_ID, CASE_ID, CHECKPOINT_ID, mismatch_dir, self.official_reviews)

        coverage_dir = Path(self.temp.name) / "script-gap"
        _make_complete_run(coverage_dir, script_markdown=f"{SENTENCE_1}\nUNMAPPED TEXT\n{SENTENCE_2}\n")
        with self.assertRaisesRegex(ValueError, "SCRIPT_OFFSETS_INVALID"):
            build_checkpoint_draft(RUN_ID, CASE_ID, CHECKPOINT_ID, coverage_dir, self.official_reviews)

    def test_broken_claim_source_and_evidence_references_fail(self) -> None:
        from fanglei.checkpoint_authoring import build_checkpoint_draft
        cases = [
            ("claim-source", _facts(claims=[{**_facts()["claims"][0], "source_ids": ["missing-source"]}]),
             "CROSS_RUN_REFERENCE"),
            ("evidence-source", _facts(claims=[{**_facts()["claims"][0], "evidence": [_evidence(source_id="missing-source")]}]),
             "CROSS_RUN_REFERENCE"),
            ("evidence-anchor", _facts(claims=[{**_facts()["claims"][0], "evidence": [_evidence(evidence_text="not in source")]}]),
             "SOURCE_SNAPSHOT_MISMATCH"),
            ("empty-evidence", _facts(claims=[{**_facts()["claims"][0], "evidence": []}]), "FACTS_MAPPING_INVALID"),
        ]
        for label, facts, expected in cases:
            with self.subTest(label=label):
                runs = Path(self.temp.name) / label
                _make_complete_run(runs, facts=facts)
                with self.assertRaisesRegex(ValueError, expected):
                    build_checkpoint_draft(RUN_ID, CASE_ID, CHECKPOINT_ID, runs, self.official_reviews)

    def test_facts_and_angles_run_identity_must_match_selected_run(self) -> None:
        from fanglei.checkpoint_authoring import build_checkpoint_draft
        for label, overrides, expected in (
            ("facts-run", {"facts": _facts(run_id="2026-09-23-002-other")}, "CHECKPOINT_IDENTITY_MISMATCH"),
            ("angles-run", {"angle_run_id": "2026-09-23-002-other"}, "CHECKPOINT_IDENTITY_MISMATCH"),
        ):
            with self.subTest(label=label):
                runs = Path(self.temp.name) / label
                _make_complete_run(runs, **overrides)
                with self.assertRaisesRegex(ValueError, expected):
                    build_checkpoint_draft(RUN_ID, CASE_ID, CHECKPOINT_ID, runs, self.official_reviews)


if __name__ == "__main__":
    unittest.main()
