"""Deterministic source-overlap checks for generated content."""
from dataclasses import dataclass
from typing import Literal
import re

_COMMON = {"实际国内生产总值增长", "国内生产总值", "世界银行", "美国经济", "经济增长"}


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
