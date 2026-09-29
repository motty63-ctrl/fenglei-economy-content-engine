"""Deterministic, offline scene visual assets rendered from an approved Storyboard."""
from __future__ import annotations

import hashlib
import html
import json
import unicodedata
from typing import Any

from fanglei.errors import ArtifactConflictError
from fanglei.human_storyboard_approval import HumanStoryboardApprovalV1
from fanglei.human_visual_asset_recovery import (
    VisualAssetRecoveryPlanV1,
    VisualSceneLayoutV1,
    parse_signed_display_value,
)
from fanglei.human_storyboard_recovery import canonical_json_sha256
from fanglei.visual_models import Storyboard, StoryboardObject, StoryboardScene


CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920
_SHA256_LENGTH = 64


def build_visual_asset_bundle(
    storyboard: Storyboard,
    approval: HumanStoryboardApprovalV1,
    *,
    approval_artifact_sha256: str,
    recovery_plan: VisualAssetRecoveryPlanV1 | None = None,
) -> dict[str, str]:
    """Render one static SVG per approved scene plus an offline review contact sheet."""
    if len(approval_artifact_sha256) != _SHA256_LENGTH or any(
        char not in "0123456789abcdef" for char in approval_artifact_sha256
    ):
        raise ArtifactConflictError("VISUAL_ASSET_APPROVAL_HASH_INVALID")
    if storyboard.run_id != approval.run_id:
        raise ArtifactConflictError("VISUAL_ASSET_RUN_BINDING_MISMATCH")
    if canonical_json_sha256(storyboard) != approval.candidate_storyboard_sha256:
        raise ArtifactConflictError("VISUAL_ASSET_STORYBOARD_APPROVAL_MISMATCH")
    if not storyboard.scenes or any(
        scene.start_ms is None or scene.end_ms is None for scene in storyboard.scenes
    ):
        raise ArtifactConflictError("VISUAL_ASSET_SCENE_TIMING_REQUIRED")
    if len({scene.scene_id for scene in storyboard.scenes}) != len(storyboard.scenes):
        raise ArtifactConflictError("VISUAL_ASSET_SCENE_ID_DUPLICATE")
    layouts: dict[str, VisualSceneLayoutV1] = {}
    if recovery_plan is not None:
        if (
            recovery_plan.run_id != storyboard.run_id
            or recovery_plan.storyboard_sha256 != canonical_json_sha256(storyboard)
            or recovery_plan.storyboard_approval_sha256 != approval_artifact_sha256
            or recovery_plan.storyboard_artifact_sha256 != approval.candidate_artifact_sha256
            or recovery_plan.candidate_id != recovery_plan.source_candidate_id + 1
        ):
            raise ArtifactConflictError("VISUAL_ASSET_RECOVERY_STORYBOARD_BINDING_INVALID")
        if [row.scene_id for row in recovery_plan.scene_layouts] != [
            scene.scene_id for scene in storyboard.scenes
        ]:
            raise ArtifactConflictError("VISUAL_ASSET_RECOVERY_SCENE_COVERAGE_INVALID")
        layouts = {row.scene_id: row for row in recovery_plan.scene_layouts}
        if len(layouts) != len(recovery_plan.scene_layouts):
            raise ArtifactConflictError("VISUAL_ASSET_RECOVERY_SCENE_COVERAGE_INVALID")

    files: dict[str, str] = {}
    scene_rows: list[dict[str, Any]] = []
    scene_entries: list[tuple[str, str]] = []
    scene_footer = recovery_plan.source_footer if recovery_plan else None
    for scene in storyboard.scenes:
        filename = f"scene_{scene.order:03d}.svg"
        layout = layouts.get(scene.scene_id)
        if layout is not None and layout.order != scene.order:
            raise ArtifactConflictError("VISUAL_ASSET_RECOVERY_SCENE_ORDER_CHANGED")
        svg, rendered_sizes, bar_metadata = _render_scene(
            scene,
            layout=layout,
            source_footer=scene_footer if layout is not None and scene.order > 1 else None,
        )
        files[filename] = svg
        scene_entries.append((scene.scene_id, filename))
        scene_row = {
            "scene_id": scene.scene_id,
            "order": scene.order,
            "start_ms": scene.start_ms,
            "end_ms": scene.end_ms,
            "sentence_ids": list(scene.sentence_ids),
            "claim_ids": sorted({claim_id for obj in scene.objects for claim_id in obj.claim_ids}),
            "asset_path": filename,
            "asset_sha256": hashlib.sha256(svg.encode("utf-8")).hexdigest(),
            "objects": [
                {
                    "object_id": obj.object_id,
                    "object_type": obj.object_type,
                    "content": obj.content,
                    "factual": obj.factual,
                    "sentence_ids": list(obj.sentence_ids),
                    "claim_ids": list(obj.claim_ids),
                    "placement": obj.placement.model_dump(mode="json"),
                    "emphasis": obj.emphasis,
                }
                for obj in sorted(scene.objects, key=lambda item: item.appearance_order)
            ],
        }
        if layout is not None:
            scene_row.update({
                "layout_profile": layout.profile,
                "rendered_font_sizes": rendered_sizes,
                "diverging_bars": bar_metadata,
                "source_footer": (
                    {"label": scene_footer.label, "source_ids": scene_footer.source_ids}
                    if scene_footer is not None and scene.order > 1 else None
                ),
            })
        scene_rows.append(scene_row)

    manifest = {
        "schema_version": "visual-assets/1.1" if recovery_plan else "visual-assets/1.0",
        "run_id": approval.run_id,
        "case_id": approval.case_id,
        "review_status": "pending_human_visual_review",
        "approval_sha256": approval_artifact_sha256,
        "candidate_storyboard_sha256": approval.candidate_storyboard_sha256,
        "candidate_artifact_sha256": approval.candidate_artifact_sha256,
        "timing_basis": storyboard.timing_basis,
        "total_estimated_duration_seconds": storyboard.total_estimated_duration_seconds,
        "scene_count": len(scene_rows),
        "scenes": scene_rows,
    }
    if recovery_plan is not None:
        manifest["candidate_id"] = recovery_plan.candidate_id
        manifest["source_candidate_id"] = recovery_plan.source_candidate_id
        manifest["source_visual_bundle_sha256"] = recovery_plan.source_visual_bundle_sha256
        manifest["source_review_sha256"] = recovery_plan.source_review_sha256
        manifest["recovery_plan_sha256"] = canonical_json_sha256(recovery_plan)
        manifest["source_footer"] = {
            "label": recovery_plan.source_footer.label,
            "source_ids": recovery_plan.source_footer.source_ids,
            "first_scene_without_footer": storyboard.scenes[0].scene_id,
        }
    files["manifest.json"] = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False,
    ) + "\n"
    files["index.html"] = _render_contact_sheet(
        scene_entries,
        candidate_id=recovery_plan.candidate_id if recovery_plan else None,
        previous_candidate_href="../visual_assets/index.html" if recovery_plan else None,
    )
    return files


