"""Source independence, evidence extraction, and deterministic fact checks."""

from __future__ import annotations

import hashlib
from difflib import SequenceMatcher
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping
from urllib.parse import urlsplit

from fanglei.evidence_policy import gate_evidence, script_usage
from fanglei.source_contract import (
    AuthoritativePrimarySetPolicyV1,
    SourcePackageValidationError,
    SourceRowV21,
    validate_sources_artifact_v21,
)


@dataclass(frozen=True)
class FetchedDocument:
    source_id: str
    url: str
    title: str
    text: str
    source_type: str
    published_at: str | None
    retrieved_at: str
    original_url: str | None = None
    document_format: str = "html"
    retrieval_method: str = "html"
    evidence_eligible: bool = True
    eligibility_reason: str = "original_document"
    document_hash: str | None = None
    api_endpoint: str | None = None
    request_fingerprint: str | None = None
    api_observations: list[dict[str, Any]] = field(default_factory=list)
    raw_content: str | None = None
    pages: list[dict[str, Any]] = field(default_factory=list)
    raw_bytes: bytes | None = None


SOURCE_TIERS = {
    "official": "A",
    "original_data": "A",
    "international_organization": "B",
    "company_disclosure": "C",
    "mainstream_media": "D",
    "industry_media": "E",
    "blog": "F",
    "wechat": "F",
}


_TABLE_TITLE = re.compile(r"^\s*Table\s+\d+\s*\.\s*.+$", re.IGNORECASE)
_TABLE_PERIOD = re.compile(r"^(?:19|20)\d{2}$|^longer\s+run$", re.IGNORECASE)
_TABLE_NUMBER = re.compile(r"^[+-]?\d+(?:\.\d+)?(?:\s*(?:%|percent))?$", re.IGNORECASE)
_MONTH_DATE_SUFFIX = re.compile(
    r"\s*,?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\s*$",
    re.IGNORECASE,
)


def _clean_table_label(value: str) -> str:
    return re.sub(r"(?<=[A-Za-z])\d+$", "", value.strip()).strip()


def _table_signature(title: str) -> str:
    without_release_date = _MONTH_DATE_SUFFIX.sub("", title.strip())
    return " ".join(without_release_date.casefold().split())


def _line_range(first: int, last: int) -> str:
    return f"line:{first}" if first == last else f"line:{first}-{last}"


