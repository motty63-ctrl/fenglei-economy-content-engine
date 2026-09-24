from __future__ import annotations

import copy
import json
import unittest

from pydantic import ValidationError

from fanglei.source_contract import authoritative_source_package_sha256
from fanglei.checkpoint_contract import (
    ApprovalBodyHashMismatch,
    ApprovedCheckpointV2,
    ApprovedCheckpointV21,
    canonical_body_sha256,
    classify_checkpoint_version,
    parse_approved_checkpoint_v21,
    verify_approval_body_hash,
)
from fanglei.research import verify_claims


def _checkpoint() -> dict:
    digest = "a" * 64
    body = {
        "checkpoint_schema_version": "approved-checkpoint/2.0",
        "checkpoint_id": "checkpoint-1",
        "case_id": "fed-sep-revisions",
        "source_run_id": "2026-09-23-001-research",
        "protected_artifact_hashes": {
            "checkpoint_authoring_binding.json": digest,
            "source.md": digest,
            "questions.json": digest,
            "source_documents/index.json": digest,
            "sources.json": digest,
            "facts.json": digest,
            "research.md": digest,
            "angles.json": digest,
            "angle.md": digest,
            "script.json": digest,
            "script.md": digest,
        },
        "facts_source": {
            "schema_version": "2.1",
            "policy_version": "fact-policy/2.1",
            "summary": {},
        },
        "research": {"content": "Research text.\n"},
        "sources": [
            {
                "external_id": "src-1",
                "url": "https://example.gov/report",
                "official": True,
                "official_review": {
                    "decision": "approved_official",
                    "reviewer": "reviewer-1",
                    "reviewed_at": "2026-09-23T09:00:00+08:00",
                    "basis": "Official publication record.",
                },
                "title": "Example report",
                "published_at": None,
                "snapshot": {
                    "source_text_sha256": digest,
                    "raw_capture_bytes_sha256": None,
                    "indexed_file_hashes": [
                        {
                            "role": "normalized_text",
                            "path": "source_documents/src-1.md",
                            "hash_kind": "utf8_text_sha256",
                            "sha256": digest,
                        }
                    ],
                },
            }
        ],
        "claims": [
            {
                "external_id": "claim-1",
                "proposition": "The report states a value.",
                "classification": "fact",
                "verification_status": "verified",
                "rationale": "Directly stated in the source.",
                "allowed_downstream": True,
                "source_ids": ["src-1"],
                "evidence_ids": ["evidence-1"],
                "native_metadata": {
                    "domain": "macro",
                    "risk_level": "low",
                    "script_usage": "verified_fact",
                },
            }
        ],
        "evidence": [
            {
                "external_id": "evidence-1",
                "claim_ids": ["claim-1"],
                "source_ids": ["src-1"],
                "relation": "supports",
                "evidence_text": "The report states a value.",
                "excerpt_anchor": "The report states a value.",
                "source_section": "Table 1",
                "paragraph_locator": "row 1",
                "published_at": None,
                "retrieved_at": "2026-09-23T09:00:00+08:00",
                "original_url": "https://example.gov/report",
            }
        ],
        "angle": {
            "external_id": "angle-1",
            "title": "Approved angle",
            "hook": "What changed?",
            "core_question": "What does the report say?",
            "core_insight": "A recorded value matters.",
            "hook_mechanism": "contrast",
            "audience_takeaway": "Read the source carefully.",
            "narrative_framing": "evidence-first",
            "supporting_claim_ids": ["claim-1"],
            "audience_relevance": 4,
            "novelty": 3,
            "hook_strength": 4,
            "visual_potential": 3,
            "explainability": 5,
            "risk_notes": [],
            "evidence_strength": 4,
            "controversy_risk": 1,
            "total_score": 80,
            "eligibility": "eligible",
            "rejection_codes": [],
            "originality": {"basis": "source-specific"},
        },
        "script": {
            "external_id": "script-1",
            "angle_external_id": "angle-1",
            "title": "Approved script",
            "target_duration_seconds": 75,
            "speaking_rate_chars_per_second": 4.0,
            "spoken_character_count": 20,
            "estimated_duration_seconds": 5.0,
            "text": "A sentence.",
            "sentences": [
                {
                    "external_id": "sentence-1",
                    "section": "hook",
                    "sentence_type": "verified_fact",
                    "text": "A sentence.",
                    "claim_ids": ["claim-1"],
                    "byte_start": 0,
                    "byte_end": 11,
                    "evidence_ids": ["evidence-1"],
                }
            ],
        },
    }
    checkpoint = {**body, "approval": {
        "status": "approved",
        "reviewer": "reviewer-1",
        "approved_at": "2026-09-23T09:10:00+08:00",
        "body_sha256": canonical_body_sha256(body),
    }}
    return checkpoint


