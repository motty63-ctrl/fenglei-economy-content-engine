"""Strict, downstream-only framing contract for Research synthesis."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal, Mapping

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from fanglei.artifact_registry import ArtifactRegistry
from fanglei.artifacts import read_json
from fanglei.errors import ArtifactConflictError
from fanglei.models import RunManifest
from fanglei.paths import resolve_run_dir
from fanglei.source_contract import (
    AuthoritativePrimarySetPolicyV1,
    parse_sources_artifact,
)


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


NonBlank = Annotated[str, StringConstraints(strict=True, min_length=1), AfterValidator(_nonblank)]


def _aware_timestamp(value: str) -> str:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError("must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("must include a timezone")
    return value


AwareTimestamp = Annotated[NonBlank, AfterValidator(_aware_timestamp)]


class ResearchFocusV1(BaseModel):
    """Explicit content framing applied only after source and fact stages."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["research-focus/1.0"]
    run_id: NonBlank
    case_id: NonBlank
    primary_question: NonBlank
    subquestions: list[NonBlank] = Field(min_length=1)
    constraints: list[NonBlank] = Field(min_length=1)
    created_at: AwareTimestamp
    created_by: NonBlank


def write_research_focus(
    run_id: str,
    runs_dir: Path,
    focus: ResearchFocusV1 | Mapping[str, object],
    *,
    force: bool = False,
) -> Path:
    """Write a registered Research focus without invalidating acquisition artifacts.

    The caller supplies both identities in the focus body. The owner validates
    current source/fact artifacts and any authority-package binding before the
    focus can be written.
    """
    run_dir = resolve_run_dir(Path(runs_dir), run_id)
    manifest = RunManifest.model_validate(read_json(run_dir / "run.json"))
    if manifest.run_id != run_id:
        raise ArtifactConflictError("run manifest identity does not match the requested run")
    registry = ArtifactRegistry(run_dir, manifest, research_focus_mode=True)
    if registry.imported_checkpoint_mode or "research_focus.json" not in registry.graph:
        raise ArtifactConflictError("research focus cannot be authored for an imported checkpoint run")
    try:
        parsed = focus if isinstance(focus, ResearchFocusV1) else ResearchFocusV1.model_validate(focus)
    except Exception as error:
        raise ArtifactConflictError(f"invalid research-focus/1.0 contract: {error}") from error
    if parsed.run_id != run_id:
        raise ArtifactConflictError("research focus run_id does not match the active run")

    try:
        source_artifact = registry.read_json("sources.json")
        facts = registry.read_json("facts.json")
        parsed_sources = parse_sources_artifact(source_artifact)
    except Exception as error:
        registry.save_manifest()
        raise ArtifactConflictError(f"research focus requires current sources.json and facts.json: {error}") from error
    if facts.get("run_id") != run_id:
        raise ArtifactConflictError("facts.json run_id does not match the active run")
    if not isinstance(facts.get("claims"), list):
        raise ArtifactConflictError("facts.json must contain a claims list")
    if isinstance(getattr(parsed_sources, "source_policy", None), AuthoritativePrimarySetPolicyV1):
        if parsed_sources.package_admissibility != "admissible":
            raise ArtifactConflictError("research focus requires an admissible authority source package")
        if parsed_sources.source_policy.run_id != run_id or parsed_sources.source_policy.case_id != parsed.case_id:
            raise ArtifactConflictError("research focus run/case identity does not match the approved source package")

    artifact_path = run_dir / "research_focus.json"
    state = manifest.artifacts["research_focus.json"]
    if artifact_path.exists():
        if state.status == "missing" or not state.content_hash:
            raise ArtifactConflictError("existing research_focus.json is unregistered; refusing to overwrite")
        try:
            registry.validate("research_focus.json")
        except ArtifactConflictError:
            registry.save_manifest()
            raise
        existing = registry.read_json("research_focus.json")
        if existing == parsed.model_dump(mode="json"):
            return artifact_path
        if not force:
            raise ArtifactConflictError("research focus already exists; use force to replace through its owner")

    registry.write_json(
        "research_focus.json",
        parsed.model_dump(mode="json"),
        "research_focus",
        force=force,
    )
    registry.save_manifest()
    return artifact_path
