"""Deterministic, auditable separation of display narration and TTS text."""
from __future__ import annotations

import re

from fanglei.artifacts import sha256_text
from fanglei.v05_models import (
    NarrationDocument,
    NarrationNormalization,
    NarrationSentence,
    SemanticValidation,
)


_CHINESE_DIGITS = "零一二三四五六七八九"
_DIGITS = str.maketrans("0123456789", _CHINESE_DIGITS)
_YEAR_DIGITS = str.maketrans("0123456789", "〇一二三四五六七八九")
_SMALL_UNITS = ("", "十", "百", "千")
_LARGE_UNITS = ("", "万", "亿", "兆")
_NUMBER_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_.\-/:\\])(?P<number>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)(?![A-Za-z0-9_.\-/:\\])"
)


def _four_digit_number(value: int, *, omit_leading_one_ten: bool) -> str:
    if value == 0:
        return "零"
    parts: list[str] = []
    pending_zero = False
    for position in range(3, -1, -1):
        unit = 10 ** position
        digit = value // unit % 10
        remainder = value % unit
        if digit == 0:
            if parts and remainder:
                pending_zero = True
            continue
        if pending_zero:
            parts.append("零")
            pending_zero = False
        if not (omit_leading_one_ten and position == 1 and digit == 1 and not parts):
            parts.append(_CHINESE_DIGITS[digit])
        parts.append(_SMALL_UNITS[position])
    return "".join(parts)


def _integer_to_chinese(value: int) -> str:
    if value == 0:
        return "零"
    groups: list[int] = []
    remaining = value
    while remaining:
        groups.append(remaining % 10_000)
        remaining //= 10_000
    if len(groups) > len(_LARGE_UNITS):
        raise ValueError("ZH_NUMBER_MAGNITUDE_UNSUPPORTED")

    parts: list[str] = []
    pending_zero = False
    for index in range(len(groups) - 1, -1, -1):
        group = groups[index]
        if group == 0:
            if parts:
                pending_zero = True
            continue
        if parts and (pending_zero or group < 1000):
            if parts[-1] != "零":
                parts.append("零")
        parts.append(_four_digit_number(group, omit_leading_one_ten=not parts))
        parts.append(_LARGE_UNITS[index])
        pending_zero = False
    return "".join(parts)


def _spoken_number(value: str) -> str:
    normalized = value.replace(",", "")
    if "." in normalized:
        whole, fraction = normalized.split(".", 1)
        whole_spoken = _integer_to_chinese(int(whole or "0"))
        return whole_spoken + "点" + fraction.translate(_DIGITS)
    return _integer_to_chinese(int(normalized))


def _normalize_tts_text(original: str, language: str) -> tuple[str, list[NarrationNormalization]]:
    if language.casefold().replace("_", "-") != "zh-cn":
        return original, []

    text = original
    changes: list[NarrationNormalization] = []

    def replace(pattern: str, kind: str, reason: str, transform) -> None:
        nonlocal text

        def callback(match: re.Match[str]) -> str:
            source = match.group(0)
            replacement = transform(source)
            changes.append(NarrationNormalization(
                type=kind, source=source, replacement=replacement, reason=reason,
            ))
            return replacement

        text = re.sub(pattern, callback, text)

    replace(r"(?<![A-Z])(?:BEA|GDP|API|IMF|OECD)(?![A-Z])",
            "abbreviation_pronunciation", "英文缩写逐字母朗读",
            lambda value: " ".join(value))
    replace(r"(?<![A-Za-z0-9_./:-])(?:19|20)\d{2}年",
            "year_pronunciation", "年份按数字逐位朗读",
            lambda value: value[:-1].translate(_YEAR_DIGITS) + "年")
    replace(r"(?<![A-Za-z0-9_./:-])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%(?![A-Za-z0-9_.])",
            "percentage_pronunciation", "百分数保留数值并使用中文数词朗读",
            lambda value: "百分之" + _spoken_number(value[:-1]))
    replace(_NUMBER_PATTERN.pattern, "number_pronunciation",
            "数字保留原值并使用中文基数词朗读",
            lambda value: _spoken_number(value))
    return text, changes