def _render_scene(
    scene: StoryboardScene,
    *,
    layout: VisualSceneLayoutV1 | None = None,
    source_footer=None,
) -> tuple[str, dict[str, int], list[dict[str, Any]]]:
    styles = {style.object_id: style for style in layout.object_styles} if layout else {}
    svg: list[str] = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_WIDTH}" height="{CANVAS_HEIGHT}" '
            f'viewBox="0 0 {CANVAS_WIDTH} {CANVAS_HEIGHT}" role="img" aria-labelledby="title"'
            + (f' data-visual-profile="{layout.profile}"' if layout else "")
            + ">"
        ),
        f'<title id="title">{html.escape(scene.scene_id)}</title>',
        f'<rect width="{CANVAS_WIDTH}" height="{CANVAS_HEIGHT}" fill="#101a2d"/>',
        '<path d="M0 0H1080V28H0Z" fill="#6ed7cf"/>',
    ]
    if layout is not None:
        for decoration in layout.decorations:
            svg.append(_render_decoration(decoration))
    bar_metadata = _render_diverging_bars(scene, layout) if layout is not None else []
    if layout is not None:
        for bar in bar_metadata:
            svg.append(bar.pop("svg"))
    rendered_sizes: dict[str, int] = {}
    for obj in sorted(scene.objects, key=lambda item: item.appearance_order):
        if obj.claim_ids and not obj.factual:
            raise ArtifactConflictError(f"VISUAL_ASSET_CLAIM_BINDING_INVALID:{scene.scene_id}:{obj.object_id}")
        if obj.factual and not obj.claim_ids:
            raise ArtifactConflictError(f"VISUAL_ASSET_FACT_WITHOUT_CLAIM:{scene.scene_id}:{obj.object_id}")
        style = styles.get(obj.object_id)
        placement = style.placement if style else obj.placement
        lines, font_size = _fit_text(
            obj, scene.scene_id, placement=placement,
            preferred_font_size=style.target_font_size if style else None,
        )
        rendered_sizes[obj.object_id] = font_size
        x = round(placement.x * CANVAS_WIDTH)
        y = round(placement.y * CANVAS_HEIGHT)
        width = round(placement.width * CANVAS_WIDTH)
        height = round(placement.height * CANVAS_HEIGHT)
        background, foreground, border = _palette(obj.emphasis, style.tone if style else None)
        object_id = html.escape(obj.object_id, quote=True)
        claim_ids = html.escape(",".join(obj.claim_ids), quote=True)
        sentence_ids = html.escape(",".join(obj.sentence_ids), quote=True)
        svg.append(
            f'<g data-object-id="{object_id}" data-object-type="{obj.object_type}" '
            f'data-sentence-ids="{sentence_ids}" data-claim-ids="{claim_ids}">'
            + (
                f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="24" '
                f'fill="{background}" stroke="{border}" stroke-width="2"/>'
                if style is None or style.show_card else ""
            )
        )
        line_height = font_size * 1.22
        first_baseline = y + (height - len(lines) * line_height) / 2 + font_size
        svg.append(
            f'<text x="{x + width / 2:.1f}" y="{first_baseline:.1f}" text-anchor="middle" '
            f'font-family="Noto Sans CJK SC, Microsoft YaHei, sans-serif" font-size="{font_size}" '
            f'font-weight="650" fill="{foreground}" xml:space="preserve">'
        )
        for index, line in enumerate(lines):
            dy = "0" if index == 0 else f"{line_height:.1f}"
            svg.append(f'<tspan x="{x + width / 2:.1f}" dy="{dy}">{html.escape(line, quote=False)}</tspan>')
        svg.extend(("</text>", "</g>"))
    if source_footer is not None:
        svg.append(
            f'<text x="{CANVAS_WIDTH * 0.08:.1f}" y="{CANVAS_HEIGHT * 0.885:.1f}" '
            'text-anchor="start" font-family="Noto Sans CJK SC, Microsoft YaHei, sans-serif" '
            'font-size="22" font-weight="400" fill="#92a2b8" '
            f'data-source-ids="{html.escape(",".join(source_footer.source_ids), quote=True)}">'
            f'{html.escape(source_footer.label, quote=False)}</text>'
        )
    svg.append("</svg>")
    return "\n".join(svg) + "\n", rendered_sizes, bar_metadata


