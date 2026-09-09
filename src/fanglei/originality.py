"""Deterministic source-overlap checks for generated content."""
from dataclasses import dataclass
from typing import Literal
import re

_COMMON = {"实际国内生产总值增长", "国内生产总值", "世界银行", "美国经济", "经济增长"}
_FACT_TERMS = (
    r"United States", r"U\.S\.", r"USA", r"美国",
    r"World Bank", r"世界银行", r"BEA", r"IMF", r"OECD",
    r"real GDP growth(?: rate)?", r"real GDP", r"GDP growth(?: rate)?", r"GDP",
    r"实际国内生产总值增长率", r"实际国内生产总值", r"实际GDP增长率", r"实际GDP", r"国内生产总值",
    r"增长率", r"同比", r"环比", r"通胀率", r"失业率", r"利率", r"汇率",
)
_DISTINCTIVE_MARKERS = ("就像", "好比", "仿佛", "如同", "一面", "一把", "一场", "一扇")


@dataclass(frozen=True)
class OriginalityResult:
    status: Literal["passed", "regenerate", "blocked"]
    max_contiguous_overlap: int
    five_gram_jaccard: float
    issue_codes: tuple[str, ...]


def _norm(text: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]", "", text).lower()


def _longest(a: str, b: str) -> int:
    previous = [0] * (len(b) + 1)
    best = 0
    for ca in a:
        current = [0]
        for index, cb in enumerate(b, 1):
            value = previous[index - 1] + 1 if ca == cb else 0
            current.append(value)
            best = max(best, value)
        previous = current
    return best


def check_originality(generated: str, source: str) -> OriginalityResult:
    a, b = _norm(generated), _norm(source)
    if a in _COMMON or b in _COMMON:
        return OriginalityResult("passed", len(a) if a == b else 0, 0.0, ())
    overlap = _longest(a, b)
    ga = {a[i:i+5] for i in range(max(0, len(a)-4))}
    gb = {b[i:i+5] for i in range(max(0, len(b)-4))}
    jaccard = len(ga & gb) / len(ga | gb) if ga | gb else 0.0
    issues = []
    if overlap >= 16: issues.append("CONTIGUOUS_SOURCE_REUSE")
    if jaccard > 0.50: issues.append("HIGH_SOURCE_SIMILARITY")
    status = "blocked" if issues else ("regenerate" if overlap >= 12 or jaccard >= 0.35 else "passed")
    return OriginalityResult(status, overlap, round(jaccard, 4), tuple(issues))


def _mask_allowed_fact_terms(text: str) -> str:
    masked = text
    for pattern in _FACT_TERMS:
        masked = re.sub(pattern, " ", masked, flags=re.I)
    masked = re.sub(r"\b(?:19|20)\d{2}\b", " ", masked)
    masked = re.sub(r"\d+(?:\.\d+)?\s*(?:%|percent|百分点)?", " ", masked, flags=re.I)
    return masked


def check_fact_originality(generated: str, source: str) -> OriginalityResult:
    """Allow necessary fact vocabulary while retaining expression-level checks."""
    raw_generated, raw_source = _norm(generated), _norm(source)
    raw_overlap = _longest(raw_generated, raw_source)
    distinctive_copy = (
        raw_overlap >= 12
        and any(marker in generated for marker in _DISTINCTIVE_MARKERS)
        and raw_generated in raw_source
    )
    masked_generated = _mask_allowed_fact_terms(generated)
    masked_source = _mask_allowed_fact_terms(source)
    if raw_overlap >= 28 or distinctive_copy:
        return OriginalityResult(
            "blocked", raw_overlap, 1.0 if raw_generated == raw_source else 0.0,
            ("DISTINCTIVE_FACT_EXPRESSION_REUSE" if distinctive_copy else "CONTIGUOUS_SOURCE_REUSE",),
        )
    if len(_norm(masked_generated)) <= 6:
        return OriginalityResult("passed", raw_overlap, 0.0, ())

    masked = check_originality(masked_generated, masked_source)
    return OriginalityResult(
        masked.status, raw_overlap, masked.five_gram_jaccard, masked.issue_codes,
    )
