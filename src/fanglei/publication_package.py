"""Offline publication preparation from an immutable, already approved Final."""
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from fanglei.artifact_registry import ArtifactRegistry
from fanglei.artifacts import read_json
from fanglei.errors import ArtifactConflictError
from fanglei.final_render import ArtifactBinding, FinalRenderConfiguration, _path
from fanglei.final_video_qa import (
    _registry_candidate, _current_qa, _implementation_status,
    validate_existing_human_final_video_approval,
)
from fanglei.preview_composition import apply_presentation_mode


PACKAGE_DIRECTORY = "renderer_project_publication"
PACKAGE_ARTIFACT = "publication_renderer_package.json"


class PublicationRendererPackageV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["publication-renderer-package/1.0"] = "publication-renderer-package/1.0"
    run_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    status: Literal["ready_for_publication_render"] = "ready_for_publication_render"
    presentation_mode: Literal["publication"] = "publication"
    allowed_difference: Literal["review_overlays_removed"] = "review_overlays_removed"
    accepted_candidate: ArtifactBinding
    accepted_media: ArtifactBinding
    human_final_approval: ArtifactBinding
    accepted_qa: ArtifactBinding
    human_final_approval_qa_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    qa_implementation_status: Literal["current", "superseded", "unknown"]
    final_render_request: ArtifactBinding
    source_renderer_package: ArtifactBinding
    renderer_package: ArtifactBinding
    timeline: ArtifactBinding
    visual_bundle: ArtifactBinding
    subtitle: ArtifactBinding
    playback_subtitle: ArtifactBinding | None
    audio: ArtifactBinding
    storyboard: ArtifactBinding
    script: ArtifactBinding
    render_configuration: FinalRenderConfiguration
    dependency_hashes: dict[str, str]


def _inputs(run_dir):
    registry, candidate, request, _ = _registry_candidate(Path(run_dir).resolve())
    review = validate_existing_human_final_video_approval(registry.run_dir)
    registry = ArtifactRegistry(registry.run_dir, registry.manifest,
        playback_preview_mode=True, final_render_mode=True, publication_package_mode=True)
    dependencies = {}
    for name in registry.graph[PACKAGE_DIRECTORY][1]:
        registry.validate(name)
        dependencies[name] = registry.manifest.artifacts[name].content_hash
    qa_names = [name for name in registry.manifest.artifacts["human_final_video_review.json"].dependencies
                if name == "final_video_qa.json" or name.startswith("final_video_qa_attempt_")]
    qa_name = qa_names[0]  # exact binding already checked by the existing-approval validator
    qa = _current_qa(registry, qa_name)
    return registry, candidate, request, review, qa_name, qa, dependencies


def _files(registry, request):
    source = _path(registry, "renderer_project_final")
    files = {}
    for asset in sorted(source.rglob("*")):
        if not asset.is_file():
            continue
        try:
            asset.resolve().relative_to(source.resolve())
        except ValueError as error:
            raise ValueError("PUBLICATION_PACKAGE_PATH_ESCAPE") from error
        files[asset.relative_to(source).as_posix()] = asset.read_bytes()
    entry = request.render_configuration.entry
    if entry not in files:
        raise ValueError("PUBLICATION_ENTRY_MISSING")
    # Decode/encode without universal-newline translation: only overlay bytes differ.
    files[entry] = apply_presentation_mode(files[entry].decode("utf-8"), "publication").encode("utf-8")
    return files


def _manifest(registry, candidate, request, review, qa_name, qa, dependencies, package_sha):
    binding = lambda name: ArtifactBinding(path=name, sha256=registry.manifest.artifacts[name].content_hash)
    return PublicationRendererPackageV1(
        run_id=request.run_id, case_id=request.case_id,
        accepted_candidate=binding("final_video_candidate.json"), accepted_media=candidate.media,
        human_final_approval=binding("human_final_video_review.json"), accepted_qa=binding(qa_name),
        human_final_approval_qa_sha256=review.qa_sha256,
        qa_implementation_status=_implementation_status(qa),
        final_render_request=binding("final_render_request.json"),
        source_renderer_package=binding("renderer_project_final"),
        renderer_package=ArtifactBinding(path=PACKAGE_DIRECTORY, sha256=package_sha),
        timeline=request.timeline, visual_bundle=request.visual_bundle, subtitle=request.subtitle,
        playback_subtitle=request.playback_subtitle, audio=request.audio,
        storyboard=request.storyboard, script=request.script,
        render_configuration=request.render_configuration, dependency_hashes=dependencies,
    )


def prepare_publication_renderer_package(
    run_dir: Path, *, presentation_mode: Literal["publication"],
    expected_candidate_sha256: str, expected_approval_sha256: str,
) -> Path:
    """Prepare only; no render, publication QA, human approval or upload is implied."""
    if presentation_mode != "publication":
        raise ValueError("PUBLICATION_PRESENTATION_MODE_REQUIRED")
    registry, candidate, request, review, qa_name, qa, deps = _inputs(run_dir)
    if (expected_candidate_sha256 != registry.manifest.artifacts["final_video_candidate.json"].content_hash
        or expected_approval_sha256 != registry.manifest.artifacts["human_final_video_review.json"].content_hash):
        raise ValueError("PUBLICATION_EXPECTED_HASH_MISMATCH")
    for name in (PACKAGE_DIRECTORY, PACKAGE_ARTIFACT):
        if _path(registry, name).exists() or registry.manifest.artifacts[name].status != "missing":
            raise ArtifactConflictError("PUBLICATION_PACKAGE_ALREADY_EXISTS")
    files = _files(registry, request)
    registry.write_directory(PACKAGE_DIRECTORY, files, "publication_package")
    manifest = _manifest(registry, candidate, request, review, qa_name, qa, deps,
                         registry.manifest.artifacts[PACKAGE_DIRECTORY].content_hash)
    path = registry.write_json(PACKAGE_ARTIFACT, manifest.model_dump(mode="json"), "publication_package")
    registry.save_manifest()
    return path


def validate_publication_renderer_package(run_dir: Path) -> PublicationRendererPackageV1:
    """Read-only validation of bindings and the exact permitted package transformation."""
    registry, candidate, request, review, qa_name, qa, deps = _inputs(run_dir)
    registry.validate(PACKAGE_ARTIFACT)
    manifest = PublicationRendererPackageV1.model_validate(read_json(_path(registry, PACKAGE_ARTIFACT)))
    expected = _manifest(registry, candidate, request, review, qa_name, qa, deps,
                         registry.manifest.artifacts[PACKAGE_DIRECTORY].content_hash)
    # Implementation status is an observation at preparation time, not a content dependency.
    expected.qa_implementation_status = manifest.qa_implementation_status
    if manifest != expected:
        raise ValueError("PUBLICATION_PACKAGE_BINDING_MISMATCH")
    package = _path(registry, PACKAGE_DIRECTORY)
    actual = {}
    for asset in package.rglob("*"):
        if asset.is_file():
            asset.resolve().relative_to(package.resolve())
            actual[asset.relative_to(package).as_posix()] = asset.read_bytes()
    if actual != _files(registry, request):
        raise ValueError("PUBLICATION_PACKAGE_UNAUTHORIZED_DIFFERENCE")
    return manifest
