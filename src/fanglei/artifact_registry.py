"""Owner-enforced artifact registry with dependency invalidation."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import json

from fanglei.artifacts import atomic_write_json, atomic_write_text, read_json, sha256_bytes, sha256_text
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
        value = path.read_text(encoding="utf-8") if path.is_file() else ""
        if not path.is_file() or sha256_text(value) != state.content_hash:
            state.status = "stale"
            state.updated_at = _now()
            self._invalidate_descendants(name)
            raise ArtifactConflictError(f"Artifact {name} hash changed and is now stale")
        if name == "source_documents/index.json":
            for document in json.loads(value).get("documents", []):
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
