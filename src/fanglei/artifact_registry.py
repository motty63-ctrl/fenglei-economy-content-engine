"""Owner-enforced artifact registry with dependency invalidation."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import json
import shutil
import tempfile

from fanglei.artifacts import (
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_text,
    read_json,
    sha256_bytes,
    sha256_text,
)
from fanglei.errors import ArtifactConflictError
from fanglei.models import ArtifactState, RunManifest


ARTIFACT_GRAPH: dict[str, tuple[str, tuple[str, ...]]] = {
    "source.md": ("ingest", ()),
    "questions.json": ("analyze", ("source.md",)),
    "search_results.json": ("search", ("questions.json",)),
    "source_documents/index.json": ("source_fetch", ("search_results.json",)),
    "sources.json": ("source_selection", ("search_results.json", "source_documents/index.json")),
    "facts.json": ("factcheck", ("questions.json", "sources.json", "source_documents/index.json")),
    "research.md": ("research_synthesis", ("questions.json", "sources.json", "facts.json")),
    "angles.json": ("angle_generation", ("facts.json", "research.md", "questions.json", "source.md")),
    "angle.md": ("angle_selection", ("angles.json", "facts.json")),
    "script.json": ("script_generation", ("angle.md", "facts.json", "research.md", "source.md")),
    "script.md": ("script_render", ("script.json",)),
    "visual_beats.json": ("visual_planning", ("script.json", "facts.json", "angle.md")),
    "storyboard.json": ("storyboard_generation", ("visual_beats.json", "script.json", "facts.json")),
    "visual_plan.md": ("visual_plan_render", ("storyboard.json",)),
    "narration.json": ("narration_generation", ("script.json",)),
    "narration.txt": ("narration_generation", ("narration.json",)),
    "audio/narration.wav": ("audio_generation", ("narration.json", "narration.txt")),
    "audio/metadata.json": ("audio_generation", ("audio/narration.wav", "narration.json")),
    "audio/quality.json": ("audio_generation", ("audio/narration.wav", "audio/metadata.json")),
    "audio/review.json": ("voice_review", ("audio/narration.wav", "audio/quality.json")),
    "alignment_candidate.json": ("audio_alignment", ("narration.json", "audio/narration.wav", "audio/metadata.json", "audio/quality.json", "audio/review.json")),
    "alignment_review.json": ("alignment_review", ("alignment_candidate.json", "audio/review.json")),
    "alignment.json": ("audio_alignment", ("narration.json", "audio/narration.wav", "audio/metadata.json", "audio/quality.json", "audio/review.json")),
    "timeline.json": ("timeline_compilation", ("alignment.json", "storyboard.json", "visual_beats.json", "audio/metadata.json")),
    "renderer_project": ("nikola_adaptation", ("storyboard.json", "timeline.json")),
    "render_manifest.json": ("nikola_adaptation", ("storyboard.json", "timeline.json", "renderer_project")),
    "preflight_report.json": ("render_preflight", ("render_manifest.json", "renderer_project")),
    "render_qa.json": ("render_preflight", ("render_manifest.json", "renderer_project", "preflight_report.json")),
}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class ArtifactRegistry:
    def __init__(self, run_dir: Path, manifest: RunManifest):
        self.run_dir = Path(run_dir)
        self.manifest = manifest
        for name, (owner, dependencies) in ARTIFACT_GRAPH.items():
            self.manifest.artifacts.setdefault(
                name, ArtifactState(owner=owner, dependencies={dep: "" for dep in dependencies})
            )

    def _state(self, name: str) -> ArtifactState:
        if name not in ARTIFACT_GRAPH:
            raise ArtifactConflictError(f"Unknown artifact: {name}")
        return self.manifest.artifacts[name]

    def _validate_write(self, name: str, owner: str, force: bool) -> dict[str, str]:
        state = self._state(name)
        if state.owner != owner:
            raise ArtifactConflictError(f"Only owner stage {state.owner} may write {name}")
        if state.status == "valid" and not force:
            raise ArtifactConflictError(f"Artifact already valid: {name}; use --force")
        dependency_hashes: dict[str, str] = {}
        for dep in ARTIFACT_GRAPH[name][1]:
            dep_state = self._state(dep)
            if dep_state.status != "valid" or not dep_state.content_hash:
                raise ArtifactConflictError(f"Dependency {dep} is {dep_state.status}; rerun its owner stage")
            dependency_hashes[dep] = dep_state.content_hash
        return dependency_hashes

    def _invalidate_descendants(self, changed: str) -> None:
        queue = [changed]
        seen: set[str] = set()
        while queue:
            upstream = queue.pop(0)
            for name, (_, dependencies) in ARTIFACT_GRAPH.items():
                if upstream in dependencies and name not in seen:
                    seen.add(name)
                    state = self._state(name)
                    if state.status == "valid":
                        state.status = "stale"
                        state.updated_at = _now()
                    queue.append(name)

    def write_text(self, name: str, value: str, owner: str, force: bool = False) -> Path:
        deps = self._validate_write(name, owner, force)
        state = self._state(name)
        old_hash = state.content_hash
        path = self.run_dir / name
        atomic_write_text(path, value)
        timestamp = _now()
        state.status = "valid"
        state.content_hash = sha256_text(value)
        state.created_at = state.created_at or timestamp
        state.updated_at = timestamp
        state.dependencies = deps
        if old_hash and old_hash != state.content_hash:
            self._invalidate_descendants(name)
        return path

    def write_json(self, name: str, value: Any, owner: str, force: bool = False) -> Path:
        import json

        return self.write_text(name, json.dumps(value, ensure_ascii=False, indent=2) + "\n", owner, force)

    def write_bytes(self, name: str, value: bytes, owner: str, force: bool = False) -> Path:
        deps = self._validate_write(name, owner, force)
        state = self._state(name)
        old_hash = state.content_hash
        path = self.run_dir / name
        atomic_write_bytes(path, value)
        timestamp = _now()
        state.status = "valid"
        state.content_hash = sha256_bytes(value)
        state.created_at = state.created_at or timestamp
        state.updated_at = timestamp
        state.dependencies = deps
        if old_hash and old_hash != state.content_hash:
            self._invalidate_descendants(name)
        return path

    def write_directory(self, name: str, files: dict[str, str | bytes], owner: str,
                        force: bool = False) -> Path:
        deps = self._validate_write(name, owner, force)
        target = self.run_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))
        state = self._state(name)
        old_hash = state.content_hash
        try:
            expected: set[str] = set()
            for relative, value in files.items():
                relative_path = Path(relative)
                if relative_path.is_absolute() or ".." in relative_path.parts:
                    raise ArtifactConflictError(f"Unsafe renderer project path: {relative}")
                expected.add(relative_path.as_posix())
                path = temporary / relative_path
                if isinstance(value, bytes):
                    atomic_write_bytes(path, value)
                else:
                    atomic_write_text(path, value)
            if target.exists() and not target.is_dir():
                raise ArtifactConflictError(f"Directory artifact path is not a directory: {name}")
            # Mark replacement in progress. If any file operation fails, _execute persists
            # this stale state so a retry cannot silently reuse a partially updated tree.
            if state.status == "valid":
                state.status = "stale"
            target.mkdir(parents=True, exist_ok=True)
            for existing in sorted(item for item in target.rglob("*") if item.is_file()):
                if existing.relative_to(target).as_posix() not in expected:
                    _unlink_with_retry(existing)
            for staged in sorted(item for item in temporary.rglob("*") if item.is_file()):
                destination = target / staged.relative_to(temporary)
                atomic_write_bytes(destination, staged.read_bytes())
        finally:
            _rmtree_best_effort(temporary)
        timestamp = _now()
        state.status = "valid"
        state.content_hash = _directory_hash(target)
        state.created_at = state.created_at or timestamp
        state.updated_at = timestamp
        state.dependencies = deps
        if old_hash and old_hash != state.content_hash:
            self._invalidate_descendants(name)
        return target

    def read_json(self, name: str) -> dict[str, Any]:
        self.validate(name)
        state = self._state(name)
        path = self.run_dir / name
        return read_json(path)

    def validate(self, name: str) -> None:
        state = self._state(name)
        if state.status != "valid":
            raise ArtifactConflictError(f"Artifact {name} is {state.status}")
        path = self.run_dir / name
        text_value: str | None = None
        if path.is_dir():
            actual_hash = _directory_hash(path)
        elif path.is_file() and name == "audio/narration.wav":
            actual_hash = sha256_bytes(path.read_bytes())
        elif path.is_file():
            text_value = path.read_text(encoding="utf-8")
            actual_hash = sha256_text(text_value)
        else:
            actual_hash = None
        if actual_hash != state.content_hash:
            state.status = "stale"
            state.updated_at = _now()
            self._invalidate_descendants(name)
            raise ArtifactConflictError(f"Artifact {name} hash changed and is now stale")
        if name == "source_documents/index.json":
            for document in json.loads(text_value or "{}").get("documents", []):
                document_path = self.run_dir / document.get("path", "")
                if (
                    not document.get("path")
                    or not document_path.is_file()
                    or sha256_text(document_path.read_text(encoding="utf-8")) != document.get("content_hash")
                ):
                    state.status = "stale"
                    self._invalidate_descendants(name)
                    raise ArtifactConflictError(f"source document changed or missing: {document.get('path')}")
                for asset in document.get("files", []):
                    asset_path = self.run_dir / asset.get("path", "")
                    if (
                        not asset.get("path")
                        or not asset_path.is_file()
                        or sha256_bytes(asset_path.read_bytes()) != asset.get("content_hash")
                    ):
                        state.status = "stale"
                        self._invalidate_descendants(name)
                        raise ArtifactConflictError(f"source document changed or missing: {asset.get('path')}")
        for dependency, recorded_hash in state.dependencies.items():
            try:
                self.validate(dependency)
            except ArtifactConflictError as error:
                state.status = "stale"
                self._invalidate_descendants(name)
                raise ArtifactConflictError(f"Artifact {name} is stale because {error}") from error
            if self._state(dependency).content_hash != recorded_hash:
                state.status = "stale"
                self._invalidate_descendants(name)
                raise ArtifactConflictError(f"Artifact {name} dependency hash changed: {dependency}")

    def save_manifest(self) -> None:
        self.manifest.updated_at = _now()
        atomic_write_json(self.run_dir / "run.json", self.manifest.model_dump(mode="json"))


def _directory_hash(path: Path) -> str:
    rows: list[bytes] = []
    for file_path in sorted(item for item in path.rglob("*") if item.is_file()):
        relative = file_path.relative_to(path).as_posix().encode("utf-8")
        rows.append(relative + b"\0" + file_path.read_bytes())
    return sha256_bytes(b"\0".join(rows))


def _unlink_with_retry(path: Path) -> None:
    import time

    for attempt in range(5):
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(.02 * (attempt + 1))


def _rmtree_best_effort(path: Path) -> None:
    import time

    for attempt in range(5):
        try:
            shutil.rmtree(path, ignore_errors=False)
            return
        except (FileNotFoundError, PermissionError):
            if not path.exists():
                return
            if attempt < 4:
                time.sleep(.02 * (attempt + 1))
