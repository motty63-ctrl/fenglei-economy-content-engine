"""Human-readable rendering for a validated storyboard."""
from __future__ import annotations

from fanglei.visual_models import Storyboard


def render_visual_plan(storyboard: Storyboard) -> str:
    lines = [
        "# Visual Plan", "", f"Run: `{storyboard.run_id}`", "",
        "## Timing", "", "All durations are estimated from the script; no audio timestamps exist in V0.4.", "",
        "## Renderer selection", "",
        f"- Primary route: `{storyboard.renderer_selection['primary_route']}`",
        f"- Reason: {storyboard.renderer_selection['reason']}",
        "- Final renderer invoked: no", "", "## Scenes", "",
    ]
    for scene in storyboard.scenes:
        directive = scene.renderer_directives
        lines.extend([
            f"### {scene.scene_id}: {scene.narrative_role}", "",
            f"- Sentences: {', '.join(f'`{sid}`' for sid in scene.sentence_ids)}",
            f"- Estimated duration: {scene.estimated_duration_seconds:.2f}s",
            f"- Route / structure: `{directive.primary_route}` / `{directive.structure}`",
            f"- Layout: {scene.layout}",
            f"- Introduced: {', '.join(scene.introduced_objects) or 'none'}",
            f"- Inherited: {', '.join(scene.inherited_objects) or 'none'}",
            f"- Persistent: {', '.join(scene.persistent_objects) or 'none'}",
            f"- Removed: {', '.join(scene.removed_objects) or 'none'}",
            "- Appearance order: " + " → ".join(scene.appearance_sequence),
            "",
        ])
    gate = storyboard.quality_gate
    lines.extend(["## Quality gate", "", f"- Passed: {str(bool(gate and gate.passed)).lower()}"])
    if gate:
        lines.extend([
            f"- Sentence coverage: {gate.sentence_coverage_ratio:.0%}",
            f"- Scene/sentence ratio: {gate.scene_sentence_ratio:.4f}",
            f"- Issues: {', '.join(issue.code for issue in gate.issues) or 'none'}",
        ])
    lines.append("")
    return "\n".join(lines)
