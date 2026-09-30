"""Human review recording and downstream playback-preview artifact owners."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from pathlib import PurePosixPath
import re
from typing import Literal

from pydantic import Field, field_validator, model_validator

from fanglei.artifact_registry import ArtifactRegistry
from fanglei.artifacts import read_json, sha256_bytes
from fanglei.errors import ArtifactConflictError
from fanglei.human_script_approval import HumanScriptApprovalV1
from fanglei.human_visual_asset_recovery import HumanVisualAssetReviewV1
from fanglei.models import RunManifest
from fanglei.nikola_adapter import build_nikola_project
from fanglei.playback_timing import (
    PlaybackTimingRefinementV1,
    PreviewSubtitleTrackV1,
    build_playback_timing_refinement,
    build_preview_subtitle_track,
    compile_playback_timeline_candidate_2,
    derive_compact_subtitle_layout,
)
from fanglei.v05_models import AlignmentDocument, AudioMetadata, NarrationDocument, TimelineDocument
from fanglei.v05_models import StrictModel
from fanglei.v05_models import VoiceReviewDocument
from fanglei.v1b_models import SubtitleTrack


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class PreviewReviewFindingV1(StrictModel):
    code: str = Field(min_length=1)
    observation: str = Field(min_length=1)
    scene_ids: list[str] = Field(default_factory=list)


class HumanPreviewReviewV1(StrictModel):
    schema_version: Literal["human-preview-review/1.0"] = "human-preview-review/1.0"
    artifact_type: Literal["human_preview_review"] = "human_preview_review"
    candidate_id: Literal[1, 2, 3]
    run_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    reviewer: str = Field(min_length=1)
    reviewed_at: str = Field(min_length=1)
    decision: Literal["changes_required", "approved_for_review"]
    reason_code: str = Field(min_length=1)
    findings: list[PreviewReviewFindingV1] = Field(min_length=1)
    preview_path: str = Field(min_length=1)
    preview_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    timeline_path: Literal["timeline.json", "timeline_candidate_2.json"]
    timeline_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dependency_hashes: dict[str, str]
    final_render_approved: Literal[False] = False

    @field_validator("reviewed_at")
    @classmethod
    def timestamp_is_timezone_aware(cls, value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("reviewed_at must be ISO-8601") from error
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("reviewed_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def dependency_map_is_valid(self) -> "HumanPreviewReviewV1":
        if not self.dependency_hashes or any(
            not name or not re.fullmatch(r"[0-9a-f]{64}", digest)
            for name, digest in self.dependency_hashes.items()
        ):
            raise ValueError("PREVIEW_REVIEW_DEPENDENCY_HASH_INVALID")
        expected_timeline = "timeline.json" if self.candidate_id == 1 else "timeline_candidate_2.json"
        if self.timeline_path != expected_timeline:
            raise ValueError("PREVIEW_REVIEW_TIMELINE_IDENTITY_INVALID")
        if self.decision == "changes_required" and self.reason_code == "APPROVED_FOR_REVIEW":
            raise ValueError("PREVIEW_REVIEW_REASON_INVALID")
        return self


def _load_registry(run_dir: Path) -> tuple[RunManifest, ArtifactRegistry]:
    run_dir = Path(run_dir).resolve()
    manifest = RunManifest.model_validate(read_json(run_dir / "run.json"))
    registry = ArtifactRegistry(run_dir, manifest, playback_preview_mode=True)
    return manifest, registry


def _safe_preview_path(run_dir: Path, candidate_id: int) -> tuple[str, Path]:
    if candidate_id not in (1, 2, 3):
        raise ValueError("PREVIEW_CANDIDATE_ID_INVALID")
    relative = "review-preview.mp4" if candidate_id == 1 else f"review-preview-candidate-{candidate_id}.mp4"
    target = (run_dir / relative).resolve()
    try:
        target.relative_to(run_dir.resolve())
    except ValueError as error:
        raise ValueError("PREVIEW_REVIEW_PATH_INVALID") from error
    return relative, target


def record_human_preview_review(
    run_dir: Path,
    *,
    candidate_id: Literal[1, 2, 3],
    reviewer: str,
    decision: Literal["changes_required", "approved_for_review"],
    reason_code: str,
    findings: list[dict],
    expected_preview_sha256: str,
) -> Path:
    """Record an explicit human decision bound to the current local preview bytes."""
    run_dir = Path(run_dir).resolve()
    manifest, registry = _load_registry(run_dir)
    timeline_name = "timeline.json" if candidate_id == 1 else "timeline_candidate_2.json"
    render_manifest_name = "render_manifest.json" if candidate_id == 1 else f"render_manifest_candidate_{candidate_id}.json"
    review_name = f"human_preview_review_candidate_{candidate_id}.json"
    if registry.manifest.artifacts[review_name].status != "missing":
        raise ArtifactConflictError("PREVIEW_REVIEW_DECISION_ALREADY_RECORDED")
    dependency_names = registry.graph[review_name][1]
    for name in dependency_names:
        registry.validate(name)

    preview_relative, preview_path = _safe_preview_path(run_dir, candidate_id)
    if not preview_path.is_file():
        raise ValueError("PREVIEW_MEDIA_MISSING")
    actual_preview_sha = sha256_bytes(preview_path.read_bytes())
    if actual_preview_sha != expected_preview_sha256:
        raise ValueError("PREVIEW_MEDIA_HASH_MISMATCH")

    timeline = registry.read_json(timeline_name)
    render_manifest = registry.read_json(render_manifest_name)
    composition = timeline.get("composition") or {}
    visual_review_name = composition.get("visual_review_artifact")
    visual_bundle_name = composition.get("visual_bundle_artifact")
    if (
        not isinstance(visual_review_name, str) or visual_review_name not in registry.graph
        or not isinstance(visual_bundle_name, str) or visual_bundle_name not in registry.graph
    ):
        raise ValueError("PREVIEW_CANDIDATE_VISUAL_BINDING_INVALID")
    visual_review = HumanVisualAssetReviewV1.model_validate(registry.read_json(visual_review_name))
    renderer = render_manifest.get("renderer", {})
    if (
        timeline.get("run_id") != manifest.run_id
        or visual_review.run_id != manifest.run_id
        or not visual_review.case_id
        or render_manifest.get("run_id") != manifest.run_id
        or renderer.get("preview_only") is not True
        or renderer.get("full_render_requested") is not False
        or renderer.get("preview_review_status") != "pending_human_preview_review"
        or composition.get("preview_only") is not True
    ):
        raise ValueError("PREVIEW_CANDIDATE_NOT_PENDING_HUMAN_REVIEW")
    if composition.get("visual_candidate_id") != visual_review.candidate_id:
        raise ValueError("PREVIEW_CANDIDATE_VISUAL_BINDING_INVALID")
    dependency_hashes = {
        name: registry.manifest.artifacts[name].content_hash or ""
        for name in dependency_names
    }
    timeline_sha = registry.manifest.artifacts[timeline_name].content_hash or ""
    document = HumanPreviewReviewV1(
        candidate_id=candidate_id,
        run_id=manifest.run_id,
        case_id=visual_review.case_id,
        reviewer=reviewer,
        reviewed_at=_now(),
        decision=decision,
        reason_code=reason_code,
        findings=findings,
        preview_path=preview_relative,
        preview_sha256=actual_preview_sha,
        timeline_path=timeline_name,
        timeline_sha256=timeline_sha,
        dependency_hashes=dependency_hashes,
    )
    path = registry.write_json(
        review_name, document.model_dump(mode="json"), "human_preview_review",
    )
    registry.save_manifest()
    return path


def _validated_dependency_hashes(registry: ArtifactRegistry, artifact_name: str) -> dict[str, str]:
    names = registry.graph[artifact_name][1]
    hashes: dict[str, str] = {}
    for name in names:
        registry.validate(name)
        state = registry.manifest.artifacts[name]
        if state.status != "valid" or not state.content_hash:
            raise ArtifactConflictError(f"PLAYBACK_DEPENDENCY_NOT_CURRENT:{name}")
        hashes[name] = state.content_hash
    return hashes


def create_playback_timing_refinement(run_dir: Path) -> Path:
    """Write a pause-evidence timing layer without replacing planning alignment."""
    run_dir = Path(run_dir).resolve()
    manifest, registry = _load_registry(run_dir)
    dependency_hashes = _validated_dependency_hashes(registry, "playback_timing_refinement.json")
    preview_review = HumanPreviewReviewV1.model_validate(
        registry.read_json("human_preview_review_candidate_1.json"),
    )
    if (
        preview_review.decision != "changes_required"
        or preview_review.reason_code != "SUBTITLE_OCCLUSION_AND_TIMING_SYNC"
        or preview_review.final_render_approved
        or preview_review.run_id != manifest.run_id
    ):
        raise ValueError("PLAYBACK_REFINEMENT_REQUIRES_CANDIDATE_ONE_CHANGES_REQUIRED")

    audio_bytes = (run_dir / "audio/narration.wav").read_bytes()
    audio = AudioMetadata.model_validate(registry.read_json("audio/metadata.json"))
    if sha256_bytes(audio_bytes) != audio.sha256:
        raise ValueError("PLAYBACK_AUDIO_HASH_MISMATCH")
    alignment = AlignmentDocument.model_validate(registry.read_json("alignment.json"))
    narration = NarrationDocument.model_validate(registry.read_json("narration.json"))
    script_approval = HumanScriptApprovalV1.model_validate(registry.read_json("human_script_approval.json"))
    audio_review = VoiceReviewDocument.model_validate(registry.read_json("audio/review.json"))
    timeline = registry.read_json("timeline.json")
    visual_review_name = (timeline.get("composition") or {}).get("visual_review_artifact")
    if not isinstance(visual_review_name, str) or visual_review_name not in registry.graph:
        raise ValueError("PLAYBACK_VISUAL_REVIEW_BINDING_MISSING")
    visual_review = HumanVisualAssetReviewV1.model_validate(registry.read_json(visual_review_name))
    script_sha = manifest.artifacts["script.json"].content_hash
    narration_sha = manifest.artifacts["narration.json"].content_hash
    alignment_sha = manifest.artifacts["alignment.json"].content_hash
    if (
        not script_sha or not narration_sha or not alignment_sha
        or script_approval.status != "approved_for_tts"
        or script_approval.run_id != manifest.run_id
        or script_approval.case_id != preview_review.case_id
        or script_approval.script_sha256 != script_sha
        or audio_review.status != "approved"
        or audio_review.run_id != manifest.run_id
        or audio_review.audio_sha256 != audio.sha256
        or alignment.run_id != manifest.run_id
        or narration.run_id != manifest.run_id
        or visual_review.case_id != preview_review.case_id
        or audio.duration_ms != alignment.audio_duration_ms
    ):
        raise ValueError("PLAYBACK_REFINEMENT_UPSTREAM_APPROVAL_BINDING_INVALID")

    refinement = build_playback_timing_refinement(
        audio_bytes,
        alignment,
        run_id=manifest.run_id,
        case_id=preview_review.case_id,
        audio_sha256=audio.sha256,
        narration_sha256=narration_sha,
        planning_alignment_sha256=alignment_sha,
        script_sha256=script_sha,
    )
    path = registry.write_json(
        "playback_timing_refinement.json", refinement.model_dump(mode="json"),
        "playback_timing_refinement",
    )
    registry.save_manifest()
    return path


def create_preview_subtitle_track_candidate_2(run_dir: Path) -> Path:
    """Retiming/reflow exact canonical subtitle text against Candidate 3 safe regions."""
    run_dir = Path(run_dir).resolve()
    manifest, registry = _load_registry(run_dir)
    _validated_dependency_hashes(registry, "preview_subtitle_track_candidate_2.json")
    canonical = SubtitleTrack.model_validate(registry.read_json("subtitle_track.json"))
    refinement = PlaybackTimingRefinementV1.model_validate(
        registry.read_json("playback_timing_refinement.json"),
    )
    timeline = TimelineDocument.model_validate(registry.read_json("timeline.json"))
    composition = timeline.composition
    if composition is None or refinement.run_id != manifest.run_id:
        raise ValueError("PREVIEW_SUBTITLE_UPSTREAM_COMPOSITION_INVALID")
    visual_review = HumanVisualAssetReviewV1.model_validate(
        registry.read_json(composition.visual_review_artifact),
    )
    bundle_name = composition.visual_bundle_artifact
    registry.validate(bundle_name)
    bundle_dir = run_dir / bundle_name
    visual_manifest = read_json(bundle_dir / "manifest.json")
    visual_files: dict[str, bytes] = {}
    for scene in visual_manifest.get("scenes", []):
        relative = scene.get("asset_path")
        asset_path = PurePosixPath(relative) if isinstance(relative, str) else None
        if (
            asset_path is None or asset_path.is_absolute() or "\\" in relative
            or any(part in {"", ".", ".."} for part in asset_path.parts)
        ):
            raise ValueError("PREVIEW_SUBTITLE_ASSET_PATH_INVALID")
        target = (bundle_dir / Path(*asset_path.parts)).resolve()
        try:
            target.relative_to(bundle_dir.resolve())
        except ValueError as error:
            raise ValueError("PREVIEW_SUBTITLE_ASSET_PATH_INVALID") from error
        if not target.is_file():
            raise ValueError("PREVIEW_SUBTITLE_ASSET_MISSING")
        visual_files[asset_path.as_posix()] = target.read_bytes()
    layout = derive_compact_subtitle_layout(visual_manifest, visual_files)
    canonical_sha = manifest.artifacts["subtitle_track.json"].content_hash
    timing_sha = manifest.artifacts["playback_timing_refinement.json"].content_hash
    audio_sha = manifest.artifacts["audio/narration.wav"].content_hash
    if not canonical_sha or not timing_sha or not audio_sha:
        raise ValueError("PREVIEW_SUBTITLE_UPSTREAM_HASH_MISSING")
    preview_track = build_preview_subtitle_track(
        canonical, refinement, layout,
        canonical_subtitle_sha256=canonical_sha,
        timing_refinement_sha256=timing_sha,
        audio_sha256=audio_sha,
    )
    if preview_track.case_id != visual_review.case_id:
        raise ValueError("PREVIEW_SUBTITLE_CASE_BINDING_INVALID")
    path = registry.write_json(
        "preview_subtitle_track_candidate_2.json", preview_track.model_dump(mode="json"),
        "playback_subtitle_generation",
    )
    registry.save_manifest()
    return path


def create_timeline_candidate_2(run_dir: Path) -> Path:
    """Compile Candidate 2 playback timing from current immutable inputs."""
    run_dir = Path(run_dir).resolve()
    manifest, registry = _load_registry(run_dir)
    dependency_hashes = _validated_dependency_hashes(registry, "timeline_candidate_2.json")
    base = TimelineDocument.model_validate(registry.read_json("timeline.json"))
    refinement = PlaybackTimingRefinementV1.model_validate(
        registry.read_json("playback_timing_refinement.json"),
    )
    preview_track = PreviewSubtitleTrackV1.model_validate(
        registry.read_json("preview_subtitle_track_candidate_2.json"),
    )
    base_sha = manifest.artifacts["timeline.json"].content_hash
    if not base_sha:
        raise ValueError("PLAYBACK_BASE_TIMELINE_HASH_MISSING")
    timeline = compile_playback_timeline_candidate_2(
        base, refinement, preview_track,
        current_dependency_hashes=dependency_hashes,
        base_timeline_sha256=base_sha,
    )
    path = registry.write_json(
        "timeline_candidate_2.json", timeline.model_dump(mode="json"),
        "playback_timeline_compilation",
    )
    registry.save_manifest()
    return path


def create_renderer_project_candidate(run_dir: Path, *, candidate_id: Literal[2, 3]) -> Path:
    """Build a separate preview-only renderer package from Timeline Candidate 2."""
    if candidate_id not in (2, 3):
        raise ValueError("PREVIEW_CANDIDATE_ID_INVALID")
    run_dir = Path(run_dir).resolve()
    manifest, registry = _load_registry(run_dir)
    _validated_dependency_hashes(registry, f"renderer_project_candidate_{candidate_id}")
    storyboard_name = "human_storyboard_candidate.json"
    storyboard = registry.read_json(storyboard_name)
    timeline = TimelineDocument.model_validate(registry.read_json("timeline_candidate_2.json"))
    composition = timeline.composition
    if composition is None or composition.preview_only is not True:
        raise ValueError("PREVIEW_RENDERER_REQUIRES_PREVIEW_TIMELINE")
    bundle_name = composition.visual_bundle_artifact
    registry.validate(bundle_name)
    bundle_dir = run_dir / bundle_name
    visual_manifest = read_json(bundle_dir / "manifest.json")
    visual_files: dict[str, bytes] = {}
    for scene in visual_manifest.get("scenes", []):
        relative = scene.get("asset_path")
        asset_path = PurePosixPath(relative) if isinstance(relative, str) else None
        if (
            asset_path is None or asset_path.is_absolute() or "\\" in relative
            or any(part in {"", ".", ".."} for part in asset_path.parts)
        ):
            raise ValueError("PREVIEW_RENDERER_ASSET_PATH_INVALID")
        target = (bundle_dir / Path(*asset_path.parts)).resolve()
        try:
            target.relative_to(bundle_dir.resolve())
        except ValueError as error:
            raise ValueError("PREVIEW_RENDERER_ASSET_PATH_INVALID") from error
        if not target.is_file():
            raise ValueError("PREVIEW_RENDERER_ASSET_MISSING")
        visual_files[asset_path.as_posix()] = target.read_bytes()
    audio_bytes = (run_dir / "audio/narration.wav").read_bytes()
    files, render_manifest = build_nikola_project(
        storyboard, timeline, audio_bytes, visual_asset_files=visual_files,
    )
    timeline_sha = manifest.artifacts["timeline_candidate_2.json"].content_hash
    storyboard_sha = manifest.artifacts[storyboard_name].content_hash
    render_manifest["inputs"]["timeline"] = {
        "path": "timeline_candidate_2.json", "sha256": timeline_sha,
    }
    render_manifest["inputs"]["storyboard"] = {
        "path": storyboard_name, "sha256": storyboard_sha,
    }
    render_manifest["renderer"].update({
        "candidate_id": candidate_id,
        "preview_only": True,
        "preview_review_status": "pending_human_preview_review",
        "full_render_requested": False,
    })
    project_path = registry.write_directory(
        f"renderer_project_candidate_{candidate_id}", files, "playback_preview_adaptation",
    )
    registry.write_json(
        f"render_manifest_candidate_{candidate_id}.json", render_manifest,
        "playback_preview_adaptation",
    )
    registry.save_manifest()
    return project_path


def record_preview_candidate(run_dir: Path, rendered_file: Path, *, candidate_id: Literal[2, 3]) -> Path:
    """Register one externally rendered local MP4 as a non-final review artifact."""
    if candidate_id not in (2, 3):
        raise ValueError("PREVIEW_CANDIDATE_ID_INVALID")
    run_dir = Path(run_dir).resolve()
    rendered_file = Path(rendered_file).resolve()
    try:
        rendered_file.relative_to(run_dir)
    except ValueError as error:
        raise ValueError("PREVIEW_RENDER_OUTPUT_OUTSIDE_RUN") from error
    if not rendered_file.is_file():
        raise ValueError("PREVIEW_RENDER_OUTPUT_MISSING")
    payload = rendered_file.read_bytes()
    if len(payload) < 12 or payload[4:8] != b"ftyp":
        raise ValueError("PREVIEW_RENDER_OUTPUT_NOT_MP4")
    manifest, registry = _load_registry(run_dir)
    _validated_dependency_hashes(registry, f"review-preview-candidate-{candidate_id}.mp4")
    render_manifest = registry.read_json(f"render_manifest_candidate_{candidate_id}.json")
    timeline = TimelineDocument.model_validate(registry.read_json("timeline_candidate_2.json"))
    renderer = render_manifest.get("renderer", {})
    if (
        render_manifest.get("run_id") != manifest.run_id
        or renderer.get("candidate_id") != candidate_id
        or renderer.get("preview_only") is not True
        or renderer.get("full_render_requested") is not False
        or renderer.get("preview_review_status") != "pending_human_preview_review"
        or timeline.composition is None
        or timeline.composition.preview_only is not True
    ):
        raise ValueError("PREVIEW_RENDER_OUTPUT_NOT_PENDING_REVIEW")
    path = registry.write_bytes(
        f"review-preview-candidate-{candidate_id}.mp4", payload, "review_preview_render",
    )
    registry.save_manifest()
    return path


def create_renderer_project_candidate_2(run_dir: Path) -> Path:
    """Compatibility owner for the original playback recovery package."""
    return create_renderer_project_candidate(run_dir, candidate_id=2)


def record_preview_candidate_2(run_dir: Path, rendered_file: Path) -> Path:
    """Compatibility owner for the original playback recovery preview."""
    return record_preview_candidate(run_dir, rendered_file, candidate_id=2)