def _checkpoint_v21() -> dict:
    checkpoint = copy.deepcopy(_checkpoint())
    body = {key: value for key, value in checkpoint.items() if key != "approval"}
    body["checkpoint_schema_version"] = "approved-checkpoint/2.1"
    body["facts_source"] = {
        **body["facts_source"],
        "schema_version": "2.2",
    }
    first = body["sources"][0]
    first["published_at"] = "2026-06-17"
    first["credibility_tier"] = "A"
    first["independence_key"] = "institution:example.gov"
    first["counts_as_independent"] = True
    second = copy.deepcopy(first)
    second.update({
        "external_id": "src-2",
        "url": "https://example.gov/report-two",
        "title": "Example report two",
        "published_at": "2026-09-23",
        "credibility_tier": "A",
        "counts_as_independent": False,
        "snapshot": {
            "source_text_sha256": "b" * 64,
            "raw_capture_bytes_sha256": None,
            "indexed_file_hashes": [{
                "role": "normalized_text",
                "path": "source_documents/src-2.md",
                "hash_kind": "utf8_text_sha256",
                "sha256": "b" * 64,
            }],
        },
    })
    body["sources"] = [first, second]
    body["source_policy"] = {
        "name": "authoritative_primary_set",
        "version": "1.0",
        "run_id": body["source_run_id"],
        "case_id": body["case_id"],
        "institution": {"institution_id": "example", "display_name": "Example Institution"},
        "approved_documents": [
            {
                "source_id": "src-1",
                "url": "https://example.gov/report",
                "document_identity": "example-report-1",
                "evidence_role": "baseline report",
                "release_date": "2026-06-17",
                "classification": "official_primary",
                "source_text_sha256": "a" * 64,
                "raw_capture_bytes_sha256": None,
            },
            {
                "source_id": "src-2",
                "url": "https://example.gov/report-two",
                "document_identity": "example-report-2",
                "evidence_role": "target report",
                "release_date": "2026-09-23",
                "classification": "official_primary",
                "source_text_sha256": "b" * 64,
                "raw_capture_bytes_sha256": None,
            },
        ],
    }
    body["source_policy"]["approval"] = {
        "status": "approved",
        "reviewer": "reviewer-1",
        "approved_at": "2026-09-24T09:00:00+08:00",
        "rationale": "The two exact documents are official primary material.",
        "package_sha256": authoritative_source_package_sha256(body["source_policy"]),
    }
    body["source_selection"] = {
        "package_admissibility": "admissible",
        "independent_source_count": 1,
        "selection_status": "insufficient_sources",
    }
    body["claims"][0].update({
        "verification_basis": "authoritative_primary_attestation",
        "authority_attestation": {
            "kind": "document_report",
            "source_ids": ["src-1"],
            "attribution": "The report states",
            "scope": {
                "subject": "reported metric",
                "measure": "reported value",
                "period": "2026",
                "unit": None,
                "statistic": None,
                "certainty": "reported",
            },
        },
    })
    return {
        **body,
        "approval": {
            **checkpoint["approval"],
            "body_sha256": canonical_body_sha256(body),
        },
    }


def _refresh_v21_approval(checkpoint: dict) -> None:
    policy = checkpoint.get("source_policy")
    if isinstance(policy, dict) and policy.get("name") == "authoritative_primary_set":
        policy["approval"]["package_sha256"] = authoritative_source_package_sha256(policy)
    body = {key: value for key, value in checkpoint.items() if key != "approval"}
    checkpoint["approval"]["body_sha256"] = canonical_body_sha256(body)