def _structured_table_evidence(document: FetchedDocument) -> list[dict[str, Any]]:
    """Extract only unambiguous first-column cells from line-oriented tables.

    The normalized captures retain accessible tables as one cell per line. This
    reader recognizes their explicit ``Variable`` / statistic / period header
    shape and deliberately emits the first statistic/period cell only: later
    cells cannot be aligned safely when a normalized table omits blank cells.
    """
    lines = document.text.splitlines()
    nonempty = [(index, line.strip()) for index, line in enumerate(lines) if line.strip()]
    output: list[dict[str, Any]] = []

    for title_position, (_, table_title) in enumerate(nonempty):
        if not _TABLE_TITLE.match(table_title):
            continue
        table_end = next(
            (
                position
                for position in range(title_position + 1, len(nonempty))
                if _TABLE_TITLE.match(nonempty[position][1])
                or re.match(r"^(?:Note:|Figure\s+\d+\.)", nonempty[position][1], re.IGNORECASE)
            ),
            len(nonempty),
        )
        table_lines = nonempty[title_position + 1 : table_end]
        variable_position = next(
            (i for i, (_, line) in enumerate(table_lines[:24]) if line.casefold() == "variable"),
            None,
        )
        if variable_position is None or variable_position == 0:
            continue
        unit_line_number, unit = table_lines[variable_position - 1]
        first_period_position = next(
            (
                i
                for i in range(variable_position + 1, min(len(table_lines), variable_position + 16))
                if _TABLE_PERIOD.fullmatch(table_lines[i][1])
            ),
            None,
        )
        if first_period_position is None:
            continue
        statistic_rows = table_lines[variable_position + 1 : first_period_position]
        statistics = [_clean_table_label(line) for _, line in statistic_rows]
        if not statistics or any(not re.search(r"[A-Za-z]", item) for item in statistics):
            continue

        period_rows: list[tuple[int, str]] = []
        for row in table_lines[first_period_position:]:
            if not _TABLE_PERIOD.fullmatch(row[1]):
                break
            period_rows.append(row)
        if not period_rows or len(period_rows) % len(statistics):
            continue
        period_width = len(period_rows) // len(statistics)
        period_groups = [
            [value.casefold() for _, value in period_rows[i * period_width : (i + 1) * period_width]]
            for i in range(len(statistics))
        ]
        if not period_width or any(group != period_groups[0] for group in period_groups[1:]):
            continue
        first_period = period_rows[0][1]
        if not re.fullmatch(r"(?:19|20)\d{2}", first_period):
            continue

        header_first_line = unit_line_number + 1
        header_last_line = period_rows[-1][0] + 1
        header_excerpt = "\n".join(lines[header_first_line - 1 : header_last_line])
        first_statistic = statistics[0]
        signature = _table_signature(table_title)

        row_start = first_period_position + len(period_rows)
        row_position = row_start
        while row_position + 1 < len(table_lines):
            raw_label = table_lines[row_position][1]
            next_value = table_lines[row_position + 1][1]
            if (
                not _TABLE_NUMBER.fullmatch(next_value)
                or _TABLE_PERIOD.fullmatch(raw_label)
                or _TABLE_NUMBER.fullmatch(raw_label)
            ):
                row_position += 1
                continue
            row_label = _clean_table_label(raw_label)
            if not row_label or not re.search(r"[A-Za-z]", row_label):
                row_position += 1
                continue

            row_line = table_lines[row_position][0] + 1
            value_line = table_lines[row_position + 1][0] + 1
            value = re.sub(r"\s*(?:%|percent)$", "", next_value, flags=re.IGNORECASE).strip()
            context = {
                "table_title": table_title,
                "table_signature": signature,
                "row_label": row_label,
                "statistic": first_statistic,
                "period": first_period,
                "unit": unit,
                "value": value,
                "header_locator": _line_range(header_first_line, header_last_line),
                "header_excerpt": header_excerpt,
            }
            claim_key = "structured-table|" + "|".join(
                " ".join(part.casefold().split())
                for part in (signature, row_label, first_statistic, first_period, unit)
            )
            output.append(
                {
                    "source_id": document.source_id,
                    "evidence_text": f"{lines[row_line - 1]}\n{lines[value_line - 1]}",
                    "source_section": table_title,
                    "paragraph_locator": _line_range(row_line, value_line),
                    "published_at": document.published_at,
                    "retrieved_at": document.retrieved_at,
                    "original_url": document.original_url or document.url,
                    "relation": "supports",
                    "claim_type": "fact",
                    "claim_key": claim_key,
                    "claim_values": [value],
                    "document_hash": document.document_hash,
                    "document_format": document.document_format,
                    "evidence_origin": "original_document",
                    "table_context": context,
                }
            )
            row_position += 2

    return output


def _canonical(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}{parts.path.rstrip('/')}"


def _institution(host: str) -> str:
    host = host.lower().split(":", 1)[0].rstrip(".")
    for registered_domain in ("worldbank.org", "imf.org", "oecd.org", "bea.gov"):
        if host == registered_domain or host.endswith(f".{registered_domain}"):
            return registered_domain
    return host