def _palette(emphasis: str, tone: str | None = None) -> tuple[str, str, str]:
    if tone == "positive":
        return "#173a3b", "#9af2d8", "#55cdb4"
    if tone == "negative":
        return "#3b2835", "#ffd5df", "#e87591"
    if tone == "muted":
        return "#141f33", "#9eacc0", "#34445e"
    if tone == "neutral":
        return "#1a2940", "#e6edf7", "#64758e"
    if tone == "primary":
        return "#1c3150", "#ffffff", "#6ed7cf"
    if tone == "secondary":
        return "#18253b", "#e6edf7", "#435674"
    if emphasis == "primary":
        return "#1c3150", "#ffffff", "#6ed7cf"
    if emphasis == "secondary":
        return "#18253b", "#e6edf7", "#435674"
    return "#141f33", "#d4deed", "#34445e"


def _fit_text(
    obj: StoryboardObject,
    scene_id: str,
    *,
    placement=None,
    preferred_font_size: int | None = None,
) -> tuple[list[str], int]:
    placement = placement or obj.placement
    width = placement.width * CANVAS_WIDTH
    height = placement.height * CANVAS_HEIGHT
    horizontal_padding = min(32.0, width * 0.08)
    vertical_padding = min(24.0, height * 0.12)
    available_width = width - horizontal_padding * 2
    available_height = height - vertical_padding * 2
    start_font_size = preferred_font_size or 92
    for font_size in range(start_font_size, 15, -2):
        lines = _wrap_text(obj.content, available_width, font_size)
        line_height = font_size * 1.22
        if len(lines) * line_height <= available_height and all(
            _measured_width(line, font_size) <= available_width + 0.1 for line in lines
        ):
            return lines, font_size
    raise ArtifactConflictError(f"VISUAL_ASSET_TEXT_DOES_NOT_FIT:{scene_id}:{obj.object_id}")


