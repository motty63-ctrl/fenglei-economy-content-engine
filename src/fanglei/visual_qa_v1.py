"""Minimal V1.0a QA: reject obviously broken renders, never score aesthetics."""
from __future__ import annotations

import re

from pydantic import Field

from fanglei.visual_system_v1 import StrictModel, StoryboardV1, VisualIssue, VisualProgram


class FrameSample(StrictModel):
    timestamp_ms: int = Field(ge=0)
    mean_luma: float = Field(ge=0)
    foreground_ratio: float = Field(ge=0, le=1)
    active_semantic_objects: int | None = Field(default=None, ge=0)


class LayoutSample(StrictModel):
    timestamp_ms: int = Field(ge=0)
    object_id: str
    x: float
    y: float
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    primary: bool = False


class StaticDurationRow(StrictModel):
    scene_id: str | None = None
    state_id: str | None = None
    duration_ms: int
    severity: str
    reason: str | None = None


class VisualQAReport(StrictModel):
    schema_version: str = "visual-qa.v1.0a"
    passed: bool
    issues: list[VisualIssue]
    static_duration_report: list[StaticDurationRow]
    checks: dict[str, bool]


def _scene_for_time(program: VisualProgram, timestamp_ms: int) -> str | None:
    for scene in program.scenes:
        if scene.start_ms <= timestamp_ms <= scene.end_ms:
            return scene.scene_id
    return None


def _duration_from_message(message: str) -> int:
    match = re.search(r"(\d+) ms", message)
    return int(match.group(1)) if match else 0


def run_minimal_visual_qa(program: VisualProgram, storyboard: StoryboardV1, *,
                          timeline: dict | None = None,
                          frame_samples: list[FrameSample] | None = None,
                          layout_samples: list[LayoutSample] | None = None,
                          perceptual_static_intervals: list[tuple[int, int]] | None = None,
                          ) -> VisualQAReport:
    issues: list[VisualIssue] = []
    frame_samples = frame_samples or []
    layout_samples = layout_samples or []
    perceptual_static_intervals = perceptual_static_intervals or []

    for scene in storyboard.scenes:
        if not scene.objects or not scene.primitive.state_sequence:
            issues.append(VisualIssue(
                code="VISUAL_BLANK_SCENE", severity="error",
                message="active scene has no semantic content", scene_id=scene.scene_id,
            ))
    last_scene = program.scenes[-1] if program.scenes else None
    final_frame_semantic_coverage = bool(
        last_scene
        and last_scene.end_frame_exclusive == program.frame_count
        and last_scene.states
        and last_scene.states[-1].target_object_ids
    )
    if not final_frame_semantic_coverage:
        issues.append(VisualIssue(
            code="VISUAL_FINAL_FRAME_EMPTY", severity="error",
            message="frame_count - 1 is not covered by the final semantic state",
            scene_id=last_scene.scene_id if last_scene else None,
        ))
    for sample in frame_samples:
        if sample.mean_luma <= 1.0 or sample.foreground_ratio < 0.01:
            issues.append(VisualIssue(
                code="VISUAL_BLANK_FRAME", severity="error",
                message=f"blank frame at {sample.timestamp_ms} ms",
                scene_id=_scene_for_time(program, sample.timestamp_ms),
            ))
        final_frame_start_ms = program.duration_ms - round(1000 / program.fps)
        if (
            sample.timestamp_ms >= final_frame_start_ms
            and sample.active_semantic_objects is not None
            and sample.active_semantic_objects == 0
        ):
            final_frame_semantic_coverage = False
            issues.append(VisualIssue(
                code="VISUAL_FINAL_FRAME_EMPTY", severity="error",
                message="rendered final frame contains no active semantic objects",
                scene_id=last_scene.scene_id if last_scene else None,
            ))

    theme = storyboard.theme
    for sample in layout_samples:
        overflow = (
            sample.x < 0 or sample.y < 0
            or sample.x + sample.width > theme.canvas_width
            or sample.y + sample.height > theme.canvas_height
            or (sample.primary and sample.y + sample.height > theme.subtitle_reserved_zone.y)
        )
        if overflow:
            issues.append(VisualIssue(
                code="VISUAL_LAYOUT_OVERFLOW", severity="error",
                message=f"{sample.object_id} exceeds the visual safe area",
                scene_id=_scene_for_time(program, sample.timestamp_ms),
            ))

    scene_mismatch = False
    if timeline is not None:
        timeline_by_id = {row["scene_id"]: row for row in timeline.get("scenes", [])}
        tolerance_ms = 1000 / program.fps
        for scene in program.scenes:
            expected = timeline_by_id.get(scene.scene_id)
            if expected is None or (
                abs(scene.start_ms - int(expected["start_ms"])) > tolerance_ms
                or abs(scene.end_ms - int(expected["end_ms"])) > tolerance_ms
            ):
                scene_mismatch = True
                issues.append(VisualIssue(
                    code="VISUAL_SCENE_TIMELINE_MISMATCH", severity="error",
                    message="compiled scene does not match the authoritative timeline",
                    scene_id=scene.scene_id,
                ))

    density_issues = [
        issue if isinstance(issue, VisualIssue) else VisualIssue.model_validate(issue)
        for issue in program.density_issues
    ]
    issues.extend(density_issues)
    static_rows = [StaticDurationRow(
        scene_id=issue.scene_id, state_id=issue.state_id,
        duration_ms=_duration_from_message(issue.message), severity=issue.severity,
        reason=(issue.message.rsplit("(", 1)[-1].rstrip(")") if "(" in issue.message else None),
    ) for issue in density_issues if issue.code == "VISUAL_STATIC_DURATION_EXCEEDED"]
    for start_ms, end_ms in perceptual_static_intervals:
        duration_ms = end_ms - start_ms
        if duration_ms <= 3000:
            continue
        scene = next(
            (item for item in program.scenes if item.start_ms <= start_ms <= item.end_ms),
            None,
        )
        changed_states = [
            state for state in (scene.states if scene else [])
            if start_ms < state.at_ms < end_ms and state.meaningful_change
        ]
        if not changed_states:
            continue
        state = changed_states[0]
        severity = "warning" if state.hold_reason else "error"
        reason = "semantic_state_changed_but_perceptual_change_insufficient"
        issue = VisualIssue(
            code="VISUAL_PERCEPTUAL_STATIC_DURATION_EXCEEDED",
            severity=severity,
            message=f"semantic state changed but pixels remained static for {duration_ms} ms",
            scene_id=scene.scene_id if scene else None,
            state_id=state.state_id,
        )
        issues.append(issue)
        static_rows.append(StaticDurationRow(
            scene_id=issue.scene_id,
            state_id=issue.state_id,
            duration_ms=duration_ms,
            severity=severity,
            reason=reason,
        ))
    passed = not any(issue.severity == "error" for issue in issues)
    return VisualQAReport(
        passed=passed, issues=issues, static_duration_report=static_rows,
        checks={
            "blank_frames": not any(
                issue.code.startswith("VISUAL_BLANK")
                or issue.code == "VISUAL_FINAL_FRAME_EMPTY"
                for issue in issues
            ),
            "final_frame_semantic_coverage": final_frame_semantic_coverage,
            "overflow": not any(issue.code == "VISUAL_LAYOUT_OVERFLOW" for issue in issues),
            "scene_timeline_match": not scene_mismatch,
            "static_duration_reported": True,
        },
    )