def deduplicate_sources(documents: list[FetchedDocument]) -> list[dict[str, Any]]:
    known: dict[str, str] = {}
    prior_content: list[tuple[str, str]] = []
    rows: list[dict[str, Any]] = []
    for doc in documents:
        canonical = _canonical(doc.url)
        origin = _canonical(doc.original_url) if doc.original_url else canonical
        institution = _institution(urlsplit(origin).netloc)
        content_key = hashlib.sha256(" ".join(doc.text.split()).encode()).hexdigest()[:16]
        normalized_content = re.sub(r"\W+", "", doc.text).lower()
        similar_key = next(
            (key for previous, key in prior_content if SequenceMatcher(None, normalized_content, previous).ratio() >= 0.9),
            None,
        )
        is_authoritative_origin = doc.source_type in {"official", "original_data", "international_organization", "company_disclosure"}
        authoritative_key = f"institution:{institution}" if is_authoritative_origin else None
        independence_key = known.get(origin) or known.get(content_key) or similar_key or (
            known.get(authoritative_key) if authoritative_key else None
        ) or authoritative_key or f"origin:{origin}"
        certain = bool(doc.original_url) or is_authoritative_origin
        counts = certain and independence_key not in {row["independence_key"] for row in rows if row["counts_as_independent"]}
        if origin not in known:
            known[origin] = independence_key
        if authoritative_key:
            known[authoritative_key] = independence_key
        known[content_key] = independence_key
        prior_content.append((normalized_content, independence_key))
        rows.append(
            {
                "source_id": doc.source_id,
                "url": doc.url,
                "title": doc.title,
                "published_at": doc.published_at,
                "retrieved_at": doc.retrieved_at,
                "source_type": doc.source_type,
                "credibility_tier": SOURCE_TIERS.get(doc.source_type, "F"),
                "independence_key": independence_key,
                "counts_as_independent": counts,
                "independence_reason": "traceable original source" if counts else "republication or origin independence uncertain",
                "origin_chain": [doc.original_url, doc.url] if doc.original_url else [doc.url],
            }
        )
    return sorted(rows, key=lambda row: (row["credibility_tier"], not row["counts_as_independent"], row["source_id"]))


