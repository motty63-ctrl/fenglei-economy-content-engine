"""Artifact-first V0.4 semantic and render visual planning pipeline."""
from __future__ import annotations

from pathlib import Path
import wave

from fanglei.artifact_registry import ArtifactRegistry
from fanglei.artifacts import read_json, sha256_bytes
from fanglei.angle_selection import HumanAngleSelectionV1
from fanglei.models import RunManifest
from fanglei.paths import resolve_run_dir
from fanglei.pipeline import _execute, _load
from fanglei.providers.visual import VisualPlanningProvider, VisualPlanningRequest
from fanglei.storyboard import build_storyboard
from fanglei.storyboard_quality import lint_storyboard
from fanglei.visual_models import VisualBeatPlan
from fanglei.visual_render import render_visual_plan
from fanglei.visual_timing import apply_alignment_derived_timing, build_timing_aware_context, validate_timed_scene_coverage


VISUAL_STAGES = {"visual_planning", "storyboard_generation", "visual_plan_render"}


def build_timing_aware_visual_request(run_id: str, runs_dir: Path) -> VisualPlanningRequest:
    """Validate current V0.2 media dependencies and build a request without writes."""
    run_dir = resolve_run_dir(Path(runs_dir), run_id)
    manifest = RunManifest.model_validate(read_json(run_dir / "run.json"))
    if manifest.run_id != run_id:
        raise ValueError("VISUAL_TIMING_RUN_ID_MISMATCH")
    registry = ArtifactRegistry(
        run_dir, manifest, timing_aware_storyboard_mode=True,
    )
    if "angle_selection.json" not in registry.graph:
        raise ValueError("TIMING_AWARE_STORYBOARD_REQUIRES_HUMAN_ANGLE_SELECTION")
    # These two owner roots cover the full identity/audio/timing dependency set:
    # script approval covers the selected angle and script chain; subtitle covers
    # alignment, voice review, audio metadata, quality, and narration.
    for name in ("human_script_approval.json", "subtitle_track.json"):
        registry.validate(name)

    script = read_json(run_dir / "script.json")
    facts = read_json(run_dir / "facts.json")
    angles = read_json(run_dir / "angles.json")
    selection_raw = read_json(run_dir / "angle_selection.json")
    selection = HumanAngleSelectionV1.model_validate(selection_raw)
    candidates = angles.get("candidates", angles.get("angles", []))
    selected_angle = next((row for row in candidates
                           if row.get("angle_id") == selection.selected_angle_id), None)
    if selected_angle is None:
        raise ValueError("VISUAL_TIMING_SELECTED_ANGLE_MISSING")

    audio_path = run_dir / "audio/narration.wav"
    audio_bytes = audio_path.read_bytes()
    actual_audio_sha256 = sha256_bytes(audio_bytes)
    with wave.open(str(audio_path), "rb") as audio_stream:
        duration_ms = round(audio_stream.getnframes() * 1000 / audio_stream.getframerate())
    audio_metadata = read_json(run_dir / "audio/metadata.json")
    audio_quality = read_json(run_dir / "audio/quality.json")
    voice_review = read_json(run_dir / "audio/review.json")
    alignment = read_json(run_dir / "alignment.json")
    subtitle = read_json(run_dir / "subtitle_track.json")
    narration = read_json(run_dir / "narration.json")
    script_approval = read_json(run_dir / "human_script_approval.json")

    hashes = {name: manifest.artifacts[name].content_hash for name in (
        "script.json", "facts.json", "angles.json", "angle_selection.json",
        "script_terminology.json", "human_script_edit.json", "audio/review.json",
        "alignment.json", "subtitle_track.json",
    )}
    if any(not value for value in hashes.values()):
        raise ValueError("VISUAL_TIMING_REGISTRY_HASH_MISSING")
    context = build_timing_aware_context(
        run_id=run_id,
        script=script,
        script_sha256=hashes["script.json"],
        facts=facts,
        facts_sha256=hashes["facts.json"],
        selected_angle=selected_angle,
        angle_selection=selection_raw,
        angle_selection_sha256=hashes["angle_selection.json"],
        angles_sha256=hashes["angles.json"],
        script_approval=script_approval,
        script_terminology_sha256=hashes["script_terminology.json"],
        human_script_edit_sha256=hashes["human_script_edit.json"],
        narration=narration,
        audio_metadata=audio_metadata,
        actual_audio_sha256=actual_audio_sha256,
        actual_audio_duration_ms=duration_ms,
        audio_quality=audio_quality,
        voice_review=voice_review,
        voice_review_sha256=hashes["audio/review.json"],
        alignment=alignment,
        alignment_sha256=hashes["alignment.json"],
        subtitle_track=subtitle,
        subtitle_sha256=hashes["subtitle_track.json"],
    )
    return VisualPlanningRequest(
        run_id=run_id,
        script=script,
        allowed_claim_ids=set(context.allowed_claim_ids),
        timing_context=context,
    )


