from __future__ import annotations

import unittest
from pathlib import Path

from fanglei.artifact_registry import ARTIFACT_GRAPH, ArtifactRegistry
from fanglei.artifacts import atomic_write_json, read_json, sha256_text
from fanglei.errors import ArtifactConflictError, RunPathError
from fanglei.models import ArtifactState, RunManifest
from fanglei.checkpoint_authoring import bind_source_run_to_case


RUN_ID = "2026-09-23-001-research"
CASE_ID = "fed-sep-revisions"


def _make_run(runs_dir: Path, *, run_id: str = RUN_ID, manifest_run_id: str | None = None) -> Path:
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    manifest = RunManifest(
        run_id=manifest_run_id or run_id,
        created_at="2026-09-23T09:00:00+08:00",
        updated_at="2026-09-23T09:00:00+08:00",
    )
    atomic_write_json(run_dir / "run.json", manifest.model_dump(mode="json"))
    return run_dir


class CheckpointAuthoringBindingTests(unittest.TestCase):
    def test_binding_artifact_is_registered_without_dependencies(self) -> None:
        self.assertEqual(ARTIFACT_GRAPH["checkpoint_authoring_binding"], ("checkpoint_authoring_binding", ()))

    def test_first_binding_is_write_once_and_registered(self) -> None:
        with self.subTest("first explicit bind"):
            from tempfile import TemporaryDirectory

            with TemporaryDirectory() as temp:
                runs_dir = Path(temp) / "runs"
                run_dir = _make_run(runs_dir)

                bind_source_run_to_case(RUN_ID, CASE_ID, runs_dir)

                expected = {
                    "schema_version": "checkpoint-authoring-binding/1.0",
                    "run_id": RUN_ID,
                    "case_id": CASE_ID,
                }
                binding_path = run_dir / "checkpoint_authoring_binding.json"
                self.assertEqual(read_json(binding_path), expected)
                saved_manifest = RunManifest.model_validate(read_json(run_dir / "run.json"))
                state = saved_manifest.artifacts["checkpoint_authoring_binding"]
                self.assertEqual(state.status, "valid")
                self.assertEqual(state.content_hash, sha256_text(binding_path.read_text(encoding="utf-8")))
                self.assertEqual(state.dependencies, {})
                registry = ArtifactRegistry(run_dir, saved_manifest)
                self.assertEqual(registry.read_json("checkpoint_authoring_binding"), expected)

    def test_identical_binding_is_idempotent_without_rewriting(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp:
            runs_dir = Path(temp) / "runs"
            run_dir = _make_run(runs_dir)
            bind_source_run_to_case(RUN_ID, CASE_ID, runs_dir)
            binding_path = run_dir / "checkpoint_authoring_binding.json"
            manifest_path = run_dir / "run.json"
            binding_before = binding_path.read_bytes()
            manifest_before = manifest_path.read_bytes()

            bind_source_run_to_case(RUN_ID, CASE_ID, runs_dir)

            self.assertEqual(binding_path.read_bytes(), binding_before)
            self.assertEqual(manifest_path.read_bytes(), manifest_before)

    def test_generic_registry_writes_cannot_bypass_binding_write_once(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp:
            runs_dir = Path(temp) / "runs"
            run_dir = _make_run(runs_dir)
            binding_path = run_dir / "checkpoint_authoring_binding.json"
            manifest = RunManifest.model_validate(read_json(run_dir / "run.json"))
            registry = ArtifactRegistry(run_dir, manifest)
            binding_value = {
                "schema_version": "checkpoint-authoring-binding/1.0",
                "run_id": RUN_ID,
                "case_id": CASE_ID,
            }

            with self.assertRaises(ArtifactConflictError):
                registry.write_json("checkpoint_authoring_binding", binding_value, "checkpoint_authoring_binding", force=True)
            self.assertFalse(binding_path.exists())

            bind_source_run_to_case(RUN_ID, CASE_ID, runs_dir)
            original = binding_path.read_bytes()
            manifest = RunManifest.model_validate(read_json(run_dir / "run.json"))
            registry = ArtifactRegistry(run_dir, manifest)
            conflicting = {**binding_value, "case_id": "another-case"}
            with self.assertRaises(ArtifactConflictError):
                registry.write_json("checkpoint_authoring_binding", conflicting, "checkpoint_authoring_binding", force=True)
            self.assertEqual(binding_path.read_bytes(), original)

    def test_conflicting_case_fails_without_overwriting_binding(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp:
            runs_dir = Path(temp) / "runs"
            run_dir = _make_run(runs_dir)
            bind_source_run_to_case(RUN_ID, CASE_ID, runs_dir)
            binding_path = run_dir / "checkpoint_authoring_binding.json"
            binding_before = binding_path.read_bytes()

            with self.assertRaises(ArtifactConflictError):
                bind_source_run_to_case(RUN_ID, "another-case", runs_dir)

            self.assertEqual(binding_path.read_bytes(), binding_before)

    def test_malformed_registered_binding_fails_closed(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp:
            runs_dir = Path(temp) / "runs"
            run_dir = _make_run(runs_dir)
            malformed = '{"schema_version":"wrong","run_id":"broken","case_id":"x"}\n'
            binding_path = run_dir / "checkpoint_authoring_binding.json"
            binding_path.write_text(malformed, encoding="utf-8")
            manifest = RunManifest.model_validate(read_json(run_dir / "run.json"))
            manifest.artifacts["checkpoint_authoring_binding"] = ArtifactState(
                owner="checkpoint_authoring_binding",
                status="valid",
                content_hash=sha256_text(malformed),
                dependencies={},
            )
            atomic_write_json(run_dir / "run.json", manifest.model_dump(mode="json"))

            with self.assertRaises(ArtifactConflictError):
                bind_source_run_to_case(RUN_ID, CASE_ID, runs_dir)

    def test_unregistered_existing_binding_is_not_adopted(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp:
            runs_dir = Path(temp) / "runs"
            run_dir = _make_run(runs_dir)
            atomic_write_json(run_dir / "checkpoint_authoring_binding.json", {
                "schema_version": "checkpoint-authoring-binding/1.0",
                "run_id": RUN_ID,
                "case_id": CASE_ID,
            })

            with self.assertRaises(ArtifactConflictError):
                bind_source_run_to_case(RUN_ID, CASE_ID, runs_dir)

    def test_registered_hash_mismatch_fails_closed(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp:
            runs_dir = Path(temp) / "runs"
            run_dir = _make_run(runs_dir)
            bind_source_run_to_case(RUN_ID, CASE_ID, runs_dir)
            binding_path = run_dir / "checkpoint_authoring_binding.json"
            binding_path.write_text(binding_path.read_text(encoding="utf-8").replace(CASE_ID, "changed-case"), encoding="utf-8")

            with self.assertRaises(ArtifactConflictError):
                bind_source_run_to_case(RUN_ID, CASE_ID, runs_dir)

    def test_wrong_manifest_identity_and_missing_run_fail(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp:
            runs_dir = Path(temp) / "runs"
            _make_run(runs_dir, manifest_run_id="2026-09-23-001-other")
            with self.assertRaises(ArtifactConflictError):
                bind_source_run_to_case(RUN_ID, CASE_ID, runs_dir)
            with self.assertRaises(RunPathError):
                bind_source_run_to_case("2026-09-23-002-missing", CASE_ID, runs_dir)

    def test_run_path_traversal_is_rejected(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp:
            with self.assertRaises(RunPathError):
                bind_source_run_to_case("..\\outside", CASE_ID, Path(temp) / "runs")


if __name__ == "__main__":
    unittest.main()
