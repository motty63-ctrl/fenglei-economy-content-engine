"""Source independence, evidence extraction, and deterministic fact checks."""

from __future__ import annotations

import hashlib
from difflib import SequenceMatcher
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit


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

        independent_ids = {item["source_id"] for item in items if is_independent(item["source_id"])}
        independent_count = len(independent_ids)
        has_primary = any(is_primary(source_id) for source_id in independent_ids)
        claim_type = items[0].get("claim_type", "fact")
        values = {
            tuple(item["claim_values"]) if item.get("claim_values") else _claim_identity(item["evidence_text"])[1]
            for item in items
        }
        status = "conflicted" if claim_type == "fact" and len(values) > 1 else (
            "verified" if claim_type == "fact" and minimum_sources_met and independent_count >= 2 and has_primary else "unverified"
        )
        internal_fields = {"claim_type", "claim_key", "claim_values", "normalized_claim_text"}
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
            }
        )
    return {
        "schema_version": "2.0",
        "policy_version": "economics-v1",
        "claims": claims,
        "summary": {
            "verified": sum(c["verification_status"] == "verified" for c in claims),
            "conflicted": sum(c["verification_status"] == "conflicted" for c in claims),
            "unverified": sum(c["verification_status"] == "unverified" for c in claims),
        },
    }
