"""Fail-closed downstream checks for authority-attested claims.

These checks do not attempt general semantic entailment. They only allow a
small, explicit set of attributed document reports and scoped comparisons to
survive angle/script projection.
"""
from __future__ import annotations

import re
from typing import Any


_ATTRIBUTION_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (r"\bfederal\s+reserve\b", ("federal reserve", "fed", "\u7f8e\u8054\u50a8", "\u7f8e\u56fd\u8054\u90a6\u50a8\u5907")),
    (r"\bfomc\b", ("fomc", "\u8054\u90a6\u516c\u5f00\u5e02\u573a\u59d4\u5458\u4f1a")),
    (r"\bsep\b", ("sep", "\u7ecf\u6d4e\u9884\u6d4b\u6458\u8981")),
    (r"\bparticipants?\b", ("participant", "participants", "\u53c2\u4e0e\u8005")),
    (r"\bseptember\b", ("september", "\u4e5d\u6708", "9\u6708")),
    (r"\bjune\b", ("june", "\u516d\u6708", "6\u6708")),
    (r"\bstatement\b", ("statement", "\u58f0\u660e")),
)

_SCOPE_ALIASES: dict[str, tuple[str, ...]] = {
    "change": ("change", "changed", "revision", "revised", "\u53d8\u5316", "\u53d8\u52a8", "\u8c03\u6574", "\u6539\u53d8"),
    "real": ("real", "\u5b9e\u9645"),
    "gdp": ("gdp", "gross domestic product", "\u56fd\u5185\u751f\u4ea7\u603b\u503c"),
    "federal": ("federal", "\u8054\u90a6"),
    "fund": ("fund", "funds", "\u57fa\u91d1"),
    "funds": ("fund", "funds", "\u57fa\u91d1"),
    "rate": ("rate", "rates", "\u5229\u7387", "\u7387"),
    "unemployment": ("unemployment", "\u5931\u4e1a", "\u5931\u4e1a\u7387"),
    "pce": ("pce",),
    "inflation": ("inflation", "\u901a\u80c0", "\u901a\u8d27\u81a8\u80c0"),
    "core": ("core", "\u6838\u5fc3"),
    "projection": ("projection", "projected", "forecast", "\u9884\u6d4b", "\u9884\u671f"),
    "median": ("median", "\u4e2d\u4f4d\u6570"),
    "percent": ("percent", "percentage", "%", "\u767e\u5206\u6bd4"),
    "today": ("today", "\u4eca\u65e5", "\u4eca\u5929"),
    "policy": ("policy", "\u653f\u7b56"),
    "action": ("action", "\u884c\u52a8", "\u63aa\u65bd"),
    "support": ("support", "\u652f\u6301"),
    "timelier": ("timelier", "\u66f4\u53ca\u65f6"),
    "return": ("return", "\u56de\u5f52"),
    "committee": ("committee", "\u59d4\u5458\u4f1a"),
    "goal": ("goal", "\u76ee\u6807"),
    "inflationary": ("inflationary", "\u901a\u80c0"),
    "elevated": ("elevated", "\u504f\u9ad8", "\u9ad8\u4f01"),
}

_STOP_WORDS = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "of", "on", "the", "to"}
_EXPANSION_RE = re.compile(
    r"\b(?:because|cause[sd]?|causal(?:ly)?|due\s+to|driven\s+by|forced?|led\s+to|"
    r"resulted\s+in|motive|market\s+impact|market\s+effect|therefore)\b|"
    r"\u56e0\u4e3a|\u7531\u4e8e|\u5bfc\u81f4|\u9020\u6210|\u4fc3\u4f7f|\u8feb\u4f7f|\u5f52\u56e0\u4e8e|\u52a8\u673a|"
    r"\u5e02\u573a\u5f71\u54cd|\u5e02\u573a\u6548\u5e94|\u6240\u4ee5\u5bfc\u81f4|\u56e0\u6b64\u4f7f",
    re.I,
)
_NUMBER_RE = re.compile(r"(?<![\w.])[+-]?\d[\d,]*(?:\.\d+)?(?![\w.])")


def _has_alias(text: str, alias: str) -> bool:
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9 ]*", alias):
        return bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])", text, re.I))
    return alias.casefold() in text.casefold()


def _attribution_preserved(text: str, attribution: Any) -> bool:
    if not isinstance(attribution, str) or not attribution.strip():
        return False
    if _has_alias(text, attribution.strip()):
        return True

    remaining = attribution
    required_groups: list[tuple[str, ...]] = []
    for pattern, aliases in _ATTRIBUTION_ALIASES:
        if re.search(pattern, remaining, re.I):
            required_groups.append(aliases)
            remaining = re.sub(pattern, " ", remaining, flags=re.I)

    if required_groups:
        tokens = [word for word in re.findall(r"[A-Za-z][A-Za-z0-9-]*", remaining)
                  if word.casefold() not in _STOP_WORDS and word.casefold() not in {
                      "says", "said", "reports", "reported", "states", "stated"
                  }]
        required_groups.extend((token,) for token in tokens)
        return all(any(_has_alias(text, alias) for alias in group) for group in required_groups)

    # Unknown attribution forms must remain literal; no guessed translation.
    return False


