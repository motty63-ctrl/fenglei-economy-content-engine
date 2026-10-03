"""Artifact-first V0.5 narration, timeline, and renderer preparation pipeline."""
from __future__ import annotations

from pathlib import Path
from pathlib import PurePosixPath

from fanglei.audio_alignment import align_audio
from fanglei.audio_generation import generate_audio
from fanglei.narration_normalization import (
    normalize_script,
    render_tts_text,
)
from fanglei.nikola_adapter import build_nikola_project
from fanglei.paths import resolve_run_dir
from fanglei.pipeline import _execute, _load
from fanglei.artifacts import read_json, sha256_bytes
from fanglei.providers.alignment import AlignmentProvider
from fanglei.providers.narration import NarrationProvider
from fanglei.render_preflight import RendererProbe, run_render_preflight
from fanglei.timeline import compile_approved_visual_timeline, compile_timeline
from fanglei.v05_models import (
    AlignmentDocument, AudioMetadata, NarrationDocument, NarrationSynthesisConfig,
    TimelineDocument, VoiceReviewDocument,
)
from fanglei.voice_review import approve_voice, record_voice_review
from fanglei.human_visual_asset_recovery import HumanVisualAssetReviewV1
from fanglei.v1b_models import SubtitleTrack


V05_STAGES = (
    "narration_generation", "audio_generation", "audio_alignment", "timeline_compilation",
    "nikola_adaptation", "render_preflight",
)


def _timeline_storyboard_artifact(registry) -> str:
    dependencies = registry.graph["timeline.json"][1]
    return (
        "human_storyboard_candidate.json"
        if "human_storyboard_candidate.json" in dependencies else "storyboard.json"
    )


