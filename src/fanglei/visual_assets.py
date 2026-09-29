"""Deterministic, offline scene visual assets rendered from an approved Storyboard."""
from __future__ import annotations

import hashlib
import html
import json
import unicodedata
from typing import Any

from fanglei.errors import ArtifactConflictError
from fanglei.human_storyboard_approval import HumanStoryboardApprovalV1
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

    files: dict[str, str] = {}
    scene_rows: list[dict[str, Any]] = []
    scene_entries: list[tuple[str, str]] = []
    for scene in storyboard.scenes:
        filename = f"scene_{scene.order:03d}.svg"
        svg = _render_scene(scene)
        files[filename] = svg
        scene_entries.append((scene.scene_id, filename))
        scene_rows.append({
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
        })

    manifest = {
        "schema_version": "visual-assets/1.0",
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
    files["manifest.json"] = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False,
    ) + "\n"
    files["index.html"] = _render_contact_sheet(scene_entries)
    return files


def _render_scene(scene: StoryboardScene) -> str:
    svg: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_WIDTH}" height="{CANVAS_HEIGHT}" '
        f'viewBox="0 0 {CANVAS_WIDTH} {CANVAS_HEIGHT}" role="img" aria-labelledby="title">',
        f'<title id="title">{html.escape(scene.scene_id)}</title>',
        f'<rect width="{CANVAS_WIDTH}" height="{CANVAS_HEIGHT}" fill="#101a2d"/>',
        '<path d="M0 0H1080V28H0Z" fill="#6ed7cf"/>',
    ]
    for obj in sorted(scene.objects, key=lambda item: item.appearance_order):
        if obj.claim_ids and not obj.factual:
            raise ArtifactConflictError(f"VISUAL_ASSET_CLAIM_BINDING_INVALID:{scene.scene_id}:{obj.object_id}")
        if obj.factual and not obj.claim_ids:
            raise ArtifactConflictError(f"VISUAL_ASSET_FACT_WITHOUT_CLAIM:{scene.scene_id}:{obj.object_id}")
        lines, font_size = _fit_text(obj, scene.scene_id)
        x = round(obj.placement.x * CANVAS_WIDTH)
        y = round(obj.placement.y * CANVAS_HEIGHT)
        width = round(obj.placement.width * CANVAS_WIDTH)
        height = round(obj.placement.height * CANVAS_HEIGHT)
        background, foreground, border = _palette(obj.emphasis)
        object_id = html.escape(obj.object_id, quote=True)
        claim_ids = html.escape(",".join(obj.claim_ids), quote=True)
        sentence_ids = html.escape(",".join(obj.sentence_ids), quote=True)
        svg.append(
            f'<g data-object-id="{object_id}" data-object-type="{obj.object_type}" '
            f'data-sentence-ids="{sentence_ids}" data-claim-ids="{claim_ids}">'
            f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="24" '
            f'fill="{background}" stroke="{border}" stroke-width="2"/>'
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
    svg.append("</svg>")
    return "\n".join(svg) + "\n"


def _palette(emphasis: str) -> tuple[str, str, str]:
    if emphasis == "primary":
        return "#1c3150", "#ffffff", "#6ed7cf"
    if emphasis == "secondary":
        return "#18253b", "#e6edf7", "#435674"
    return "#141f33", "#d4deed", "#34445e"


def _fit_text(obj: StoryboardObject, scene_id: str) -> tuple[list[str], int]:
    width = obj.placement.width * CANVAS_WIDTH
    height = obj.placement.height * CANVAS_HEIGHT
    horizontal_padding = min(32.0, width * 0.08)
    vertical_padding = min(24.0, height * 0.12)
    available_width = width - horizontal_padding * 2
    available_height = height - vertical_padding * 2
    for font_size in range(92, 15, -2):
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


def _render_contact_sheet(scene_entries: list[tuple[str, str]]) -> str:
    cards = "\n".join(
        f'<section><h2>{html.escape(scene_id)}</h2><img src="{html.escape(path, quote=True)}" '
        f'alt="{html.escape(scene_id, quote=True)}"></section>'
        for scene_id, path in scene_entries
    )
    return (
        "<!doctype html>\n<html lang=\"zh-CN\"><head><meta charset=\"utf-8\">\n"
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; "
        "img-src 'self'; style-src 'unsafe-inline'\">\n"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
        "<title>Visual assets</title>\n<style>body{margin:0;background:#101a2d;color:#e6edf7;"
        "font:16px sans-serif;padding:24px}main{display:grid;grid-template-columns:repeat(auto-fit,"
        "minmax(240px,1fr));gap:24px}section{min-width:0}h2{font-size:16px}img{display:block;width:100%;"
        "height:auto;border:1px solid #435674;border-radius:8px}</style></head>\n"
        f"<body><main>\n{cards}\n</main></body></html>\n"
    )