def run_visual_pipeline(run_id: str, runs_dir: Path, provider: VisualPlanningProvider, *,
                        stop_after: str | None = None, force_stage: str | None = None) -> Path:
    if stop_after is not None and stop_after not in VISUAL_STAGES:
        raise ValueError("INVALID_VISUAL_STOP_STAGE")
    if force_stage is not None and force_stage not in VISUAL_STAGES:
        raise ValueError("INVALID_VISUAL_FORCE_STAGE")
    run_dir = resolve_run_dir(Path(runs_dir), run_id)
    manifest, registry = _load(run_dir)
    script = registry.read_json("script.json")
    facts = registry.read_json("facts.json")
    registry.validate("angle.md")
    allowed_claim_ids = {
        row["claim_id"] for row in facts.get("claims", [])
        if row.get("verification_status") == "verified" and row.get("allowed_downstream") is True
    }
    timing_aware = "alignment.json" in registry.graph["storyboard.json"][1]

    def plan_beats() -> None:
        request = (build_timing_aware_visual_request(run_id, runs_dir) if timing_aware else
                   VisualPlanningRequest(run_id=run_id, script=script,
                                        allowed_claim_ids=allowed_claim_ids))
        plan = provider.plan(request)
        plan.provider = {"name": provider.name, "model": provider.model,
                         "prompt_version": provider.prompt_version}
        expected = [row["sentence_id"] for row in script.get("sentences", [])]
        actual = [sid for beat in plan.beats for sid in beat.sentence_ids]
        if actual != expected:
            raise ValueError("VISUAL_BEAT_SENTENCE_COVERAGE_INVALID")
        registry.write_json("visual_beats.json", plan.model_dump(mode="json"), "visual_planning",
                            force=force_stage == "visual_planning")

    _execute(manifest, registry, "visual_planning", plan_beats, force_stage == "visual_planning")
    if stop_after == "visual_planning":
        return run_dir

    def assemble_storyboard() -> None:
        plan = VisualBeatPlan.model_validate(registry.read_json("visual_beats.json"))
        storyboard = build_storyboard(plan, script, facts)
        if timing_aware:
            request = build_timing_aware_visual_request(run_id, runs_dir)
            validate_timed_scene_coverage(plan, request.timing_context, script)
            storyboard = apply_alignment_derived_timing(storyboard, plan, request.timing_context)
        gate = lint_storyboard(storyboard, script, facts)
        storyboard.quality_gate = gate
        if not gate.passed:
            raise ValueError("STORYBOARD_QUALITY_FAILED:" + ",".join(issue.code for issue in gate.issues))
        registry.write_json("storyboard.json", storyboard.model_dump(mode="json"),
                            "storyboard_generation", force=force_stage == "storyboard_generation")

    _execute(manifest, registry, "storyboard_generation", assemble_storyboard,
             force_stage == "storyboard_generation")
    if stop_after == "storyboard_generation":
        return run_dir

    def render_plan() -> None:
        from fanglei.visual_models import Storyboard
        storyboard = Storyboard.model_validate(registry.read_json("storyboard.json"))
        registry.write_text("visual_plan.md", render_visual_plan(storyboard), "visual_plan_render",
                            force=force_stage == "visual_plan_render")

    _execute(manifest, registry, "visual_plan_render", render_plan, force_stage == "visual_plan_render")
    manifest.status = "visual_planned"
    registry.save_manifest()
    return run_dir