def _wrap_text(value: str, available_width: float, font_size: int) -> list[str]:
    paragraphs = value.split("\n")
    lines: list[str] = []
    for paragraph in paragraphs:
        if not paragraph:
            lines.append("")
            continue
        current = ""
        current_width = 0.0
        for character in paragraph:
            char_width = _character_width(character) * font_size
            if current and current_width + char_width > available_width:
                lines.append(current)
                current = character
                current_width = char_width
            else:
                current += character
                current_width += char_width
        lines.append(current)
    return lines


def _character_width(character: str) -> float:
    if character.isspace():
        return 0.36
    if unicodedata.east_asian_width(character) in {"F", "W", "A"}:
        return 1.0
    return 0.58


def _measured_width(value: str, font_size: int) -> float:
    return sum(_character_width(character) for character in value) * font_size


def _render_decoration(decoration) -> str:
    _, foreground, border = _palette("secondary", decoration.tone)
    x = decoration.x * CANVAS_WIDTH
    y = decoration.y * CANVAS_HEIGHT
    width = decoration.width * CANVAS_WIDTH
    height = decoration.height * CANVAS_HEIGHT
    opacity = f'{decoration.opacity:.3f}'
    if decoration.kind == "line":
        return (
            f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x + width:.1f}" y2="{y + height:.1f}" '
            f'stroke="{foreground}" stroke-width="{decoration.stroke_width}" opacity="{opacity}" '
            f'transform="rotate({decoration.rotation_degrees} {x:.1f} {y:.1f})"/>'
        )
    if decoration.kind == "circle":
        shape = (
            f'<ellipse cx="{x + width / 2:.1f}" cy="{y + height / 2:.1f}" '
            f'rx="{width / 2:.1f}" ry="{height / 2:.1f}"'
        )
    else:
        shape = f'<rect x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}" rx="18"'
    if decoration.filled:
        return f'{shape} fill="{border}" opacity="{opacity}"/>'
    return f'{shape} fill="none" stroke="{border}" stroke-width="{decoration.stroke_width}" opacity="{opacity}"/>'


