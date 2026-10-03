"""Small topic-neutral predicates shared by deterministic visual planning."""
from __future__ import annotations

import re


_NUMERIC_VALUE = re.compile(r"(?<!\d)[+-]?\d[\d,]*(?:\.\d+)?%?")
_COMPARISON_MARKER = re.compile(r"(?:变化|从|到|由|至|→|->|\bfrom\b|\bto\b|\bchanged\b)", re.I)
_NUMBER = r"[+-]?\d[\d,]*(?:\.\d+)?%?"
_SIGNED_CHANGE = re.compile(r"(?<!\d)[+-]\d[\d,]*(?:\.\d+)?%?")
_ARROW_COMPARISON = re.compile(
    rf"^\s*(?P<label>[^:：\n]{{1,80}})[:：]\s*(?P<before>{_NUMBER})"
    rf"\s*(?:→|->)\s*(?P<after>{_NUMBER})(?P<suffix>[^\n]*)$"
)
_CHINESE_FROM_TO = re.compile(
    rf"(?P<label>[^,，。;；:\n]{{1,80}}?)\s*(?:从|由)\s*(?P<before>{_NUMBER})"
    rf"\s*(?:到|至|变为|升至|降至|调整至)\s*(?P<after>{_NUMBER})(?P<suffix>[^\n]*)"
)
_ENGLISH_FROM_TO = re.compile(
    rf"(?P<label>[^,.;:\n]{{1,80}}?)\s+from\s+(?P<before>{_NUMBER})"
    rf"\s+to\s+(?P<after>{_NUMBER})(?P<suffix>[^\n]*)", re.I
)


def is_numeric_comparison(text: str) -> bool:
    """True when an input sentence contains at least two values and a comparison cue."""
    return len(_NUMERIC_VALUE.findall(text)) >= 2 and _COMPARISON_MARKER.search(text) is not None


def extract_numeric_comparison(text: str) -> dict[str, str | None] | None:
    """Extract only explicitly labeled, ordered values; preserve each input substring."""
    match = (_ARROW_COMPARISON.search(text)
             or _CHINESE_FROM_TO.search(text)
             or _ENGLISH_FROM_TO.search(text))
    if match is None:
        return None
    label = match.group("label").strip()
    before_value = match.group("before")
    after_value = match.group("after")
    if not label or not before_value or not after_value:
        return None
    change_matches = _SIGNED_CHANGE.findall(match.group("suffix"))
    change = change_matches[0] if len(change_matches) == 1 else None
    return {
        "label": label,
        "before_value": before_value,
        "after_value": after_value,
        "change": change,
    }
