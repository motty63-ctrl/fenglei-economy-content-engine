"""Artifact-first V0.4 semantic and render visual planning pipeline."""
from __future__ import annotations

from pathlib import Path

from fanglei.paths import resolve_run_dir
from fanglei.pipeline import _execute, _load
from fanglei.providers.visual import VisualPlanningProvider, VisualPlanningRequest
from fanglei.storyboard import build_storyboard
from fanglei.storyboard_quality import lint_storyboard
from fanglei.visual_models import VisualBeatPlan
from fanglei.visual_render import render_visual_plan


VISUAL_STAGES = {"visual_planning", "storyboard_generation", "visual_plan_render"}


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

    def plan_beats() -> None:
        plan = provider.plan(VisualPlanningRequest(
            run_id=run_id, script=script, allowed_claim_ids=allowed_claim_ids,
        ))
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