class RuleBasedEvidenceExtractor:
    _markers = re.compile(r"(?:GDP|国内生产总值|通胀|inflation|CPI|利率|interest rate|就业|employment|汇率|exchange rate|政策|policy)", re.I)

    def extract(self, documents: list[FetchedDocument], questions: list[str]) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        question_context = " ".join(questions).lower()
        target_years = set(re.findall(r"(?:19|20)\d{2}", question_context))
        target_country = "us" if re.search(r"\bus\b|united states|美国", question_context) else "unspecified"
        for doc in documents:
            paragraphs = [p.strip() for p in re.split(r"\n+", doc.text) if p.strip()]
            for index, paragraph in enumerate(paragraphs, 1):
                for sentence in re.split(r"(?<=[。！？!?])|(?<!\d)\.(?!\d)", paragraph):
                    sentence = sentence.strip()
                    has_number = bool(re.search(r"\d", sentence))
                    is_noise = "�" in sentence or sentence.startswith("%PDF") or len(sentence) < 6
                    claim_type = "opinion" if re.search(r"认为|主张|观点|believes?", sentence, re.I) else (
                        "inference" if re.search(r"因此|可能|意味着|may|therefore", sentence, re.I) else "fact"
                    )
                    if sentence and self._markers.search(sentence) and (has_number or claim_type != "fact") and not is_noise:
                        sentence_years = set(re.findall(r"(?:19|20)\d{2}", sentence))
                        percent_values = re.findall(r"(\d+(?:\.\d+)?)\s*(?:%|percent|百分比|个百分点)", sentence, re.I)
                        annual_real_gdp_context = (
                            bool(re.search(r"real\s+gdp|实际(?:国内生产总值|GDP)", sentence, re.I))
                            and bool(re.search(r"growth|increased|grew|增长|增幅", sentence, re.I))
                            and not re.search(r"quarter|季度|q[1-4]", sentence, re.I)
                            and bool(percent_values)
                        )
                        value_year_pairs = re.findall(
                            r"(?:increased|grew|growth\s+(?:was|of)|increase\s+of)\s+"
                            r"(\d+(?:\.\d+)?)\s*(?:%|percent)\s+in\s+((?:19|20)\d{2})",
                            sentence,
                            re.I,
                        )
                        if annual_real_gdp_context and not value_year_pairs and len(sentence_years) == 1:
                            value_year_pairs = [(percent_values[0], next(iter(sentence_years)))]
                        targeted_pairs = [
                            (value, year) for value, year in value_year_pairs
                            if not target_years or year in target_years
                        ]
                        base = {
                                "source_id": doc.source_id,
                                "evidence_text": sentence,
                                "source_section": None,
                                "paragraph_locator": f"paragraph:{index}",
                                "published_at": doc.published_at,
                                "retrieved_at": doc.retrieved_at,
                                "original_url": doc.original_url or doc.url,
                                "relation": "supports",
                                "claim_type": claim_type,
                                "document_hash": doc.document_hash,
                                "document_format": doc.document_format,
                                "evidence_origin": (
                                    "official_api" if doc.document_format == "api" else "original_document"
                                ),
                        }
                        if doc.document_format == "api" and index <= len(doc.api_observations):
                            observation = doc.api_observations[index - 1]
                            base.update({
                                "api_endpoint": doc.api_endpoint,
                                "request_fingerprint": doc.request_fingerprint,
                                "json_pointer": observation.get("json_pointer"),
                                "observation": observation.get("observation"),
                            })
                        elif doc.document_format == "pdf":
                            page = next((item for item in doc.pages if sentence in str(item.get("text", ""))), None)
                            if page:
                                base.update({
                                    "page_number": page.get("page_number"),
                                    "page_content_hash": page.get("content_hash"),
                                })
                        if annual_real_gdp_context and targeted_pairs:
                            for value, year in targeted_pairs:
                                evidence.append({
                                    **base,
                                    "claim_key": f"{target_country}|annual_real_gdp_growth|{year}",
                                    "claim_values": [value],
                                    "normalized_claim_text": (
                                        f"United States real GDP grew {value}% in {year}."
                                        if target_country == "us" else f"Real GDP grew {value}% in {year}."
                                    ),
                                })
                        else:
                            evidence.append({**base, "claim_key": None, "claim_values": None})
            evidence.extend(_structured_table_evidence(doc))
        return evidence


def _claim_identity(text: str) -> tuple[str, tuple[str, ...]]:
    lowered = text.lower()
    years = re.findall(r"(?:19|20)\d{2}", lowered)
    numbers = tuple(value for value in re.findall(r"\d+(?:[.,]\d+)?", lowered) if value not in years)
    canonical = lowered.replace("国内生产总值", "gdp")
    canonical = re.sub(r"同比(?:增幅为|增长率为|增长为|增长)", "同比增长", canonical)
    canonical = re.sub(r"\s+|[，,。!！；;：:]", "", canonical)
    for value in sorted(numbers, key=len, reverse=True):
        canonical = canonical.replace(value, "#", 1)
    canonical = canonical.replace(".", "")
    identity = canonical
    return identity, numbers


