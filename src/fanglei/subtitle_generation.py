"""Deterministic sentence-level subtitle compilation from approved artifacts."""

from __future__ import annotations

import re
import unicodedata

from fanglei.content_models import ScriptDraft
from fanglei.v05_models import AlignmentDocument
from fanglei.v1b_models import (
    EmphasisSpan,
    SubtitleCue,
    SubtitleLayout,
    SubtitleLine,
    SubtitleSource,
    SubtitleTrack,
    SubtitleValidation,
)


FONT_SIZE_TOKENS = (52, 48, 44, 40)
BREAK_PUNCTUATION = frozenset("，。？！；：,!?;:")
NARROW_PUNCTUATION = frozenset("，。？！；：、,.!?;:()（）《》“”‘’%")
EMPHASIS_TERMS_V1 = (
    "世界银行", "四舍五入", "小数点", "实际GDP增长率", "原始来源", "指标", "年份", "精度",
)
NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?%?")
ACRONYM_PATTERN = re.compile(r"[A-Z]{2,}")


def measure_display_units(text: str) -> float:
    """Estimate horizontal glyph demand without changing the text."""
    total = 0.0
    for char in text:
        if char.isspace():
            total += 0.33
        elif char in NARROW_PUNCTUATION:
            total += 0.5
        elif char.isascii() and (char.isalnum() or char in "-_/"):
            total += 0.56
        elif unicodedata.east_asian_width(char) in {"W", "F", "A"}:
            total += 1.0
        else:
            total += 0.72
    return total


def _line_capacity(layout: SubtitleLayout, font_size_px: int, *, safety_factor: float = 1.0) -> float:
    usable_px = layout.reserved_zone.width - 2 * layout.horizontal_padding_px
    return usable_px / (font_size_px * safety_factor)


def _break_rank(text: str, index: int) -> int:
    preceding = text[index - 1]
    if preceding in BREAK_PUNCTUATION:
        return 0
    if preceding.isspace():
        return 1
    return 2


def _layout_lines(text: str, layout: SubtitleLayout) -> tuple[int, list[SubtitleLine]]:
    for font_size in FONT_SIZE_TOKENS:
        if font_size < layout.minimum_font_size_px or font_size > layout.default_font_size_px:
            continue
        capacity = _line_capacity(layout, font_size)
        # Browser-measured GDP hook was ~13% wider than our one-line estimate.
        # Prefer a line split when a single line only fits without this margin.
        if measure_display_units(text) <= _line_capacity(layout, font_size, safety_factor=1.15):
            return font_size, [
                SubtitleLine(line_id="line_01", text=text, start_char=0, end_char=len(text))
            ]

        candidates: list[tuple[int, float, int]] = []
        for index in range(1, len(text)):
            left = text[:index]
            right = text[index:]
            left_width = measure_display_units(left)
            right_width = measure_display_units(right)
            if left_width <= capacity and right_width <= capacity:
                candidates.append((_break_rank(text, index), abs(left_width - right_width), index))
        if candidates:
            _, _, index = min(candidates)
            return font_size, [
                SubtitleLine(
                    line_id="line_01", text=text[:index], start_char=0, end_char=index
                ),
                SubtitleLine(
                    line_id="line_02", text=text[index:], start_char=index, end_char=len(text)
                ),
            ]
    raise ValueError("SUBTITLE_TEXT_OVERFLOW")


def _emphasis_candidates(text: str) -> list[tuple[int, int, str, str, int]]:
    candidates: list[tuple[int, int, str, str, int]] = []
    for match in NUMBER_PATTERN.finditer(text):
        candidates.append((match.start(), match.end(), match.group(), "number", 0))
    for match in ACRONYM_PATTERN.finditer(text):
        candidates.append((match.start(), match.end(), match.group(), "acronym", 1))
    for term in EMPHASIS_TERMS_V1:
        start = text.find(term)
        if start >= 0:
            candidates.append((start, start + len(term), term, "keyword", 2))
    return sorted(candidates, key=lambda row: (row[4], row[0], -(row[1] - row[0])))


def _build_emphasis(text: str) -> list[EmphasisSpan]:
    selected: list[EmphasisSpan] = []
    used = 0
    maximum = len(text) * 0.4
    for start, end, value, kind, _ in _emphasis_candidates(text):
        if len(selected) >= 2:
            break
        if any(start < span.end_char and end > span.start_char for span in selected):
            continue
        if used + (end - start) > maximum:
            continue
        selected.append(EmphasisSpan(
            start_char=start, end_char=end, text=value, kind=kind  # type: ignore[arg-type]
        ))
        used += end - start
    return sorted(selected, key=lambda span: span.start_char)


def _validate_alignment(script: ScriptDraft, alignment: AlignmentDocument) -> None:
    script_ids = [sentence.sentence_id for sentence in script.sentences]
    alignment_ids = [sentence.sentence_id for sentence in alignment.sentences]
    if script_ids != alignment_ids:
        raise ValueError("SUBTITLE_SENTENCE_ORDER_MISMATCH")
    if alignment.coverage_ratio != 1.0:
        raise ValueError("SUBTITLE_SENTENCE_COVERAGE_INCOMPLETE")
    if alignment.fallback_used:
        raise ValueError("SUBTITLE_FAKE_OR_FALLBACK_ALIGNMENT_FORBIDDEN")
    previous_end = -1
    for sentence in alignment.sentences:
        if sentence.timing_source == "deterministic_fake":
            raise ValueError("SUBTITLE_FAKE_OR_FALLBACK_ALIGNMENT_FORBIDDEN")
        if sentence.start_ms < previous_end:
            raise ValueError("SUBTITLE_ALIGNMENT_OVERLAP")
        if sentence.end_ms > alignment.audio_duration_ms:
            raise ValueError("SUBTITLE_ALIGNMENT_OUT_OF_BOUNDS")
        previous_end = sentence.end_ms


def compile_subtitle_track(
    script: ScriptDraft,
    alignment: AlignmentDocument,
    *,
    run_id: str,
    script_sha256: str,
    alignment_sha256: str,
    layout: SubtitleLayout | None = None,
) -> SubtitleTrack:
    """Compile exact approved script text against exact approved sentence timing."""
    _validate_alignment(script, alignment)
    layout = layout or SubtitleLayout()
    cues: list[SubtitleCue] = []
    for script_sentence, aligned_sentence in zip(script.sentences, alignment.sentences, strict=True):
        font_size, lines = _layout_lines(script_sentence.text, layout)
        cues.append(SubtitleCue(
            cue_id=f"subtitle_{script_sentence.sentence_id}",
            sentence_id=script_sentence.sentence_id,
            text=script_sentence.text,
            start_ms=aligned_sentence.start_ms,
            end_ms=aligned_sentence.end_ms,
            font_size_px=font_size,
            lines=lines,
            emphasis_spans=_build_emphasis(script_sentence.text),
        ))
    return SubtitleTrack(
        run_id=run_id,
        script_id=script.script_id,
        source=SubtitleSource(
            script_sha256=script_sha256,
            alignment_sha256=alignment_sha256,
            alignment_audio_sha256=alignment.audio_sha256,
        ),
        layout=layout,
        cues=cues,
        validation=SubtitleValidation(
            passed=True,
            sentence_coverage=1.0,
            text_exact_match=True,
            timing_exact_match=True,
            issues=[],
        ),
    )
