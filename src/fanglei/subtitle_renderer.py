"""Independent sentence-level subtitle overlay for V1.0b."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
import json

from .v1b_models import SubtitleCue, SubtitleTrack
from .visual_system_v1 import VisualTheme


@dataclass(frozen=True)
class SubtitleLayerBundle:
    html: str
    css: str
    javascript: str
    qa_metadata: dict[str, object]


def _render_line(cue: SubtitleCue, start: int, end: int) -> str:
    points = {start, end}
    for span in cue.emphasis_spans:
        if span.end_char > start and span.start_char < end:
            points.add(max(start, span.start_char))
            points.add(min(end, span.end_char))
    ordered = sorted(points)
    parts: list[str] = []
    for left, right in zip(ordered, ordered[1:]):
        value = escape(cue.text[left:right])
        emphasis = next(
            (span for span in cue.emphasis_spans
             if left >= span.start_char and right <= span.end_char), None
        )
        if emphasis:
            parts.append(
                f'<span class="subtitle-emphasis subtitle-emphasis-{emphasis.kind}">{value}</span>'
            )
        else:
            parts.append(value)
    return "".join(parts)


def render_subtitle_layer(track: SubtitleTrack, theme: VisualTheme) -> SubtitleLayerBundle:
    zone = theme.subtitle_reserved_zone
    cues: list[str] = []
    for cue in track.cues:
        lines = "".join(
            f'<span class="subtitle-line" data-line-id="{escape(line.line_id, quote=True)}">'
            f'{_render_line(cue, line.start_char, line.end_char)}</span>'
            for line in cue.lines
        )
        cues.append(
            f'<div class="subtitle-cue" id="{escape(cue.cue_id, quote=True)}" '
            f'data-sentence-id="{escape(cue.sentence_id, quote=True)}" '
            f'data-start-ms="{cue.start_ms}" data-end-ms="{cue.end_ms}" '
            f'data-font-size-px="{cue.font_size_px}" '
            f'aria-label="{escape(cue.text, quote=True)}" '
            f'style="font-size:{cue.font_size_px}px">{lines}</div>'
        )
    html = (
        '<div id="subtitle-layer" aria-live="off">' + "".join(cues) + '</div>'
        '<script id="v1b-layout-qa" type="application/json">{}</script>'
    )
    css = f"""
#subtitle-layer{{position:absolute;left:{zone.x}px;top:{zone.y}px;width:{zone.width}px;
height:{zone.height}px;z-index:80;pointer-events:none;display:flex;align-items:center;
justify-content:center;text-align:center;color:{theme.colors.ink_primary};
font-family:'Noto Sans SC','Microsoft YaHei',sans-serif;box-sizing:border-box;
padding:24px 36px;background:rgba(247,242,232,.86);border-radius:24px;overflow:hidden}}
.subtitle-cue{{position:absolute;inset:24px 36px;display:flex;flex-direction:column;
align-items:center;justify-content:center;line-height:1.28;font-weight:700;opacity:0;
box-sizing:border-box}}
.subtitle-line{{display:block;white-space:nowrap}}
.subtitle-emphasis{{color:{theme.colors.emphasis_primary};font-weight:900}}
""".strip()
    javascript = """
// Cue visibility follows exact [start,end) milliseconds; natural gaps stay empty.
window.installFangleiSubtitles = function(totalDurationMs) {
  const cues = [...document.querySelectorAll('.subtitle-cue')];
  cues.forEach((cue) => {
    const start = Number(cue.dataset.startMs);
    const end = Number(cue.dataset.endMs);
    cue.animate([{opacity:0},{opacity:1},{opacity:1},{opacity:0}], {
      duration: totalDurationMs, fill:'both', easing:'steps(1,end)',
      keyframes: undefined,
      delay: 0,
      iterations: 1,
      composite: 'replace'
    }).effect.setKeyframes([
      {opacity:0, offset:0}, {opacity:0, offset:start/totalDurationMs},
      {opacity:1, offset:start/totalDurationMs}, {opacity:1, offset:end/totalDurationMs},
      {opacity:0, offset:end/totalDurationMs}, {opacity:0, offset:1}
    ]);
  });
  const emitQa = () => {
    const zone = document.querySelector('#subtitle-layer').getBoundingClientRect();
    const rows = cues.map((cue) => ({
      cue_id: cue.id,
      sentence_id: cue.dataset.sentenceId,
      start_ms: Number(cue.dataset.startMs), end_ms: Number(cue.dataset.endMs),
      font_size_px: parseFloat(getComputedStyle(cue).fontSize),
      cue_bounds: rect(cue.getBoundingClientRect()),
      line_bounds: [...cue.querySelectorAll('.subtitle-line')].map(x => rect(x.getBoundingClientRect()))
    }));
    document.querySelector('#v1b-layout-qa').textContent = JSON.stringify({zone:rect(zone), cues:rows});
  };
  const rect = (r) => ({x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom});
  document.fonts.ready.then(emitQa);
};
""".strip()
    return SubtitleLayerBundle(
        html=html,
        css=css,
        javascript=javascript,
        qa_metadata={
            "cue_count": len(track.cues),
            "line_counts": [len(cue.lines) for cue in track.cues],
            "minimum_font_size_px": min(cue.font_size_px for cue in track.cues),
            "reserved_zone": zone.model_dump(),
            "source_hashes": track.source.model_dump(),
            "cue_timing": [
                {"sentence_id": cue.sentence_id, "start_ms": cue.start_ms, "end_ms": cue.end_ms}
                for cue in track.cues
            ],
            "plain_text_sha256": __import__("hashlib").sha256(
                json.dumps([cue.text for cue in track.cues], ensure_ascii=False).encode("utf-8")
            ).hexdigest(),
        },
    )
