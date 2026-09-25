"""Independently rerunnable V1.0b subtitle and mastering stages."""

from __future__ import annotations

from pathlib import Path
import json

from .audio_mastering import master_audio
from .paths import resolve_run_dir
from .pipeline import _execute, _load
from .providers.mastering import AudioMasteringEngine
from .subtitle_generation import compile_subtitle_track
from .content_models import ScriptDraft
from .v05_models import AlignmentDocument, AudioMetadata, VoiceReviewDocument
from .v1b_models import AudioMasteringDocument, SubtitleTrack
from .visual_project_v1b import build_v1b_renderer_project


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


def run_v1b_render_adaptation(run_id: str, runs_dir: Path, *, force: bool = False) -> Path:
    """Overlay approved V1.0b media onto the frozen V1.0a project."""
    run_dir = resolve_run_dir(Path(runs_dir), run_id)
    manifest, registry = _load(run_dir)

    def stage() -> None:
        for name in ("storyboard.json", "timeline.json", "subtitle_track.json",
                     "audio/mastered_narration.wav", "audio_mastering.json"):
            registry.validate(name)
        base_dir = run_dir / "renderer_project_v1a"
        base_manifest_path = run_dir / "render_manifest_v1a.json"
        if base_dir.is_dir() and base_manifest_path.is_file():
            base_manifest = json.loads(base_manifest_path.read_text(encoding="utf-8"))
        else:
            # The generic V0.5 Nikola project is the normal base for cases that do
            # not use the isolated GDP V1.0a calibration renderer.
            registry.validate("renderer_project")
            registry.validate("render_manifest.json")
            base_dir = run_dir / "renderer_project"
            base_manifest_path = run_dir / "render_manifest.json"
            base_manifest = registry.read_json("render_manifest.json")
        if not base_dir.is_dir():
            raise ValueError("V1B_BASE_PROJECT_MISSING")
        base_files: dict[str, str | bytes] = {}
        for path in base_dir.rglob("*"):
            if path.is_file():
                relative = path.relative_to(base_dir).as_posix()
                base_files[relative] = (path.read_bytes() if path.suffix == ".wav"
                                        else path.read_text(encoding="utf-8"))
        if not base_manifest_path.is_file():
            raise ValueError("V1B_BASE_MANIFEST_MISSING")
        files, adapted = build_v1b_renderer_project(
            base_files, base_manifest,
            SubtitleTrack.model_validate(registry.read_json("subtitle_track.json")),
            AudioMasteringDocument.model_validate(registry.read_json("audio_mastering.json")),
            (run_dir / "audio" / "mastered_narration.wav").read_bytes(),
        )
        registry.write_directory("renderer_project_v1b", files, "v1b_render_adaptation",
                                 force=force)
        registry.write_json("render_manifest_v1b.json", adapted, "v1b_render_adaptation",
                            force=force)

    _execute(manifest, registry, "v1b_render_adaptation", stage, force)
    return run_dir
