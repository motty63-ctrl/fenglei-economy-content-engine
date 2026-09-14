"""Deterministic pronunciation normalization without editorial rewriting."""
from __future__ import annotations

import re

from fanglei.artifacts import sha256_text
from fanglei.v05_models import (
    NarrationDocument,
    NarrationNormalization,
    NarrationSentence,
    SemanticValidation,
)


_DIGITS = str.maketrans("0123456789", "〇一二三四五六七八九")


def _spoken_number(value: str) -> str:
    if "." in value:
        whole, fraction = value.split(".", 1)
        return whole.translate(_DIGITS) + "点" + fraction.translate(_DIGITS)
    return value.translate(_DIGITS)


def _normalize_sentence(sentence_id: str, original: str) -> NarrationSentence:
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

    replace(r"(?<![A-Z])(?:BEA|GDP|API|IMF|OECD)(?![A-Z])", "abbreviation_pronunciation",
            "英文缩写逐字母朗读", lambda value: " ".join(value))
    replace(r"(?:19|20)\d{2}年", "year_pronunciation", "年份按数字逐位朗读",
            lambda value: value[:-1].translate(_DIGITS) + "年")
    replace(r"\d+(?:\.\d+)?%", "percentage_pronunciation", "百分数按原数值朗读",
            lambda value: "百分之" + _spoken_number(value[:-1]))
    replace(r"\d+(?:\.\d+)?", "number_pronunciation", "数字按原数值朗读", _spoken_number)
    reasons = "；".join(dict.fromkeys(item.reason for item in changes)) or "无必要规范化"
    return NarrationSentence(
        sentence_id=sentence_id,
        original_text=original,
        narration_text=text,
        normalization_reason=reasons,
        normalizations=changes,
    )


def _canonical_pair(document: NarrationDocument) -> tuple[str, str]:
    original_rows: list[str] = []
    narration_rows: list[str] = []
    for sentence in document.sentences:
        original_rows.append(sentence.original_text)
        expected = sentence.original_text
        for change in sentence.normalizations:
            expected = expected.replace(change.source, change.replacement, 1)
        # Compare against a deterministic forward replay. Reversing substitutions is
        # ambiguous when the original already contains the spoken representation.
        narration_rows.append(
            sentence.original_text if sentence.narration_text == expected
            else sentence.narration_text
        )
    return "\n".join(original_rows), "\n".join(narration_rows)


def validate_narration_semantics(document: NarrationDocument) -> SemanticValidation:
    original, restored = _canonical_pair(document)
    passed = original == restored
    return SemanticValidation(
        passed=passed,
        canonical_original_hash=sha256_text(original),
        canonical_narration_hash=sha256_text(restored),
        issues=[] if passed else ["NARRATION_SEMANTIC_CHANGE"],
    )


def normalize_script(script: dict, run_id: str) -> NarrationDocument:
    sentences = [
        _normalize_sentence(row["sentence_id"], row["text"])
        for row in script.get("sentences", [])
    ]
    if not sentences:
        raise ValueError("NARRATION_REQUIRES_SCRIPT_SENTENCES")
    document = NarrationDocument(
        run_id=run_id,
        script_id=script.get("script_id") or "script",
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
    if not validate_narration_semantics(document).passed:
        raise ValueError("NARRATION_SEMANTIC_CHANGE")
    return "\n".join(sentence.narration_text for sentence in document.sentences) + "\n"
