"""Artifact-first V0.3 content planning pipeline."""
from __future__ import annotations
import re
from pathlib import Path
from fanglei.angle_policy import score_angles, select_angle
from fanglei.content_models import AngleCandidate, ScriptDraft
from fanglei.content_policy import build_fact_palette
from fanglei.content_render import render_angle_markdown, render_script_json, render_script_markdown
from fanglei.paths import resolve_run_dir
from fanglei.pipeline import _execute, _load
from fanglei.providers.content import AngleGenerationInput, ContentPlanningProvider, ScriptGenerationInput
from fanglei.script_lint import lint_script


def run_content_pipeline(run_id: str, runs_dir: Path, provider: ContentPlanningProvider, *,
                         stop_after: str | None = None, force_stage: str | None = None,
                         angle_id: str | None = None, speaking_rate: float = 4.0) -> Path:
    run_dir = resolve_run_dir(Path(runs_dir), run_id)
    manifest, registry = _load(run_dir)
    facts = registry.read_json("facts.json")
    palette = build_fact_palette(facts)
    if not palette: raise ValueError("NO_SCRIPT_READY_FACTS")
    source_text = (run_dir / "source.md").read_text(encoding="utf-8")
    research = (run_dir / "research.md").read_text(encoding="utf-8")
    questions = registry.read_json("questions.json")

    def generate_angles() -> None:
        proposed = provider.generate_angles(AngleGenerationInput(run_id=run_id,
            core_topic=questions.get("core_topic", ""),
            research_questions=[q.get("question", "") for q in questions.get("research_questions", [])],
            research_md=research, fact_palette=palette))
        candidates = score_angles(proposed.candidates, palette, source_text)
        if len([c for c in candidates if c.eligibility == "eligible"]) < 3:
            raise ValueError("AT_LEAST_THREE_DISTINCT_ANGLES_REQUIRED")
        recommended = select_angle(candidates)
        registry.write_json("angles.json", {"schema_version": "3.0", "run_id": run_id,
            "provider": {"name": provider.name, "model": provider.model, "prompt_version": provider.angle_prompt_version},
            "recommended_angle_id": recommended.angle_id,
            "candidates": [c.model_dump(mode="json") for c in candidates]},
            "angle_generation", force=force_stage == "angle_generation")
    _execute(manifest, registry, "angle_generation", generate_angles, force_stage == "angle_generation")
    if stop_after == "angle_generation": return run_dir

    existing_selected = None
    if (run_dir / "angle.md").is_file():
        match = re.search(r"selected_angle_id: `([^`]+)`", (run_dir / "angle.md").read_text(encoding="utf-8"))
        existing_selected = match.group(1) if match else None
    force_select = force_stage == "angle_selection" or bool(angle_id and angle_id != existing_selected)
    def choose_angle() -> None:
        artifact = registry.read_json("angles.json")
        candidates = [AngleCandidate.model_validate(row) for row in artifact["candidates"]]
        chosen = select_angle(candidates, angle_id or artifact["recommended_angle_id"])
        registry.write_text("angle.md", render_angle_markdown(chosen), "angle_selection", force=force_select)
    _execute(manifest, registry, "angle_selection", choose_angle, force_select)
    if stop_after == "angle_selection": return run_dir

    force_script = force_stage == "script_generation"
    if (run_dir / "script.json").is_file():
        old = registry.read_json("script.json") if manifest.artifacts["script.json"].status == "valid" else {}
        force_script = force_script or old.get("speaking_rate_chars_per_second") != speaking_rate
    selected_id = re.search(r"selected_angle_id: `([^`]+)`", (run_dir / "angle.md").read_text(encoding="utf-8")).group(1)
    angles = registry.read_json("angles.json")
    selected = AngleCandidate.model_validate(next(row for row in angles["candidates"] if row["angle_id"] == selected_id))
    def generate_script() -> None:
        draft = provider.generate_script(ScriptGenerationInput(run_id=run_id, selected_angle=selected,
            research_md=research, fact_palette=palette))
        lint = lint_script(draft, selected, facts, source_text, speaking_rate=speaking_rate)
        registry.write_json("script.json", render_script_json(draft, lint), "script_generation", force=force_script)
    _execute(manifest, registry, "script_generation", generate_script, force_script)
    if stop_after == "script_generation": return run_dir

    def render_script() -> None:
        payload = registry.read_json("script.json")
        draft = ScriptDraft.model_validate(payload)
        lint = lint_script(draft, selected, facts, source_text,
                           speaking_rate=payload["speaking_rate_chars_per_second"])
        registry.write_text("script.md", render_script_markdown(draft, lint), "script_render",
                            force=force_stage == "script_render" or manifest.artifacts["script.md"].status == "stale")
    _execute(manifest, registry, "script_render", render_script, force_stage == "script_render")
    manifest.status = "scripted"
    registry.save_manifest()
    return run_dir