def verify_claims(
    evidence: list[dict[str, Any]],
    source_context: dict[str, bool | dict[str, Any]],
    *,
    minimum_sources_met: bool = True,
) -> dict[str, Any]:
    claims: list[dict[str, Any]] = []
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in evidence:
        compact = re.sub(r"\s+", "", item["evidence_text"]).lower()
        key = item.get("claim_key") or (_claim_identity(compact)[0] if item.get("claim_type") == "fact" else compact)
        groups.setdefault(key, []).append(item)
    for index, items in enumerate(groups.values(), 1):
        def is_independent(source_id: str) -> bool:
            context = source_context.get(source_id, False)
            return context if isinstance(context, bool) else bool(context.get("counts_as_independent"))

        def is_primary(source_id: str) -> bool:
            context = source_context.get(source_id, False)
            return context if isinstance(context, bool) else context.get("credibility_tier") in {"A", "B", "C"}

        eligible_items = [item for item in items if item.get("evidence_eligible", True)]
        independent_ids = {item["source_id"] for item in eligible_items if is_independent(item["source_id"])}
        independent_count = len(independent_ids)
        has_primary = any(is_primary(source_id) for source_id in independent_ids)
        claim_type = items[0].get("claim_type", "fact")
        values = {
            tuple(item["claim_values"]) if item.get("claim_values") else _claim_identity(item["evidence_text"])[1]
            for item in eligible_items
        }
        status = "conflicted" if claim_type == "fact" and len(values) > 1 else (
            "verified" if claim_type == "fact" and minimum_sources_met and independent_count >= 2 and has_primary else "unverified"
        )
        internal_fields = {
            "claim_type",
            "claim_key",
            "claim_values",
            "normalized_claim_text",
            "table_context",
        }
        clean_evidence = [{key: value for key, value in item.items() if key not in internal_fields} for item in items]
        claims.append(
            {
                "claim_id": f"claim_{index:03d}",
                "claim_text": items[0].get("normalized_claim_text") or items[0]["evidence_text"],
                "claim_type": claim_type,
                "verification_status": status,
                "domain": "economic_data",
                "risk_level": "high",
                "source_ids": list(dict.fromkeys(item["source_id"] for item in items)),
                "evidence": clean_evidence,
                "verification_reason": (
                    "independent sources report conflicting values"
                    if status == "conflicted"
                    else
                    "confirmed by at least two independent eligible sources"
                    if status == "verified"
                    else "high-risk claim lacks the run-level three-source minimum and/or a primary source plus an independent corroborator"
                ),
                "allowed_downstream": status == "verified" and claim_type == "fact",
                "script_usage": script_usage(status),
            }
        )
    return {
        "schema_version": "2.1",
        "policy_version": "economics-v1.1",
        "claims": claims,
        "summary": {
            "verified": sum(c["verification_status"] == "verified" for c in claims),
            "conflicted": sum(c["verification_status"] == "conflicted" for c in claims),
            "unverified": sum(c["verification_status"] == "unverified" for c in claims),
        },
    }


_AUTHORITY_SCOPE_EXPANSION = re.compile(
    r"\b(?:because|cause[sd]?|causal(?:ly)?|due\s+to|led\s+to|prompted|resulted\s+in|"
    r"forced|motive|motivated|intended\s+to|market\s+(?:impact|effect|reaction)|"
    r"will\s+(?:cause|lead|make)|therefore)\b|因为|导致|促使|由于|动机|市场(?:影响|反应)",
    re.IGNORECASE,
)


def evidence_claim_key(item: dict[str, Any]) -> str:
    """Return the same deterministic grouping key used by ``verify_claims``."""
    compact = re.sub(r"\s+", "", item["evidence_text"]).lower()
    return item.get("claim_key") or (
        _claim_identity(compact)[0] if item.get("claim_type") == "fact" else compact
    )


def _scope_terms_appear(scope: Any, text: str) -> bool:
    folded = " ".join(text.casefold().split())
    required = [scope.subject, scope.measure, scope.period, scope.certainty]
    required.extend(value for value in (scope.unit, scope.statistic) if value is not None)
    return all(" ".join(value.casefold().split()) in folded for value in required)


def _value_appears(value: str, text: str) -> bool:
    return re.search(rf"(?<![\w.]){re.escape(value)}(?![\w.])", text, re.IGNORECASE) is not None


