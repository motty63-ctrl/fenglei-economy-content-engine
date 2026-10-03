"""Offline, human-approved final export owners. No encoder or provider is invoked."""
from __future__ import annotations

from pathlib import Path, PurePosixPath
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from fanglei.artifact_registry import ArtifactRegistry
from fanglei.artifacts import read_json, sha256_bytes
from fanglei.errors import ArtifactConflictError
from fanglei.human_storyboard_recovery import canonical_json_sha256
from fanglei.models import RunManifest
from fanglei.playback_preview import HumanPreviewReviewV1
from fanglei.v05_models import TimelineDocument


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ArtifactBinding(_Contract):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("path")
    @classmethod
    def relative_path(cls, value):
        if ("\\" in value or ":" in value or PurePosixPath(value).is_absolute()
            or any(part in {"", ".", ".."} for part in value.split("/"))):
            raise ValueError("FINAL_RENDER_PATH_INVALID")
        return value


class FinalRenderConfiguration(_Contract):
    engine: Literal["hyperframes"]
    renderer_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    entry: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: int = Field(gt=0)
    duration_ms: int = Field(gt=0)
    frame_count: int = Field(gt=0)
    # Native MP4 export profile; bitrate/quality are inherited from the renderer.
    video_codec: Literal["h264"] = "h264"
    audio_codec: Literal["aac"] = "aac"
    quality_policy: Literal["renderer_default"] = "renderer_default"
    package_configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("entry")
    @classmethod
    def safe_entry(cls, value):
        return ArtifactBinding.relative_path(value)


class FinalRenderRequestV1(_Contract):
    schema_version: Literal["final-render-request/1.0"] = "final-render-request/1.0"
    run_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    preview_candidate_id: Literal[1, 2, 3]
    human_preview_approval: ArtifactBinding
    preview: ArtifactBinding
    timeline: ArtifactBinding
    visual_bundle: ArtifactBinding
    audio: ArtifactBinding
    storyboard: ArtifactBinding
    storyboard_canonical_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    script: ArtifactBinding
    subtitle: ArtifactBinding
    playback_subtitle: ArtifactBinding | None
    source_renderer_package: ArtifactBinding
    source_render_manifest: ArtifactBinding
    render_configuration: FinalRenderConfiguration
    render_configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dependency_hashes: dict[str, str]
    output_path: Literal["final.mp4"] = "final.mp4"
    output_intent: Literal["final_candidate"] = "final_candidate"
    preview_only: Literal[False] = False
    full_render_requested: Literal[True] = True

    @model_validator(mode="after")
    def bindings_are_consistent(self):
        bindings = (
            self.human_preview_approval, self.preview, self.timeline, self.visual_bundle,
            self.audio, self.storyboard, self.script, self.subtitle,
            self.source_renderer_package, self.source_render_manifest,
        ) + ((self.playback_subtitle,) if self.playback_subtitle else ())
        if any(self.dependency_hashes.get(item.path) != item.sha256 for item in bindings):
            raise ValueError("FINAL_RENDER_REQUEST_BINDING_MISMATCH")
        if any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in self.dependency_hashes.values()):
            raise ValueError("FINAL_RENDER_REQUEST_HASH_INVALID")
        if canonical_json_sha256(self.render_configuration) != self.render_configuration_sha256:
            raise ValueError("FINAL_RENDER_CONFIGURATION_HASH_MISMATCH")
        return self


class FinalVideoCandidateV1(_Contract):
    schema_version: Literal["final-video-candidate/1.0"] = "final-video-candidate/1.0"
    run_id: str
    case_id: str
    status: Literal["pending_human_final_review"] = "pending_human_final_review"
    media: ArtifactBinding
    request: ArtifactBinding
    render_manifest: ArtifactBinding
    provenance: FinalRenderRequestV1
    technical_qa_artifact: Literal["final_video_qa.json"] = "final_video_qa.json"
    human_final_video_review: Literal["pending"] = "pending"
    workflow_acceptance: Literal["pending"] = "pending"


