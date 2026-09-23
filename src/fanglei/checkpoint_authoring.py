"""Phase 1 checkpoint authoring identity operations."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import tempfile

from pydantic import ValidationError

from fanglei.artifact_registry import ARTIFACT_GRAPH, ArtifactRegistry
from fanglei.artifacts import read_json, sha256_text
from fanglei.checkpoint_contract import CheckpointAuthoringBindingV1
from fanglei.errors import ArtifactConflictError
from fanglei.models import RunManifest
from fanglei.paths import resolve_run_dir


BINDING_ARTIFACT = "checkpoint_authoring_binding"
BINDING_FILENAME = "checkpoint_authoring_binding.json"


def _binding_error(code: str, message: str) -> ArtifactConflictError:
    return ArtifactConflictError(f"{code}: {message}")


def _load_manifest(run_dir: Path) -> RunManifest:
    manifest_path = run_dir / "run.json"
    if not manifest_path.is_file():
        raise _binding_error("CASE_BINDING_MISSING", f"Run manifest is missing: {manifest_path}")
    try:
        return RunManifest.model_validate(read_json(manifest_path))
    except (OSError, ValueError, ValidationError) as error:
        raise _binding_error("CASE_BINDING_INVALID", f"Run manifest is malformed: {error}") from error


def _read_registered_binding(
    registry: ArtifactRegistry,
    binding_path: Path,
    manifest_had_binding_state: bool,
) -> CheckpointAuthoringBindingV1 | None:
    if not binding_path.exists():
        if manifest_had_binding_state:
            state = registry.manifest.artifacts[BINDING_ARTIFACT]
            if (
                state.status == "missing"
                and state.content_hash is None
                and not state.dependencies
                and state.owner == ARTIFACT_GRAPH[BINDING_ARTIFACT][0]
            ):
                return None
            raise _binding_error("CASE_BINDING_STALE", "Registered case binding file is missing")
        return None

    if not binding_path.is_file():
        raise _binding_error("CASE_BINDING_INVALID", "Case binding path is not a regular file")
    if not manifest_had_binding_state:
        raise _binding_error("CASE_BINDING_UNREGISTERED", "Existing case binding is not registered in run.json")

    state = registry.manifest.artifacts[BINDING_ARTIFACT]
    if state.owner != ARTIFACT_GRAPH[BINDING_ARTIFACT][0] or state.dependencies:
        raise _binding_error("CASE_BINDING_INVALID", "Case binding registry owner/dependencies are invalid")
    try:
        registry.validate(BINDING_ARTIFACT)
        raw = read_json(binding_path)
        return CheckpointAuthoringBindingV1.model_validate(raw)
    except (OSError, ValueError, ValidationError, ArtifactConflictError) as error:
        raise _binding_error("CASE_BINDING_STALE", f"Registered case binding is invalid: {error}") from error


def _atomic_create_json(path: Path, value: dict[str, str]) -> str:
    """Publish a JSON file atomically without replacing an existing name."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
            temporary_path = Path(handle.name)
        os.link(temporary_path, path)
    except FileExistsError as error:
        raise _binding_error("CASE_BINDING_CONFLICT", f"Case binding already exists: {path}") from error
    except OSError as error:
        raise _binding_error("CASE_BINDING_CREATE_FAILED", f"Could not atomically create case binding: {error}") from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return text


def bind_source_run_to_case(run_id: str, case_id: str, runs_dir: Path) -> None:
    """Create or validate the explicit, write-once case binding for one run."""
    run_dir = resolve_run_dir(Path(runs_dir), run_id)
    manifest = _load_manifest(run_dir)
    if manifest.run_id != run_id:
        raise _binding_error(
            "CHECKPOINT_IDENTITY_MISMATCH",
            f"Run directory requested as {run_id!r} has manifest run_id {manifest.run_id!r}",
        )

    try:
        requested = CheckpointAuthoringBindingV1.model_validate({
            "schema_version": "checkpoint-authoring-binding/1.0",
            "run_id": run_id,
            "case_id": case_id,
        })
    except ValidationError as error:
        raise _binding_error("CASE_BINDING_INVALID", f"Explicit run_id/case_id is invalid: {error}") from error

    manifest_had_binding_state = BINDING_ARTIFACT in manifest.artifacts
    registry = ArtifactRegistry(run_dir, manifest)
    binding_path = run_dir / BINDING_FILENAME
    existing = _read_registered_binding(registry, binding_path, manifest_had_binding_state)
    if existing is not None:
        if existing != requested:
            raise _binding_error(
                "CASE_BINDING_CONFLICT",
                f"Run {run_id!r} is already bound to case {existing.case_id!r}",
            )
        return

    state = manifest.artifacts[BINDING_ARTIFACT]
    if (
        state.owner != ARTIFACT_GRAPH[BINDING_ARTIFACT][0]
        or state.status != "missing"
        or state.content_hash is not None
        or state.dependencies
    ):
        raise _binding_error("CASE_BINDING_STALE", "Binding registry state is not an untouched missing artifact")

    binding_value = requested.model_dump(mode="json")
    text = _atomic_create_json(binding_path, binding_value)
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    state.status = "valid"
    state.content_hash = sha256_text(text)
    state.created_at = state.created_at or timestamp
    state.updated_at = timestamp
    state.dependencies = {}
    registry.save_manifest()