def _render_diverging_bars(scene: StoryboardScene, layout: VisualSceneLayoutV1) -> list[dict[str, Any]]:
    if not layout.diverging_bars:
        return []
    objects = {obj.object_id: obj for obj in scene.objects}
    parsed = [
        parse_signed_display_value(objects[bar.value_object_id].content)
        for bar in layout.diverging_bars
    ]
    if len({unit for _, unit, _ in parsed}) != 1:
        raise ArtifactConflictError("VISUAL_ASSET_BAR_UNITS_MISMATCH")
    max_value = max(amount for amount, _, _ in parsed)
    result: list[dict[str, Any]] = []
    for bar, (amount, unit, sign) in zip(layout.diverging_bars, parsed, strict=True):
        normalized = float(amount / max_value)
        width = bar.max_half_width * normalized
        x = bar.center_x if sign == "positive" else bar.center_x - width
        _, foreground, _ = _palette("secondary", sign)
        svg = (
            f'<g data-value-object-id="{html.escape(bar.value_object_id, quote=True)}" '
            f'data-sign="{sign}" data-unit="{html.escape(unit, quote=True)}" '
            f'data-normalized-length="{normalized:.6f}">'
            f'<line x1="{bar.center_x * CANVAS_WIDTH:.1f}" y1="{bar.y * CANVAS_HEIGHT:.1f}" '
            f'x2="{bar.center_x * CANVAS_WIDTH:.1f}" y2="{(bar.y + bar.height) * CANVAS_HEIGHT:.1f}" '
            'stroke="#8192aa" stroke-width="3" opacity="0.75"/>'
            f'<rect x="{x * CANVAS_WIDTH:.1f}" y="{bar.y * CANVAS_HEIGHT:.1f}" '
            f'width="{width * CANVAS_WIDTH:.1f}" height="{bar.height * CANVAS_HEIGHT:.1f}" '
            f'rx="12" fill="{foreground}" opacity="0.75"/></g>'
        )
        result.append({
            "label_object_id": bar.label_object_id,
            "value_object_id": bar.value_object_id,
            "sign": sign,
            "unit": unit,
            "normalized_length": normalized,
            "x": x,
            "y": bar.y,
            "width": width,
            "height": bar.height,
            "svg": svg,
        })
    return result


def _render_contact_sheet(
    scene_entries: list[tuple[str, str]],
    *,
    candidate_id: int | None = None,
    previous_candidate_href: str | None = None,
) -> str:
    cards = "\n".join(
        f'<section><h2>{html.escape(scene_id)}</h2><img src="{html.escape(path, quote=True)}" '
        f'alt="{html.escape(scene_id, quote=True)}"></section>'
        for scene_id, path in scene_entries
    )
    candidate_banner = ""
    if candidate_id is not None:
        previous_link = (
            f'<a href="{html.escape(previous_candidate_href, quote=True)}">'
            "Candidate 1 — CHANGES_REQUIRED</a> · "
            if previous_candidate_href else ""
        )
        candidate_banner = (
            f'<aside>{previous_link}<strong>Candidate {candidate_id} — '
            "PENDING HUMAN VISUAL REVIEW</strong></aside>\n"
        )
    return (
        "<!doctype html>\n<html lang=\"zh-CN\"><head><meta charset=\"utf-8\">\n"
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; "
        "img-src 'self'; style-src 'unsafe-inline'\">\n"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
        "<title>Visual assets</title>\n<style>body{margin:0;background:#101a2d;color:#e6edf7;"
        "font:16px sans-serif;padding:24px}aside{position:sticky;top:0;background:#18253b;padding:16px;"
        "margin-bottom:20px;border:1px solid #435674;border-radius:8px}a{color:#9af2d8}main{display:grid;"
        "grid-template-columns:repeat(auto-fit,"
        "minmax(240px,1fr));gap:24px}section{min-width:0}h2{font-size:16px}img{display:block;width:100%;"
        "height:auto;border:1px solid #435674;border-radius:8px}</style></head>\n"
        f"<body>{candidate_banner}<main>\n{cards}\n</main></body></html>\n"
    )
