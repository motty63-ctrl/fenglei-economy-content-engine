"""Artifact-first V0.5 narration, timeline, and renderer preparation pipeline."""
from __future__ import annotations

from pathlib import Path

from fanglei.audio_alignment import align_audio
from fanglei.audio_generation import generate_audio
from fanglei.narration_normalization import normalize_script, render_narration_text
from fanglei.nikola_adapter import build_nikola_project
from fanglei.paths import resolve_run_dir
from fanglei.pipeline import _execute, _load
from fanglei.providers.alignment import AlignmentProvider
from fanglei.providers.narration import NarrationProvider
from fanglei.render_preflight import RendererProbe, run_render_preflight
from fanglei.timeline import compile_timeline
from fanglei.v05_models import (
    AlignmentDocument, AudioMetadata, NarrationDocument, NarrationSynthesisConfig,
    TimelineDocument, VoiceReviewDocument,
)
from fanglei.voice_review import approve_voice


V05_STAGES = (
    "narration_generation", "audio_generation", "audio_alignment", "timeline_compilation",
    "nikola_adaptation", "render_preflight",
)


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
        document = normalize_script(registry.read_json("script.json"), run_id)
        registry.write_json("narration.json", document.model_dump(mode="json"),
                            "narration_generation", force=force_stage == "narration_generation")
        registry.write_text("narration.txt", render_narration_text(document),
                            "narration_generation", force=force_stage == "narration_generation")

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
        alignment = AlignmentDocument.model_validate(registry.read_json("alignment.json"))
        audio = AudioMetadata.model_validate(registry.read_json("audio/metadata.json"))
        timeline = compile_timeline(alignment, registry.read_json("storyboard.json"),
                                    registry.read_json("visual_beats.json"), audio)
        registry.write_json("timeline.json", timeline.model_dump(mode="json"),
                            "timeline_compilation", force=force_stage == "timeline_compilation")

    _execute(manifest, registry, "timeline_compilation", timeline_stage,
             force_stage == "timeline_compilation")
    if stop_after == "timeline_compilation":
        return run_dir

    def adaptation_stage() -> None:
        timeline = TimelineDocument.model_validate(registry.read_json("timeline.json"))
        files, render_manifest = build_nikola_project(
            registry.read_json("storyboard.json"), timeline,
            (run_dir / "audio" / "narration.wav").read_bytes(),
        )
        registry.write_directory("renderer_project", files, "nikola_adaptation",
                                 force=force_stage == "nikola_adaptation")
        registry.write_json("render_manifest.json", render_manifest, "nikola_adaptation",
                            force=force_stage == "nikola_adaptation")

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
        for name in (
            "alignment.json", "storyboard.json", "visual_beats.json",
            "audio/narration.wav", "audio/metadata.json",
        ):
            registry.validate(name)
        alignment = AlignmentDocument.model_validate(registry.read_json("alignment.json"))
        audio = AudioMetadata.model_validate(registry.read_json("audio/metadata.json"))
        if alignment.run_id != run_id:
            raise ValueError("TIMELINE_RUN_ID_MISMATCH")
        timeline = compile_timeline(
            alignment, registry.read_json("storyboard.json"),
            registry.read_json("visual_beats.json"), audio,
        )
        registry.write_json("timeline.json", timeline.model_dump(mode="json"),
                            "timeline_compilation", force=force)

    _execute(manifest, registry, "timeline_compilation", stage, force)
    return run_dir / "timeline.json"


def run_nikola_adaptation(run_id: str, runs_dir: Path, *, force: bool = False) -> Path:
    """Build the renderer project from current visuals, timeline, and existing audio."""
    run_dir = resolve_run_dir(Path(runs_dir), run_id)
    manifest, registry = _load(run_dir)

    def stage() -> None:
        for name in ("storyboard.json", "timeline.json", "audio/narration.wav"):
            registry.validate(name)
        timeline = TimelineDocument.model_validate(registry.read_json("timeline.json"))
        if timeline.run_id != run_id:
            raise ValueError("NIKOLA_RUN_ID_MISMATCH")
        files, render_manifest = build_nikola_project(
            registry.read_json("storyboard.json"), timeline,
            (run_dir / "audio" / "narration.wav").read_bytes(),
        )
        registry.write_directory("renderer_project", files, "nikola_adaptation", force=force)
        registry.write_json("render_manifest.json", render_manifest, "nikola_adaptation",
                            force=force)

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
    registry.validate("audio/narration.wav")
    audio = AudioMetadata.model_validate(registry.read_json("audio/metadata.json"))
    quality = registry.read_json("audio/quality.json")
    if audio.provider_type != "real" or not quality["production_eligible"]:
        raise ValueError("PRODUCTION_AUDIO_QUALITY_REQUIRED")
    if quality["audio_sha256"] != audio.sha256:
        raise ValueError("AUDIO_QUALITY_HASH_MISMATCH")
    review = approve_voice(run_id, audio.sha256, reviewer=reviewer, voice=voice,
                           rate=rate, pauses=pauses,
                           number_pronunciation=number_pronunciation)
    registry.write_json("audio/review.json", review.model_dump(mode="json"),
                        "voice_review", force=True)
    manifest.status = "voice_approved"
    registry.save_manifest()
    return run_dir