def _authority_evidence_matches(
    item: dict[str, Any], document: FetchedDocument, approved: Any
) -> bool:
    if (
        item.get("source_id") != approved.source_id
        or item.get("original_url") != approved.url
        or item.get("document_hash") != document.document_hash
        or item.get("relation") != "supports"
        or item.get("evidence_eligible") is not True
        or not isinstance(item.get("evidence_text"), str)
        or not item["evidence_text"]
        or item["evidence_text"] not in document.text
    ):
        return False
    table_context = item.get("table_context")
    if table_context is not None:
        reparsed = _structured_table_evidence(document)
        if not any(
            row["paragraph_locator"] == item.get("paragraph_locator")
            and row["evidence_text"] == item.get("evidence_text")
            and row["claim_key"] == item.get("claim_key")
            and row["claim_values"] == item.get("claim_values")
            and row["table_context"] == table_context
            for row in reparsed
        ):
            return False
    has_locator = any(
        item.get(name) not in (None, "")
        for name in ("source_section", "paragraph_locator", "page_number", "json_pointer")
    )
    return has_locator


def _authority_scope_matches(scope: Any, item: dict[str, Any]) -> bool:
    context = item.get("table_context")
    if context is None:
        return _scope_terms_appear(scope, item["evidence_text"])
    if (
        scope.subject.casefold().strip() != context["row_label"].casefold().strip()
        or scope.period.casefold().strip() != context["period"].casefold().strip()
        or (scope.unit or "").casefold().strip() != context["unit"].casefold().strip()
        or (scope.statistic or "").casefold().strip() != context["statistic"].casefold().strip()
    ):
        return False
    heading = " ".join(
        f"{context['table_title']} {context['header_excerpt']}".casefold().split()
    )
    for term in (scope.measure, scope.certainty):
        folded = " ".join(term.casefold().split())
        if folded in {"projection", "projections"}:
            if re.search(r"\bprojections?\b", heading) is None:
                return False
        elif folded not in heading:
            return False
    return True


def _verify_authority_candidate(
    candidate: dict[str, Any],
    items: list[dict[str, Any]],
    source_policy: AuthoritativePrimarySetPolicyV1,
    documents: dict[str, FetchedDocument],
) -> tuple[str, dict[str, Any]] | None:
    """Verify only exact attributed reports or a fixed deterministic comparison wording."""
    if set(candidate) - {"claim_text", "claim_type", "authority_attestation", "comparison"}:
        return None
    if candidate.get("claim_type") != "fact" or not isinstance(candidate.get("claim_text"), str):
        return None
    try:
        from fanglei.checkpoint_contract import AuthorityAttestation

        attestation = AuthorityAttestation.model_validate(candidate.get("authority_attestation"))
    except Exception:
        return None
    approved_by_id = {row.source_id: row for row in source_policy.approved_documents}
    if not set(attestation.source_ids).issubset(approved_by_id):
        return None
    if source_policy.institution.display_name.casefold() not in attestation.attribution.casefold():
        return None
    if attestation.attribution not in candidate["claim_text"]:
        return None
    if _AUTHORITY_SCOPE_EXPANSION.search(candidate["claim_text"]):
        return None
    if not items or any(item.get("claim_type") != "fact" for item in items):
        return None
    if any(item.get("relation") != "supports" for item in items):
        return None
    item_ids = [item.get("source_id") for item in items]
    if len(item_ids) != len(set(item_ids)) or set(item_ids) != set(attestation.source_ids):
        return None
    if any(
        source_id not in documents
        or not _authority_evidence_matches(item, documents[source_id], approved_by_id[source_id])
        or not _authority_scope_matches(attestation.scope, item)
        or _AUTHORITY_SCOPE_EXPANSION.search(item["evidence_text"])
        for item, source_id in zip(items, item_ids)
    ):
        return None

    if attestation.kind == "document_report":
        if len(items) != 1 or len(attestation.source_ids) != 1 or "comparison" in candidate:
            return None
        exact_proposition = f'{attestation.attribution}: "{items[0]["evidence_text"]}"'
        if candidate["claim_text"] != exact_proposition:
            return None
        return candidate["claim_text"], attestation.model_dump(mode="json")

    if attestation.kind != "deterministic_document_comparison" or len(items) != 2:
        return None
    comparison = candidate.get("comparison")
    if not isinstance(comparison, dict) or set(comparison) != {"values"}:
        return None
    values = comparison.get("values")
    if not isinstance(values, dict) or set(values) != set(attestation.source_ids):
        return None
    source_documents = [approved_by_id[source_id] for source_id in attestation.source_ids]
    if (
        len({row.document_identity for row in source_documents}) != 2
        or len({row.source_text_sha256 for row in source_documents}) != 2
        or len({row.release_date for row in source_documents}) != 2
        or len({row.evidence_role for row in source_documents}) != 2
    ):
        return None
    if any(not isinstance(value, str) or not value.strip() for value in values.values()):
        return None
    ordered = sorted(
        attestation.source_ids,
        key=lambda source_id: approved_by_id[source_id].release_date,
    )
    earlier_id, later_id = ordered
    earlier_value, later_value = values[earlier_id], values[later_id]
    if earlier_value == later_value:
        return None
    item_by_id = {item["source_id"]: item for item in items}
    if any(
        not _value_appears(values[source_id], item_by_id[source_id]["evidence_text"])
        for source_id in ordered
    ):
        return None
    scope = attestation.scope
    unit = f" {scope.unit}" if scope.unit else ""
    comparison_text = (
        f"{attestation.attribution}: published {scope.statistic or 'value'} {scope.measure} for "
        f"{scope.subject} ({scope.period}) changed from {earlier_value}{unit} in "
        f"{approved_by_id[earlier_id].document_identity} ({approved_by_id[earlier_id].release_date}) "
        f"to {later_value}{unit} in {approved_by_id[later_id].document_identity} "
        f"({approved_by_id[later_id].release_date})."
    )
    if candidate["claim_text"] != comparison_text:
        return None
    return comparison_text, attestation.model_dump(mode="json")


