"""Generic publication rendering, media registration and immutable provenance."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from fanglei.artifact_registry import ArtifactRegistry
from fanglei.artifacts import read_json, sha256_bytes
from fanglei.errors import ArtifactConflictError
from fanglei.final_render import ArtifactBinding, FinalRenderConfiguration, _path
from fanglei.final_video_qa import (
    _registry_candidate, validate_existing_human_final_video_approval,
)
from fanglei.human_storyboard_recovery import canonical_json_sha256
from fanglei.models import RunManifest
from fanglei.publication_package import (
    PACKAGE_ARTIFACT, PACKAGE_DIRECTORY, PublicationRendererPackageV1,
    validate_publication_renderer_package,
)


REQUEST_ARTIFACT = "publication_render_request.json"
RENDER_MANIFEST = "publication_render_manifest.json"
MEDIA_ARTIFACT = "publication_media.json"
PUBLICATION_OWNER = "publication_render"
AUTHORIZED_DIFFERENCES = ["review_overlay_removal"]


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def _valid_output_path(value: str) -> str:
    parts = value.split("/") if isinstance(value, str) else []
    if ("\\" in value or ":" in value or value.startswith("/") or len(parts) != 3
        or parts[0] != "release" or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", parts[1])
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.mp4", parts[2])
        or any(part in {"", ".", ".."} for part in parts)
        or parts[2].lower() in {"final.mp4", "review-preview.mp4"}
        or re.fullmatch(r"review-preview-candidate-\d+\.mp4", parts[2], re.I)):
        raise ValueError("PUBLICATION_OUTPUT_PATH_INVALID")
    return value


class PublicationRenderRequestV1(_Contract):
    schema_version: Literal["publication-render-request/1.0"] = "publication-render-request/1.0"
    run_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    status: Literal["ready_for_publication_render"] = "ready_for_publication_render"
    release_version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    asset_filename: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.mp4$")
    output_path: str
    presentation_mode: Literal["publication"] = "publication"
    authorized_visual_differences: list[Literal["review_overlay_removal"]]
    publication_package: ArtifactBinding
    publication_renderer_package: ArtifactBinding
    accepted_final_candidate: ArtifactBinding
    accepted_final_media: ArtifactBinding
    human_final_approval: ArtifactBinding
    final_render_request: ArtifactBinding
    render_configuration: FinalRenderConfiguration
    render_configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    toolchain_lock_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dependency_hashes: dict[str, str]
    created_at: datetime

    @field_validator("output_path")
    @classmethod
    def safe_publication_namespace(cls, value):
        return _valid_output_path(value)

    @field_validator("created_at")
    @classmethod
    def timestamp_aware(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("PUBLICATION_RENDER_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
        return value

    @model_validator(mode="after")
    def identity_and_bindings(self):
        if self.output_path != f"release/{self.release_version}/{self.asset_filename}":
            raise ValueError("PUBLICATION_OUTPUT_TARGET_MISMATCH")
        if self.authorized_visual_differences != AUTHORIZED_DIFFERENCES:
            raise ValueError("PUBLICATION_AUTHORIZED_DIFFERENCES_INVALID")
        rows = (self.publication_package, self.publication_renderer_package,
                self.accepted_final_candidate, self.accepted_final_media,
                self.human_final_approval, self.final_render_request)
        if any(self.dependency_hashes.get(row.path) != row.sha256 for row in rows):
            raise ValueError("PUBLICATION_RENDER_REQUEST_BINDING_MISMATCH")
        if canonical_json_sha256(self.render_configuration) != self.render_configuration_sha256:
            raise ValueError("PUBLICATION_RENDER_CONFIGURATION_HASH_MISMATCH")
        if any(not re.fullmatch(r"[0-9a-f]{64}", digest) for digest in self.dependency_hashes.values()):
            raise ValueError("PUBLICATION_RENDER_DEPENDENCY_HASH_INVALID")
        return self


class PublicationRenderManifestV1(_Contract):
    schema_version: Literal["publication-render-manifest/1.0"] = "publication-render-manifest/1.0"
    run_id: str
    case_id: str
    request: ArtifactBinding
    publication_renderer_package: ArtifactBinding
    output_path: str
    status: Literal["ready_for_publication_render"] = "ready_for_publication_render"
    renderer_command: list[str] = Field(min_length=1)
    ffmpeg_identity: dict[str, str]
    ffprobe_identity: dict[str, str]
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def timestamp_aware(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("PUBLICATION_RENDER_MANIFEST_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
        return value


class PublicationVideoV1(_Contract):
    schema_version: Literal["publication-video/1.0"] = "publication-video/1.0"
    run_id: str
    case_id: str
    status: Literal["pending_publication_qa"] = "pending_publication_qa"
    path: str
    media_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    file_size: int = Field(gt=0)
    source_publication_render_request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_publication_package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_final_candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_final_media_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_human_final_approval_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    presentation_mode: Literal["publication"] = "publication"
    authorized_visual_differences: list[Literal["review_overlay_removal"]]
    expected_technical_properties: dict[str, Any]
    created_at: datetime

    @field_validator("path")
    @classmethod
    def publication_path(cls, value):
        return _valid_output_path(value)

    @field_validator("created_at")
    @classmethod
    def timestamp_aware(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("PUBLICATION_MEDIA_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
        return value


def publication_render_registry(run_dir: Path, *, qa_attempt: int | None = None) -> ArtifactRegistry:
    root = Path(run_dir).resolve()
    manifest = RunManifest.model_validate(read_json(root / "run.json"))
    return ArtifactRegistry(
        root, manifest, playback_preview_mode=True, final_render_mode=True,
        publication_package_mode=True, publication_render_mode=True,
        publication_qa_attempt=qa_attempt,
    )


def _artifact_binding(registry: ArtifactRegistry, path: str) -> ArtifactBinding:
    state = registry.manifest.artifacts[path]
    return ArtifactBinding(path=path, sha256=state.content_hash)


def _current_inputs(run_dir: Path):
    root = Path(run_dir).resolve()
    validate_publication_renderer_package(root)
    registry, candidate, final_request, candidate_sha = _registry_candidate(root)
    final_review = validate_existing_human_final_video_approval(root)
    registry = publication_render_registry(root)
    return registry, candidate, final_request, candidate_sha, final_review


def _request_body(registry, final_request, candidate_sha, final_review, release_version, asset_filename):
    if PurePosixPath(asset_filename).name != asset_filename:
        raise ValueError("PUBLICATION_ASSET_FILENAME_INVALID")
    output_path = _valid_output_path(f"release/{release_version}/{asset_filename}")
    package = PublicationRendererPackageV1.model_validate(read_json(_path(registry, PACKAGE_ARTIFACT)))
    deps = {}
    for name in registry.graph[REQUEST_ARTIFACT][1]:
        registry.validate(name)
        deps[name] = registry.manifest.artifacts[name].content_hash
    config = package.render_configuration
    lock_file = Path(__file__).resolve().parents[2] / "tools/ffmpeg/package-lock.json"
    if not lock_file.is_file():
        raise ValueError("PUBLICATION_TOOLCHAIN_LOCK_MISSING")
    return PublicationRenderRequestV1(
        run_id=package.run_id, case_id=package.case_id,
        release_version=release_version, asset_filename=asset_filename, output_path=output_path,
        presentation_mode="publication", authorized_visual_differences=AUTHORIZED_DIFFERENCES,
        publication_package=_artifact_binding(registry, PACKAGE_ARTIFACT),
        publication_renderer_package=_artifact_binding(registry, PACKAGE_DIRECTORY),
        accepted_final_candidate=_artifact_binding(registry, "final_video_candidate.json"),
        accepted_final_media=_artifact_binding(registry, "final.mp4"),
        human_final_approval=_artifact_binding(registry, "human_final_video_review.json"),
        final_render_request=_artifact_binding(registry, "final_render_request.json"),
        render_configuration=config,
        render_configuration_sha256=canonical_json_sha256(config),
        toolchain_lock_sha256=sha256_bytes(lock_file.read_bytes()),
        dependency_hashes=deps, created_at=datetime.now(timezone.utc),
    )


def create_publication_render_request(
    run_dir: Path, *, release_version: str, asset_filename: str,
    expected_package_sha256: str, expected_candidate_sha256: str,
    expected_final_media_sha256: str, expected_approval_sha256: str,
) -> Path:
    registry, candidate, final_request, candidate_sha, final_review = _current_inputs(Path(run_dir))
    expected = {
        PACKAGE_ARTIFACT: expected_package_sha256,
        "final_video_candidate.json": expected_candidate_sha256,
        "final.mp4": expected_final_media_sha256,
        "human_final_video_review.json": expected_approval_sha256,
    }
    if any(registry.manifest.artifacts[name].content_hash != digest for name, digest in expected.items()):
        raise ValueError("PUBLICATION_RENDER_EXPECTED_HASH_MISMATCH")
    path = _path(registry, REQUEST_ARTIFACT)
    if path.exists() or registry.manifest.artifacts[REQUEST_ARTIFACT].status != "missing":
        raise ArtifactConflictError("PUBLICATION_RENDER_REQUEST_ALREADY_EXISTS")
    request = _request_body(registry, final_request, candidate_sha, final_review, release_version, asset_filename)
    result = registry.write_json(REQUEST_ARTIFACT, request.model_dump(mode="json"), PUBLICATION_OWNER)
    registry.save_manifest()
    return result


def validate_publication_render_request(run_dir: Path) -> PublicationRenderRequestV1:
    registry, candidate, final_request, candidate_sha, final_review = _current_inputs(Path(run_dir))
    registry.validate(REQUEST_ARTIFACT)
    request = PublicationRenderRequestV1.model_validate_json(_path(registry, REQUEST_ARTIFACT).read_text(encoding="utf-8"))
    expected = _request_body(registry, final_request, candidate_sha, final_review,
                             request.release_version, request.asset_filename)
    # Creation time is part of immutable request identity, not recomputed on read.
    expected.created_at = request.created_at
    if request != expected or request.run_id != candidate.run_id or request.case_id != candidate.case_id:
        raise ValueError("PUBLICATION_RENDER_REQUEST_NOT_CURRENT")
    return request


def _tool_identity(path: str) -> dict[str, str]:
    executable = Path(path).resolve()
    if not executable.is_file():
        raise ValueError("PUBLICATION_RENDER_TOOL_UNAVAILABLE")
    return {"filename": executable.name, "sha256": sha256_bytes(executable.read_bytes())}


def _render_toolchain():
    from fanglei.render_preflight import resolve_renderer_environment

    environment = resolve_renderer_environment()
    if not environment.hyperframes_command or not environment.node:
        raise ValueError("PUBLICATION_RENDER_TOOLCHAIN_UNAVAILABLE")
    ffmpeg = (os.environ.get("HYPERFRAMES_FFMPEG_PATH") or os.environ.get("NIKOLA_FFMPEG_PATH")
              or environment.ffmpeg)
    ffprobe = (os.environ.get("HYPERFRAMES_FFPROBE_PATH") or os.environ.get("NIKOLA_FFPROBE_PATH")
               or environment.ffprobe)
    node = environment.node
    tools_root = Path(__file__).resolve().parents[2] / "tools/ffmpeg/node_modules"
    for current, package in (("ffmpeg", tools_root / "@ffmpeg-installer/ffmpeg"),
                             ("ffprobe", tools_root / "ffprobe-static")):
        if (current == "ffmpeg" and ffmpeg) or (current == "ffprobe" and ffprobe):
            continue
        if package.exists():
            result = subprocess.run([node, "-e", "console.log(require(process.argv[1]).path)", str(package)],
                                    capture_output=True, text=True, check=False, timeout=20)
            if result.returncode == 0:
                if current == "ffmpeg":
                    ffmpeg = result.stdout.strip()
                else:
                    ffprobe = result.stdout.strip()
    if not ffmpeg or not ffprobe:
        raise ValueError("PUBLICATION_RENDER_MEDIA_TOOLS_UNAVAILABLE")
    return environment, ffmpeg, ffprobe


def prepare_publication_render(run_dir: Path) -> Path:
    request = validate_publication_render_request(run_dir)
    registry = publication_render_registry(Path(run_dir))
    target = _path(registry, RENDER_MANIFEST)
    if target.exists() or registry.manifest.artifacts[RENDER_MANIFEST].status != "missing":
        raise ArtifactConflictError("PUBLICATION_RENDER_MANIFEST_ALREADY_EXISTS")
    media_target = _path(registry, request.output_path)
    if media_target.exists() or registry.manifest.artifacts[request.output_path].status != "missing":
        raise ArtifactConflictError("PUBLICATION_MEDIA_ALREADY_EXISTS")
    environment, ffmpeg, ffprobe = _render_toolchain()
    command = [*environment.hyperframes_command, "render", ".", "--output", request.output_path]
    manifest = PublicationRenderManifestV1(
        run_id=request.run_id, case_id=request.case_id,
        request=_artifact_binding(registry, REQUEST_ARTIFACT),
        publication_renderer_package=_artifact_binding(registry, PACKAGE_DIRECTORY),
        output_path=request.output_path, renderer_command=command,
        ffmpeg_identity=_tool_identity(ffmpeg), ffprobe_identity=_tool_identity(ffprobe),
        created_at=datetime.now(timezone.utc),
    )
    path = registry.write_json(RENDER_MANIFEST, manifest.model_dump(mode="json"), PUBLICATION_OWNER)
    registry.save_manifest()
    return path


def _validate_render_manifest(registry, request, *, environment=None, ffmpeg=None, ffprobe=None):
    registry.validate(RENDER_MANIFEST)
    manifest = PublicationRenderManifestV1.model_validate_json(_path(registry, RENDER_MANIFEST).read_text(encoding="utf-8"))
    if (manifest.run_id != request.run_id or manifest.case_id != request.case_id
        or manifest.request.sha256 != registry.manifest.artifacts[REQUEST_ARTIFACT].content_hash
        or manifest.publication_renderer_package.sha256 != registry.manifest.artifacts[PACKAGE_DIRECTORY].content_hash
        or manifest.output_path != request.output_path):
        raise ValueError("PUBLICATION_RENDER_MANIFEST_BINDING_MISMATCH")
    if environment is not None:
        expected_command = [*environment.hyperframes_command, "render", ".", "--output", request.output_path]
        if manifest.renderer_command != expected_command:
            raise ValueError("PUBLICATION_RENDERER_COMMAND_CHANGED")
        if (_tool_identity(ffmpeg) != manifest.ffmpeg_identity
            or _tool_identity(ffprobe) != manifest.ffprobe_identity):
            raise ValueError("PUBLICATION_RENDER_TOOLCHAIN_CHANGED")
    return manifest


def record_publication_media(
    run_dir: Path, rendered_file: Path, *, expected_request_sha256: str,
    expected_manifest_sha256: str,
) -> Path:
    root = Path(run_dir).resolve()
    request = validate_publication_render_request(root)
    registry = publication_render_registry(root)
    _validate_render_manifest(registry, request)
    if (registry.manifest.artifacts[REQUEST_ARTIFACT].content_hash != expected_request_sha256
        or registry.manifest.artifacts[RENDER_MANIFEST].content_hash != expected_manifest_sha256):
        raise ValueError("PUBLICATION_RENDER_RESULT_PROVENANCE_MISMATCH")
    source = Path(rendered_file).resolve()
    if not source.is_file() or not source.stat().st_size:
        raise ValueError("PUBLICATION_RENDER_OUTPUT_MISSING")
    output = _path(registry, request.output_path)
    if output.exists() or registry.manifest.artifacts[request.output_path].status != "missing":
        raise ArtifactConflictError("PUBLICATION_MEDIA_ALREADY_EXISTS")
    media_bytes = source.read_bytes()
    if len(media_bytes) < 12 or media_bytes[4:8] != b"ftyp":
        raise ValueError("PUBLICATION_RENDER_OUTPUT_NOT_MP4")
    media_sha = sha256_bytes(media_bytes)
    config = request.render_configuration
    media = PublicationVideoV1(
        run_id=request.run_id, case_id=request.case_id, path=request.output_path,
        media_sha256=media_sha, file_size=len(media_bytes),
        source_publication_render_request_sha256=expected_request_sha256,
        source_publication_package_sha256=registry.manifest.artifacts[PACKAGE_ARTIFACT].content_hash,
        source_final_candidate_sha256=registry.manifest.artifacts["final_video_candidate.json"].content_hash,
        source_final_media_sha256=registry.manifest.artifacts["final.mp4"].content_hash,
        source_human_final_approval_sha256=registry.manifest.artifacts["human_final_video_review.json"].content_hash,
        presentation_mode="publication", authorized_visual_differences=AUTHORIZED_DIFFERENCES,
        expected_technical_properties={
            "container": "mp4", "width": config.width, "height": config.height, "fps": config.fps,
            "duration_ms": config.duration_ms, "frame_count": config.frame_count,
            "video_codec": config.video_codec, "audio_codec": config.audio_codec,
        }, created_at=datetime.now(timezone.utc),
    )
    registry.write_bytes(request.output_path, media_bytes, PUBLICATION_OWNER)
    path = registry.write_json(MEDIA_ARTIFACT, media.model_dump(mode="json"), PUBLICATION_OWNER)
    registry.save_manifest()
    return path


def run_publication_render(
    run_dir: Path, *, renderer_runner: Callable[[Path, Path, list[str], dict[str, str]], Any] | None = None,
) -> Path:
    """Render one explicitly requested publication package to a sibling temp, then atomically register it."""
    request = validate_publication_render_request(run_dir)
    registry = publication_render_registry(Path(run_dir))
    manifest_path = _path(registry, RENDER_MANIFEST)
    if not manifest_path.exists():
        manifest_path = prepare_publication_render(run_dir)
        registry = publication_render_registry(Path(run_dir))
    environment, ffmpeg, ffprobe = _render_toolchain()
    manifest = _validate_render_manifest(
        registry, request, environment=environment, ffmpeg=ffmpeg, ffprobe=ffprobe,
    )
    target = _path(registry, request.output_path)
    if target.exists() or registry.manifest.artifacts[request.output_path].status != "missing":
        raise ArtifactConflictError("PUBLICATION_MEDIA_ALREADY_EXISTS")
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=f".{target.stem}.", suffix=".rendering.mp4", dir=target.parent)
    os.close(handle)
    temporary = Path(temporary_name)
    temporary.unlink(missing_ok=True)
    try:
        command = [*environment.hyperframes_command, "render", ".", "--output", str(temporary)]
        child_env = dict(os.environ)
        child_env["HYPERFRAMES_FFMPEG_PATH"] = str(ffmpeg)
        child_env["HYPERFRAMES_FFPROBE_PATH"] = str(ffprobe)
        package = _path(registry, PACKAGE_DIRECTORY)
        if renderer_runner is None:
            subprocess.run(command, cwd=package, env=child_env, check=True,
                           capture_output=True, text=True, encoding="utf-8", timeout=max(300, request.render_configuration.duration_ms // 1000 * 20))
        else:
            renderer_runner(package, temporary, command, child_env)
        return record_publication_media(
            run_dir, temporary,
            expected_request_sha256=registry.manifest.artifacts[REQUEST_ARTIFACT].content_hash,
            expected_manifest_sha256=registry.manifest.artifacts[RENDER_MANIFEST].content_hash,
        )
    finally:
        temporary.unlink(missing_ok=True)