def _checkpoint_v21_independent() -> dict:
    checkpoint = _checkpoint_v21()
    body = {key: value for key, value in checkpoint.items() if key != "approval"}
    body["source_policy"] = {"name": "independent_sources", "version": "1.0"}
    first, second = body["sources"]
    first["counts_as_independent"] = True
    first["independence_key"] = "institution:source-one.example"
    second["counts_as_independent"] = True
    second["credibility_tier"] = "D"
    second["independence_key"] = "institution:source-two.example"
    third = copy.deepcopy(second)
    third.update({
        "external_id": "src-3",
        "url": "https://source-three.example/report",
        "title": "Example report three",
        "published_at": "2026-09-24",
        "credibility_tier": "D",
        "independence_key": "institution:source-three.example",
        "snapshot": {
            "source_text_sha256": "c" * 64,
            "raw_capture_bytes_sha256": None,
            "indexed_file_hashes": [{
                "role": "normalized_text",
                "path": "source_documents/src-3.md",
                "hash_kind": "utf8_text_sha256",
                "sha256": "c" * 64,
            }],
        },
    })
    body["sources"] = [first, second, third]
    body["source_selection"] = {
        "package_admissibility": "admissible",
        "independent_source_count": 3,
        "selection_status": "selected",
    }
    body["claims"][0].update({
        "verification_basis": "independent_corroboration",
        "authority_attestation": None,
        "source_ids": ["src-1", "src-2"],
    })
    body["evidence"][0]["source_ids"] = ["src-1", "src-2"]
    checkpoint = {
        **body,
        "approval": {
            **checkpoint["approval"],
            "body_sha256": canonical_body_sha256(body),
        },
    }
    return checkpoint


