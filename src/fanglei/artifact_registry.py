"""Owner-enforced artifact registry with dependency invalidation."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import json
import shutil
import tempfile

from fanglei.artifacts import (
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_text,
    read_json,
    sha256_bytes,
    sha256_text,
)
from fanglei.errors import ArtifactConflictError
from fanglei.models import ArtifactState, RunManifest


ARTIFACT_GRAPH: dict[str, tuple[str, tuple[str, ...]]] = {
    "source.md": ("ingest", ()),
    "checkpoint_authoring_binding": ("checkpoint_authoring_binding", ()),
    "questions.json": ("analyze", ("source.md",)),
    "search_results.json": ("search", ("questions.json",)),
    "source_documents/index.json": ("source_fetch", ("search_results.json",)),
    "sources.json": ("source_selection", ("search_results.json", "source_documents/index.json")),
    "facts.json": ("factcheck", ("questions.json", "sources.json", "source_documents/index.json")),
    "research.md": ("research_synthesis", ("questions.json", "sources.json", "facts.json")),
    "angles.json": (
        "angle_generation", ("facts.json", "research.md", "questions.json", "source.md", "sources.json")
    ),
    "angle.md": ("angle_selection", ("angles.json", "facts.json")),
    "script.json": ("script_generation", ("angle.md", "facts.json", "research.md", "source.md")),
    "script.md": ("script_render", ("script.json",)),
    "visual_beats.json": ("visual_planning", ("script.json", "facts.json", "angle.md")),
    "storyboard.json": ("storyboard_generation", ("visual_beats.json", "script.json", "facts.json")),
    "visual_plan.md": ("visual_plan_render", ("storyboard.json",)),
    "narration.json": ("narration_generation", ("script.json",)),
    "narration.txt": ("narration_generation", ("narration.json",)),
    "audio/narration.wav": ("audio_generation", ("narration.json", "narration.txt")),
    "audio/metadata.json": ("audio_generation", ("audio/narration.wav", "narration.json")),
    "audio/quality.json": ("audio_generation", ("audio/narration.wav", "audio/metadata.json")),
    "audio/review.json": ("voice_review", ("audio/narration.wav", "audio/quality.json")),
    "alignment_candidate.json": ("audio_alignment", ("narration.json", "audio/narration.wav", "audio/metadata.json", "audio/quality.json", "audio/review.json")),
    "alignment_review.json": ("alignment_review", ("alignment_candidate.json", "audio/review.json")),
    "alignment.json": ("audio_alignment", ("narration.json", "audio/narration.wav", "audio/metadata.json", "audio/quality.json", "audio/review.json")),
    "timeline.json": ("timeline_compilation", ("alignment.json", "storyboard.json", "visual_beats.json", "audio/metadata.json")),
    "renderer_project": ("nikola_adaptation", ("storyboard.json", "timeline.json")),
    "render_manifest.json": ("nikola_adaptation", ("storyboard.json", "timeline.json", "renderer_project")),
    "preflight_report.json": ("render_preflight", ("render_manifest.json", "renderer_project")),
    "render_qa.json": ("render_preflight", ("render_manifest.json", "renderer_project", "preflight_report.json")),
    "subtitle_track.json": ("subtitle_generation", ("script.json", "alignment.json")),
    "audio/mastered_narration.wav": (
        "audio_mastering",
        ("audio/narration.wav", "audio/metadata.json", "audio/quality.json", "audio/review.json"),
    ),
    "audio_mastering.json": (
        "audio_mastering",
        (
            "audio/narration.wav", "audio/metadata.json", "audio/quality.json",
            "audio/review.json", "audio/mastered_narration.wav",
        ),
    ),
    "renderer_project_v1b": (
        "v1b_render_adaptation",
        (
            "storyboard.json", "timeline.json", "subtitle_track.json",
            "audio/mastered_narration.wav", "audio_mastering.json",
        ),
    ),
    "render_manifest_v1b.json": (
        "v1b_render_adaptation",
        ("renderer_project_v1b", "timeline.json", "subtitle_track.json", "audio_mastering.json"),
    ),
}


def _human_angle_selection_graph(
    base_graph: dict[str, tuple[str, tuple[str, ...]]],
) -> dict[str, tuple[str, tuple[str, ...]]]:
    """Add hash-bound human selection without changing legacy/import graphs."""
    return {
        **base_graph,
        "angle_selection.json": ("human_angle_selection", ("angles.json", "facts.json")),
        "angle.md": ("angle_selection", ("angle_selection.json", "angles.json", "facts.json")),
        "script.json": (
            "script_generation",
            ("angle_selection.json", "angle.md", "facts.json", "research.md", "source.md"),
        ),
    }


def _evidence_target_graph(
    base_graph: dict[str, tuple[str, tuple[str, ...]]],
) -> dict[str, tuple[str, tuple[str, ...]]]:
    """Register explicit run-bound evidence targets as a facts input."""
    graph = dict(base_graph)
    facts_owner, facts_dependencies = graph["facts.json"]
    graph["evidence_targets.json"] = ("evidence_targets", ("sources.json",))
    graph["facts.json"] = (
        facts_owner,
        tuple(dict.fromkeys((*facts_dependencies, "evidence_targets.json"))),
    )
    return graph


def _script_terminology_graph(
    base_graph: dict[str, tuple[str, tuple[str, ...]]],
) -> dict[str, tuple[str, tuple[str, ...]]]:
    """Opt in to a human-reviewed, Facts-bound terminology artifact."""
    graph = dict(base_graph)
    graph["script_terminology.json"] = ("script_terminology_review", ("facts.json",))
    owner, dependencies = graph["script.json"]
    graph["script.json"] = (
        owner,
        tuple(dict.fromkeys((*dependencies, "script_terminology.json"))),
    )
    return graph


def _human_script_recovery_graph(
    base_graph: dict[str, tuple[str, tuple[str, ...]]],
) -> dict[str, tuple[str, tuple[str, ...]]]:
    """Opt in to a provider-free, hash-bound human script submission."""
    graph = _script_terminology_graph(base_graph)
    dependencies = [
        name for name in (
            "source.md", "research.md", "facts.json", "angles.json", "angle_selection.json",
            "script_terminology.json", "research_focus.json",
        ) if name in graph
    ]
    graph["human_script_edit.json"] = ("human_script_recovery", tuple(dependencies))
    owner, script_dependencies = graph["script.json"]
    graph["script.json"] = (
        owner, tuple(dict.fromkeys((*script_dependencies, "human_script_edit.json"))),
    )
    return graph


def _human_script_approval_graph(
    base_graph: dict[str, tuple[str, tuple[str, ...]]],
) -> dict[str, tuple[str, tuple[str, ...]]]:
    """Opt in to a hash-bound human approval required before narration."""
    graph = dict(base_graph)
    dependencies = tuple(
        name for name in (
            "research_focus.json", "facts.json", "angles.json", "angle_selection.json",
            "script_terminology.json", "human_script_edit.json", "script.json",
        ) if name in graph
    )
    graph["human_script_approval.json"] = ("human_script_approval", dependencies)
    owner, narration_dependencies = graph["narration.json"]
    graph["narration.json"] = (
        owner,
        tuple(dict.fromkeys((*narration_dependencies, "human_script_approval.json"))),
    )
    return graph


def _timing_aware_visual_graph(
    base_graph: dict[str, tuple[str, tuple[str, ...]]],
) -> dict[str, tuple[str, tuple[str, ...]]]:
    """Opt V0.2 media runs into approved-audio/alignment/subtitle storyboard inputs."""
    graph = dict(base_graph)
    visual_inputs = (
        "angle_selection.json", "human_script_approval.json", "narration.json",
        "audio/narration.wav", "audio/metadata.json", "audio/quality.json", "audio/review.json",
        "alignment.json", "subtitle_track.json",
    )
    for name in ("visual_beats.json", "storyboard.json"):
        owner, dependencies = graph[name]
        graph[name] = (owner, tuple(dict.fromkeys((*dependencies, *(
            dep for dep in visual_inputs if dep in graph
        )))))
    return graph


def _human_storyboard_recovery_graph(
    base_graph: dict[str, tuple[str, tuple[str, ...]]],
) -> dict[str, tuple[str, tuple[str, ...]]]:
    """Register a pending human-edited candidate while preserving storyboard.json."""
    graph = dict(base_graph)
    storyboard_inputs = tuple(dict.fromkeys((
        "storyboard.json", *graph["storyboard.json"][1],
    )))
    review_dependencies = tuple(
        name for name in storyboard_inputs if name in graph
    )
    graph["storyboard_review.json"] = ("human_storyboard_review", review_dependencies)
    graph["human_storyboard_edit.json"] = (
        "human_storyboard_recovery",
        tuple(dict.fromkeys(("storyboard_review.json", *review_dependencies))),
    )
    graph["human_storyboard_candidate.json"] = (
        "human_storyboard_recovery",
        tuple(dict.fromkeys((
            "storyboard.json", "storyboard_review.json", "human_storyboard_edit.json",
            *graph["storyboard.json"][1],
        ))),
    )

    graph["visual_plan.md"] = ("visual_plan_render", ("human_storyboard_candidate.json",))
    for name in ("timeline.json", "renderer_project", "render_manifest.json", "renderer_project_v1b"):
        if name in graph:
            owner, dependencies = graph[name]
            graph[name] = (
                owner,
                tuple("human_storyboard_candidate.json" if dep == "storyboard.json" else dep
                      for dep in dependencies),
            )
    return graph


def _human_storyboard_approval_graph(
    base_graph: dict[str, tuple[str, tuple[str, ...]]],
) -> dict[str, tuple[str, tuple[str, ...]]]:
    """Require a run-bound human approval before deterministic scene asset generation."""
    graph = dict(base_graph)
    candidate_inputs = tuple(graph["human_storyboard_candidate.json"][1])
    approval_dependencies = tuple(dict.fromkeys(("human_storyboard_candidate.json", *candidate_inputs)))
    graph["human_storyboard_approval.json"] = (
        "human_storyboard_approval", approval_dependencies,
    )
    graph["visual_assets"] = (
        "visual_asset_generation", ("human_storyboard_approval.json", "human_storyboard_candidate.json"),
    )
    return graph


def _human_visual_asset_recovery_graph(
    base_graph: dict[str, tuple[str, tuple[str, ...]]],
    *,
    candidate_three_timeline_enabled: bool = False,
) -> dict[str, tuple[str, tuple[str, ...]]]:
    """Keep each reviewed visual candidate immutable and recover into a new artifact."""
    graph = dict(base_graph)
    review_dependencies = (
        "visual_assets", "human_storyboard_approval.json", "human_storyboard_candidate.json",
    )
    graph["human_visual_asset_review_candidate_1.json"] = (
        "human_visual_asset_review", review_dependencies,
    )
    recovery_dependencies = (
        "human_visual_asset_review_candidate_1.json", "visual_assets",
        "human_storyboard_approval.json", "human_storyboard_candidate.json",
    )
    graph["visual_asset_recovery.json"] = (
        "visual_asset_recovery", recovery_dependencies,
    )
    graph["visual_assets_candidate_2"] = (
        "visual_asset_recovery",
        ("visual_asset_recovery.json", "human_visual_asset_review_candidate_1.json", "visual_assets"),
    )
    graph["human_visual_asset_review_candidate_2.json"] = (
        "human_visual_asset_review_candidate_2",
        (
            "visual_assets_candidate_2", "visual_asset_recovery.json",
            "human_visual_asset_review_candidate_1.json", "human_storyboard_approval.json",
            "human_storyboard_candidate.json",
        ),
    )
    graph["visual_asset_recovery_candidate_3.json"] = (
        "visual_asset_recovery_candidate_3",
        (
            "human_visual_asset_review_candidate_2.json", "visual_assets_candidate_2",
            "visual_asset_recovery.json", "human_visual_asset_review_candidate_1.json",
            "human_storyboard_approval.json", "human_storyboard_candidate.json",
        ),
    )
    graph["visual_assets_candidate_3"] = (
        "visual_asset_recovery_candidate_3",
        (
            "visual_asset_recovery_candidate_3.json", "human_visual_asset_review_candidate_2.json",
            "visual_assets_candidate_2",
        ),
    )
    graph["human_visual_asset_review_candidate_3.json"] = (
        "human_visual_asset_review_candidate_3",
        (
            "visual_assets_candidate_3", "visual_asset_recovery_candidate_3.json",
            "human_visual_asset_review_candidate_2.json", "human_storyboard_approval.json",
            "human_storyboard_candidate.json", "angle_selection.json", "facts.json",
            "script.json", "human_script_approval.json", "audio/narration.wav",
            "audio/review.json", "alignment.json", "subtitle_track.json",
        ),
    )
    if "timeline.json" in graph:
        if candidate_three_timeline_enabled:
            owner, dependencies = graph["timeline.json"]
            graph["timeline.json"] = (
                owner,
                tuple(dict.fromkeys((
                    *dependencies,
                    "angle_selection.json", "facts.json", "script.json",
                    "human_script_approval.json", "audio/narration.wav", "audio/review.json",
                    "alignment.json", "subtitle_track.json", "human_storyboard_approval.json",
                    "visual_asset_recovery_candidate_3.json", "visual_assets_candidate_3",
                    "human_visual_asset_review_candidate_3.json",
                ))),
            )
    return graph


def _playback_preview_graph(
    base_graph: dict[str, tuple[str, tuple[str, ...]]],
) -> dict[str, tuple[str, tuple[str, ...]]]:
    """Add an immutable playback-recovery branch beside the approved timeline."""
    graph = dict(base_graph)
    timeline_dependencies = base_graph.get("timeline.json", ("", ()))[1]
    visual_bundle = next((
        name for name in timeline_dependencies
        if name == "visual_assets" or name.startswith("visual_assets_candidate_")
    ), None)
    visual_review = next((
        name for name in timeline_dependencies
        if name.startswith("human_visual_asset_review_candidate_")
    ), None)
    if visual_bundle is None or visual_review is None:
        raise ArtifactConflictError("PLAYBACK_PREVIEW_REQUIRES_APPROVED_VISUAL_TIMELINE")
    graph["human_preview_review_candidate_1.json"] = (
        "human_preview_review",
        (
            "timeline.json", "renderer_project", "render_manifest.json",
            "human_storyboard_candidate.json", "human_storyboard_approval.json",
            visual_bundle, visual_review,
            "angle_selection.json", "facts.json", "script.json",
            "human_script_approval.json", "audio/narration.wav", "audio/review.json",
            "alignment.json", "subtitle_track.json",
        ),
    )
    graph["playback_timing_refinement.json"] = (
        "playback_timing_refinement",
        (
            "human_preview_review_candidate_1.json", "narration.json", "audio/narration.wav",
            "audio/metadata.json", "alignment.json", "script.json",
            "human_script_approval.json", "audio/review.json",
        ),
    )
    graph["preview_subtitle_track_candidate_2.json"] = (
        "playback_subtitle_generation",
        (
            "subtitle_track.json", "playback_timing_refinement.json", "audio/narration.wav",
            visual_bundle, visual_review,
        ),
    )
    graph["timeline_candidate_2.json"] = (
        "playback_timeline_compilation",
        (
            "timeline.json", "human_preview_review_candidate_1.json",
            visual_bundle, visual_review,
            "audio/narration.wav", "alignment.json", "playback_timing_refinement.json",
            "subtitle_track.json", "preview_subtitle_track_candidate_2.json",
            "human_storyboard_candidate.json", "human_storyboard_approval.json",
            "script.json", "human_script_approval.json", "audio/review.json",
        ),
    )
    graph["renderer_project_candidate_2"] = (
        "playback_preview_adaptation", ("timeline_candidate_2.json", "human_storyboard_candidate.json"),
    )
    graph["render_manifest_candidate_2.json"] = (
        "playback_preview_adaptation", ("timeline_candidate_2.json", "renderer_project_candidate_2"),
    )
    graph["review-preview-candidate-2.mp4"] = (
        "review_preview_render",
        ("timeline_candidate_2.json", "renderer_project_candidate_2", "render_manifest_candidate_2.json"),
    )
    graph["human_preview_review_candidate_2.json"] = (
        "human_preview_review",
        (
            "review-preview-candidate-2.mp4", "timeline_candidate_2.json",
            "render_manifest_candidate_2.json",
        ),
    )
    graph["renderer_project_candidate_3"] = (
        "playback_preview_adaptation", ("timeline_candidate_2.json", "human_storyboard_candidate.json"),
    )
    graph["render_manifest_candidate_3.json"] = (
        "playback_preview_adaptation", ("timeline_candidate_2.json", "renderer_project_candidate_3"),
    )
    graph["review-preview-candidate-3.mp4"] = (
        "review_preview_render",
        ("timeline_candidate_2.json", "renderer_project_candidate_3", "render_manifest_candidate_3.json"),
    )
    graph["human_preview_review_candidate_3.json"] = (
        "human_preview_review",
        (
            "review-preview-candidate-3.mp4", "timeline_candidate_2.json",
            "render_manifest_candidate_3.json",
        ),
    )
    return graph

# The focus profile is opt-in. Research and content planning both track the
# explicit focus; legacy runs continue to use questions.json for angle framing.
RESEARCH_FOCUS_ARTIFACT_GRAPH: dict[str, tuple[str, tuple[str, ...]]] = {
    **ARTIFACT_GRAPH,
    "research_focus.json": ("research_focus", ("sources.json", "facts.json")),
    "research.md": (
        "research_synthesis",
        ("questions.json", "sources.json", "facts.json", "research_focus.json"),
    ),
    "angles.json": (
        "angle_generation", ("facts.json", "research.md", "research_focus.json", "source.md", "sources.json")
    ),
}


def _final_render_graph(base_graph, candidate_id: int):
    """Opt in to a separate, approved export branch; never reinterpret preview nodes."""
    if candidate_id not in (1, 2, 3):
        raise ArtifactConflictError("FINAL_RENDER_PREVIEW_ID_INVALID")
    graph = dict(base_graph)
    suffix = "" if candidate_id == 1 else f"_candidate_{candidate_id}"
    timeline = "timeline.json" if candidate_id == 1 else "timeline_candidate_2.json"
    preview = "review-preview.mp4" if candidate_id == 1 else f"review-preview-candidate-{candidate_id}.mp4"
    review = f"human_preview_review_candidate_{candidate_id}.json"
    if preview not in graph:
        graph[preview] = ("review_preview_render", (timeline, f"renderer_project{suffix}", f"render_manifest{suffix}.json"))
    inputs = tuple(dict.fromkeys((
        preview, timeline, f"renderer_project{suffix}", f"render_manifest{suffix}.json",
        *graph[timeline][1],
    )))
    graph[review] = ("human_preview_review", inputs)
    approved_inputs = (review, *inputs)
    graph["final_render_request.json"] = ("final_render", approved_inputs)
    graph["renderer_project_final"] = ("final_render", ("final_render_request.json",))
    graph["render_manifest_final.json"] = ("final_render", ("final_render_request.json", "renderer_project_final"))
    graph["final.mp4"] = ("final_render", ("render_manifest_final.json", "renderer_project_final", "final_render_request.json", *approved_inputs))
    graph["final_video_candidate.json"] = ("final_render", ("final.mp4", "render_manifest_final.json", "final_render_request.json"))
    graph["final_video_qa.json"] = ("final_video_qa", ("final.mp4", "final_video_candidate.json"))
    graph["human_final_video_review.json"] = (
        "human_final_video_review", ("final_video_candidate.json", "final_video_qa.json"),
    )
    return graph

# Checkpoint imports enter the graph after research and script approval. Keep the
# ordinary graph above byte-for-byte unchanged; the importer opts into this
# separate profile through the checkpoint_import manifest stage.
IMPORTED_ARTIFACT_GRAPH: dict[str, tuple[str, tuple[str, ...]]] = {
    **ARTIFACT_GRAPH,
    "approved_checkpoint.json": ("checkpoint_import", ()),
    "import_manifest.json": ("checkpoint_materialize", ("approved_checkpoint.json",)),
    "id_mapping.json": ("checkpoint_materialize", ("approved_checkpoint.json",)),
    "source_documents/index.json": (
        "checkpoint_provenance", ("approved_checkpoint.json",)
    ),
    "sources.json": (
        "checkpoint_provenance", ("approved_checkpoint.json", "source_documents/index.json")
    ),
    "facts.json": (
        "checkpoint_materialize",
        ("approved_checkpoint.json", "sources.json", "source_documents/index.json"),
    ),
    "research.md": (
        "checkpoint_materialize", ("approved_checkpoint.json", "facts.json", "sources.json")
    ),
    "angles.json": (
        "checkpoint_materialize", ("approved_checkpoint.json", "facts.json", "research.md")
    ),
    "angle.md": ("checkpoint_materialize", ("angles.json", "facts.json")),
    "script.json": (
        "checkpoint_materialize", ("approved_checkpoint.json", "angle.md", "facts.json", "research.md")
    ),
    "script.md": ("checkpoint_materialize", ("script.json",)),
}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class ArtifactRegistry:
    def __init__(
        self,
        run_dir: Path,
        manifest: RunManifest,
        *,
        research_focus_mode: bool | None = None,
        human_angle_selection_mode: bool = False,
        evidence_targets_mode: bool = False,
        script_terminology_mode: bool = False,
        human_script_recovery_mode: bool = False,
        human_script_approval_mode: bool = False,
        timing_aware_storyboard_mode: bool | None = None,
        human_storyboard_recovery_mode: bool = False,
        human_storyboard_approval_mode: bool = False,
        human_visual_asset_recovery_mode: bool = False,
        playback_preview_mode: bool = False,
        final_render_mode: bool = False,
        final_preview_candidate_id: int | None = None,
    ):
        self.run_dir = Path(run_dir)
        self.manifest = manifest
        checkpoint_stage = manifest.stages.get("checkpoint_import")
        self.imported_checkpoint_mode = bool(
            checkpoint_stage is not None and checkpoint_stage.status == "succeeded"
        )
        playback_enabled = playback_preview_mode or any(
            (self.run_dir / name).exists() or name in manifest.artifacts
            for name in (
                "human_preview_review_candidate_1.json", "playback_timing_refinement.json",
                "preview_subtitle_track_candidate_2.json", "timeline_candidate_2.json",
                "review-preview-candidate-2.mp4",
            )
        )
        if playback_enabled:
            human_angle_selection_mode = True
            human_script_recovery_mode = True
            human_script_approval_mode = True
            human_storyboard_recovery_mode = True
            human_storyboard_approval_mode = True
            human_visual_asset_recovery_mode = True
            timing_aware_storyboard_mode = True
        if self.imported_checkpoint_mode:
            self.graph = IMPORTED_ARTIFACT_GRAPH
        else:
            focus_state = manifest.artifacts.get("research_focus.json")
            focus_enabled = research_focus_mode
            if focus_enabled is None:
                focus_enabled = (self.run_dir / "research_focus.json").is_file() or (
                    focus_state is not None and focus_state.status != "missing"
                )
            base_graph = RESEARCH_FOCUS_ARTIFACT_GRAPH if focus_enabled else ARTIFACT_GRAPH
            # Once a run has entered the registered V0.2 selection flow, any
            # later owner must use the same graph. Old manifests stay legacy.
            selection_enabled = human_angle_selection_mode or "angle_selection.json" in manifest.artifacts
            self.graph = _human_angle_selection_graph(base_graph) if selection_enabled else base_graph
            target_state = manifest.artifacts.get("evidence_targets.json")
            target_enabled = evidence_targets_mode or (self.run_dir / "evidence_targets.json").is_file() or (
                target_state is not None and target_state.status != "missing"
            )
            if target_enabled:
                self.graph = _evidence_target_graph(self.graph)
            terminology_enabled = script_terminology_mode or (
                self.run_dir / "script_terminology.json"
            ).is_file()
            if terminology_enabled:
                self.graph = _script_terminology_graph(self.graph)
            recovery_enabled = human_script_recovery_mode or (
                self.run_dir / "human_script_edit.json"
            ).is_file() or "human_script_edit.json" in manifest.artifacts
            if recovery_enabled:
                self.graph = _human_script_recovery_graph(self.graph)
            approval_enabled = human_script_approval_mode or (
                self.run_dir / "human_script_approval.json"
            ).is_file() or "human_script_approval.json" in manifest.artifacts
            if approval_enabled:
                self.graph = _human_script_approval_graph(self.graph)
            timing_artifacts = (
                "audio/narration.wav", "audio/metadata.json", "audio/quality.json",
                "audio/review.json", "alignment.json", "subtitle_track.json",
            )
            timing_present = any(
                (self.run_dir / name).is_file()
                or (name in manifest.artifacts and manifest.artifacts[name].status != "missing")
                for name in timing_artifacts
            )
            timing_enabled = timing_aware_storyboard_mode if timing_aware_storyboard_mode is not None else (
                selection_enabled and timing_present
            )
            if timing_enabled:
                if not approval_enabled:
                    self.graph = _human_script_approval_graph(self.graph)
                if not selection_enabled:
                    raise ArtifactConflictError("TIMING_AWARE_STORYBOARD_REQUIRES_HUMAN_ANGLE_SELECTION")
                self.graph = _timing_aware_visual_graph(self.graph)
            storyboard_recovery_enabled = human_storyboard_recovery_mode or any(
                (self.run_dir / name).is_file() or name in manifest.artifacts
                for name in (
                    "storyboard_review.json", "human_storyboard_edit.json",
                    "human_storyboard_candidate.json",
                )
            )
            if storyboard_recovery_enabled:
                self.graph = _human_storyboard_recovery_graph(self.graph)
            storyboard_approval_enabled = human_storyboard_approval_mode or any(
                (self.run_dir / name).is_file() or name in manifest.artifacts
                for name in ("human_storyboard_approval.json", "visual_assets")
            )
            if storyboard_approval_enabled and storyboard_recovery_enabled:
                self.graph = _human_storyboard_approval_graph(self.graph)
            elif storyboard_approval_enabled:
                raise ArtifactConflictError("STORYBOARD_APPROVAL_REQUIRES_RECOVERED_CANDIDATE")
            visual_asset_recovery_enabled = human_visual_asset_recovery_mode or any(
                (self.run_dir / name).exists() or name in manifest.artifacts
                for name in (
                    "human_visual_asset_review_candidate_1.json", "visual_asset_recovery.json",
                    "visual_assets_candidate_2", "human_visual_asset_review_candidate_2.json",
                    "visual_asset_recovery_candidate_3.json", "visual_assets_candidate_3",
                    "human_visual_asset_review_candidate_3.json",
                )
            )
            if visual_asset_recovery_enabled:
                if not storyboard_approval_enabled:
                    raise ArtifactConflictError("VISUAL_ASSET_RECOVERY_REQUIRES_STORYBOARD_APPROVAL")
                candidate_three_review_state = manifest.artifacts.get(
                    "human_visual_asset_review_candidate_3.json"
                )
                candidate_three_timeline_enabled = (
                    (self.run_dir / "human_visual_asset_review_candidate_3.json").is_file()
                    or (candidate_three_review_state is not None
                        and candidate_three_review_state.status != "missing")
                )
                self.graph = _human_visual_asset_recovery_graph(
                    self.graph,
                    candidate_three_timeline_enabled=candidate_three_timeline_enabled,
                )
            if playback_enabled:
                self.graph = _playback_preview_graph(self.graph)
            final_enabled = final_render_mode or "final_render_request.json" in manifest.artifacts or (
                self.run_dir / "final_render_request.json"
            ).exists()
            if final_enabled:
                if not playback_enabled:
                    raise ArtifactConflictError("FINAL_RENDER_REQUIRES_PLAYBACK_GRAPH")
                request_state = manifest.artifacts.get("final_render_request.json")
                # Match the review AND its media as direct request dependencies.
                # Historical timing reviews alone do not authorize this export;
                # JSON object ordering never supplies identity.
                request_dependencies = request_state.dependencies if request_state else {}
                recorded_ids = [
                    i for i in (1, 2, 3)
                    if f"human_preview_review_candidate_{i}.json" in request_dependencies
                    and ("review-preview.mp4" if i == 1 else f"review-preview-candidate-{i}.mp4") in request_dependencies
                ]
                if request_dependencies and len(recorded_ids) != 1:
                    raise ArtifactConflictError("FINAL_RENDER_APPROVAL_IDENTITY_MISSING")
                if recorded_ids and (
                    final_preview_candidate_id is not None and final_preview_candidate_id != recorded_ids[0]
                ):
                    raise ArtifactConflictError("FINAL_RENDER_PREVIEW_ID_CONFLICT")
                candidate_id = final_preview_candidate_id or (recorded_ids[0] if recorded_ids else None)
                if candidate_id is None:
                    raise ArtifactConflictError("FINAL_RENDER_PREVIEW_ID_MISSING")
                self.graph = _final_render_graph(self.graph, candidate_id)
        for name, (owner, dependencies) in self.graph.items():
            state = self.manifest.artifacts.setdefault(
                name, ArtifactState(owner=owner, dependencies={dep: "" for dep in dependencies})
            )
            # Opt-in graphs may add dependencies to artifacts that an older
            # manifest already knows about. Refresh only missing states; a
            # materialized artifact keeps the dependency hashes recorded when
            # its owner last wrote it, so stale data is never blessed here.
            if state.status == "missing":
                state.owner = owner
                state.dependencies = {dep: "" for dep in dependencies}
        if not self.imported_checkpoint_mode and timing_enabled:
            for name in ("visual_beats.json", "storyboard.json"):
                state = self.manifest.artifacts[name]
                expected_dependencies = set(self.graph[name][1])
                if state.status == "valid" and not expected_dependencies.issubset(state.dependencies):
                    state.status = "stale"
                    state.updated_at = _now()
                    self._invalidate_descendants(name)
        if not self.imported_checkpoint_mode and storyboard_recovery_enabled:
            for name in (
                "visual_plan.md", "timeline.json", "renderer_project", "render_manifest.json",
                "renderer_project_v1b", "render_manifest_v1b.json",
            ):
                state = self.manifest.artifacts.get(name)
                if state is None or state.status != "valid" or name not in self.graph:
                    continue
                expected_dependencies = set(self.graph[name][1])
                if not expected_dependencies.issubset(state.dependencies):
                    state.status = "stale"
                    state.updated_at = _now()
                    self._invalidate_descendants(name)

    def _state(self, name: str) -> ArtifactState:
        if name not in self.graph:
            raise ArtifactConflictError(f"Unknown artifact: {name}")
        return self.manifest.artifacts[name]

    def _artifact_path(self, name: str) -> Path:
        filename = "checkpoint_authoring_binding.json" if name == "checkpoint_authoring_binding" else name
        return self.run_dir / filename

    def _validate_write(self, name: str, owner: str, force: bool) -> dict[str, str]:
        state = self._state(name)
        if name == "checkpoint_authoring_binding":
            raise ArtifactConflictError(
                "CASE_BINDING_WRITE_ONCE: use bind_source_run_to_case to create the case binding"
            )
        if state.owner != owner:
            raise ArtifactConflictError(f"Only owner stage {state.owner} may write {name}")
        if state.status == "valid" and not force:
            raise ArtifactConflictError(f"Artifact already valid: {name}; use --force")
        dependency_hashes: dict[str, str] = {}
        for dep in self.graph[name][1]:
            dep_state = self._state(dep)
            if dep_state.status != "valid" or not dep_state.content_hash:
                raise ArtifactConflictError(f"Dependency {dep} is {dep_state.status}; rerun its owner stage")
            dependency_hashes[dep] = dep_state.content_hash
        return dependency_hashes

    def _invalidate_descendants(self, changed: str) -> None:
        queue = [changed]
        seen: set[str] = set()
        while queue:
            upstream = queue.pop(0)
            for name, (_, dependencies) in self.graph.items():
                if upstream in dependencies and name not in seen:
                    seen.add(name)
                    state = self._state(name)
                    if state.status == "valid":
                        state.status = "stale"
                        state.updated_at = _now()
                    queue.append(name)

    def invalidate_descendants(self, changed: str) -> None:
        """Mark registered descendants stale even when regenerated bytes match."""
        self._invalidate_descendants(changed)

    def write_text(self, name: str, value: str, owner: str, force: bool = False) -> Path:
        deps = self._validate_write(name, owner, force)
        state = self._state(name)
        old_hash = state.content_hash
        path = self._artifact_path(name)
        atomic_write_text(path, value)
        timestamp = _now()
        state.status = "valid"
        state.content_hash = sha256_text(value)
        state.created_at = state.created_at or timestamp
        state.updated_at = timestamp
        state.dependencies = deps
        if old_hash != state.content_hash and (old_hash or name == "research_focus.json"):
            self._invalidate_descendants(name)
        return path

    def write_json(self, name: str, value: Any, owner: str, force: bool = False) -> Path:
        import json

        return self.write_text(name, json.dumps(value, ensure_ascii=False, indent=2) + "\n", owner, force)

    def write_bytes(self, name: str, value: bytes, owner: str, force: bool = False) -> Path:
        deps = self._validate_write(name, owner, force)
        state = self._state(name)
        old_hash = state.content_hash
        path = self._artifact_path(name)
        atomic_write_bytes(path, value)
        timestamp = _now()
        state.status = "valid"
        state.content_hash = sha256_bytes(value)
        state.created_at = state.created_at or timestamp
        state.updated_at = timestamp
        state.dependencies = deps
        if old_hash and old_hash != state.content_hash:
            self._invalidate_descendants(name)
        return path

    def write_directory(self, name: str, files: dict[str, str | bytes], owner: str,
                        force: bool = False) -> Path:
        deps = self._validate_write(name, owner, force)
        target = self._artifact_path(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))
        state = self._state(name)
        old_hash = state.content_hash
        try:
            expected: set[str] = set()
            for relative, value in files.items():
                relative_path = Path(relative)
                if relative_path.is_absolute() or ".." in relative_path.parts:
                    raise ArtifactConflictError(f"Unsafe renderer project path: {relative}")
                expected.add(relative_path.as_posix())
                path = temporary / relative_path
                if isinstance(value, bytes):
                    atomic_write_bytes(path, value)
                else:
                    atomic_write_text(path, value)
            if target.exists() and not target.is_dir():
                raise ArtifactConflictError(f"Directory artifact path is not a directory: {name}")
            # Mark replacement in progress. If any file operation fails, _execute persists
            # this stale state so a retry cannot silently reuse a partially updated tree.
            if state.status == "valid":
                state.status = "stale"
            target.mkdir(parents=True, exist_ok=True)
            for existing in sorted(item for item in target.rglob("*") if item.is_file()):
                if existing.relative_to(target).as_posix() not in expected:
                    _unlink_with_retry(existing)
            for staged in sorted(item for item in temporary.rglob("*") if item.is_file()):
                destination = target / staged.relative_to(temporary)
                atomic_write_bytes(destination, staged.read_bytes())
        finally:
            _rmtree_best_effort(temporary)
        timestamp = _now()
        state.status = "valid"
        state.content_hash = _directory_hash(target)
        state.created_at = state.created_at or timestamp
        state.updated_at = timestamp
        state.dependencies = deps
        if old_hash and old_hash != state.content_hash:
            self._invalidate_descendants(name)
        return target

    def read_json(self, name: str) -> dict[str, Any]:
        self.validate(name)
        state = self._state(name)
        path = self._artifact_path(name)
        return read_json(path)

    def validate(self, name: str) -> None:
        """Validate an artifact and its dependency DAG without repeated traversal."""
        self._validate_recursive(name, validated=set(), visiting=set())

    def _validate_recursive(self, name: str, *, validated: set[str], visiting: set[str]) -> None:
        if name in validated:
            return
        if name in visiting:
            raise ArtifactConflictError(f"Artifact dependency cycle detected: {name}")
        visiting.add(name)
        state = self._state(name)
        if state.status != "valid":
            raise ArtifactConflictError(f"Artifact {name} is {state.status}")
        path = self._artifact_path(name)
        text_value: str | None = None
        if path.is_dir():
            actual_hash = _directory_hash(path)
        elif path.is_file() and (
            name in {"audio/narration.wav", "audio/mastered_narration.wav"}
            or name.endswith(".mp4")
        ):
            actual_hash = sha256_bytes(path.read_bytes())
        elif path.is_file():
            text_value = path.read_text(encoding="utf-8")
            actual_hash = sha256_text(text_value)
        else:
            actual_hash = None
        if actual_hash != state.content_hash:
            state.status = "stale"
            state.updated_at = _now()
            self._invalidate_descendants(name)
            raise ArtifactConflictError(f"Artifact {name} hash changed and is now stale")
        if name == "source_documents/index.json":
            for document in json.loads(text_value or "{}").get("documents", []):
                document_path = self.run_dir / document.get("path", "")
                if (
                    not document.get("path")
                    or not document_path.is_file()
                    or sha256_text(document_path.read_text(encoding="utf-8")) != document.get("content_hash")
                ):
                    state.status = "stale"
                    self._invalidate_descendants(name)
                    raise ArtifactConflictError(f"source document changed or missing: {document.get('path')}")
                for asset in document.get("files", []):
                    asset_path = self.run_dir / asset.get("path", "")
                    if (
                        not asset.get("path")
                        or not asset_path.is_file()
                        or sha256_bytes(asset_path.read_bytes()) != asset.get("content_hash")
                    ):
                        state.status = "stale"
                        self._invalidate_descendants(name)
                        raise ArtifactConflictError(f"source document changed or missing: {asset.get('path')}")
        if name.startswith("human_preview_review_candidate_"):
            try:
                review = json.loads(text_value or "{}")
                relative = review.get("preview_path")
                if (
                    not isinstance(relative, str) or not relative
                    or Path(relative).is_absolute() or "\\" in relative
                    or any(part in {"", ".", ".."} for part in relative.split("/"))
                ):
                    raise ValueError("PREVIEW_REVIEW_PATH_INVALID")
                preview_path = (self.run_dir / Path(*relative.split("/"))).resolve()
                preview_path.relative_to(self.run_dir.resolve())
                expected_preview_sha = review.get("preview_sha256")
                if (
                    not preview_path.is_file()
                    or sha256_bytes(preview_path.read_bytes()) != expected_preview_sha
                ):
                    raise ValueError("PREVIEW_REVIEW_MEDIA_HASH_MISMATCH")
            except (OSError, ValueError, TypeError) as error:
                state.status = "stale"
                state.updated_at = _now()
                self._invalidate_descendants(name)
                raise ArtifactConflictError(
                    f"Artifact {name} preview media binding is invalid: {error}"
                ) from error
        for dependency, recorded_hash in state.dependencies.items():
            if dependency in validated:
                if self._state(dependency).content_hash != recorded_hash:
                    state.status = "stale"
                    self._invalidate_descendants(name)
                    raise ArtifactConflictError(f"Artifact {name} dependency hash changed: {dependency}")
                continue
            try:
                self._validate_recursive(dependency, validated=validated, visiting=visiting)
            except ArtifactConflictError as error:
                state.status = "stale"
                self._invalidate_descendants(name)
                raise ArtifactConflictError(f"Artifact {name} is stale because {error}") from error
            if self._state(dependency).content_hash != recorded_hash:
                state.status = "stale"
                self._invalidate_descendants(name)
                raise ArtifactConflictError(f"Artifact {name} dependency hash changed: {dependency}")
        visiting.remove(name)
        validated.add(name)

    def save_manifest(self) -> None:
        self.manifest.updated_at = _now()
        atomic_write_json(self.run_dir / "run.json", self.manifest.model_dump(mode="json"))


def _directory_hash(path: Path) -> str:
    rows: list[bytes] = []
    for file_path in sorted(item for item in path.rglob("*") if item.is_file()):
        relative = file_path.relative_to(path).as_posix().encode("utf-8")
        rows.append(relative + b"\0" + file_path.read_bytes())
    return sha256_bytes(b"\0".join(rows))


def _unlink_with_retry(path: Path) -> None:
    import time

    for attempt in range(5):
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(.02 * (attempt + 1))


def _rmtree_best_effort(path: Path) -> None:
    import time

    for attempt in range(5):
        try:
            shutil.rmtree(path, ignore_errors=False)
            return
        except (FileNotFoundError, PermissionError):
            if not path.exists():
                return
            if attempt < 4:
                time.sleep(.02 * (attempt + 1))