def verify_claims_v22(
    evidence: list[dict[str, Any]],
    source_context: dict[str, bool | dict[str, Any]],
    source_artifact: dict[str, Any],
    documents: list[FetchedDocument],
    document_index: dict[str, Any],
    *,
    run_id: str,
    case_id: str | None = None,
    authority_claims: Mapping[str, Mapping[str, Any]] | None = None,
    checked_at: str | None = None,
) -> dict[str, Any]:
    """Produce native facts 2.2 with independently gated verification bases.

    Authority candidates are opt-in records keyed by the same evidence claim key
    used by ``verify_claims``. Only exact attributed quotation or a fixed
    two-document numeric comparison wording can receive an authority basis.
    """
    from fanglei.source_contract import AuthoritativePrimarySetPolicyV1

    parsed = validate_sources_artifact_v21(
        source_artifact,
        documents=documents,
        document_index=document_index,
        run_id=run_id,
        case_id=case_id,
    )
    if parsed.package_admissibility != "admissible":
        raise SourcePackageValidationError("claim extraction is blocked for an inadmissible source package")
    if authority_claims is not None and (
        not isinstance(authority_claims, Mapping)
        or any(not isinstance(key, str) or not isinstance(value, Mapping) for key, value in authority_claims.items())
    ):
        raise SourcePackageValidationError("authority_claims must map evidence claim keys to objects")
    expected_context = {row.source_id: row.model_dump(mode="python") for row in parsed.sources}
    expected_source_rows = {
        row["source_id"]: SourceRowV21.model_validate(row).model_dump(mode="python")
        for row in deduplicate_sources(documents)
    }
    actual_source_rows = {row.source_id: row.model_dump(mode="python") for row in parsed.sources}
    if actual_source_rows != expected_source_rows:
        raise SourcePackageValidationError("source rows do not match the existing deduplication algorithm for this capture")
    if set(source_context) != set(expected_context):
        raise SourcePackageValidationError("source context must exactly match registered source rows")
    for source_id, expected in expected_context.items():
        context = source_context[source_id]
        if not isinstance(context, dict) or context != expected:
            raise SourcePackageValidationError(f"source context differs from registered source row {source_id}")

    source_policy = parsed.source_policy
    policy_is_authority = isinstance(source_policy, AuthoritativePrimarySetPolicyV1)
    grouped_items: dict[str, list[dict[str, Any]]] = {}
    for item in evidence:
        grouped_items.setdefault(evidence_claim_key(item), []).append(item)
    unknown_candidates = set(authority_claims or {}) - set(grouped_items)
    if unknown_candidates:
        raise SourcePackageValidationError(
            "authority claim keys do not match captured evidence groups: " + ", ".join(sorted(unknown_candidates))
        )

    # The V2.1 verifier remains the sole implementation of ordinary
    # corroboration. Its status/risk thresholds are unchanged.
    facts = verify_claims(
        evidence,
        source_context,
        minimum_sources_met=parsed.selection_status == "selected",
    )
    group_keys = list(grouped_items)
    documents_by_id = {document.source_id: document for document in documents}
    gated_by_key: dict[str, list[dict[str, Any]]] = {}
    if policy_is_authority and authority_claims:
        for item in gate_evidence(evidence, documents):
            gated_by_key.setdefault(evidence_claim_key(item), []).append(item)
    for index, claim in enumerate(facts["claims"]):
        key = group_keys[index]
        claim["verification_basis"] = (
            "independent_corroboration" if claim["verification_status"] == "verified" else "none"
        )
        claim["authority_attestation"] = None
        if claim["verification_status"] != "verified":
            claim["allowed_downstream"] = False
        candidate = (authority_claims or {}).get(key)
        if candidate is None or not policy_is_authority:
            continue
        verified = _verify_authority_candidate(
            candidate,
            gated_by_key.get(key, []),
            source_policy,
            documents_by_id,
        )
        if verified is None:
            if any(item.get("table_context") is not None for item in grouped_items[key]):
                # Different published table values are a temporal comparison,
                # not independent corroboration of one unchanged proposition.
                # If its explicit authority candidate fails, keep it unresolved.
                claim.update({
                    "verification_status": "unverified",
                    "verification_basis": "none",
                    "authority_attestation": None,
                    "verification_reason": "structured table comparison did not satisfy authority verification",
                    "allowed_downstream": False,
                    "script_usage": script_usage("unverified"),
                })
            # An invalid authority proposal cannot confer authority status. If
            # the ordinary verifier independently verified it, that separate
            # basis remains intact; otherwise it stays unverified.
            continue
        proposition, attestation = verified
        claim.update({
            "claim_text": proposition,
            "claim_type": "fact",
            "verification_status": "verified",
            "verification_basis": "authoritative_primary_attestation",
            "authority_attestation": attestation,
            "source_ids": list(attestation["source_ids"]),
            "verification_reason": "exact attributed proposition is directly supported by the approved primary document package",
            "allowed_downstream": True,
            "script_usage": {
                "status": "assertion_allowed",
                "reason": "verified attributed primary-document statement",
            },
        })
    final_checked_at = checked_at or datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        timestamp_value = final_checked_at[:-1] + "+00:00" if final_checked_at.endswith("Z") else final_checked_at
        parsed_timestamp = datetime.fromisoformat(timestamp_value)
    except (AttributeError, ValueError) as error:
        raise SourcePackageValidationError("checked_at must be a timezone-aware ISO-8601 timestamp") from error
    if parsed_timestamp.tzinfo is None or parsed_timestamp.utcoffset() is None:
        raise SourcePackageValidationError("checked_at must be a timezone-aware ISO-8601 timestamp")
    facts.update({
        "schema_version": "2.2",
        "run_id": run_id,
        "checked_at": final_checked_at,
        "policy_version": "economics-v1.2",
    })
    facts["summary"] = {
        status: sum(claim["verification_status"] == status for claim in facts["claims"])
        for status in ("verified", "conflicted", "unverified")
    }
    return facts