class CheckpointContractTests(unittest.TestCase):
    def test_valid_v2_checkpoint_parses_and_approval_matches(self) -> None:
        checkpoint = _checkpoint()

        parsed = ApprovedCheckpointV2.model_validate(checkpoint)

        self.assertEqual(parsed.checkpoint_schema_version, "approved-checkpoint/2.0")
        self.assertEqual(parsed.model_dump(mode="json", by_alias=True), checkpoint)
        self.assertEqual(verify_approval_body_hash(checkpoint), checkpoint["approval"]["body_sha256"])

    def test_v2_canonical_body_sha256_matches_literal_golden_value(self) -> None:
        checkpoint = _checkpoint()

        self.assertEqual(canonical_body_sha256(checkpoint), "6c463728e543353ed9305eb86107836935ddb7705521eb9cc5d4b401ee94d0a9")
        self.assertEqual(checkpoint["approval"]["body_sha256"], "6c463728e543353ed9305eb86107836935ddb7705521eb9cc5d4b401ee94d0a9")

    def test_v2_checkpoint_rejects_new_verification_basis(self) -> None:
        checkpoint = _checkpoint()
        checkpoint["claims"][0]["verification_basis"] = "independent_corroboration"

        with self.assertRaises(ValidationError):
            ApprovedCheckpointV2.model_validate(checkpoint)

    def test_v21_checkpoint_preserves_basis_and_uses_same_body_hash_boundary(self) -> None:
        checkpoint = _checkpoint_v21()

        parsed = parse_approved_checkpoint_v21(checkpoint)

        self.assertIsInstance(parsed, ApprovedCheckpointV21)
        self.assertEqual(parsed.claims[0].verification_basis, "authoritative_primary_attestation")
        self.assertEqual(parsed.source_selection.independent_source_count, 1)
        self.assertEqual(parsed.source_selection.selection_status, "insufficient_sources")
        self.assertEqual(parsed.model_dump(mode="json", by_alias=True), checkpoint)
        self.assertEqual(verify_approval_body_hash(checkpoint), checkpoint["approval"]["body_sha256"])

    def test_v21_authority_policy_must_match_checkpoint_run_and_case(self) -> None:
        for field, value in (("run_id", "other-run"), ("case_id", "other-case")):
            with self.subTest(field=field):
                checkpoint = _checkpoint_v21()
                checkpoint["source_policy"][field] = value
                _refresh_v21_approval(checkpoint)

                with self.assertRaises(ValidationError):
                    ApprovedCheckpointV21.model_validate(checkpoint)

    def test_v21_authority_approval_cannot_be_reused_when_run_or_case_changes(self) -> None:
        checkpoint = _checkpoint_v21()
        baseline = checkpoint["source_policy"]["approval"]["package_sha256"]
        for field in ("run_id", "case_id"):
            changed = copy.deepcopy(checkpoint)
            changed["source_policy"][field] += "-other"
            self.assertNotEqual(
                authoritative_source_package_sha256(changed["source_policy"]),
                baseline,
            )

    def test_v21_independent_rows_with_same_key_are_rejected_despite_distinct_ids(self) -> None:
        checkpoint = _checkpoint_v21()
        body = {key: value for key, value in checkpoint.items() if key != "approval"}
        body["sources"][1]["counts_as_independent"] = True
        body["source_selection"]["independent_source_count"] = 1
        checkpoint["sources"] = body["sources"]
        checkpoint["source_selection"] = body["source_selection"]
        _refresh_v21_approval(checkpoint)

        with self.assertRaises(ValidationError, msg="distinct source IDs must not inflate one key"):
            ApprovedCheckpointV21.model_validate(checkpoint)

    def test_v21_independent_claim_requires_two_counted_distinct_keys(self) -> None:
        checkpoint = _checkpoint_v21_independent()
        checkpoint["sources"][1]["counts_as_independent"] = False
        checkpoint["sources"][1]["independence_key"] = checkpoint["sources"][0]["independence_key"]
        fourth = copy.deepcopy(checkpoint["sources"][2])
        fourth.update({
            "external_id": "src-4",
            "url": "https://source-four.example/report",
            "title": "Example report four",
            "published_at": "2026-09-25",
            "independence_key": "institution:source-four.example",
            "snapshot": {
                "source_text_sha256": "d" * 64,
                "raw_capture_bytes_sha256": None,
                "indexed_file_hashes": [{
                    "role": "normalized_text",
                    "path": "source_documents/src-4.md",
                    "hash_kind": "utf8_text_sha256",
                    "sha256": "d" * 64,
                }],
            },
        })
        checkpoint["sources"].append(fourth)
        _refresh_v21_approval(checkpoint)

        with self.assertRaisesRegex(ValidationError, "two distinct claim independence_key"):
            ApprovedCheckpointV21.model_validate(checkpoint)

    def test_v21_independent_corroboration_matches_native_primary_predicate(self) -> None:
        for primary_tier in ("A", "B", "C", "D"):
            with self.subTest(primary_tier=primary_tier):
                checkpoint = _checkpoint_v21_independent()
                checkpoint["sources"][0]["credibility_tier"] = primary_tier
                _refresh_v21_approval(checkpoint)
                native = verify_claims(
                    [
                        {"source_id": "src-1", "evidence_text": "The 2026 value is 4.2.", "claim_key": "value-2026", "claim_values": [4.2]},
                        {"source_id": "src-2", "evidence_text": "The 2026 value is 4.2.", "claim_key": "value-2026", "claim_values": [4.2]},
                    ],
                    {
                        "src-1": {"counts_as_independent": True, "credibility_tier": primary_tier},
                        "src-2": {"counts_as_independent": True, "credibility_tier": "D"},
                    },
                    minimum_sources_met=True,
                )
                runtime_verified = native["claims"][0]["verification_status"] == "verified"
                self.assertEqual(runtime_verified, primary_tier in {"A", "B", "C"})

                try:
                    ApprovedCheckpointV21.model_validate(checkpoint)
                except ValidationError:
                    checkpoint_verified = False
                else:
                    checkpoint_verified = True

                self.assertEqual(checkpoint_verified, runtime_verified)

    def test_v21_status_basis_combinations_are_strict(self) -> None:
        checkpoint = _checkpoint_v21()
        checkpoint["claims"][0]["verification_basis"] = "none"
        checkpoint["approval"]["body_sha256"] = canonical_body_sha256(
            {key: value for key, value in checkpoint.items() if key != "approval"}
        )

        with self.assertRaises(ValidationError):
            ApprovedCheckpointV21.model_validate(checkpoint)

    def test_v21_authority_claim_requires_attribution_to_remain_in_proposition(self) -> None:
        checkpoint = _checkpoint_v21()
        body = {key: value for key, value in checkpoint.items() if key != "approval"}
        body["claims"][0]["proposition"] = "A value is reported."
        checkpoint["claims"] = body["claims"]
        checkpoint["approval"]["body_sha256"] = canonical_body_sha256(body)

        with self.assertRaises(ValidationError):
            ApprovedCheckpointV21.model_validate(checkpoint)

    def test_v21_authority_claim_requires_admissible_package(self) -> None:
        checkpoint = _checkpoint_v21()
        body = {key: value for key, value in checkpoint.items() if key != "approval"}
        body["source_selection"]["package_admissibility"] = "inadmissible"
        checkpoint["source_selection"] = body["source_selection"]
        checkpoint["approval"]["body_sha256"] = canonical_body_sha256(body)

        with self.assertRaises(ValidationError):
            ApprovedCheckpointV21.model_validate(checkpoint)

    def test_v21_any_claim_requires_admissible_package(self) -> None:
        checkpoint = _checkpoint_v21()
        body = {key: value for key, value in checkpoint.items() if key != "approval"}
        body["source_policy"] = {"name": "independent_sources", "version": "1.0"}
        body["source_selection"]["package_admissibility"] = "inadmissible"
        body["claims"][0].update({
            "verification_status": "unverified",
            "verification_basis": "none",
            "authority_attestation": None,
            "allowed_downstream": False,
        })
        checkpoint = {
            **body,
            "approval": {
                **checkpoint["approval"],
                "body_sha256": canonical_body_sha256(body),
            },
        }

        with self.assertRaises(ValidationError):
            ApprovedCheckpointV21.model_validate(checkpoint)

    def test_wrong_version_fails_model_validation(self) -> None:
        checkpoint = _checkpoint()
        checkpoint["checkpoint_schema_version"] = "1.0"

        with self.assertRaises(ValidationError):
            ApprovedCheckpointV2.model_validate(checkpoint)

    def test_missing_required_field_fails(self) -> None:
        checkpoint = _checkpoint()
        del checkpoint["source_run_id"]

        with self.assertRaises(ValidationError):
            ApprovedCheckpointV2.model_validate(checkpoint)

    def test_unknown_envelope_and_nested_fields_fail(self) -> None:
        checkpoint = _checkpoint()
        checkpoint["runtime_metadata"] = {}
        with self.assertRaises(ValidationError):
            ApprovedCheckpointV2.model_validate(checkpoint)

        checkpoint = _checkpoint()
        checkpoint["angle"]["uncontracted"] = "value"
        with self.assertRaises(ValidationError):
            ApprovedCheckpointV2.model_validate(checkpoint)

    def test_omitted_angle_field_is_not_filled_from_legacy_model_default(self) -> None:
        checkpoint = _checkpoint()
        del checkpoint["angle"]["hook_mechanism"]

        with self.assertRaises(ValidationError):
            ApprovedCheckpointV2.model_validate(checkpoint)

    def test_optional_native_metadata_can_be_absent_without_filling_semantics(self) -> None:
        checkpoint = _checkpoint()
        del checkpoint["claims"][0]["native_metadata"]

        parsed = ApprovedCheckpointV2.model_validate(checkpoint)

        self.assertIsNone(parsed.claims[0].native_metadata)

    def test_approval_status_reviewer_digest_and_timestamp_are_strict(self) -> None:
        malformed = [
            ("status", "pending"),
            ("reviewer", "  "),
            ("body_sha256", "A" * 64),
            ("body_sha256", "g" * 64),
            ("body_sha256", "a" * 63),
            ("approved_at", "2026-09-23T09:10:00"),
        ]
        for field, value in malformed:
            with self.subTest(field=field):
                checkpoint = _checkpoint()
                checkpoint["approval"][field] = value
                with self.assertRaises(ValidationError):
                    ApprovedCheckpointV2.model_validate(checkpoint)

    def test_source_review_timestamp_must_be_timezone_aware(self) -> None:
        checkpoint = _checkpoint()
        checkpoint["sources"][0]["official_review"]["reviewed_at"] = "2026-09-23T09:00:00"

        with self.assertRaises(ValidationError):
            ApprovedCheckpointV2.model_validate(checkpoint)

    def test_timestamps_reject_non_iso8601_separator(self) -> None:
        checkpoint = _checkpoint()
        checkpoint["approval"]["approved_at"] = "2026-09-23X09:10:00+08:00"

        with self.assertRaises(ValidationError):
            ApprovedCheckpointV2.model_validate(checkpoint)

    def test_source_must_be_explicitly_official_and_https(self) -> None:
        for field, value in (("official", False), ("url", "http://example.gov/report")):
            with self.subTest(field=field):
                checkpoint = _checkpoint()
                checkpoint["sources"][0][field] = value
                with self.assertRaises(ValidationError):
                    ApprovedCheckpointV2.model_validate(checkpoint)

    def test_json_key_order_and_formatting_do_not_change_hash(self) -> None:
        checkpoint = _checkpoint()
        compact_reordered = json.loads(json.dumps(checkpoint, ensure_ascii=False, sort_keys=True))

        self.assertEqual(canonical_body_sha256(checkpoint), canonical_body_sha256(compact_reordered))
        self.assertEqual(
            canonical_body_sha256(checkpoint),
            canonical_body_sha256(json.loads(json.dumps(checkpoint, ensure_ascii=False, indent=4))),
        )

    def test_protected_value_array_order_and_exact_unicode_change_hash(self) -> None:
        checkpoint = _checkpoint()
        baseline = canonical_body_sha256(checkpoint)

        protected_change = copy.deepcopy(checkpoint)
        protected_change["protected_artifact_hashes"]["source.md"] = "b" * 64
        self.assertNotEqual(baseline, canonical_body_sha256(protected_change))

        array_change = copy.deepcopy(checkpoint)
        second_sentence = copy.deepcopy(array_change["script"]["sentences"][0])
        second_sentence["external_id"] = "sentence-2"
        array_change["script"]["sentences"].append(second_sentence)
        ordered_hash = canonical_body_sha256(array_change)
        array_change["script"]["sentences"].reverse()
        self.assertNotEqual(ordered_hash, canonical_body_sha256(array_change))

        unicode_change = copy.deepcopy(checkpoint)
        unicode_change["research"]["content"] = "Research text.\n"
        unicode_change["angle"]["core_insight"] = "经济数据说明一个事实。"
        unicode_hash = canonical_body_sha256(unicode_change)
        unicode_change["angle"]["core_insight"] = "經濟數據說明一個事實。"
        self.assertNotEqual(unicode_hash, canonical_body_sha256(unicode_change))

        exact_text_change = copy.deepcopy(checkpoint)
        exact_text_change["research"]["content"] += " "
        self.assertNotEqual(baseline, canonical_body_sha256(exact_text_change))

    def test_approval_metadata_is_outside_body_hash(self) -> None:
        checkpoint = _checkpoint()
        original = canonical_body_sha256(checkpoint)
        checkpoint["approval"]["reviewer"] = "reviewer-2"
        checkpoint["approval"]["approved_at"] = "2026-09-24T09:10:00+08:00"

        self.assertEqual(original, canonical_body_sha256(checkpoint))
        self.assertEqual(original, verify_approval_body_hash(checkpoint))

    def test_non_approval_runtime_named_value_remains_in_hash_boundary(self) -> None:
        checkpoint = _checkpoint()
        checkpoint["runtime_metadata"] = {"imported_at": "2026-09-23T09:11:00+08:00"}
        original = canonical_body_sha256(checkpoint)
        checkpoint["runtime_metadata"]["imported_at"] = "2026-09-23T09:12:00+08:00"

        self.assertNotEqual(original, canonical_body_sha256(checkpoint))

    def test_protected_body_edit_detects_approval_hash_mismatch(self) -> None:
        checkpoint = _checkpoint()
        checkpoint["research"]["content"] += "Edited.\n"

        with self.assertRaises(ApprovalBodyHashMismatch):
            verify_approval_body_hash(checkpoint)

    def test_explicit_version_dispatch_preserves_both_v1_labels(self) -> None:
        self.assertEqual(classify_checkpoint_version({"checkpoint_schema_version": "1.0"}), "legacy_v1")
        self.assertEqual(
            classify_checkpoint_version({"checkpoint_schema_version": "approved-checkpoint/1.0"}),
            "legacy_v1",
        )
        self.assertEqual(
            classify_checkpoint_version({"checkpoint_schema_version": "approved-checkpoint/2.0"}),
            "v2",
        )
        self.assertEqual(
            classify_checkpoint_version({"checkpoint_schema_version": "approved-checkpoint/2.1"}),
            "v2_1",
        )

    def test_unknown_version_is_not_silently_treated_as_legacy(self) -> None:
        with self.assertRaises(ValueError):
            classify_checkpoint_version({"checkpoint_schema_version": "approved-checkpoint/3.0"})
        with self.assertRaises(ValueError):
            classify_checkpoint_version({"checkpoint_schema_version": ["1.0"]})

    def test_non_finite_json_number_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            canonical_body_sha256({"checkpoint_schema_version": "approved-checkpoint/2.0", "value": float("nan")})


if __name__ == "__main__":
    unittest.main()
