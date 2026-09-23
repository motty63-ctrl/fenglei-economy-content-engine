"""Phase 1 checkpoint authoring identity operations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from pathlib import PurePosixPath, PureWindowsPath
import re
import tempfile
from typing import Any

from pydantic import ValidationError

from fanglei.artifact_registry import ARTIFACT_GRAPH, ArtifactRegistry
from fanglei.artifacts import read_json, sha256_text
from fanglei.checkpoint_contract import (
    CheckpointAngle,
    CheckpointApproval,
    CheckpointAuthoringBindingV1,
    CheckpointClaim,
    CheckpointDraft,
    CheckpointEvidence,
    CheckpointScript,
    CheckpointSource,
    FactsSource,
    OfficialReview,
    canonical_body_sha256,
    canonical_json_bytes,
    parse_approved_checkpoint_v2,
)
from fanglei.content_models import AngleCandidate
from fanglei.errors import ArtifactConflictError
from fanglei.models import RunManifest
from fanglei.paths import RunPathError, resolve_run_dir


BINDING_ARTIFACT = "checkpoint_authoring_binding"
BINDING_FILENAME = "checkpoint_authoring_binding.json"

_AUTHORING_ARTIFACTS = (
    BINDING_ARTIFACT,
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
)
_PROTECTED_HASH_KEYS = {
    BINDING_ARTIFACT: BINDING_FILENAME,
    "source.md": "source.md",
    "questions.json": "questions.json",
    "source_documents/index.json": "source_documents/index.json",
    "sources.json": "sources.json",
    "facts.json": "facts.json",
    "research.md": "research.md",
    "angles.json": "angles.json",
    "angle.md": "angle.md",
    "script.json": "script.json",
    "script.md": "script.md",
}
_SELECTED_ANGLE_MARKER = re.compile(r"(?m)^selected_angle_id: `([^`]+)`\s*$")


class CheckpointAuthoringError(ValueError):
    """A deterministic authoring input violates a fail-closed contract."""

    def __init__(self, code: str, path: str, message: str):
        self.code = code
        self.path = path
        super().__init__(f"{code} at {path}: {message}")


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class ValidationReport:
    passed: bool
    body_sha256: str | None
    issues: tuple[ValidationIssue, ...] = ()


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


def _fail(code: str, path: str, message: str) -> None:
    raise CheckpointAuthoringError(code, path, message)


def _safe_component(value: str, field: str) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or PureWindowsPath(value).is_absolute()
        or bool(PureWindowsPath(value).drive)
    ):
        _fail("CHECKPOINT_IDENTITY_MISMATCH", field, "must be an explicit safe single path component")


def _safe_run_relative_path(run_dir: Path, value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value or "\0" in value:
        _fail("UNSAFE_SOURCE_PATH", field, "must be a non-empty relative path")
    windows_path = PureWindowsPath(value)
    posix_path = PurePosixPath(value.replace("\\", "/"))
    if windows_path.is_absolute() or windows_path.drive or posix_path.is_absolute() or ".." in posix_path.parts:
        _fail("UNSAFE_SOURCE_PATH", field, f"path escapes the selected source run: {value!r}")
    if not posix_path.parts:
        _fail("UNSAFE_SOURCE_PATH", field, "must identify a file inside the selected source run")
    resolved = run_dir.joinpath(*posix_path.parts).resolve(strict=False)
    if not resolved.is_relative_to(run_dir.resolve()):
        _fail("UNSAFE_SOURCE_PATH", field, f"path escapes the selected source run: {value!r}")
    return resolved


def _read_safe_index(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "source_documents" / "index.json"
    try:
        value = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail("AUTHORING_ARTIFACT_STALE", "source_documents/index.json", f"cannot read source index: {error}")
    if not isinstance(value, dict) or not isinstance(value.get("documents"), list):
        _fail("AUTHORING_ARTIFACT_STALE", "source_documents/index.json", "expected an object with a documents array")
    for index, document in enumerate(value["documents"]):
        field = f"source_documents/index.json.documents[{index}]"
        if not isinstance(document, dict):
            _fail("AUTHORING_ARTIFACT_STALE", field, "expected an object")
        _safe_run_relative_path(run_dir, document.get("path"), f"{field}.path")
        files = document.get("files")
        if not isinstance(files, list):
            _fail("AUTHORING_ARTIFACT_STALE", f"{field}.files", "expected an array")
        for file_index, entry in enumerate(files):
            entry_field = f"{field}.files[{file_index}]"
            if not isinstance(entry, dict):
                _fail("AUTHORING_ARTIFACT_STALE", entry_field, "expected an object")
            _safe_run_relative_path(run_dir, entry.get("path"), f"{entry_field}.path")
    return value


def _validate_registered_inputs(
    run_dir: Path,
    manifest: RunManifest,
    registry: ArtifactRegistry,
) -> None:
    if BINDING_ARTIFACT not in manifest.artifacts:
        _fail("CASE_BINDING_MISSING", BINDING_FILENAME, "case binding is not registered in run.json")
    missing = [name for name in _AUTHORING_ARTIFACTS if name not in manifest.artifacts]
    if missing:
        _fail("AUTHORING_ARTIFACT_MISSING", "run.json.artifacts", f"unregistered artifacts: {', '.join(missing)}")

    for name in _AUTHORING_ARTIFACTS:
        state = manifest.artifacts[name]
        expected_owner, expected_dependencies = ARTIFACT_GRAPH[name]
        if state.owner != expected_owner or set(state.dependencies) != set(expected_dependencies):
            _fail("AUTHORING_ARTIFACT_STALE", name, "registry owner or dependency declaration differs from ARTIFACT_GRAPH")
        if state.status != "valid" or not state.content_hash or re.fullmatch(r"[0-9a-f]{64}", state.content_hash) is None:
            if name == BINDING_ARTIFACT:
                code = "CASE_BINDING_MISSING" if state.status == "missing" else "CASE_BINDING_STALE"
                _fail(code, BINDING_FILENAME, f"registered case binding state is {state.status!r}")
            code = "AUTHORING_ARTIFACT_MISSING" if state.status == "missing" else "AUTHORING_ARTIFACT_STALE"
            _fail(code, name, f"registered artifact state is {state.status!r} or has no valid content hash")

    # Validate the binding first; its private reader also rejects unregistered, stale,
    # malformed, or hash-mismatched bindings without adopting or repairing them.
    try:
        binding = _read_registered_binding(
            registry,
            run_dir / BINDING_FILENAME,
            manifest_had_binding_state=True,
        )
    except ArtifactConflictError as error:
        message = str(error)
        code = message.split(":", 1)[0]
        if not code.startswith("CASE_BINDING_"):
            code = "CASE_BINDING_STALE"
        _fail(code, BINDING_FILENAME, message)
    if binding is None:
        _fail("CASE_BINDING_MISSING", BINDING_FILENAME, "registered case binding is missing")

    # The index paths are checked before registry.validate() because the registry
    # follows them to verify the indexed files.
    for name in _AUTHORING_ARTIFACTS:
        if name == "source_documents/index.json":
            continue
        try:
            registry.validate(name)
        except ArtifactConflictError as error:
            _fail("AUTHORING_ARTIFACT_STALE", name, str(error))
    try:
        registry.validate("source_documents/index.json")
    except ArtifactConflictError as error:
        _fail("AUTHORING_ARTIFACT_STALE", "source_documents/index.json", str(error))


def _exact_text(path: Path, artifact: str) -> str:
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        _fail("AUTHORING_ARTIFACT_STALE", artifact, f"cannot read exact UTF-8 text: {error}")


def _json_object(registry: ArtifactRegistry, name: str) -> dict[str, Any]:
    try:
        value = registry.read_json(name)
    except (OSError, ValueError, ArtifactConflictError) as error:
        _fail("AUTHORING_ARTIFACT_STALE", name, str(error))
    if not isinstance(value, dict):
        _fail("AUTHORING_ARTIFACT_STALE", name, "expected a JSON object")
    return value


def _protected_hashes(manifest: RunManifest) -> dict[str, str]:
    result: dict[str, str] = {}
    for artifact_name, body_name in _PROTECTED_HASH_KEYS.items():
        digest = manifest.artifacts[artifact_name].content_hash
        if not digest:
            _fail("AUTHORING_ARTIFACT_STALE", artifact_name, "registered artifact has no content hash")
        result[body_name] = digest
    return result


def _indexed_source_rows(
    run_dir: Path,
    index_value: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    by_id: dict[str, dict[str, Any]] = {}
    text_by_id: dict[str, str] = {}
    for index, document in enumerate(index_value["documents"]):
        field = f"source_documents/index.json.documents[{index}]"
        source_id = document.get("source_id")
        if not isinstance(source_id, str) or not source_id.strip() or source_id in by_id:
            _fail("CHECKPOINT_IDENTITY_MISMATCH", f"{field}.source_id", "source IDs must be unique non-empty strings")
        text_hash = document.get("content_hash")
        if not isinstance(text_hash, str) or re.fullmatch(r"[0-9a-f]{64}", text_hash) is None:
            _fail("SOURCE_SNAPSHOT_MISMATCH", f"{field}.content_hash", "normalized-text SHA-256 is missing or malformed")
        text_path = _safe_run_relative_path(run_dir, document.get("path"), f"{field}.path")
        text = _exact_text(text_path, f"{field}.path")
        if sha256_text(text) != text_hash:
            _fail("SOURCE_SNAPSHOT_MISMATCH", f"{field}.content_hash", "normalized text differs from the indexed extracted-text hash")
        indexed_text = document.get("text")
        if not isinstance(indexed_text, str) or indexed_text != text:
            _fail("SOURCE_SNAPSHOT_MISMATCH", f"{field}.text", "indexed extracted text differs from the normalized document")
        by_id[source_id] = document
        text_by_id[source_id] = text
    return by_id, text_by_id


def _snapshot_for_document(run_dir: Path, document: dict[str, Any], field: str) -> dict[str, Any]:
    files = document.get("files")
    if not isinstance(files, list) or not files:
        _fail("SOURCE_SNAPSHOT_MISMATCH", f"{field}.files", "at least the normalized-text file is required")
    source_text_hash = document.get("content_hash")
    normalized_path = document.get("path")
    mapped_files: list[dict[str, str]] = []
    raw_pdf_hashes: list[str] = []
    normalized_count = 0
    for index, asset in enumerate(files):
        item_field = f"{field}.files[{index}]"
        role = asset.get("role")
        path = asset.get("path")
        digest = asset.get("content_hash")
        if not isinstance(role, str) or not isinstance(path, str) or not isinstance(digest, str):
            _fail("SOURCE_SNAPSHOT_MISMATCH", item_field, "role, path, and content_hash are required")
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            _fail("SOURCE_SNAPSHOT_MISMATCH", f"{item_field}.content_hash", "must be lowercase SHA-256")
        asset_path = _safe_run_relative_path(run_dir, path, f"{item_field}.path")
        suffix = asset_path.suffix.lower()
        if role == "normalized_text":
            normalized_count += 1
            if path != normalized_path or digest != source_text_hash:
                _fail("SOURCE_SNAPSHOT_MISMATCH", item_field, "normalized_text path/hash must match the document row")
            try:
                actual_hash = sha256_text(asset_path.read_bytes().decode("utf-8"))
            except (OSError, UnicodeDecodeError) as error:
                _fail("SOURCE_SNAPSHOT_MISMATCH", path, f"normalized text is unreadable: {error}")
            if actual_hash != digest:
                _fail("SOURCE_SNAPSHOT_MISMATCH", path, "normalized text content hash differs from the index")
            hash_kind = "utf8_text_sha256"
        elif role == "raw_response" and suffix == ".json":
            try:
                raw_text = asset_path.read_bytes().decode("utf-8")
            except (OSError, UnicodeDecodeError) as error:
                _fail("SOURCE_SNAPSHOT_MISMATCH", path, f"raw JSON response is unreadable: {error}")
            if sha256_text(raw_text) != digest:
                _fail("SOURCE_SNAPSHOT_MISMATCH", path, "raw JSON text hash differs from the index")
            hash_kind = "utf8_text_sha256"
        elif role == "raw_response" and suffix == ".pdf":
            if document.get("document_format") != "pdf":
                _fail("SOURCE_SNAPSHOT_MISMATCH", item_field, "raw PDF bytes are not identified by document_format=pdf")
            try:
                raw_bytes = asset_path.read_bytes()
            except OSError as error:
                _fail("SOURCE_SNAPSHOT_MISMATCH", path, f"raw PDF is unreadable: {error}")
            if hashlib.sha256(raw_bytes).hexdigest() != digest:
                _fail("SOURCE_SNAPSHOT_MISMATCH", path, "raw PDF byte hash differs from the index")
            raw_pdf_hashes.append(digest)
            hash_kind = "file_bytes_sha256"
        elif role == "page_index" and suffix == ".json":
            try:
                raw_bytes = asset_path.read_bytes()
            except OSError as error:
                _fail("SOURCE_SNAPSHOT_MISMATCH", path, f"page index is unreadable: {error}")
            if hashlib.sha256(raw_bytes).hexdigest() != digest:
                _fail("SOURCE_SNAPSHOT_MISMATCH", path, "page-index file-byte hash differs from the index")
            hash_kind = "file_bytes_sha256"
        else:
            _fail("SOURCE_SNAPSHOT_MISMATCH", item_field, f"unsupported indexed file representation: {role!r} {path!r}")
        mapped_files.append({"role": role, "path": path, "hash_kind": hash_kind, "sha256": digest})
    if normalized_count != 1:
        _fail("SOURCE_SNAPSHOT_MISMATCH", f"{field}.files", "exactly one normalized_text file is required")
    if len(raw_pdf_hashes) > 1:
        _fail("SOURCE_SNAPSHOT_MISMATCH", f"{field}.files", "multiple raw PDF captures cannot be represented by one snapshot digest")
    return {
        "source_text_sha256": source_text_hash,
        "raw_capture_bytes_sha256": raw_pdf_hashes[0] if raw_pdf_hashes else None,
        "indexed_file_hashes": mapped_files,
    }


def _map_sources(
    run_dir: Path,
    sources_value: dict[str, Any],
    index_value: dict[str, Any],
    official_reviews: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, str]]:
    source_rows = sources_value.get("sources")
    if not isinstance(source_rows, list) or not source_rows:
        _fail("SOURCE_SNAPSHOT_MISMATCH", "sources.json.sources", "at least one selected source is required")
    if not isinstance(official_reviews, Mapping):
        _fail("SOURCE_OFFICIAL_REVIEW_MISSING", "official_reviews", "explicit per-source review mapping is required")
    if any(not isinstance(key, str) for key in official_reviews):
        _fail("SOURCE_OFFICIAL_REVIEW_MISSING", "official_reviews", "review keys must be exact source IDs")

    documents_by_id, text_by_id = _indexed_source_rows(run_dir, index_value)
    source_ids: set[str] = set()
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    evidence_urls: dict[str, str] = {}
    for index, source in enumerate(source_rows):
        field = f"sources.json.sources[{index}]"
        if not isinstance(source, dict):
            _fail("SOURCE_SNAPSHOT_MISMATCH", field, "expected a source object")
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not source_id.strip() or source_id in seen_ids:
            _fail("CHECKPOINT_IDENTITY_MISMATCH", f"{field}.source_id", "source IDs must be unique non-empty strings")
        seen_ids.add(source_id)
        document = documents_by_id.get(source_id)
        if document is None:
            _fail("CROSS_RUN_REFERENCE", f"{field}.source_id", "selected source has no document in this run's index")
        document_field = f"source_documents/index.json.documents[{source_id}]"
        for key in ("url", "title", "published_at", "retrieved_at"):
            if key not in source or key not in document or source[key] != document[key]:
                _fail("CHECKPOINT_IDENTITY_MISMATCH", f"{field}.{key}", "source and indexed-document identity values differ or are missing")
        url = source.get("url")
        original_url = document.get("original_url")
        if original_url is not None and (not isinstance(original_url, str) or not original_url.strip()):
            _fail("CHECKPOINT_IDENTITY_MISMATCH", f"{document_field}.original_url", "original_url must be null or a non-empty exact URL")
        expected_origin_chain = [original_url, url] if original_url else [url]
        if source.get("origin_chain") != expected_origin_chain:
            _fail("CHECKPOINT_IDENTITY_MISMATCH", f"{field}.origin_chain", "source origin chain does not match indexed URL/original URL")

        review_input = official_reviews.get(source_id)
        if not isinstance(review_input, Mapping) or set(review_input) != {"official", "official_review"}:
            _fail("SOURCE_OFFICIAL_REVIEW_MISSING", f"official_reviews.{source_id}", "explicit official=true and official_review record are required")
        if review_input.get("official") is not True:
            _fail("SOURCE_OFFICIAL_REVIEW_MISSING", f"official_reviews.{source_id}.official", "official status must be explicitly true")
        try:
            review = OfficialReview.model_validate(review_input.get("official_review"), strict=True)
        except (ValidationError, TypeError) as error:
            _fail("SOURCE_OFFICIAL_REVIEW_MISSING", f"official_reviews.{source_id}.official_review", str(error))

        snapshot = _snapshot_for_document(run_dir, document, document_field)
        mapped = {
            "external_id": source_id,
            "url": url,
            "official": True,
            "official_review": review.model_dump(mode="json"),
            "title": source["title"],
            "published_at": source["published_at"],
            "snapshot": snapshot,
        }
        try:
            CheckpointSource.model_validate(mapped, strict=True)
        except (ValidationError, TypeError) as error:
            _fail("SOURCE_NOT_ALLOWLISTABLE", field, str(error))
        rows.append(mapped)
        source_ids.add(source_id)
        evidence_urls[source_id] = original_url or url

    unknown_reviews = set(official_reviews) - source_ids
    if unknown_reviews:
        _fail("SOURCE_OFFICIAL_REVIEW_MISSING", "official_reviews", f"reviews refer to unknown sources: {sorted(unknown_reviews)!r}")
    return rows, text_by_id, evidence_urls


def _map_facts(
    facts_value: dict[str, Any],
    source_ids: set[str],
    source_texts: dict[str, str],
    evidence_urls: dict[str, str],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        facts_source = FactsSource.model_validate({
            "schema_version": facts_value.get("schema_version"),
            "policy_version": facts_value.get("policy_version"),
            "summary": facts_value.get("summary"),
        }, strict=True).model_dump(mode="json")
    except (ValidationError, TypeError) as error:
        _fail("FACTS_MAPPING_INVALID", "facts.json", str(error))

    native_claims = facts_value.get("claims")
    if not isinstance(native_claims, list) or not native_claims:
        _fail("FACTS_MAPPING_INVALID", "facts.json.claims", "at least one native claim is required")
    claims: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    claim_ids: set[str] = set()
    evidence_ids: set[str] = set()
    for claim_index, native_claim in enumerate(native_claims):
        claim_path = f"facts.json.claims[{claim_index}]"
        if not isinstance(native_claim, dict):
            _fail("FACTS_MAPPING_INVALID", claim_path, "expected a claim object")
        native_id = native_claim.get("claim_id")
        if not isinstance(native_id, str) or not native_id.strip() or native_id in claim_ids:
            _fail("FACTS_MAPPING_INVALID", f"{claim_path}.claim_id", "claim IDs must be unique non-empty strings")
        claim_ids.add(native_id)
        source_refs = native_claim.get("source_ids")
        if not isinstance(source_refs, list) or not source_refs or any(not isinstance(item, str) for item in source_refs):
            _fail("FACTS_MAPPING_INVALID", f"{claim_path}.source_ids", "claim source IDs are required")
        missing_sources = [source_id for source_id in source_refs if source_id not in source_ids]
        if missing_sources:
            _fail("CROSS_RUN_REFERENCE", f"{claim_path}.source_ids", f"unknown source IDs: {missing_sources!r}")
        native_evidence = native_claim.get("evidence")
        if not isinstance(native_evidence, list) or not native_evidence:
            _fail("FACTS_MAPPING_INVALID", f"{claim_path}.evidence", "each native claim must have evidence rows")

        claim_evidence_ids: list[str] = []
        for evidence_index, native_evidence_row in enumerate(native_evidence, start=1):
            evidence_path = f"{claim_path}.evidence[{evidence_index - 1}]"
            if not isinstance(native_evidence_row, dict):
                _fail("FACTS_MAPPING_INVALID", evidence_path, "expected an evidence object")
            evidence_source_id = native_evidence_row.get("source_id")
            if not isinstance(evidence_source_id, str) or evidence_source_id not in source_ids:
                _fail("CROSS_RUN_REFERENCE", f"{evidence_path}.source_id", f"unknown source ID {evidence_source_id!r}")
            if evidence_source_id not in source_refs:
                _fail("CROSS_RUN_REFERENCE", f"{evidence_path}.source_id", "evidence source is not listed on its claim")
            evidence_text = native_evidence_row.get("evidence_text")
            source_text = source_texts[evidence_source_id]
            if not isinstance(evidence_text, str) or not evidence_text or evidence_text not in source_text:
                _fail("SOURCE_SNAPSHOT_MISMATCH", f"{evidence_path}.evidence_text", "exact evidence text is absent from the indexed source snapshot")
            document = native_evidence_row.get("original_url")
            if document != evidence_urls[evidence_source_id]:
                _fail("CROSS_RUN_REFERENCE", f"{evidence_path}.original_url", "evidence URL differs from its indexed source identity")
            evidence_id = f"{native_id}:evidence:{evidence_index:03d}"
            if evidence_id in evidence_ids:
                _fail("FACTS_MAPPING_INVALID", evidence_path, f"deterministic evidence ID collision: {evidence_id!r}")
            evidence_ids.add(evidence_id)
            claim_evidence_ids.append(evidence_id)
            mapped_evidence = {
                "external_id": evidence_id,
                "claim_ids": [native_id],
                "source_ids": [evidence_source_id],
                "relation": native_evidence_row.get("relation"),
                "evidence_text": evidence_text,
                "excerpt_anchor": evidence_text,
                "source_section": native_evidence_row.get("source_section"),
                "paragraph_locator": native_evidence_row.get("paragraph_locator"),
                "published_at": native_evidence_row.get("published_at"),
                "retrieved_at": native_evidence_row.get("retrieved_at"),
                "original_url": document,
            }
            try:
                CheckpointEvidence.model_validate(mapped_evidence, strict=True)
            except (ValidationError, TypeError) as error:
                _fail("FACTS_MAPPING_INVALID", evidence_path, str(error))
            evidence_rows.append(mapped_evidence)

        metadata_keys = ("domain", "risk_level", "script_usage")
        native_metadata = {key: native_claim[key] for key in metadata_keys if key in native_claim}
        mapped_claim = {
            "external_id": native_id,
            "proposition": native_claim.get("claim_text"),
            "classification": native_claim.get("claim_type"),
            "verification_status": native_claim.get("verification_status"),
            "rationale": native_claim.get("verification_reason"),
            "allowed_downstream": native_claim.get("allowed_downstream"),
            "source_ids": list(source_refs),
            "evidence_ids": claim_evidence_ids,
        }
        if native_metadata:
            mapped_claim["native_metadata"] = native_metadata
        claims.append(mapped_claim)

    # Complete claim references can only be checked after collecting all IDs.
    for index, claim in enumerate(claims):
        try:
            CheckpointClaim.model_validate(claim, strict=True)
        except (ValidationError, TypeError) as error:
            _fail("FACTS_MAPPING_INVALID", f"facts.json.claims[{index}]", str(error))
    return facts_source, claims, evidence_rows


def _map_angle(
    angle_value: dict[str, Any],
    angle_markdown: str,
    claim_ids: set[str],
    source_run_id: str,
) -> dict[str, Any]:
    artifact_run_id = angle_value.get("run_id")
    if artifact_run_id is not None and artifact_run_id != source_run_id:
        _fail("CHECKPOINT_IDENTITY_MISMATCH", "angles.json.run_id", "angle artifact belongs to a different source run")
    markers = _SELECTED_ANGLE_MARKER.findall(angle_markdown)
    if len(markers) != 1:
        _fail("ANGLE_INVALID", "angle.md", "exactly one selected_angle_id marker is required")
    selected_id = markers[0]
    candidates = angle_value.get("candidates")
    if not isinstance(candidates, list):
        _fail("ANGLE_INVALID", "angles.json.candidates", "expected a candidate array")
    matches = [candidate for candidate in candidates if isinstance(candidate, dict) and candidate.get("angle_id") == selected_id]
    if len(matches) != 1:
        _fail("ANGLE_INVALID", "angles.json.candidates", "selected angle must identify exactly one candidate")
    candidate = matches[0]

    required_candidate_fields = set(CheckpointAngle.model_fields) - {"external_id"} | {"angle_id"}
    missing = sorted(required_candidate_fields - set(candidate))
    if missing:
        _fail("ANGLE_FORMAL_FIELDS_MISSING", "angles.json.candidates", f"selected candidate is missing: {', '.join(missing)}")
    unknown = sorted(set(candidate) - required_candidate_fields)
    if unknown:
        _fail("ANGLE_INVALID", "angles.json.candidates", f"selected candidate has unknown fields: {', '.join(unknown)}")
    try:
        validated_candidate = AngleCandidate.model_validate(candidate, strict=True)
    except ValidationError as error:
        _fail("ANGLE_INVALID", "angles.json.candidates", str(error))
    if validated_candidate.eligibility != "eligible":
        _fail("ANGLE_NOT_ELIGIBLE", "angles.json.candidates", "the selected candidate is not eligible")
    supporting_claims = candidate.get("supporting_claim_ids")
    if not isinstance(supporting_claims, list) or any(not isinstance(item, str) or item not in claim_ids for item in supporting_claims):
        _fail("CROSS_RUN_REFERENCE", "angles.json.candidates.supporting_claim_ids", "selected angle references an unknown claim")
    mapped = {key: value for key, value in candidate.items() if key != "angle_id"}
    mapped["external_id"] = selected_id
    try:
        CheckpointAngle.model_validate(mapped, strict=True)
    except (ValidationError, TypeError) as error:
        _fail("ANGLE_INVALID", "angle", str(error))
    return mapped


def _script_sentence_offsets(script_text: str, sentences: list[dict[str, Any]]) -> list[tuple[int, int]]:
    try:
        raw = script_text.encode("utf-8")
    except UnicodeEncodeError as error:
        _fail("SCRIPT_OFFSETS_INVALID", "script.md", f"text cannot be encoded as UTF-8: {error}")
    cursor = 0
    offsets: list[tuple[int, int]] = []
    for index, sentence in enumerate(sentences):
        sentence_text = sentence.get("text")
        if not isinstance(sentence_text, str) or not sentence_text:
            _fail("SCRIPT_MAPPING_INVALID", f"script.json.sentences[{index}].text", "sentence text must be non-empty")
        try:
            encoded = sentence_text.encode("utf-8")
        except UnicodeEncodeError as error:
            _fail("SCRIPT_OFFSETS_INVALID", f"script.json.sentences[{index}].text", f"sentence cannot be encoded as UTF-8: {error}")
        start = raw.find(encoded, cursor)
        if start < 0:
            _fail("SCRIPT_OFFSETS_INVALID", f"script.json.sentences[{index}].text", "sentence text is absent or out of order in script.md")
        gap = raw[cursor:start]
        try:
            gap_text = gap.decode("utf-8")
        except UnicodeDecodeError:
            _fail("SCRIPT_OFFSETS_INVALID", f"script.md[{cursor}:{start}]", "text gap is not valid UTF-8")
        if gap_text and not gap_text.isspace():
            _fail("SCRIPT_OFFSETS_INVALID", f"script.md[{cursor}:{start}]", "uncovered non-whitespace text occurs between sentences")
        end = start + len(encoded)
        if raw[start:end].decode("utf-8") != sentence_text:
            _fail("SCRIPT_OFFSETS_INVALID", f"script.json.sentences[{index}].text", "UTF-8 byte slice differs from native sentence text")
        offsets.append((start, end))
        cursor = end
    try:
        tail = raw[cursor:].decode("utf-8")
    except UnicodeDecodeError:
        _fail("SCRIPT_OFFSETS_INVALID", f"script.md[{cursor}:]", "trailing text is not valid UTF-8")
    if tail and not tail.isspace():
        _fail("SCRIPT_OFFSETS_INVALID", f"script.md[{cursor}:]", "uncovered non-whitespace text remains after the last sentence")
    return offsets


def _map_script(
    script_value: dict[str, Any],
    script_text: str,
    angle_id: str,
    claim_ids: set[str],
) -> dict[str, Any]:
    script_angle_id = script_value.get("angle_id")
    if script_angle_id != angle_id:
        _fail("CHECKPOINT_IDENTITY_MISMATCH", "script.json.angle_id", "script does not reference the angle selected in angle.md")
    native_sentences = script_value.get("sentences")
    if not isinstance(native_sentences, list) or not native_sentences:
        _fail("SCRIPT_MAPPING_INVALID", "script.json.sentences", "at least one native script sentence is required")
    sentence_ids: set[str] = set()
    for index, sentence in enumerate(native_sentences):
        if not isinstance(sentence, dict):
            _fail("SCRIPT_MAPPING_INVALID", f"script.json.sentences[{index}]", "expected a sentence object")
        sentence_id = sentence.get("sentence_id")
        if not isinstance(sentence_id, str) or not sentence_id.strip() or sentence_id in sentence_ids:
            _fail("SCRIPT_MAPPING_INVALID", f"script.json.sentences[{index}].sentence_id", "sentence IDs must be unique non-empty strings")
        sentence_ids.add(sentence_id)
        sentence_claims = sentence.get("claim_ids")
        if not isinstance(sentence_claims, list) or any(not isinstance(item, str) or item not in claim_ids for item in sentence_claims):
            _fail("CROSS_RUN_REFERENCE", f"script.json.sentences[{index}].claim_ids", "script references an unknown claim")

    offsets = _script_sentence_offsets(script_text, native_sentences)
    mapped_sentences: list[dict[str, Any]] = []
    for sentence, (byte_start, byte_end) in zip(native_sentences, offsets, strict=True):
        mapped_sentences.append({
            "external_id": sentence["sentence_id"],
            "section": sentence.get("section"),
            "sentence_type": sentence.get("sentence_type"),
            "text": sentence["text"],
            "claim_ids": list(sentence["claim_ids"]),
            "byte_start": byte_start,
            "byte_end": byte_end,
            "evidence_ids": [],
        })
    mapped = {
        "external_id": script_value.get("script_id"),
        "angle_external_id": script_angle_id,
        "title": script_value.get("title"),
        "target_duration_seconds": script_value.get("target_duration_seconds"),
        "speaking_rate_chars_per_second": script_value.get("speaking_rate_chars_per_second"),
        "spoken_character_count": script_value.get("spoken_character_count"),
        "estimated_duration_seconds": script_value.get("estimated_duration_seconds"),
        "text": script_text,
        "sentences": mapped_sentences,
    }
    try:
        CheckpointScript.model_validate(mapped, strict=True)
    except (ValidationError, TypeError) as error:
        _fail("SCRIPT_MAPPING_INVALID", "script.json", str(error))
    return mapped


def _confirm_source_inputs_current(
    run_dir: Path,
    run_id: str,
    case_id: str,
    expected_hashes: dict[str, str],
    expected_source_texts: dict[str, str],
    expected_research: str,
    expected_angle_markdown: str,
    expected_script_markdown: str,
) -> None:
    """Recheck registry state and exact text after assembling the in-memory body."""
    try:
        latest_manifest = _load_manifest(run_dir)
    except ArtifactConflictError as error:
        _fail("AUTHORING_ARTIFACT_STALE", "run.json", str(error))
    if latest_manifest.run_id != run_id:
        _fail("CHECKPOINT_IDENTITY_MISMATCH", "run.json.run_id", "run identity changed during draft assembly")
    latest_registry = ArtifactRegistry(run_dir, latest_manifest)
    latest_index = _read_safe_index(run_dir)
    _validate_registered_inputs(run_dir, latest_manifest, latest_registry)
    try:
        latest_binding = _read_registered_binding(
            latest_registry,
            run_dir / BINDING_FILENAME,
            manifest_had_binding_state=True,
        )
    except ArtifactConflictError as error:
        _fail("CASE_BINDING_STALE", BINDING_FILENAME, str(error))
    if latest_binding is None or latest_binding.run_id != run_id or latest_binding.case_id != case_id:
        _fail("CHECKPOINT_IDENTITY_MISMATCH", BINDING_FILENAME, "run/case binding changed during draft assembly")
    if _protected_hashes(latest_manifest) != expected_hashes:
        _fail("UPSTREAM_ARTIFACT_HASH_MISMATCH", "protected_artifact_hashes", "protected artifact hashes changed during draft assembly")
    _, latest_source_texts = _indexed_source_rows(run_dir, latest_index)
    if latest_source_texts != expected_source_texts:
        _fail("SOURCE_SNAPSHOT_MISMATCH", "source_documents/index.json", "indexed source text changed during draft assembly")
    for artifact, expected in (
        ("research.md", expected_research),
        ("angle.md", expected_angle_markdown),
        ("script.md", expected_script_markdown),
    ):
        if _exact_text(run_dir / artifact, artifact) != expected:
            _fail("AUTHORING_ARTIFACT_STALE", artifact, "exact artifact text changed during draft assembly")


def build_checkpoint_draft(
    run_id: str,
    case_id: str,
    checkpoint_id: str,
    runs_dir: Path,
    official_reviews: Mapping[str, Any],
) -> CheckpointDraft:
    """Build a deterministic, body-only V2 draft from one explicitly bound run."""
    _safe_component(case_id, "case_id")
    _safe_component(checkpoint_id, "checkpoint_id")
    try:
        run_dir = resolve_run_dir(Path(runs_dir), run_id)
    except RunPathError as error:
        _fail("AUTHORING_ARTIFACT_MISSING", "source_run_id", str(error))
    try:
        manifest = _load_manifest(run_dir)
    except ArtifactConflictError as error:
        message = str(error)
        code = message.split(":", 1)[0]
        if code == "CASE_BINDING_MISSING":
            code = "AUTHORING_ARTIFACT_MISSING"
        _fail(code, "run.json", message)
    if manifest.run_id != run_id:
        _fail("CHECKPOINT_IDENTITY_MISMATCH", "run.json.run_id", "run manifest identity differs from the explicit source_run_id")
    if manifest.stages.get("checkpoint_import") and manifest.stages["checkpoint_import"].status == "succeeded":
        _fail("CHECKPOINT_IDENTITY_MISMATCH", "run.json.stages.checkpoint_import", "an imported run cannot be used as native authoring input")
    registry = ArtifactRegistry(run_dir, manifest)
    index_value = _read_safe_index(run_dir)
    _validate_registered_inputs(run_dir, manifest, registry)
    try:
        binding = CheckpointAuthoringBindingV1.model_validate(read_json(run_dir / BINDING_FILENAME), strict=True)
    except (OSError, ValueError, ValidationError) as error:
        _fail("CASE_BINDING_STALE", BINDING_FILENAME, str(error))
    if binding.run_id != run_id or binding.case_id != case_id:
        _fail("CHECKPOINT_IDENTITY_MISMATCH", BINDING_FILENAME, "registered run/case binding differs from explicit builder inputs")

    sources_value = _json_object(registry, "sources.json")
    facts_value = _json_object(registry, "facts.json")
    angles_value = _json_object(registry, "angles.json")
    script_value = _json_object(registry, "script.json")
    if facts_value.get("run_id") is not None and facts_value["run_id"] != run_id:
        _fail("CHECKPOINT_IDENTITY_MISMATCH", "facts.json.run_id", "facts artifact belongs to a different source run")
    if angles_value.get("run_id") is not None and angles_value["run_id"] != run_id:
        _fail("CHECKPOINT_IDENTITY_MISMATCH", "angles.json.run_id", "angle artifact belongs to a different source run")

    source_rows, source_texts, evidence_urls = _map_sources(run_dir, sources_value, index_value, official_reviews)
    source_ids = {row["external_id"] for row in source_rows}
    facts_source, claims, evidence = _map_facts(facts_value, source_ids, source_texts, evidence_urls)
    claim_ids = {claim["external_id"] for claim in claims}
    research_text = _exact_text(run_dir / "research.md", "research.md")
    angle_markdown = _exact_text(run_dir / "angle.md", "angle.md")
    angle = _map_angle(angles_value, angle_markdown, claim_ids, run_id)
    script_text = _exact_text(run_dir / "script.md", "script.md")
    script = _map_script(script_value, script_text, angle["external_id"], claim_ids)
    body = {
        "checkpoint_schema_version": "approved-checkpoint/2.0",
        "checkpoint_id": checkpoint_id,
        "case_id": case_id,
        "source_run_id": run_id,
        "protected_artifact_hashes": _protected_hashes(manifest),
        "facts_source": facts_source,
        "research": {"content": research_text},
        "sources": source_rows,
        "claims": claims,
        "evidence": evidence,
        "angle": angle,
        "script": script,
    }
    try:
        draft = CheckpointDraft.model_validate(body, strict=True)
    except (ValidationError, TypeError) as error:
        _fail("CHECKPOINT_CONTRACT_INVALID", "checkpoint", str(error))
    try:
        canonical_body_sha256(draft.model_dump(mode="python", by_alias=True))
    except (TypeError, ValueError) as error:
        _fail("CHECKPOINT_CONTRACT_INVALID", "checkpoint", f"body cannot be canonicalized: {error}")
    _confirm_source_inputs_current(
        run_dir,
        run_id,
        case_id,
        draft.protected_artifact_hashes.model_dump(mode="json", by_alias=True),
        source_texts,
        research_text,
        angle_markdown,
        script_text,
    )
    return draft


def validate_checkpoint_draft(draft: CheckpointDraft | Mapping[str, Any], runs_dir: Path) -> ValidationReport:
    """Purely validate a body-only draft against the current source-run proof."""
    try:
        parsed = draft if isinstance(draft, CheckpointDraft) else CheckpointDraft.model_validate(draft, strict=True)
    except (ValidationError, TypeError) as error:
        issue = ValidationIssue("CHECKPOINT_CONTRACT_INVALID", "checkpoint", str(error))
        return ValidationReport(False, None, (issue,))
    body = parsed.model_dump(mode="python", by_alias=True)
    try:
        digest = canonical_body_sha256(body)
    except (TypeError, ValueError) as error:
        issue = ValidationIssue("CHECKPOINT_CONTRACT_INVALID", "checkpoint", f"body cannot be canonicalized: {error}")
        return ValidationReport(False, None, (issue,))
    reviews = {
        source.external_id: {
            "official": True,
            "official_review": source.official_review.model_dump(mode="json"),
        }
        for source in parsed.sources
    }
    try:
        current = build_checkpoint_draft(
            parsed.source_run_id,
            parsed.case_id,
            parsed.checkpoint_id,
            runs_dir,
            reviews,
        )
    except CheckpointAuthoringError as error:
        issue = ValidationIssue(error.code, error.path, str(error))
        return ValidationReport(False, None, (issue,))
    current_body = current.model_dump(mode="python", by_alias=True)
    if canonical_json_bytes(body) != canonical_json_bytes(current_body):
        protected_hashes_changed = (
            parsed.protected_artifact_hashes.model_dump(mode="json", by_alias=True)
            != current.protected_artifact_hashes.model_dump(mode="json", by_alias=True)
        )
        issue = ValidationIssue(
            "UPSTREAM_ARTIFACT_HASH_MISMATCH" if protected_hashes_changed else "CHECKPOINT_DRAFT_MISMATCH",
            "checkpoint",
            "draft body differs from deterministic mapping of the currently validated source-run artifacts",
        )
        return ValidationReport(False, None, (issue,))
    return ValidationReport(True, digest, ())


def approve_checkpoint(
    draft: CheckpointDraft | Mapping[str, Any],
    validation: ValidationReport,
    *,
    reviewer: str,
    expected_body_sha256: str,
    approved_at: str | None = None,
) -> CheckpointApproval:
    """Create an explicit approval bound to the exact validated V2 body."""
    try:
        parsed = draft if isinstance(draft, CheckpointDraft) else CheckpointDraft.model_validate(draft, strict=True)
    except (ValidationError, TypeError) as error:
        _fail("CHECKPOINT_NOT_VALIDATED", "checkpoint", f"draft does not satisfy the strict V2 contract: {error}")

    if (
        not isinstance(validation, ValidationReport)
        or validation.passed is not True
        or bool(validation.issues)
    ):
        _fail("CHECKPOINT_NOT_VALIDATED", "validation", "a passing validate_checkpoint_draft report is required")

    body = parsed.model_dump(mode="python", by_alias=True)
    try:
        current_digest = canonical_body_sha256(body)
    except (TypeError, ValueError) as error:
        _fail("CHECKPOINT_CONTRACT_INVALID", "checkpoint", f"body cannot be canonicalized: {error}")

    digest_pattern = re.compile(r"^[0-9a-f]{64}$")
    if (
        not isinstance(expected_body_sha256, str)
        or digest_pattern.fullmatch(expected_body_sha256) is None
        or not isinstance(validation.body_sha256, str)
        or digest_pattern.fullmatch(validation.body_sha256) is None
        or validation.body_sha256 != current_digest
        or expected_body_sha256 != current_digest
    ):
        _fail(
            "APPROVAL_BODY_HASH_MISMATCH",
            "approval.body_sha256",
            "expected digest, validation report, and current canonical draft body must match",
        )

    timestamp = approved_at
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        return CheckpointApproval.model_validate(
            {
                "status": "approved",
                "reviewer": reviewer,
                "approved_at": timestamp,
                "body_sha256": current_digest,
            },
            strict=True,
        )
    except (ValidationError, TypeError) as error:
        _fail("CHECKPOINT_NOT_APPROVED", "approval", f"explicit approval metadata is invalid: {error}")


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is not allowed: {value}")


def _existing_envelope_matches(path: Path, expected_canonical: bytes) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    try:
        value = json.loads(
            path.read_bytes().decode("utf-8"),
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
        )
        parsed = parse_approved_checkpoint_v2(value)
        existing = parsed.model_dump(mode="json", by_alias=True)
        return canonical_json_bytes(existing) == expected_canonical
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, ValidationError):
        return False


def _seal_directories(repository_root: Path, case_id: str) -> tuple[Path, Path]:
    root = repository_root.resolve(strict=True)
    if not root.is_dir():
        _fail("CHECKPOINT_SEAL_FAILED", str(repository_root), "repository root must be an existing directory")
    cases_dir = root / "cases"
    case_dir = cases_dir / case_id
    checkpoint_dir = case_dir / "approved-checkpoints"
    for directory in (cases_dir, case_dir, checkpoint_dir):
        try:
            if directory.is_symlink():
                _fail("UNSAFE_SEAL_PATH", str(directory), "seal path components must not be symlinks")
            directory.mkdir(exist_ok=True)
            resolved = directory.resolve(strict=True)
        except CheckpointAuthoringError:
            raise
        except OSError as error:
            _fail("CHECKPOINT_SEAL_FAILED", str(directory), f"cannot create sealed checkpoint directory: {error}")
        if not resolved.is_relative_to(root):
            _fail("UNSAFE_SEAL_PATH", str(directory), "sealed checkpoint path escapes repository root")
    return root, checkpoint_dir


def seal_checkpoint(
    draft: CheckpointDraft | Mapping[str, Any],
    approval: CheckpointApproval | Mapping[str, Any],
    repository_root: Path,
    *,
    runs_dir: Path,
) -> Path:
    """Revalidate, then atomically publish the approved V2 envelope once."""
    try:
        parsed_draft = draft if isinstance(draft, CheckpointDraft) else CheckpointDraft.model_validate(draft, strict=True)
    except (ValidationError, TypeError) as error:
        _fail("CHECKPOINT_CONTRACT_INVALID", "checkpoint", str(error))
    _safe_component(parsed_draft.case_id, "case_id")
    _safe_component(parsed_draft.checkpoint_id, "checkpoint_id")

    try:
        approval_value = approval.model_dump(mode="json", by_alias=True) if isinstance(approval, CheckpointApproval) else approval
        parsed_approval = CheckpointApproval.model_validate(approval_value, strict=True)
    except (ValidationError, TypeError, AttributeError) as error:
        _fail("CHECKPOINT_NOT_APPROVED", "approval", f"approval record is invalid: {error}")

    body = parsed_draft.model_dump(mode="json", by_alias=True)
    envelope = {**body, "approval": parsed_approval.model_dump(mode="json", by_alias=True)}
    try:
        digest = canonical_body_sha256(envelope)
        canonical_envelope = canonical_json_bytes(envelope)
    except (TypeError, ValueError) as error:
        _fail("CHECKPOINT_CONTRACT_INVALID", "checkpoint", f"envelope cannot be canonicalized: {error}")
    if parsed_approval.body_sha256 != digest:
        _fail(
            "APPROVAL_BODY_HASH_MISMATCH",
            "approval.body_sha256",
            "approval is not bound to the current canonical draft body",
        )
    try:
        parse_approved_checkpoint_v2(envelope)
    except (ValidationError, TypeError, ValueError) as error:
        _fail("CHECKPOINT_NOT_APPROVED", "checkpoint", f"strict V2 approval preflight failed: {error}")

    try:
        root = Path(repository_root).resolve(strict=True)
    except OSError as error:
        _fail("CHECKPOINT_SEAL_FAILED", str(repository_root), f"repository root is unavailable: {error}")
    report = validate_checkpoint_draft(parsed_draft, Path(runs_dir))
    if not report.passed:
        issue = report.issues[0] if report.issues else ValidationIssue(
            "CHECKPOINT_NOT_VALIDATED", "checkpoint", "final source-run validation failed"
        )
        _fail(issue.code, issue.path, f"final pre-seal validation failed: {issue.message}")
    if report.body_sha256 != digest:
        _fail(
            "APPROVAL_BODY_HASH_MISMATCH",
            "approval.body_sha256",
            "final pre-seal validation did not confirm the approved body digest",
        )

    root, checkpoint_dir = _seal_directories(root, parsed_draft.case_id)
    target = checkpoint_dir / f"{parsed_draft.checkpoint_id}.json"
    if target.is_symlink():
        _fail("CHECKPOINT_WRITE_ONCE_CONFLICT", str(target), "existing sealed path is not a regular checkpoint file")
    if target.exists():
        if _existing_envelope_matches(target, canonical_envelope):
            return target
        _fail(
            "CHECKPOINT_WRITE_ONCE_CONFLICT",
            str(target),
            "existing checkpoint body or approval record differs; sealed files are write-once",
        )

    serialized = json.dumps(envelope, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=checkpoint_dir,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
            temporary_path = Path(handle.name)
        try:
            os.link(temporary_path, target)
        except FileExistsError as error:
            if _existing_envelope_matches(target, canonical_envelope):
                return target
            raise CheckpointAuthoringError(
                "CHECKPOINT_WRITE_ONCE_CONFLICT",
                str(target),
                "existing checkpoint body or approval record differs; sealed files are write-once",
            ) from error
    except CheckpointAuthoringError:
        raise
    except OSError as error:
        if target.exists():
            if _existing_envelope_matches(target, canonical_envelope):
                return target
            _fail(
                "CHECKPOINT_WRITE_ONCE_CONFLICT",
                str(target),
                "another value already occupies the write-once sealed path",
            )
        _fail("CHECKPOINT_SEAL_FAILED", str(target), f"atomic no-replace publication failed: {error}")
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
    return target
