"""Independently rerunnable V1.0b subtitle and mastering stages."""

from __future__ import annotations

from pathlib import Path

from .audio_mastering import master_audio
from .paths import resolve_run_dir
from .pipeline import _execute, _load
from .providers.mastering import AudioMasteringEngine
from .subtitle_generation import compile_subtitle_track
from .content_models import ScriptDraft
from .v05_models import AlignmentDocument, AudioMetadata, VoiceReviewDocument


def run_subtitle_generation(run_id: str, runs_dir: Path, *, force: bool = False) -> Path:
    run_dir = resolve_run_dir(Path(runs_dir), run_id)
    manifest, registry = _load(run_dir)

    def stage() -> None:
        registry.validate("script.json"); registry.validate("alignment.json")
        script = ScriptDraft.model_validate(registry.read_json("script.json"))
        alignment = AlignmentDocument.model_validate(registry.read_json("alignment.json"))
        track = compile_subtitle_track(
            script, alignment,
            script_sha256=manifest.artifacts["script.json"].content_hash or "",
            alignment_sha256=manifest.artifacts["alignment.json"].content_hash or "",
            run_id=run_id,
        )
        registry.write_json("subtitle_track.json", track.model_dump(mode="json"),
                            "subtitle_generation", force=force)

    _execute(manifest, registry, "subtitle_generation", stage, force)
    return run_dir


def run_audio_mastering(run_id: str, runs_dir: Path, engine: AudioMasteringEngine, *,
                        force: bool = False) -> Path:
    run_dir = resolve_run_dir(Path(runs_dir), run_id)
    manifest, registry = _load(run_dir)

    def stage() -> None:
        for name in ("audio/narration.wav", "audio/metadata.json", "audio/quality.json",
                     "audio/review.json"):
            registry.validate(name)
        metadata = AudioMetadata.model_validate(registry.read_json("audio/metadata.json"))
        quality = registry.read_json("audio/quality.json")
        review = VoiceReviewDocument.model_validate(registry.read_json("audio/review.json"))
        if not quality.get("production_eligible") or quality.get("audio_sha256") != metadata.sha256:
            raise ValueError("MASTERING_INPUT_QUALITY_FAILED")
        result = master_audio(run_dir / "audio" / "narration.wav", metadata, review, engine,
                              run_id=run_id)
        try:
            registry.write_bytes("audio/mastered_narration.wav", result.audio_bytes,
                                 "audio_mastering", force=force)
            registry.write_json("audio_mastering.json", result.document.model_dump(mode="json"),
                                "audio_mastering", force=force)
        except Exception:
            for name in ("audio/mastered_narration.wav", "audio_mastering.json"):
                state = manifest.artifacts[name]
                if state.status == "valid": state.status = "failed"
            registry.save_manifest()
            raise

    _execute(manifest, registry, "audio_mastering", stage, force)
    return run_dir