def _legacy_canonical_pair(document: NarrationDocument) -> tuple[str, str]:
    original_rows: list[str] = []
    narration_rows: list[str] = []
    for sentence in document.sentences:
        original_rows.append(sentence.original_text)
        expected = sentence.original_text
        for change in sentence.normalizations:
            expected = expected.replace(change.source, change.replacement, 1)
        narration_rows.append(
            sentence.original_text if sentence.narration_text == expected
            else sentence.narration_text
        )
    return "\n".join(original_rows), "\n".join(narration_rows)


def validate_narration_semantics(document: NarrationDocument) -> SemanticValidation:
    if document.schema_version == "5.0":
        original, restored = _legacy_canonical_pair(document)
        passed = original == restored
        return SemanticValidation(
            passed=passed,
            canonical_original_hash=sha256_text(original),
            canonical_narration_hash=sha256_text(restored),
            issues=[] if passed else ["NARRATION_SEMANTIC_CHANGE"],
        )

    original_rows = [sentence.original_text for sentence in document.sentences]
    display_rows = [sentence.narration_text for sentence in document.sentences]
    issues: list[str] = []
    if original_rows != display_rows:
        issues.append("NARRATION_DISPLAY_TEXT_CHANGED")
    for sentence in document.sentences:
        expected_text, expected_changes = _normalize_tts_text(
            sentence.original_text, document.language,
        )
        if sentence.tts_spoken_text != expected_text or sentence.normalizations != expected_changes:
            issues.append("TTS_SPOKEN_TEXT_MISMATCH")
            break
    original = "\n".join(original_rows)
    display = "\n".join(display_rows)
    return SemanticValidation(
        passed=not issues,
        canonical_original_hash=sha256_text(original),
        canonical_narration_hash=sha256_text(display),
        issues=issues,
    )


def normalize_script(script: dict, run_id: str, *, language: str | None = None) -> NarrationDocument:
    target_language = language or script.get("target_language") or "zh-CN"
    sentences: list[NarrationSentence] = []
    for row in script.get("sentences", []):
        original = row["text"]
        tts_text, changes = _normalize_tts_text(original, target_language)
        sentences.append(NarrationSentence(
            sentence_id=row["sentence_id"],
            original_text=original,
            narration_text=original,
            tts_spoken_text=tts_text,
            normalization_reason=(
                "；".join(dict.fromkeys(item.reason for item in changes)) or "保留目标语言原文"
            ),
            normalizations=changes,
        ))
    if not sentences:
        raise ValueError("NARRATION_REQUIRES_SCRIPT_SENTENCES")
    document = NarrationDocument(
        schema_version="5.1",
        run_id=run_id,
        script_id=script.get("script_id") or "script",
        language=target_language,
        sentences=sentences,
        semantic_validation=SemanticValidation(
            passed=False, canonical_original_hash="", canonical_narration_hash="",
            issues=["NOT_VALIDATED"],
        ),
    )
    document.semantic_validation = validate_narration_semantics(document)
    if not document.semantic_validation.passed:
        raise ValueError("NARRATION_SEMANTIC_CHANGE")
    return document


def render_narration_text(document: NarrationDocument) -> str:
    """Render exact display/canonical narration, not provider pronunciation text."""
    if not validate_narration_semantics(document).passed:
        raise ValueError("NARRATION_SEMANTIC_CHANGE")
    return "\n".join(sentence.narration_text for sentence in document.sentences) + "\n"


def render_tts_text(document: NarrationDocument) -> str:
    """Render the exact, validated text supplied to a speech provider."""
    if not validate_narration_semantics(document).passed:
        raise ValueError("NARRATION_SEMANTIC_CHANGE")
    return "\n".join(sentence.spoken_text for sentence in document.sentences) + "\n"


def render_tts_payload(document: NarrationDocument) -> str:
    """Return exact provider payload text without file-format trailing newline."""
    if not validate_narration_semantics(document).passed:
        raise ValueError("NARRATION_SEMANTIC_CHANGE")
    return "\n".join(sentence.spoken_text for sentence in document.sentences)
