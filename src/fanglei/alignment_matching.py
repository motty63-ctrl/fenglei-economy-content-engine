"""Deterministic, matching-only normalization for real audio alignment."""
from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


ALIGNMENT_NORMALIZATION_VERSION = "alignment-normalization-v1"

# Deliberately enumerated. Unknown numeric or institutional forms remain different.
_EQUIVALENCES: tuple[tuple[str, str], ...] = (
    ("world bank", "世界银行"),
    ("二〇二四年", "2024年"),
    ("二零二四年", "2024年"),
    ("百分之二点七九三二", "2.7932%"),
    ("百分之二点八", "2.8%"),
)


@dataclass(frozen=True)
class TextMatchResult:
    reference: str
    recognized: str
    normalized_ref: str
    normalized_asr: str
    cer: float
    rule_version: str = ALIGNMENT_NORMALIZATION_VERSION

    @property
    def matched(self) -> bool:
        return self.normalized_ref == self.normalized_asr


def _edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for row, left_char in enumerate(left, start=1):
        current = [row]
        for column, right_char in enumerate(right, start=1):
            current.append(min(
                current[-1] + 1,
                previous[column] + 1,
                previous[column - 1] + (left_char != right_char),
            ))
        previous = current
    return previous[-1]


def normalize_alignment_text(text: str) -> str:
    """Return a canonical comparison form without changing the source string."""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = re.sub(r"\bg\s*d\s*p\b", "gdp", normalized)
    normalized = re.sub(r"\bb\s*e\s*a\b", "bea", normalized)
    for source, replacement in _EQUIVALENCES:
        normalized = normalized.replace(source, replacement)
    normalized = "".join(character for character in normalized if not character.isspace())
    decimal_marker = "\ue000"
    normalized = re.sub(r"(?<=\d)\.(?=\d)", decimal_marker, normalized)
    normalized = "".join(
        character for character in normalized
        if not unicodedata.category(character).startswith("P") or character == "%"
    )
    return normalized.replace(decimal_marker, ".")


def compare_alignment_text(reference: str, recognized: str) -> TextMatchResult:
    normalized_ref = normalize_alignment_text(reference)
    normalized_asr = normalize_alignment_text(recognized)
    denominator = max(1, len(normalized_ref))
    return TextMatchResult(
        reference=reference,
        recognized=recognized,
        normalized_ref=normalized_ref,
        normalized_asr=normalized_asr,
        cer=_edit_distance(normalized_ref, normalized_asr) / denominator,
    )
