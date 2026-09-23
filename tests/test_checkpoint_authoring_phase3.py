from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import tempfile
import unittest

from pydantic import ValidationError

from test_checkpoint_authoring_phase2 import (
    CASE_ID,
    CHECKPOINT_ID,
    RUN_ID,
    SOURCE_ID,
    SOURCE_TEXT,
    _make_complete_run,
)
from fanglei.checkpoint_authoring import (
    CheckpointAuthoringError,
    ValidationReport,
    approve_checkpoint,
    build_checkpoint_draft,
    seal_checkpoint,
    validate_checkpoint_draft,
)
from fanglei.checkpoint_contract import (
    ApprovedCheckpointV2,
    CheckpointDraft,
    canonical_body_sha256,
)
from fanglei.artifacts import read_json


APPROVED_AT = "2026-09-24T09:30:00+08:00"


def _official_reviews(basis: str = "Official institution publication record.") -> dict:
    return {
        SOURCE_ID: {
            "official": True,
            "official_review": {
                "decision": "approved_official",
                "reviewer": "source-reviewer-1",
                "reviewed_at": "2026-09-23T10:00:00+08:00",
                "basis": basis,
            },
        }
    }


class CheckpointAuthoringPhase3Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repository_root = Path(self.temp.name) / "repo"
        self.repository_root.mkdir()
        self.runs_dir = self.repository_root / "runs"
        self.run_dir = _make_complete_run(self.runs_dir)
        self.draft = build_checkpoint_draft(
            RUN_ID, CASE_ID, CHECKPOINT_ID, self.runs_dir, _official_reviews()
        )
        self.validation = validate_checkpoint_draft(self.draft, self.runs_dir)
        self.assertTrue(self.validation.passed, self.validation.issues)

    def tearDown(self) -> None:
        self.temp.cleanup()

    @property
    def sealed_path(self) -> Path:
        return (
            self.repository_root
            / "cases"
            / CASE_ID
            / "approved-checkpoints"
            / f"{CHECKPOINT_ID}.json"
        )

    def approve(self, *, reviewer: str = "human-reviewer-1", approved_at: str = APPROVED_AT,
                expected_body_sha256: str | None = None, validation: ValidationReport | None = None):
        return approve_checkpoint(
            self.draft,
            self.validation if validation is None else validation,
            reviewer=reviewer,
            expected_body_sha256=(
                self.validation.body_sha256
                if expected_body_sha256 is None
                else expected_body_sha256
            ),
            approved_at=approved_at,
        )

    def test_explicit_approval_requires_passing_report_and_exact_digest(self) -> None:
        approval = self.approve()
        self.assertEqual(approval.status, "approved")
        self.assertEqual(approval.reviewer, "human-reviewer-1")
        self.assertEqual(
            approval.body_sha256,
            canonical_body_sha256(self.draft.model_dump(mode="python", by_alias=True)),
        )

        with self.assertRaisesRegex(CheckpointAuthoringError, "CHECKPOINT_NOT_VALIDATED"):
            approve_checkpoint(
                self.draft,
                ValidationReport(False, self.validation.body_sha256),
                reviewer="human-reviewer-1",
                expected_body_sha256=self.validation.body_sha256,
                approved_at=APPROVED_AT,
            )
        with self.assertRaisesRegex(CheckpointAuthoringError, "APPROVAL_BODY_HASH_MISMATCH"):
            self.approve(expected_body_sha256="0" * 64)

    def test_approval_rejects_invalid_reviewer_digest_and_naive_time(self) -> None:
        for reviewer, digest, timestamp in (
            ("   ", self.validation.body_sha256, APPROVED_AT),
            ("reviewer", "abc", APPROVED_AT),
            ("reviewer", self.validation.body_sha256, "2026-09-24T09:30:00"),
        ):
            with self.subTest(reviewer=reviewer, digest=digest, timestamp=timestamp):
                with self.assertRaises((CheckpointAuthoringError, ValidationError)):
                    self.approve(
                        reviewer=reviewer,
                        expected_body_sha256=digest,
                        approved_at=timestamp,
                    )

    def test_seal_writes_strict_v2_at_fixed_path_and_repeat_is_idempotent(self) -> None:
        approval = self.approve()
        path = seal_checkpoint(self.draft, approval, self.repository_root, runs_dir=self.runs_dir)

        self.assertEqual(path, self.sealed_path)
        first_bytes = path.read_bytes()
        parsed = ApprovedCheckpointV2.model_validate(read_json(path), strict=True)
        self.assertEqual(
            parsed.approval.body_sha256,
            canonical_body_sha256(parsed.model_dump(mode="python", by_alias=True)),
        )
        self.assertEqual(
            seal_checkpoint(self.draft, approval, self.repository_root, runs_dir=self.runs_dir), path
        )
        self.assertEqual(path.read_bytes(), first_bytes)
        self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_body_edits_after_approval_invalidate_approval_without_sealing(self) -> None:
        approval = self.approve()
        raw = self.draft.model_dump(mode="json", by_alias=True)
        raw["research"]["content"] += "Unapproved edit."
        changed = CheckpointDraft.model_validate(raw, strict=True)

        with self.assertRaisesRegex(CheckpointAuthoringError, "APPROVAL_BODY_HASH_MISMATCH"):
            seal_checkpoint(changed, approval, self.repository_root, runs_dir=self.runs_dir)
        self.assertFalse(self.sealed_path.exists())

    def test_changes_to_protected_body_fields_after_approval_invalidate_it(self) -> None:
        approval = self.approve()
        mutations = (
            ("protected_artifact_hashes", "source.md", "f" * 64),
            ("official_review", "basis", "Changed review basis."),
            ("source_snapshot", "source_text_sha256", "e" * 64),
            ("angle", "title", "Changed title."),
            ("script", "title", "Changed script title."),
        )
        for kind, field, value in mutations:
            with self.subTest(kind=kind, field=field):
                raw = self.draft.model_dump(mode="json", by_alias=True)
                if kind == "protected_artifact_hashes":
                    raw["protected_artifact_hashes"][field] = value
                elif kind == "official_review":
                    raw["sources"][0]["official_review"][field] = value
                elif kind == "source_snapshot":
                    raw["sources"][0]["snapshot"][field] = value
                else:
                    raw[kind][field] = value
                changed = CheckpointDraft.model_validate(raw, strict=True)
                with self.assertRaisesRegex(CheckpointAuthoringError, "APPROVAL_BODY_HASH_MISMATCH"):
                    seal_checkpoint(changed, approval, self.repository_root, runs_dir=self.runs_dir)
                self.assertFalse(self.sealed_path.exists())

    def test_every_registered_input_change_after_approval_fails_before_seal(self) -> None:
        relative_paths = (
            "checkpoint_authoring_binding.json",
            "source.md",
            "questions.json",
            "source_documents/index.json",
            "sources.json",
            "facts.json",
            "research.md",
            "angles.json",
            "angle.md",
            "script.json",
            "script.md",
            "source_documents/src_001.md",
        )
        for relative_path in relative_paths:
            with self.subTest(relative_path=relative_path):
                with tempfile.TemporaryDirectory() as temp:
                    repository_root = Path(temp) / "repo"
                    repository_root.mkdir()
                    runs_dir = repository_root / "runs"
                    run_dir = _make_complete_run(runs_dir)
                    draft = build_checkpoint_draft(
                        RUN_ID, CASE_ID, CHECKPOINT_ID, runs_dir, _official_reviews()
                    )
                    report = validate_checkpoint_draft(draft, runs_dir)
                    approval_for_run = approve_checkpoint(
                        draft,
                        report,
                        reviewer="human-reviewer-1",
                        expected_body_sha256=report.body_sha256,
                        approved_at=APPROVED_AT,
                    )
                    artifact = run_dir / relative_path
                    artifact.write_bytes(artifact.read_bytes() + b" ")

                    with self.assertRaises(CheckpointAuthoringError):
                        seal_checkpoint(draft, approval_for_run, repository_root, runs_dir=runs_dir)
                    expected = repository_root / "cases" / CASE_ID / "approved-checkpoints" / f"{CHECKPOINT_ID}.json"
                    self.assertFalse(expected.exists())

    def test_different_body_or_approval_under_same_id_conflicts_without_overwrite(self) -> None:
        first_approval = self.approve()
        seal_checkpoint(self.draft, first_approval, self.repository_root, runs_dir=self.runs_dir)
        sealed_before = self.sealed_path.read_bytes()

        changed_draft = build_checkpoint_draft(
            RUN_ID,
            CASE_ID,
            CHECKPOINT_ID,
            self.runs_dir,
            _official_reviews("A separately reviewed official source basis."),
        )
        changed_report = validate_checkpoint_draft(changed_draft, self.runs_dir)
        changed_approval = approve_checkpoint(
            changed_draft,
            changed_report,
            reviewer="human-reviewer-2",
            expected_body_sha256=changed_report.body_sha256,
            approved_at=APPROVED_AT,
        )
        with self.assertRaisesRegex(CheckpointAuthoringError, "CHECKPOINT_WRITE_ONCE_CONFLICT"):
            seal_checkpoint(changed_draft, changed_approval, self.repository_root, runs_dir=self.runs_dir)

        different_approval = self.approve(reviewer="human-reviewer-2")
        with self.assertRaisesRegex(CheckpointAuthoringError, "CHECKPOINT_WRITE_ONCE_CONFLICT"):
            seal_checkpoint(self.draft, different_approval, self.repository_root, runs_dir=self.runs_dir)
        self.assertEqual(self.sealed_path.read_bytes(), sealed_before)

    def test_unsafe_case_or_checkpoint_id_fails_before_creating_output(self) -> None:
        approval = self.approve()
        for field, value in (("case_id", "../outside"), ("checkpoint_id", "..\\outside")):
            with self.subTest(field=field):
                changed = self.draft.model_copy(update={field: value})
                with self.assertRaisesRegex(CheckpointAuthoringError, "CHECKPOINT_IDENTITY_MISMATCH"):
                    seal_checkpoint(changed, approval, self.repository_root, runs_dir=self.runs_dir)
        self.assertFalse((self.repository_root / "cases").exists())

    def test_seal_uses_source_run_from_explicit_non_default_runs_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repository"
            root.mkdir()
            custom_runs_dir = Path(temp) / "external-source-runs"
            _make_complete_run(custom_runs_dir)
            draft = build_checkpoint_draft(
                RUN_ID, CASE_ID, CHECKPOINT_ID, custom_runs_dir, _official_reviews()
            )
            report = validate_checkpoint_draft(draft, custom_runs_dir)
            approval = approve_checkpoint(
                draft,
                report,
                reviewer="human-reviewer-1",
                expected_body_sha256=report.body_sha256,
                approved_at=APPROVED_AT,
            )

            sealed_path = seal_checkpoint(draft, approval, root, runs_dir=custom_runs_dir)

            self.assertEqual(
                sealed_path,
                root / "cases" / CASE_ID / "approved-checkpoints" / f"{CHECKPOINT_ID}.json",
            )

    def test_seal_does_not_require_repository_root_runs_when_runs_dir_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repository"
            root.mkdir()
            custom_runs_dir = Path(temp) / "run-store" / "runs"
            _make_complete_run(custom_runs_dir)
            draft = build_checkpoint_draft(
                RUN_ID, CASE_ID, CHECKPOINT_ID, custom_runs_dir, _official_reviews()
            )
            report = validate_checkpoint_draft(draft, custom_runs_dir)
            approval = approve_checkpoint(
                draft,
                report,
                reviewer="human-reviewer-1",
                expected_body_sha256=report.body_sha256,
                approved_at=APPROVED_AT,
            )
            self.assertFalse((root / "runs").exists())

            sealed_path = seal_checkpoint(draft, approval, root, runs_dir=custom_runs_dir)

            self.assertTrue(sealed_path.is_file())
            self.assertFalse((root / "runs").exists())

    def test_default_same_id_different_run_is_ignored_in_favor_of_explicit_runs_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repository"
            root.mkdir()
            default_runs_dir = root / "runs"
            default_run_dir = _make_complete_run(
                default_runs_dir,
                source_text=SOURCE_TEXT + " This content belongs only to the default run.\n",
            )
            selected_runs_dir = Path(temp) / "selected-run-store"
            _make_complete_run(selected_runs_dir)
            draft = build_checkpoint_draft(
                RUN_ID, CASE_ID, CHECKPOINT_ID, selected_runs_dir, _official_reviews()
            )
            report = validate_checkpoint_draft(draft, selected_runs_dir)
            approval = approve_checkpoint(
                draft,
                report,
                reviewer="human-reviewer-1",
                expected_body_sha256=report.body_sha256,
                approved_at=APPROVED_AT,
            )

            sealed_path = seal_checkpoint(draft, approval, root, runs_dir=selected_runs_dir)

            sealed = ApprovedCheckpointV2.model_validate(read_json(sealed_path), strict=True)
            default_index = read_json(default_run_dir / "source_documents" / "index.json")
            self.assertNotEqual(
                sealed.sources[0].snapshot.source_text_sha256,
                default_index["documents"][0]["content_hash"],
            )

    def test_wrong_explicit_runs_dir_fails_closed_without_sealed_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repository"
            root.mkdir()
            selected_runs_dir = Path(temp) / "selected-runs"
            _make_complete_run(selected_runs_dir)
            draft = build_checkpoint_draft(
                RUN_ID, CASE_ID, CHECKPOINT_ID, selected_runs_dir, _official_reviews()
            )
            report = validate_checkpoint_draft(draft, selected_runs_dir)
            approval = approve_checkpoint(
                draft,
                report,
                reviewer="human-reviewer-1",
                expected_body_sha256=report.body_sha256,
                approved_at=APPROVED_AT,
            )

            with self.assertRaises(CheckpointAuthoringError):
                seal_checkpoint(draft, approval, root, runs_dir=Path(temp) / "wrong-runs")

            expected = root / "cases" / CASE_ID / "approved-checkpoints" / f"{CHECKPOINT_ID}.json"
            self.assertFalse(expected.exists())
            self.assertFalse((root / "cases").exists())

    def test_concurrent_distinct_seals_publish_only_one_complete_envelope(self) -> None:
        approvals = (self.approve(reviewer="human-reviewer-1"), self.approve(reviewer="human-reviewer-2"))

        def seal(approval):
            try:
                return seal_checkpoint(self.draft, approval, self.repository_root, runs_dir=self.runs_dir)
            except CheckpointAuthoringError as error:
                return error

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = [future.result() for future in as_completed([executor.submit(seal, item) for item in approvals])]

        self.assertEqual(sum(isinstance(item, Path) for item in outcomes), 1)
        conflicts = [item for item in outcomes if isinstance(item, CheckpointAuthoringError)]
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].code, "CHECKPOINT_WRITE_ONCE_CONFLICT")
        parsed = ApprovedCheckpointV2.model_validate(read_json(self.sealed_path), strict=True)
        self.assertIn(parsed.approval.reviewer, {"human-reviewer-1", "human-reviewer-2"})
        self.assertEqual(list(self.sealed_path.parent.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