def _registry(run_dir: Path, candidate_id: int | None = None, *, qa_attempt: int | None = None):
    root = Path(run_dir).resolve()
    manifest = RunManifest.model_validate(read_json(root / "run.json"))
    return ArtifactRegistry(
        root, manifest, playback_preview_mode=True,
        final_render_mode=True, final_preview_candidate_id=candidate_id,
        final_qa_attempt=qa_attempt,
    )


def _path(registry: ArtifactRegistry, relative: str) -> Path:
    ArtifactBinding.relative_path(relative)
    target = (registry.run_dir / relative).resolve()
    try:
        target.relative_to(registry.run_dir.resolve())
    except ValueError as error:
        raise ValueError("FINAL_RENDER_PATH_ESCAPE") from error
    return target


def _current_hashes(registry, name):
    hashes = {}
    for dependency in registry.graph[name][1]:
        _path(registry, dependency)
        registry.validate(dependency)
        hashes[dependency] = registry.manifest.artifacts[dependency].content_hash
    return hashes


def _expected_request(registry, candidate_id):
    review_name = f"human_preview_review_candidate_{candidate_id}.json"
    review = HumanPreviewReviewV1.model_validate(read_json(_path(registry, review_name)))
    if not review.final_render_approved or review.decision != "approved_for_final_render":
        raise ValueError("FINAL_RENDER_HUMAN_APPROVAL_REQUIRED")
    if review.run_id != registry.manifest.run_id or review.candidate_id != candidate_id:
        raise ValueError("FINAL_RENDER_APPROVAL_IDENTITY_MISMATCH")
    deps = _current_hashes(registry, "final_render_request.json")
    approval_deps = {name: value for name, value in deps.items() if name != review_name}
    if review.dependency_hashes != approval_deps:
        raise ValueError("FINAL_RENDER_APPROVAL_DEPENDENCIES_MISMATCH")
    timeline = TimelineDocument.model_validate(read_json(_path(registry, review.timeline_path)))
    comp = timeline.composition
    if comp is None or timeline.run_id != review.run_id:
        raise ValueError("FINAL_RENDER_TIMELINE_BINDING_INVALID")
    visual_review = read_json(_path(registry, comp.visual_review_artifact))
    if (visual_review.get("case_id") != review.case_id or visual_review.get("run_id") != review.run_id
        or visual_review.get("decision") != "approved_for_timeline"):
        raise ValueError("FINAL_RENDER_CASE_BINDING_INVALID")
    if any(deps.get(name) != digest for name, digest in comp.dependency_hashes.items()):
        raise ValueError("FINAL_RENDER_COMPOSITION_BINDING_MISMATCH")
    if canonical_json_sha256(read_json(_path(registry, "human_storyboard_candidate.json"))) != comp.storyboard_sha256:
        raise ValueError("FINAL_RENDER_STORYBOARD_CANONICAL_HASH_MISMATCH")
    suffix = "" if candidate_id == 1 else f"_candidate_{candidate_id}"
    manifest_name, package_name = f"render_manifest{suffix}.json", f"renderer_project{suffix}"
    source_manifest = read_json(_path(registry, manifest_name))
    renderer = source_manifest.get("renderer", {})
    if (source_manifest.get("run_id") != review.run_id or renderer.get("preview_only") is not True
        or renderer.get("full_render_requested") is not False
        or renderer.get("preview_review_status") != "pending_human_preview_review"
        or source_manifest.get("inputs", {}).get("timeline") != {"path": review.timeline_path, "sha256": review.timeline_sha256}
        or review.timeline_sha256 != deps[review.timeline_path]
        or review.preview_sha256 != deps[review.preview_path]):
        raise ValueError("FINAL_RENDER_SOURCE_MANIFEST_INVALID")
    package = _path(registry, package_name)
    package_json = read_json(package / "package.json")
    command = package_json.get("scripts", {}).get("render:full", "")
    version = re.search(r"\bhyperframes@(\d+\.\d+\.\d+)\b", command)
    if not version:
        raise ValueError("FINAL_RENDER_VERSION_NOT_PINNED")
    entry = renderer.get("preview_entry")
    if not isinstance(entry, str) or not _path(registry, f"{package_name}/{entry}").is_file():
        raise ValueError("FINAL_RENDER_ENTRY_MISSING")
    config = FinalRenderConfiguration(
        engine=renderer["engine"], renderer_version=version.group(1), entry=entry,
        width=source_manifest["canvas"]["width"], height=source_manifest["canvas"]["height"],
        fps=source_manifest["canvas"]["fps"], duration_ms=renderer["duration_ms"],
        frame_count=renderer["frame_count"],
        package_configuration_sha256=canonical_json_sha256({
            "package": package_json, "hyperframes": read_json(package / "hyperframes.json"),
        }),
    )
    if (config.duration_ms != timeline.audio.get("duration_ms") or config.fps != renderer.get("fps")
        or timeline.audio.get("sha256") != deps["audio/narration.wav"]):
        raise ValueError("FINAL_RENDER_CONFIGURATION_TIMELINE_MISMATCH")
    def binding(name):
        return ArtifactBinding(path=name, sha256=deps[name])
    return FinalRenderRequestV1(
        run_id=review.run_id, case_id=review.case_id, preview_candidate_id=candidate_id,
        human_preview_approval=binding(review_name), preview=binding(review.preview_path),
        timeline=binding(review.timeline_path), visual_bundle=binding(comp.visual_bundle_artifact),
        audio=binding("audio/narration.wav"), storyboard=binding("human_storyboard_candidate.json"),
        storyboard_canonical_sha256=comp.storyboard_sha256, script=binding("script.json"),
        subtitle=binding("subtitle_track.json"),
        playback_subtitle=binding("preview_subtitle_track_candidate_2.json") if candidate_id != 1 else None,
        source_renderer_package=binding(package_name), source_render_manifest=binding(manifest_name),
        render_configuration=config, render_configuration_sha256=canonical_json_sha256(config),
        dependency_hashes=deps,
    )