def _scope_term_present(text: str, term: str) -> bool:
    normalized = term.strip()
    if not normalized:
        return False
    words = re.findall(r"[A-Za-z][A-Za-z0-9-]*|[\u4e00-\u9fff]+|%", normalized)
    if not words:
        return False
    for word in words:
        if word.casefold() in _STOP_WORDS:
            continue
        aliases = _SCOPE_ALIASES.get(word.casefold(), (word,))
        if not any(_has_alias(text, alias) for alias in aliases):
            return False
    return True


def _comparison_evidence_values(claim: dict[str, Any], attestation: dict[str, Any]) -> list[tuple[str, str]]:
    approved_ids = set(attestation.get("source_ids", []))
    values: list[tuple[str, str]] = []
    for item in claim.get("evidence", []):
        source_id = item.get("source_id")
        if (source_id not in approved_ids or item.get("evidence_eligible") is not True
                or not isinstance(item.get("evidence_text"), str)):
            continue
        matches = _NUMBER_RE.findall(item["evidence_text"])
        if matches:
            values.append((source_id, matches[-1].replace(",", "")))
    return values


def _number_present(text: str, value: str) -> bool:
    return bool(re.search(rf"(?<![\d.]){re.escape(value)}(?![\d.])", text))


def _authority_expansion(text: str, exact_evidence: list[str], *, comparison: bool) -> bool:
    if not _EXPANSION_RE.search(text):
        return False
    if comparison:
        return True
    remainder = text
    for excerpt in exact_evidence:
        if excerpt:
            remainder = remainder.replace(excerpt, "", 1)
    return bool(_EXPANSION_RE.search(remainder))


def authority_text_issues(text: str, claim: dict[str, Any]) -> tuple[str, ...]:
    """Return fail-closed eligibility issue codes for one downstream text."""
    attestation = claim.get("authority_attestation")
    if not isinstance(attestation, dict):
        return ("AUTHORITY_SCOPE_MISMATCH",)

    issues: set[str] = set()
    attribution = attestation.get("attribution")
    if not _attribution_preserved(text, attribution):
        issues.add("AUTHORITY_ATTRIBUTION_MISSING")

    kind = attestation.get("kind")
    attested_ids = set(attestation.get("source_ids", []))
    eligible = [item for item in claim.get("evidence", [])
                if item.get("evidence_eligible") is True
                and item.get("source_id") in attested_ids
                and isinstance(item.get("evidence_text"), str)]
    exact_evidence = [item["evidence_text"] for item in eligible]
    claim_source_ids = set(claim.get("source_ids", []))
    eligible_source_ids = {item.get("source_id") for item in eligible}
    if not attested_ids or claim_source_ids != attested_ids or eligible_source_ids != attested_ids:
        issues.add("AUTHORITY_SCOPE_MISMATCH")

    if kind == "document_report":
        if not eligible or not any(excerpt and excerpt in text for excerpt in exact_evidence):
            issues.add("AUTHORITY_SCOPE_MISMATCH")
    elif kind == "deterministic_document_comparison":
        scope = attestation.get("scope")
        required = ("subject", "measure", "period", "unit", "statistic", "certainty")
        if not isinstance(scope, dict) or any(not isinstance(scope.get(key), str) or not scope[key].strip()
                                               for key in required):
            issues.add("AUTHORITY_SCOPE_MISMATCH")
        else:
            if any(not _scope_term_present(text, scope[key]) for key in required if key != "period"):
                issues.add("AUTHORITY_SCOPE_MISMATCH")
            if not re.search(rf"(?<!\d){re.escape(scope['period'])}(?!\d)", text):
                issues.add("AUTHORITY_SCOPE_MISMATCH")

            values = _comparison_evidence_values(claim, attestation)
            source_ids = {source_id for source_id, _ in values}
            if len(source_ids) < 2 or any(not _number_present(text, value) for _, value in values):
                issues.add("AUTHORITY_SCOPE_MISMATCH")
            if not re.search(
                r"\bfrom\b.{0,60}\bto\b|\bchanged\b|\brevised\b|\bincreased\b|\bdecreased\b|"
                r"\u4ece.{0,60}(?:\u5230|\u81f3)|(?:\u8c03\u6574|\u53d8\u5316|\u6539\u53d8|\u53d8\u4e3a|\u5347\u81f3|\u964d\u81f3)", text, re.I,
            ):
                issues.add("AUTHORITY_SCOPE_MISMATCH")

        if re.search(r"\b(?:commit(?:ment)?|pledge|promise|target|decided|will set)\b|\u627f\u8bfa|\u4fdd\u8bc1|\u51b3\u5b9a|\u76ee\u6807", text, re.I):
            issues.add("AUTHORITY_SCOPE_MISMATCH")
    else:
        issues.add("AUTHORITY_SCOPE_MISMATCH")

    if _authority_expansion(text, exact_evidence, comparison=kind == "deterministic_document_comparison"):
        issues.add("AUTHORITY_SCOPE_EXPANSION")
    return tuple(sorted(issues))