def _read_registered_visual_assets(run_dir: Path, bundle_name: str, scene_rows: list[dict]) -> dict[str, bytes]:
    root = (run_dir / bundle_name).resolve()
    if not root.is_dir():
        raise ValueError("TIMELINE_VISUAL_BUNDLE_MISSING")
    files: dict[str, bytes] = {}
    for row in scene_rows:
        relative = row.get("asset_path")
        path = PurePosixPath(relative) if isinstance(relative, str) else None
        if (
            path is None or path.is_absolute() or "\\" in relative
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise ValueError("TIMELINE_VISUAL_ASSET_PATH_INVALID")
        target = (root / Path(*path.parts)).resolve()
        try:
            target.relative_to(root)
        except ValueError as error:
            raise ValueError("TIMELINE_VISUAL_ASSET_PATH_INVALID") from error
        if not target.is_file():
            raise ValueError("TIMELINE_VISUAL_ASSET_MISSING")
        files[path.as_posix()] = target.read_bytes()
    return files


def _current_timeline_dependency_hashes(registry, manifest, dependency_names, review_dependency_names=()):
    """Return current hashes for the timeline graph and its approval's bound inputs."""
    names = dict.fromkeys((*dependency_names, *review_dependency_names))
    current: dict[str, str] = {}
    for name in names:
        if name not in registry.graph or name not in manifest.artifacts:
            raise ValueError("TIMELINE_DEPENDENCY_NOT_REGISTERED")
        registry.validate(name)
        state = manifest.artifacts[name]
        if state.status != "valid" or not state.content_hash:
            raise ValueError("TIMELINE_DEPENDENCY_NOT_CURRENT")
        current[name] = state.content_hash
    return current


def _compile_registered_timeline(run_id: str, run_dir: Path, manifest, registry, *, force: bool) -> None:
    dependency_names = registry.graph["timeline.json"][1]
    for name in dependency_names:
        registry.validate(name)
    storyboard_name = _timeline_storyboard_artifact(registry)
    alignment = AlignmentDocument.model_validate(registry.read_json("alignment.json"))
    audio = AudioMetadata.model_validate(registry.read_json("audio/metadata.json"))
    if alignment.run_id != run_id:
        raise ValueError("TIMELINE_RUN_ID_MISMATCH")
    storyboard = registry.read_json(storyboard_name)
    beats = registry.read_json("visual_beats.json")

    review_name = next((
        name for name in dependency_names if name.startswith("human_visual_asset_review_candidate_")
    ), None)
    if review_name is None:
        timeline = compile_timeline(alignment, storyboard, beats, audio)
    else:
        visual_review = HumanVisualAssetReviewV1.model_validate(registry.read_json(review_name))
        bundle_name = (
            "visual_assets" if visual_review.candidate_id == 1
            else f"visual_assets_candidate_{visual_review.candidate_id}"
        )
        bundle_dir = run_dir / bundle_name
        bundle_manifest = read_json(bundle_dir / "manifest.json")
        asset_bytes = _read_registered_visual_assets(
            run_dir, bundle_name, bundle_manifest.get("scenes", []),
        )
        subtitles = SubtitleTrack.model_validate(registry.read_json("subtitle_track.json"))
        current_hashes = _current_timeline_dependency_hashes(
            registry, manifest, dependency_names, visual_review.dependency_hashes,
        )
        timeline = compile_approved_visual_timeline(
            alignment,
            storyboard=storyboard,
            visual_beats=beats,
            audio=audio,
            visual_bundle_manifest=bundle_manifest,
            visual_bundle_sha256=current_hashes[bundle_name],
            visual_review=visual_review,
            visual_review_sha256=current_hashes[review_name],
            subtitle_track=subtitles,
            subtitle_sha256=current_hashes["subtitle_track.json"],
            dependency_hashes=current_hashes,
            asset_bytes=asset_bytes,
            storyboard_artifact_sha256=current_hashes[storyboard_name],
            storyboard_approval_sha256=current_hashes["human_storyboard_approval.json"],
            script_sha256=current_hashes["script.json"],
            script_approval_sha256=current_hashes["human_script_approval.json"],
            audio_review_sha256=current_hashes["audio/review.json"],
        )
    registry.write_json("timeline.json", timeline.model_dump(mode="json"),
                        "timeline_compilation", force=force)


def _build_registered_renderer_project(run_dir: Path, manifest, registry, *, force: bool) -> None:
    for name in registry.graph["renderer_project"][1]:
        registry.validate(name)
    storyboard_name = (
        "human_storyboard_candidate.json"
        if "human_storyboard_candidate.json" in registry.graph["renderer_project"][1]
        else "storyboard.json"
    )
    timeline = TimelineDocument.model_validate(registry.read_json("timeline.json"))
    visual_asset_files = None
    if timeline.composition is not None:
        bundle_name = timeline.composition.visual_bundle_artifact
        registry.validate(bundle_name)
        visual_asset_files = _read_registered_visual_assets(
            run_dir, bundle_name,
            [{"asset_path": scene.asset_path} for scene in timeline.composition.scene_visuals],
        )
    audio_bytes = (run_dir / "audio" / "narration.wav").read_bytes()
    files, render_manifest = build_nikola_project(
        registry.read_json(storyboard_name), timeline, audio_bytes,
        visual_asset_files=visual_asset_files,
    )
    registry.write_directory("renderer_project", files, "nikola_adaptation", force=force)
    registry.write_json("render_manifest.json", render_manifest,
                        "nikola_adaptation", force=force)


def _write_narration_artifacts(run_id: str, registry, *, force: bool) -> None:
    registry.validate("script.json")
    script = registry.read_json("script.json")
    document = normalize_script(
        script, run_id, language=script.get("target_language") or "zh-CN",
    )
    registry.write_json("narration.json", document.model_dump(mode="json"),
                        "narration_generation", force=force)
    registry.write_text("narration.txt", render_tts_text(document),
                        "narration_generation", force=force)


def run_narration_generation(run_id: str, runs_dir: Path, *, force: bool = False) -> Path:
    """Run only the formal narration owner, without requiring visual/downstream artifacts."""
    run_dir = resolve_run_dir(Path(runs_dir), run_id)
    manifest, registry = _load(run_dir)

    def stage() -> None:
        _write_narration_artifacts(run_id, registry, force=force)

    _execute(manifest, registry, "narration_generation", stage, force)
    return run_dir / "narration.json"


def run_v05_pipeline(run_id: str, runs_dir: Path, narration_provider: NarrationProvider,
                     alignment_provider: AlignmentProvider, renderer_probe: RendererProbe, *,
                     voice_id: str = "fake-voice", stop_after: str | None = None,
                     force_stage: str | None = None,
                     fallback_alignment_provider: AlignmentProvider | None = None) -> Path:
    if getattr(narration_provider, "provider_type", "fake") != "fake":
        raise ValueError("PRODUCTION_VOICE_REQUIRES_AUDIO_ONLY")
    if stop_after is not None and stop_after not in V05_STAGES:
        raise ValueError("INVALID_V05_STOP_STAGE")
    if force_stage is not None and force_stage not in V05_STAGES:
        raise ValueError("INVALID_V05_FORCE_STAGE")
    run_dir = resolve_run_dir(Path(runs_dir), run_id)
    manifest, registry = _load(run_dir)
    registry.validate("script.json")
    registry.validate("storyboard.json")

    def narration_stage() -> None:
        _write_narration_artifacts(
            run_id, registry, force=force_stage == "narration_generation",
        )

    _execute(manifest, registry, "narration_generation", narration_stage,
             force_stage == "narration_generation")
    if stop_after == "narration_generation":
        return run_dir

    audio_force = force_stage == "audio_generation"
    audio_record = manifest.artifacts.get("audio/metadata.json")
    if audio_record is not None and audio_record.status == "valid":
        current_audio = AudioMetadata.model_validate(registry.read_json("audio/metadata.json"))
        audio_force = audio_force or (
            current_audio.provider != narration_provider.name
            or current_audio.voice_id != voice_id
        )

    def audio_stage() -> None:
        narration = NarrationDocument.model_validate(registry.read_json("narration.json"))
        bundle = generate_audio(narration, narration_provider,
                                NarrationSynthesisConfig(voice_id=voice_id))
        registry.write_bytes("audio/narration.wav", bundle.audio_bytes, "audio_generation",
                             force=audio_force)
        registry.write_json("audio/metadata.json", bundle.metadata.model_dump(mode="json"),
                            "audio_generation", force=audio_force)
        registry.write_json("audio/quality.json", bundle.quality.model_dump(mode="json"),
                            "audio_generation", force=audio_force)

    _execute(manifest, registry, "audio_generation", audio_stage, audio_force)
    if stop_after == "audio_generation":
        return run_dir

    # The legacy all-fake pipeline is test infrastructure only. Its explicit test-only
    # review satisfies artifact dependencies but can never authorize production alignment.
    review_state = manifest.artifacts["audio/review.json"]
    if review_state.status != "valid" and getattr(narration_provider, "provider_type", "fake") == "fake":
        metadata = AudioMetadata.model_validate(registry.read_json("audio/metadata.json"))
        review = VoiceReviewDocument(
            run_id=run_id, audio_sha256=metadata.sha256, status="test_only", reviewer="test",
            reviewed_at=manifest.updated_at, voice_approved=True, rate_approved=True,
            pauses_approved=True, number_pronunciation_approved=True,
        )
        registry.write_json("audio/review.json", review.model_dump(mode="json"), "voice_review")
        registry.save_manifest()

    alignment_force = force_stage == "audio_alignment"
    alignment_record = manifest.artifacts.get("alignment.json")
    if alignment_record is not None and alignment_record.status == "valid":
        current_alignment = AlignmentDocument.model_validate(registry.read_json("alignment.json"))
        configured_providers = {(alignment_provider.name, alignment_provider.method)}
        if fallback_alignment_provider is not None:
            configured_providers.add(
                (fallback_alignment_provider.name, fallback_alignment_provider.method)
            )
        alignment_force = alignment_force or (
            (current_alignment.provider, current_alignment.method) not in configured_providers
        )

    def alignment_stage() -> None:
        narration = NarrationDocument.model_validate(registry.read_json("narration.json"))
        audio = AudioMetadata.model_validate(registry.read_json("audio/metadata.json"))
        result = align_audio(narration, audio, alignment_provider,
                             fallback_provider=fallback_alignment_provider)
        registry.write_json("alignment.json", result.model_dump(mode="json"), "audio_alignment",
                            force=alignment_force)

    _execute(manifest, registry, "audio_alignment", alignment_stage, alignment_force)
    if stop_after == "audio_alignment":
        return run_dir

    def timeline_stage() -> None:
        _compile_registered_timeline(
            run_id, run_dir, manifest, registry,
            force=force_stage == "timeline_compilation",
        )

    _execute(manifest, registry, "timeline_compilation", timeline_stage,
             force_stage == "timeline_compilation")
    if stop_after == "timeline_compilation":
        return run_dir

    def adaptation_stage() -> None:
        _build_registered_renderer_project(
            run_dir, manifest, registry,
            force=force_stage == "nikola_adaptation",
        )

    _execute(manifest, registry, "nikola_adaptation", adaptation_stage,
             force_stage == "nikola_adaptation")
    if stop_after == "nikola_adaptation":
        return run_dir

    def preflight_stage() -> None:
        probe_root = run_dir / ".render-preflight-temp"
        preflight, qa = run_render_preflight(
            run_dir / "renderer_project", registry.read_json("render_manifest.json"),
            renderer_probe, probe_root=probe_root,
        )
        if probe_root.exists() and not any(probe_root.iterdir()):
            try:
                probe_root.rmdir()
            except OSError:
                pass
        registry.write_json("preflight_report.json", preflight, "render_preflight",
                            force=force_stage == "render_preflight")
        registry.write_json("render_qa.json", qa, "render_preflight",
                            force=force_stage == "render_preflight")
        if not preflight["passed"] or not qa["passed"]:
            manifest.artifacts["preflight_report.json"].status = "failed"
            manifest.artifacts["render_qa.json"].status = "failed"
            registry.save_manifest()
            raise ValueError("RENDER_PREFLIGHT_FAILED")

    _execute(manifest, registry, "render_preflight", preflight_stage,
             force_stage == "render_preflight")
    manifest.status = "renderer_ready"
    registry.save_manifest()
    return run_dir


def run_timeline_compilation(run_id: str, runs_dir: Path, *, force: bool = False) -> Path:
    """Compile scene and subtitle timing from existing narration/alignment artifacts."""
    run_dir = resolve_run_dir(Path(runs_dir), run_id)
    manifest, registry = _load(run_dir)

    def stage() -> None:
        _compile_registered_timeline(run_id, run_dir, manifest, registry, force=force)

    _execute(manifest, registry, "timeline_compilation", stage, force)
    return run_dir / "timeline.json"


def run_nikola_adaptation(run_id: str, runs_dir: Path, *, force: bool = False) -> Path:
    """Build the renderer project from current visuals, timeline, and existing audio."""
    run_dir = resolve_run_dir(Path(runs_dir), run_id)
    manifest, registry = _load(run_dir)

    def stage() -> None:
        timeline = TimelineDocument.model_validate(registry.read_json("timeline.json"))
        if timeline.run_id != run_id:
            raise ValueError("NIKOLA_RUN_ID_MISMATCH")
        _build_registered_renderer_project(run_dir, manifest, registry, force=force)

    _execute(manifest, registry, "nikola_adaptation", stage, force)
    return run_dir / "renderer_project"


def run_voice_generation(run_id: str, runs_dir: Path, provider: NarrationProvider,
                         config: NarrationSynthesisConfig, *, force: bool = False) -> Path:
    """Generate and validate a real audio bundle, then stop for human listening review."""
    if getattr(provider, "provider_type", None) != "real":
        raise ValueError("PRODUCTION_PROVIDER_REQUIRED")
    run_dir = resolve_run_dir(Path(runs_dir), run_id)
    manifest, registry = _load(run_dir)
    registry.validate("narration.json")
    registry.validate("narration.txt")
    current_state = manifest.artifacts["audio/narration.wav"]
    if current_state.status == "valid" and not force:
        raise ValueError("AUDIO_ALREADY_VALID_USE_FORCE")
    if force:
        for name in ("audio/narration.wav", "audio/metadata.json", "audio/quality.json"):
            state = manifest.artifacts[name]
            if state.status == "valid":
                state.status = "stale"
                registry._invalidate_descendants(name)
        registry.save_manifest()

    def stage() -> None:
        narration = NarrationDocument.model_validate(registry.read_json("narration.json"))
        bundle = generate_audio(narration, provider, config, production=True)
        registry.write_bytes("audio/narration.wav", bundle.audio_bytes, "audio_generation", force=True)
        registry.write_json("audio/metadata.json", bundle.metadata.model_dump(mode="json"),
                            "audio_generation", force=True)
        registry.write_json("audio/quality.json", bundle.quality.model_dump(mode="json"),
                            "audio_generation", force=True)

    _execute(manifest, registry, "audio_generation", stage, force=True)
    manifest.status = "voice_review_pending"
    registry.save_manifest()
    return run_dir


def approve_voice_run(run_id: str, runs_dir: Path, *, reviewer: str,
                      voice: bool, rate: bool, pauses: bool,
                      number_pronunciation: bool) -> Path:
    """Persist human approval for the current real, quality-passing audio hash."""
    run_dir = resolve_run_dir(Path(runs_dir), run_id)
    manifest, registry = _load(run_dir)
    registry.validate("script.json")
    registry.validate("audio/narration.wav")
    audio = AudioMetadata.model_validate(registry.read_json("audio/metadata.json"))
    quality = registry.read_json("audio/quality.json")
    if audio.provider_type != "real" or not quality["production_eligible"]:
        raise ValueError("PRODUCTION_AUDIO_QUALITY_REQUIRED")
    if quality["audio_sha256"] != audio.sha256:
        raise ValueError("AUDIO_QUALITY_HASH_MISMATCH")
    review = approve_voice(run_id, audio.sha256, reviewer=reviewer, voice=voice,
                           rate=rate, pauses=pauses,
                           number_pronunciation=number_pronunciation,
                           script_sha256=manifest.artifacts["script.json"].content_hash)
    registry.write_json("audio/review.json", review.model_dump(mode="json"),
                        "voice_review", force=True)
    manifest.status = "voice_approved"
    registry.save_manifest()
    return run_dir


def record_voice_review_run(
    run_id: str,
    runs_dir: Path,
    *,
    reviewer: str,
    status: str,
    reason_code: str | None = None,
    findings: list[str] | None = None,
    voice: bool,
    rate: bool,
    pauses: bool,
    number_pronunciation: bool,
) -> Path:
    """Persist a human audio decision through the registered voice-review owner."""
    if status not in {"approved", "changes_required"}:
        raise ValueError("VOICE_REVIEW_STATUS_INVALID")
    run_dir = resolve_run_dir(Path(runs_dir), run_id)
    manifest, registry = _load(run_dir)
    registry.validate("script.json")
    registry.validate("audio/narration.wav")
    audio = AudioMetadata.model_validate(registry.read_json("audio/metadata.json"))
    quality = registry.read_json("audio/quality.json")
    actual_sha = sha256_bytes((run_dir / audio.path).read_bytes())
    if actual_sha != audio.sha256:
        raise ValueError("AUDIO_METADATA_HASH_MISMATCH")
    if audio.provider_type != "real" or not quality.get("production_eligible"):
        raise ValueError("PRODUCTION_AUDIO_QUALITY_REQUIRED")
    if quality.get("audio_sha256") != actual_sha:
        raise ValueError("AUDIO_QUALITY_HASH_MISMATCH")
    script_sha = manifest.artifacts["script.json"].content_hash
    if not script_sha:
        raise ValueError("SCRIPT_HASH_REQUIRED_FOR_AUDIO_REVIEW")
    review = record_voice_review(
        run_id, actual_sha, reviewer=reviewer, status=status,
        script_sha256=script_sha, voice=voice, rate=rate, pauses=pauses,
        number_pronunciation=number_pronunciation, reason_code=reason_code,
        findings=findings,
    )
    registry.write_json("audio/review.json", review.model_dump(mode="json"),
                        "voice_review", force=True)
    manifest.status = (
        "voice_approved" if status == "approved" else "voice_review_changes_required"
    )
    registry.save_manifest()
    return run_dir / "audio" / "review.json"