def create_final_render_request(run_dir: Path, *, candidate_id: int, expected_approval_sha256: str) -> Path:
    """Consume an explicit, current human decision; never initiate rendering."""
    registry = _registry(run_dir, candidate_id)
    review_name = f"human_preview_review_candidate_{candidate_id}.json"
    registry.validate(review_name)
    if registry.manifest.artifacts[review_name].content_hash != expected_approval_sha256:
        raise ValueError("FINAL_RENDER_APPROVAL_HASH_MISMATCH")
    request = _expected_request(registry, candidate_id)
    _path(registry, "final_render_request.json")
    path = registry.write_json("final_render_request.json", request.model_dump(mode="json"), "final_render")
    registry.save_manifest()
    return path


def validate_final_render_request(run_dir: Path) -> FinalRenderRequestV1:
    """Read-only validation of both the dependency DAG and semantic identity."""
    registry = _registry(run_dir)
    registry.validate("final_render_request.json")
    payload = read_json(_path(registry, "final_render_request.json"))
    request = FinalRenderRequestV1.model_validate(payload)
    if request != _expected_request(registry, request.preview_candidate_id):
        raise ValueError("FINAL_RENDER_REQUEST_NOT_CURRENT_APPROVED_INPUTS")
    return request


def prepare_final_render(run_dir: Path) -> Path:
    """Prepare an independent export package/manifest offline, without changing composition."""
    request = validate_final_render_request(run_dir)
    registry = _registry(run_dir)
    for name in ("renderer_project_final", "render_manifest_final.json", "final.mp4"):
        _path(registry, name)
        if registry.manifest.artifacts[name].status != "missing" or (registry.run_dir / name).exists():
            raise ArtifactConflictError("FINAL_RENDER_OUTPUT_ALREADY_EXISTS")
    source = _path(registry, request.source_renderer_package.path)
    files = {}
    for asset in sorted(source.rglob("*")):
        if asset.is_file():
            try:
                asset.resolve().relative_to(source.resolve())
            except ValueError as error:
                raise ValueError("FINAL_RENDER_PACKAGE_PATH_ESCAPE") from error
            files[asset.relative_to(source).as_posix()] = asset.read_bytes()
    manifest = {
        "schema_version": "final-render-manifest/1.0", "run_id": request.run_id, "case_id": request.case_id,
        "request": {"path": "final_render_request.json", "sha256": registry.manifest.artifacts["final_render_request.json"].content_hash},
        "inputs": request.model_dump(mode="json"),
        "renderer": {**request.render_configuration.model_dump(mode="json"),
            "preview_only": False, "full_render_requested": True},
        "output_path": request.output_path, "status": "ready_for_final_render",
        "human_final_video_review": "pending", "workflow_acceptance": "pending",
    }
    registry.write_directory("renderer_project_final", files, "final_render")
    manifest["renderer_package"] = {"path": "renderer_project_final", "sha256": registry.manifest.artifacts["renderer_project_final"].content_hash}
    path = registry.write_json("render_manifest_final.json", manifest, "final_render")
    registry.save_manifest()
    return path


def record_final_video_candidate(
    run_dir: Path, rendered_file: Path, *, expected_request_sha256: str, expected_manifest_sha256: str,
) -> Path:
    """Future render handoff: register media as pending QA/human review, never accepted."""
    request = validate_final_render_request(run_dir)
    registry = _registry(run_dir)
    registry.validate("render_manifest_final.json")
    registry.validate("renderer_project_final")
    if (registry.manifest.artifacts["final_render_request.json"].content_hash != expected_request_sha256
        or registry.manifest.artifacts["render_manifest_final.json"].content_hash != expected_manifest_sha256):
        raise ValueError("FINAL_RENDER_RESULT_PROVENANCE_MISMATCH")
    manifest = read_json(_path(registry, "render_manifest_final.json"))
    if (manifest.get("inputs") != request.model_dump(mode="json")
        or manifest.get("renderer") != {**request.render_configuration.model_dump(mode="json"), "preview_only": False, "full_render_requested": True}
        or manifest.get("run_id") != request.run_id or manifest.get("case_id") != request.case_id
        or manifest.get("request") != {"path": "final_render_request.json", "sha256": expected_request_sha256}
        or manifest.get("renderer_package") != {"path": "renderer_project_final", "sha256": registry.manifest.artifacts["renderer_project_final"].content_hash}):
        raise ValueError("FINAL_RENDER_MANIFEST_BINDING_INVALID")
    if (manifest.get("schema_version") != "final-render-manifest/1.0"
        or manifest.get("status") != "ready_for_final_render"
        or manifest.get("output_path") != request.output_path
        or manifest.get("human_final_video_review") != "pending"
        or manifest.get("workflow_acceptance") != "pending"
        or registry.manifest.artifacts["renderer_project_final"].content_hash != request.source_renderer_package.sha256):
        raise ValueError("FINAL_RENDER_MANIFEST_INTENT_INVALID")
    target = _path(registry, request.output_path)
    result = Path(rendered_file).resolve()
    try:
        result.relative_to(registry.run_dir.resolve())
    except ValueError as error:
        raise ValueError("FINAL_RENDER_OUTPUT_OUTSIDE_RUN") from error
    if result == _path(registry, request.preview.path) or result == target:
        raise ValueError("FINAL_RENDER_REQUIRES_SEPARATE_EXPORT_OUTPUT")
    payload = result.read_bytes()
    if len(payload) < 12 or payload[4:8] != b"ftyp":
        raise ValueError("FINAL_RENDER_OUTPUT_NOT_MP4")
    for name in ("final.mp4", "final_video_candidate.json"):
        _path(registry, name)
        if (registry.run_dir / name).exists() or registry.manifest.artifacts[name].status != "missing":
            raise ArtifactConflictError("FINAL_RENDER_OUTPUT_ALREADY_EXISTS")
    candidate = FinalVideoCandidateV1(
        run_id=request.run_id, case_id=request.case_id,
        media=ArtifactBinding(path="final.mp4", sha256=sha256_bytes(payload)),
        request=ArtifactBinding(path="final_render_request.json", sha256=expected_request_sha256),
        render_manifest=ArtifactBinding(path="render_manifest_final.json", sha256=expected_manifest_sha256),
        provenance=request,
    )
    registry.write_bytes("final.mp4", payload, "final_render")
    path = registry.write_json("final_video_candidate.json", candidate.model_dump(mode="json"), "final_render")
    registry.save_manifest()
    return path
