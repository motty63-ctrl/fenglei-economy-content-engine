"""Deterministic factual, duration, structure, and oral-quality gates."""
from __future__ import annotations
from decimal import Decimal
import re
from fanglei.authority_safety import authority_text_issues
from fanglei.content_models import AngleCandidate, LintIssue, ScriptDraft, ScriptLintResult
from fanglei.evidence_policy import is_claim_eligible_for_content
from fanglei.originality import check_fact_originality, check_originality
from fanglei.script_terminology import (
    ScriptTerminologyMapV1,
    _canonical_field_values,
    validate_script_terminology_map,
)


def _spoken_count(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", text))


_ENTITY_PATTERNS = {
    "institution:bea": r"\bBEA\b|美国经济分析局",
    "institution:world_bank": r"\bWorld Bank\b|世界银行",
    "institution:imf": r"\bIMF\b|国际货币基金组织",
    "institution:oecd": r"\bOECD\b|经济合作与发展组织",
    "institution:fed": r"\bFederal Reserve\b|\bFed\b|美联储|美国联邦储备(?:委员会|系统)?",
    "institution:ecb": r"\bEuropean Central Bank\b|\bECB\b|欧洲中央银行|欧洲央行",
    "country:us": r"\b(?:United States|U\.S\.|USA)\b|美国",
    "country:china": r"\bChina\b|中国",
    "country:canada": r"\bCanada\b|加拿大",
    "country:germany": r"\bGermany\b|德国",
    "country:brazil": r"\bBrazil\b|巴西",
    "metric:real_gdp": r"\breal GDP\b|实际GDP|实际国内生产总值",
    "metric:gdp": r"\bGDP\b|国内生产总值",
    "metric:inflation": r"\binflation\b|\bCPI\b|通胀率|消费者价格指数",
    "metric:unemployment": r"\bunemployment\b|失业率",
    "metric:interest_rate": r"\b(?:interest rate|federal funds rate)\b|联邦基金利率|政策利率|利率",
    "metric:exchange_rate": r"\bexchange rate\b|汇率",
    "metric:employment": r"\bemployment\b|\bjobs?\b|就业",
    "metric:wages": r"\bwages?\b|工资|薪资",
}


def _value_tokens(text: str) -> set[tuple[Decimal, str, str]]:
    tokens = set()
    pattern = re.compile(
        r"(?P<sign>[+-]?)\s*(?P<number>\d[\d,]*(?:\.\d+)?)\s*"
        r"(?P<unit>个百分点|percentage\s+points?|percent|%|万亿美元|亿美元|美元|亿元|元)?",
        re.I,
    )
    for match in pattern.finditer(text):
        value = Decimal(match.group("number").replace(",", ""))
        sign = match.group("sign")
        if sign == "-":
            value = -value
        unit_raw = (match.group("unit") or "").lower().replace(" ", "")
        unit = ("percentage_point" if unit_raw in {"个百分点", "percentagepoint", "percentagepoints"}
                else "percent" if unit_raw in {"%", "percent"}
                else {"万亿美元": "usd_trillion", "亿美元": "usd_100m", "美元": "usd",
                      "亿元": "cny_100m", "元": "cny"}.get(unit_raw, "number"))
        is_year = unit == "number" and sign != "-" and Decimal(1900) <= value <= Decimal(2100)
        if is_year:
            direction = "year"
        else:
            window = text[max(0, match.start() - 14):match.end() + 8]
            negative = bool(re.search(r"下降|下跌|减少|收缩|declin|fell|fall|decreas|contract", window, re.I))
            positive = bool(re.search(r"增长|上升|增加|grew|growth|rose|ris|increas", window, re.I))
            direction = "negative" if value < 0 or negative else "positive" if positive else "neutral"
        tokens.add((value, unit, direction))
    return tokens


def _entities(text: str) -> set[str]:
    entities = {name for name, pattern in _ENTITY_PATTERNS.items() if re.search(pattern, text, re.I)}
    known_acronyms = {"GDP", "CPI", "BEA", "IMF", "OECD", "US", "USA"}
    entities.update(f"named:{value.lower()}" for value in re.findall(r"\b[A-Z]{2,10}\b", text)
                    if value not in known_acronyms)
    for name in re.findall(
        r"([\u4e00-\u9fff]{2,10})(?:称|表示|显示(?!精度|差异|方式)|认为|预计|宣布)", text
    ):
        if not any(re.search(pattern, name, re.I) for pattern in _ENTITY_PATTERNS.values()):
            entities.add(f"named:{name}")
    for name in re.findall(
        r"\b((?:[A-Z][a-z]+\s+){1,5}[A-Z][a-z]+)\s+(?:said|reported|shows?|expects?)\b",
        text,
    ):
        if not any(re.search(pattern, name, re.I) for pattern in _ENTITY_PATTERNS.values()):
            normalized_name = re.sub(r"\s+", " ", name).lower()
            entities.add(f"named:{normalized_name}")
    return entities


def _evidence_context(claim: dict, evidence: list[dict]) -> str:
    parts = [str(claim.get("claim_text", ""))]
    for item in evidence:
        parts.extend(str(item.get(key, "")) for key in ("evidence_text", "observation", "value"))
    return " ".join(parts)


_TRANSLATED_NUMBER_RE = re.compile(
    r"(?P<prefix>\$|USD\s*|CNY\s*)?(?P<sign>[+-]?)\s*"
    r"(?P<number>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)"
    r"(?P<magnitude>万|億|亿)?\s*"
    r"(?P<unit>percentage\s+points?|percentage|percent|个百分点|百分比|%|"
    r"cents?|美分|dollars?|美元|元|hours?|小时|units?|单位|jobs?|岗位|人)?",
    re.I,
)
_CHINESE_NUMERIC_WITH_CONTEXT_RE = re.compile(
    r"(?:百分之[零〇一二两三四五六七八九十百千万亿点]+|"
    r"[零〇一二两三四五六七八九十百千万亿]+(?:点[零〇一二两三四五六七八九]+)?)(?="
    r"个|单位|人|岗位|小时|美元|百分比|个百分点|倍|项|件|年|月|日)|"
    r"(?:增加|减少|上升|下降|提高|降低|为|达|从|到)"
    r"[零〇一二两三四五六七八九十百千万亿]+(?:点[零〇一二两三四五六七八九]+)?"
)
_LANGUAGE_EXPANSION_RE = re.compile(
    r"\b(?:because|caused? by|caus(?:e|ed|ing)|forced?|motive|due to|"
    r"led to|resulted in|market impact|market effect|therefore|will cut rates?|"
    r"predict(?:s|ed|ing)?|expect(?:s|ed|ing)?|policy judgment|should (?:raise|cut|hold))\b|"
    r"因为|由于|导致|造成|促使|迫使|归因于|动机|市场影响|市场效应|因此使|"
    r"预测|预计|将(?:会|要)?(?:上升|下降|增加|减少|降息|加息)|应当(?:加息|降息|维持)",
    re.I,
)


def _language_script_counts(text: str) -> tuple[int, int]:
    return len(re.findall(r"[\u4e00-\u9fff]", text)), len(re.findall(r"[A-Za-z]", text))


def _is_cross_language_claim(claim: dict, target_language: str | None) -> bool:
    if not target_language:
        return False
    source = " ".join([
        str(claim.get("claim_text", "")),
        *[str(item.get("proposition_span", {}).get("text", ""))
          for item in claim.get("evidence", []) if isinstance(item, dict)],
    ])
    cjk, latin = _language_script_counts(source)
    language = target_language.casefold().replace("_", "-")
    if language.startswith(("zh", "ja", "ko")):
        return latin >= 8 and latin > cjk
    if language.startswith(("en", "de", "fr", "es", "it", "pt", "nl")):
        return cjk >= 2 and cjk > latin
    return cjk > 0 and latin > cjk or latin >= 8 and latin > cjk


def _approved_entries(
    terminology: ScriptTerminologyMapV1, claim_id: str, role: str | None = None,
) -> list[Any]:
    return [entry for entry in terminology.entries
            if claim_id in entry.claim_ids and entry.review_status == "approved"
            and (role is None or entry.semantic_role == role)]


def _has_term(text: str, term: str) -> bool:
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9 .'-]*", term):
        return bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", text, re.I))
    return term.casefold() in text.casefold()


def _required_cross_language_terms(claim: dict) -> list[tuple[str, str, str]]:
    attestation = claim.get("authority_attestation", {})
    scope = attestation.get("scope", {}) if isinstance(attestation, dict) else {}
    fields = (
        ("subject", "authority_attestation.scope.subject"),
        ("metric", "authority_attestation.scope.measure"),
        ("population", "authority_attestation.scope.population"),
        ("reporting_scope", "authority_attestation.scope.reporting_scope"),
        ("unit", "authority_attestation.scope.unit"),
        ("period", "authority_attestation.scope.period"),
        ("statistic", "authority_attestation.scope.statistic"),
        ("direction", "authority_attestation.scope.certainty"),
    )
    result: list[tuple[str, str, str]] = []
    for role, source_field in fields:
        value = scope.get(source_field.rsplit(".", 1)[1]) if isinstance(scope, dict) else None
        if isinstance(value, str) and value.strip():
            result.append((role, source_field, value))
    if not any(role == "reporting_scope" for role, _, _ in result):
        sections = sorted({value for value in _canonical_field_values(claim, "evidence.source_section")})
        if len(sections) == 1:
            result.append(("reporting_scope", "evidence.source_section", sections[0]))
    for value in sorted(set(_canonical_field_values(claim, "evidence.explicit_values.unit"))):
        result.append(("unit", "evidence.explicit_values.unit", value))
    revision_fields = (
        ("revision_previous", "evidence.revision_values.previous_value"),
        ("revision_revised", "evidence.revision_values.revised_value"),
        ("revision_delta", "evidence.revision_values.revision_amount"),
        ("direction", "evidence.revision_values.direction"),
    )
    for role, source_field in revision_fields:
        for value in _canonical_field_values(claim, source_field):
            result.append((role, source_field, value))
    return result


def _number_and_unit(value: str, declared_unit: str | None = None) -> tuple[Decimal, str, bool] | None:
    match = _TRANSLATED_NUMBER_RE.search(value)
    if not match:
        return None
    try:
        number = Decimal(match.group("number").replace(",", ""))
    except Exception:
        return None
    sign = match.group("sign") or ""
    if sign == "-":
        number = -number
    magnitude = match.group("magnitude") or ""
    if magnitude in {"万"}:
        number *= Decimal(10000)
    elif magnitude in {"亿", "億"}:
        number *= Decimal(100000000)
    prefix = (match.group("prefix") or "").strip().casefold()
    raw_unit = (match.group("unit") or "").casefold().replace(" ", "")
    if prefix in {"$", "usd"} or raw_unit in {"dollar", "dollars", "美元", "元"}:
        unit = "currency"
    elif prefix == "cny":
        unit = "currency_cny"
    elif raw_unit in {"%", "percent", "percentage", "百分比"}:
        unit = "percent"
    elif raw_unit in {"percentagepoint", "percentagepoints", "个百分点"}:
        unit = "percentage_point"
    elif raw_unit in {"cent", "cents", "美分"}:
        unit = "cents"
    elif raw_unit in {"hour", "hours", "小时"}:
        unit = "hours"
    elif raw_unit in {"unit", "units", "单位"}:
        unit = "units"
    elif raw_unit in {"job", "jobs", "岗位", "人"}:
        unit = "jobs"
    elif raw_unit:
        unit = raw_unit
    else:
        unit = "number"
    if declared_unit is not None and unit == "number":
        unit = _normalize_declared_unit(declared_unit)
    return number, unit, bool(sign)


def _normalize_declared_unit(value: str | None) -> str:
    raw = (value or "").strip().casefold().replace(" ", "")
    if raw in {"%", "percent", "percentage"}:
        return "percent"
    if raw in {"percentagepoint", "percentagepoints", "pp", "个百分点"}:
        return "percentage_point"
    if raw in {"cent", "cents", "美分"}:
        return "cents"
    if raw in {"$", "usd", "dollar", "dollars", "美元", "元"}:
        return "currency"
    if raw in {"hour", "hours", "小时"}:
        return "hours"
    if raw in {"job", "jobs", "岗位", "人"}:
        return "jobs"
    if raw in {"unit", "units", "单位"}:
        return "units"
    return raw or "number"


def _expected_numbers(claim: dict) -> list[tuple[Decimal, str, bool, str | None]]:
    result: list[tuple[Decimal, str, bool, str | None]] = []
    for evidence in claim.get("evidence", []):
        if not isinstance(evidence, dict) or evidence.get("evidence_eligible") is not True:
            continue
        revision = evidence.get("revision_values")
        revision_numbers: dict[tuple[Decimal, str], str] = {}
        if isinstance(revision, dict):
            for key, role in (("previous_value", "revision_previous"),
                              ("revised_value", "revision_revised"),
                              ("revision_amount", "revision_delta")):
                raw = revision.get(key)
                parsed = _number_and_unit(str(raw)) if isinstance(raw, str) else None
                if parsed:
                    revision_numbers[(parsed[0], parsed[1])] = role
        explicit = evidence.get("explicit_values")
        if isinstance(explicit, list):
            for item in explicit:
                if not isinstance(item, dict) or not isinstance(item.get("value"), str):
                    continue
                parsed = _number_and_unit(item["value"], item.get("unit"))
                if not parsed:
                    continue
                number, unit, signed = parsed
                role = revision_numbers.get((number, unit))
                result.append((number, unit, signed, role))
        elif isinstance(revision, dict):
            for key, role in (("previous_value", "revision_previous"),
                              ("revised_value", "revision_revised"),
                              ("revision_amount", "revision_delta")):
                raw = revision.get(key)
                parsed = _number_and_unit(str(raw)) if isinstance(raw, str) else None
                if parsed:
                    result.append((parsed[0], parsed[1], parsed[2], role))
    return result


def _number_token_role_ok(
    text: str, start: int, end: int, role: str | None, claim_id: str,
    terminology: ScriptTerminologyMapV1,
) -> bool:
    if role is None:
        return True
    entries = _approved_entries(terminology, claim_id, role)
    before = text[max(0, start - 24):start]
    return bool(entries) and any(_has_term(before, alias)
                                 for entry in entries for alias in entry.approved_target_terms)


def _cross_language_claim_issues(
    text: str,
    claim: dict,
    terminology: ScriptTerminologyMapV1,
    *,
    attribution_inherited: bool = False,
) -> set[str]:
    issues: set[str] = set()
    claim_id = claim.get("claim_id")
    if not isinstance(claim_id, str) or not is_claim_eligible_for_content(claim):
        return {"CLAIM_NOT_ELIGIBLE"}
    attestation = claim.get("authority_attestation")
    if not isinstance(attestation, dict) or attestation.get("kind") not in {
        "document_report", "deterministic_document_comparison"
    }:
        return {"AUTHORITY_SCOPE_MISMATCH"}
    from fanglei.authority_safety import _atomic_evidence_rows

    if _atomic_evidence_rows(claim, attestation) is None:
        return {"AUTHORITY_SCOPE_MISMATCH"}

    required_scope = attestation.get("scope", {})
    if not all(isinstance(required_scope.get(key), str) and required_scope[key].strip()
               for key in ("subject", "measure", "period", "certainty")):
        issues.add("AUTHORITY_SCOPE_INCOMPLETE")
    explicit_scopes = _canonical_field_values(claim, "authority_attestation.scope.reporting_scope")
    section_scopes = _canonical_field_values(claim, "evidence.source_section")
    if not explicit_scopes and len(set(section_scopes)) != 1:
        issues.add("AUTHORITY_SCOPE_INCOMPLETE")
    attribution = attestation.get("attribution")
    attribution_entries = [entry for entry in _approved_entries(terminology, claim_id, "source_attribution")
                           if entry.source_field == "authority_attestation.attribution"
                           and entry.source_term == attribution]
    if not attribution_inherited and (not attribution_entries or not any(
        _has_term(text, alias) for entry in attribution_entries for alias in entry.approved_target_terms
    )):
        issues.add("ATTRIBUTION_CONTEXT_ANCHOR_REQUIRED")

    for role, source_field, source_term in _required_cross_language_terms(claim):
        equivalent_fields = {source_field}
        if role == "reporting_scope":
            equivalent_fields.update({
                field for field in ("authority_attestation.scope.reporting_scope", "evidence.source_section")
                if source_term in _canonical_field_values(claim, field)
            })
        elif role == "unit":
            equivalent_fields.update({
                field for field in ("authority_attestation.scope.unit", "evidence.explicit_values.unit")
                if source_term in _canonical_field_values(claim, field)
            })
        matching = [entry for entry in _approved_entries(terminology, claim_id, role)
                    if entry.source_field in equivalent_fields and entry.source_term == source_term]
        if not matching or not any(
            _has_term(text, alias) for entry in matching for alias in entry.approved_target_terms
        ):
            issues.add("TERMINOLOGY_TERM_MISSING")

    if _LANGUAGE_EXPANSION_RE.search(text):
        issues.add("AUTHORITY_SCOPE_EXPANSION")

    period_aliases = [alias for entry in _approved_entries(terminology, claim_id, "period")
                      for alias in entry.approved_target_terms]
    number_text = text
    for alias in sorted(set(period_aliases), key=len, reverse=True):
        if alias:
            number_text = re.sub(re.escape(alias), " ", number_text, flags=re.I)
    if _CHINESE_NUMERIC_WITH_CONTEXT_RE.search(number_text):
        issues.add("UNSUPPORTED_NUMERIC_FORMAT")

    expected = _expected_numbers(claim)
    matches = list(_TRANSLATED_NUMBER_RE.finditer(number_text))
    for match in matches:
        parsed = _number_and_unit(match.group(0))
        if not parsed:
            issues.add("UNSUPPORTED_NUMERIC_VALUE")
            continue
        value, unit, signed = parsed
        candidates = [row for row in expected if row[0] == value and row[1] == unit
                      and (not row[2] or signed)]
        if not candidates:
            issues.add("UNSUPPORTED_NUMERIC_VALUE")
            continue
        if not any(_number_token_role_ok(number_text, match.start(), match.end(), row[3],
                                         claim_id, terminology) for row in candidates):
            issues.add("REVISION_ROLE_MISMATCH")
        declared_unit = unit != "number"
        if declared_unit:
            unit_entries = _approved_entries(terminology, claim_id, "unit")
            rendered_unit = " ".join(filter(None, (match.group("prefix"), match.group("unit"))))
            if not any(
                _normalize_declared_unit(entry.source_term) == unit
                and any(_has_term(rendered_unit, alias)
                        for alias in entry.approved_target_terms)
                for entry in unit_entries
            ):
                issues.add("UNIT_SCOPE_MISMATCH")
    return issues


def _validate_cross_language_attribution_contexts(
    sentences: list[Any], claims: dict[str, dict], terminology: ScriptTerminologyMapV1,
) -> tuple[dict[str, set[str]], set[str]]:
    """Validate explicit, consecutive source attribution contexts."""
    failures: dict[str, set[str]] = {}
    inherited: set[str] = set()
    active_id: str | None = None
    active_signature: tuple[tuple[str, ...], tuple[str, ...], str] | None = None
    for sentence in sentences:
        bound = [claims.get(claim_id) for claim_id in sentence.claim_ids]
        authorities = [claim for claim in bound if isinstance(claim, dict)
                       and claim.get("verification_basis") == "authoritative_primary_attestation"]
        context_id = sentence.attribution_context_id
        if not authorities or len(authorities) != len(bound):
            if context_id is not None:
                failures.setdefault(sentence.sentence_id, set()).add("ATTRIBUTION_CONTEXT_INVALID")
            active_id, active_signature = None, None
            continue
        signatures = []
        for claim in authorities:
            attestation = claim.get("authority_attestation", {})
            signatures.append((tuple(sorted(claim.get("source_ids", []))),
                               str(attestation.get("attribution", ""))))
        signature = (
            tuple(sorted({source for sources, _ in signatures for source in sources})),
            tuple(sorted({attribution for _, attribution in signatures})),
            sentence.section,
        )
        active_reuse = context_id is not None and context_id == active_id and signature == active_signature
        explicit = True
        for claim in authorities:
            claim_id = claim["claim_id"]
            attestation = claim.get("authority_attestation", {})
            attribution = attestation.get("attribution")
            entries = _approved_entries(terminology, claim_id, "source_attribution")
            has_alias = isinstance(attribution, str) and any(
                entry.source_field == "authority_attestation.attribution"
                and entry.source_term == attribution
                and any(_has_term(sentence.text, alias) for alias in entry.approved_target_terms)
                for entry in entries
            )
            if not has_alias:
                explicit = False
        if active_reuse:
            foreign_attributions = {
                entry.source_term
                for entry in terminology.entries
                if entry.semantic_role == "source_attribution"
                and entry.source_field == "authority_attestation.attribution"
                and any(_has_term(sentence.text, alias) for alias in entry.approved_target_terms)
                and entry.source_term not in {item[1] for item in signatures}
            }
            if foreign_attributions:
                failures.setdefault(sentence.sentence_id, set()).add("ATTRIBUTION_CONTEXT_CONFLICT")
                active_id, active_signature = None, None
                continue
            inherited.add(sentence.sentence_id)
        elif not explicit:
            failures.setdefault(sentence.sentence_id, set()).add("ATTRIBUTION_CONTEXT_ANCHOR_REQUIRED")
            active_id, active_signature = None, None
            continue
        if context_id is not None:
            active_id, active_signature = context_id, signature
        else:
            active_id, active_signature = None, None
    return failures, inherited


def _cross_language_closing_issues(
    draft: ScriptDraft, angle: AngleCandidate, claims: dict[str, dict],
    terminology: ScriptTerminologyMapV1,
) -> set[str]:
    if not draft.sentences:
        return {"CORE_JUDGMENT_MISSING"}
    selected_terms = {
        (role, term.casefold())
        for claim_id in angle.supporting_claim_ids
        if isinstance(claims.get(claim_id), dict)
        for role, _field, term in _required_cross_language_terms(claims[claim_id])
        if role in {"subject", "metric"}
    }
    # A one-dimension angle cannot produce a multi-dimension synthesis; retain
    # the generic declarative closing rule for that narrower case.
    if len({term for _role, term in selected_terms}) < 2:
        return set()
    closing = draft.sentences[-1]
    bound_ids = list(dict.fromkeys(closing.claim_ids))
    if len(bound_ids) < 2 or not set(bound_ids) <= set(angle.supporting_claim_ids):
        return {"CORE_JUDGMENT_WEAK"}
    dimensions: set[tuple[str, str]] = set()
    for claim_id in bound_ids:
        claim = claims.get(claim_id)
        if not isinstance(claim, dict):
            continue
        terms = _required_cross_language_terms(claim)
        for role, field, source_term in terms:
            if role not in {"subject", "metric"}:
                continue
            approved = [entry for entry in _approved_entries(terminology, claim_id, role)
                        if entry.source_field == field and entry.source_term == source_term]
            if not approved or not any(
                _has_term(closing.text, alias)
                for entry in approved for alias in entry.approved_target_terms
            ):
                continue
            dimensions.add((role, source_term.casefold()))
    if len({term for _, term in dimensions}) < 2:
        return {"CORE_JUDGMENT_WEAK"}
    if _LANGUAGE_EXPANSION_RE.search(closing.text):
        return {"AUTHORITY_SCOPE_EXPANSION"}
    return set()


def semantic_factuality_signals(text: str) -> set[str]:
    """Detect externally checkable assertions without trusting sentence_type."""
    signals = set()
    explicit_nonfactual = bool(re.search(
        r"打个比方|好比|就像|仿佛|我更愿意|我把它看成|可以把.+理解成|"
        r"我的判断|我认为|我建议|建议(?:先|你)|请(?:先)?核对|不妨(?:先)?核对|"
        r"下次.+(?:先看|先查|核对)|你可以(?:先)?|你不妨|你要做的是",
        text,
    ))
    assertive_factual_clause = bool(re.search(
        r"其实|事实上|(?:数据|结果|数值).{0,12}(?:是|有|带着|包含|保留|显示)",
        text,
    ))
    if _value_tokens(text):
        signals.add("numeric_or_date")
    if re.search(r"一半|半数|两倍|三倍|[四五六七八九十]倍|百分之[零一二三四五六七八九十百]+", text):
        signals.add("numeric_or_date")
    institution_pattern = "|".join(
        f"(?:{pattern})" for name, pattern in _ENTITY_PATTERNS.items() if name.startswith("institution:")
    )
    if re.search(institution_pattern, text, re.I) and re.search(
        r"显示|公布|发布|宣布|认为|预计|报告|存(?:着|有)|提供|收录|保留|采用|使用|said|reported|shows?",
        text,
        re.I,
    ):
        signals.add("institution_action")
    if re.search(r"数据口径|统计口径|计算口径|季调|修订|基期|样本范围|四舍五入|保留.{0,6}小数|原始数(?:据|值)|原始值|显示精度", text) and not re.search(r"是否|先核对|需要核对|要看", text):
        signals.add("data_methodology")
    if re.search(r"导致|造成|源于|归因于|因为|使得", text):
        signals.add("causal_fact")
    if re.search(r"通常|往往|一般会|经常|常用|常被|偏好|倾向于|习惯于|方便.+(?:传播|复算|计算)", text):
        signals.add("usual_behavior")
    if (explicit_nonfactual and not assertive_factual_clause
            and "numeric_or_date" not in signals and not _entities(text)):
        return set()
    return signals


def lint_script(draft: ScriptDraft, angle: AngleCandidate, facts: dict, source_text: str,
                *, speaking_rate: float = 4.0, target_duration_seconds: int | None = None,
                hard_min_duration_seconds: int = 60, hard_max_duration_seconds: int = 90,
                terminology_map: dict | ScriptTerminologyMapV1 | None = None,
                current_facts_sha256: str | None = None, run_id: str | None = None,
                case_id: str | None = None, target_language: str | None = None) -> ScriptLintResult:
    issues: list[LintIssue] = []
    if not 2.5 <= speaking_rate <= 6.0:
        issues.append(LintIssue(code="INVALID_SPEAKING_RATE", message="speaking rate must be 2.5–6.0"))
    enforce_cross_language_contract = target_language is not None
    target_language = target_language or draft.target_language
    cross_language_claim_ids = {
        claim.get("claim_id") for claim in facts.get("claims", [])
        if isinstance(claim, dict) and isinstance(claim.get("claim_id"), str)
        and claim.get("verification_basis") == "authoritative_primary_attestation"
        and enforce_cross_language_contract and _is_cross_language_claim(claim, target_language)
    }
    parsed_terminology: ScriptTerminologyMapV1 | None = None
    terminology_error: str | None = None
    if cross_language_claim_ids:
        if terminology_map is None:
            terminology_error = "TERMINOLOGY_APPROVAL_REQUIRED"
        elif not all((current_facts_sha256, run_id, case_id)):
            terminology_error = "TERMINOLOGY_IDENTITY_REQUIRED"
        else:
            try:
                parsed_terminology = validate_script_terminology_map(
                    terminology_map, facts, expected_run_id=run_id or "",
                    expected_case_id=case_id or "", facts_sha256=current_facts_sha256 or "",
                    allowed_claim_ids=set(angle.supporting_claim_ids), require_approved=True,
                )
                if parsed_terminology.target_language.casefold() != target_language.casefold():
                    raise ValueError("TARGET_LANGUAGE_MISMATCH")
            except Exception as error:
                terminology_error = str(error).split(":", 1)[0]
                parsed_terminology = None
        if terminology_error:
            issues.append(LintIssue(
                code="SCRIPT_TERMINOLOGY_REVIEW_REQUIRED",
                message="cross-language authority claims require a current, approved terminology map",
            ))
    claims = {item["claim_id"]: item for item in facts.get("claims", [])}
    cross_sentence_ids: set[str] = set()
    if parsed_terminology is not None:
        context_failures, inherited_attribution = _validate_cross_language_attribution_contexts(
            draft.sentences, claims, parsed_terminology
        )
        for sentence in draft.sentences:
            if any(claim_id in cross_language_claim_ids for claim_id in sentence.claim_ids):
                cross_sentence_ids.add(sentence.sentence_id)
                if not set(sentence.claim_ids) <= cross_language_claim_ids:
                    issues.append(LintIssue(
                        code="MIXED_LANGUAGE_CLAIM_BINDING",
                        message="a translated sentence cannot mix mapped and unmapped claim languages",
                        sentence_id=sentence.sentence_id,
                    ))
                if not set(sentence.claim_ids) <= set(angle.supporting_claim_ids):
                    issues.append(LintIssue(
                        code="CLAIM_OUTSIDE_SELECTED_ANGLE",
                        message="script sentence references a claim outside the selected angle",
                        sentence_id=sentence.sentence_id,
                    ))
                for claim_id in sentence.claim_ids:
                    claim = claims.get(claim_id)
                    if claim is None or _is_cross_language_claim(claim, target_language):
                        if claim is None:
                            issues.append(LintIssue(code="CLAIM_NOT_ELIGIBLE", message="bound claim is unavailable",
                                                    sentence_id=sentence.sentence_id))
                        else:
                            codes = _cross_language_claim_issues(
                                sentence.text, claim, parsed_terminology,
                                attribution_inherited=sentence.sentence_id in inherited_attribution,
                            )
                            issues.extend(LintIssue(code=code, message="translated fact exceeds or misses its approved structured claim scope",
                                                    sentence_id=sentence.sentence_id)
                                          for code in sorted(codes))
        for sentence_id, codes in context_failures.items():
            issues.extend(LintIssue(code=code, message="authority attribution context is missing, stale, or incompatible",
                                    sentence_id=sentence_id) for code in sorted(codes))
        if cross_sentence_ids:
            closing_codes = _cross_language_closing_issues(draft, angle, claims, parsed_terminology)
            issues.extend(LintIssue(code=code, message="closing must synthesize distinct supported angle dimensions without scope expansion",
                                    sentence_id=draft.sentences[-1].sentence_id if draft.sentences else None)
                          for code in sorted(closing_codes))
    for sentence in draft.sentences:
        count = _spoken_count(sentence.text)
        if count > 48 or len(re.findall(r"[，；;：:]", sentence.text)) > 3:
            issues.append(LintIssue(code="COMPLEX_LONG_SENTENCE", message="sentence is too complex for speech", sentence_id=sentence.sentence_id))
        semantic_signals = semantic_factuality_signals(sentence.text)
        requires_claim = sentence.sentence_type == "verified_fact" or bool(semantic_signals)
        if requires_claim and not sentence.claim_ids:
            if semantic_signals:
                issues.append(LintIssue(code="UNDECLARED_FACT",
                                        message="factual-looking sentence lacks claim",
                                        sentence_id=sentence.sentence_id))
            codes = ([f"SEMANTIC_FACTUALITY_UNSUPPORTED_{signal.upper()}__{sentence.sentence_id.upper()}"
                      for signal in sorted(semantic_signals)]
                     or ["SEMANTIC_FACTUALITY_UNSUPPORTED"])
            issues.extend(LintIssue(code=code,
                                    message="externally checkable assertion requires a verified claim",
                                    sentence_id=sentence.sentence_id) for code in codes)
        if (re.search(r"打个比方|好比|就像|仿佛|(?:这|它|那)像", sentence.text)
                and sentence.sentence_type != "analogy"):
            issues.append(LintIssue(code="SENTENCE_TYPE_MISMATCH",
                                    message="obvious analogy must use sentence_type=analogy",
                                    sentence_id=sentence.sentence_id))
            issues.append(LintIssue(code=f"SENTENCE_TYPE_MISMATCH__{sentence.sentence_id.upper()}",
                                    message="obvious analogy must use sentence_type=analogy",
                                    sentence_id=sentence.sentence_id))
        if sentence.claim_ids:
            contexts: list[str] = []
            valid = True
            related_authority_claims = [
                claims[claim_id] for claim_id in sentence.claim_ids
                if claim_id in claims
                and claims[claim_id].get("verification_basis") == "authoritative_primary_attestation"
            ]
            for claim_id in sentence.claim_ids:
                claim = claims.get(claim_id)
                if not claim or not is_claim_eligible_for_content(claim):
                    valid = False
                    continue
                source_ids = set(claim.get("source_ids", []))
                eligible = [e for e in claim.get("evidence", [])
                            if e.get("evidence_eligible")
                            and e.get("source_id") in source_ids
                            and e.get("original_url")
                            and (e.get("evidence_text") or e.get("observation") is not None
                                 or e.get("value") is not None)]
                if not eligible: valid = False
                contexts.append(_evidence_context(claim, eligible))
                is_mapped_cross_language = (
                    enforce_cross_language_contract and parsed_terminology is not None
                    and _is_cross_language_claim(claim, target_language)
                )
                if claim.get("verification_basis") == "authoritative_primary_attestation" and not is_mapped_cross_language:
                    for code in authority_text_issues(
                        sentence.text, claim, related_claims=related_authority_claims
                    ):
                        issues.append(LintIssue(
                            code=code,
                            message="authority-backed claim attribution and scope must remain intact",
                            sentence_id=sentence.sentence_id,
                        ))
            if sentence.sentence_id not in cross_sentence_ids:
                clauses = [part for part in re.split(r"[，,；;。]", sentence.text) if part.strip()]
                factual_clauses = [part for part in clauses if _value_tokens(part) or _entities(part)]
                supported = all(any(
                    _value_tokens(part).issubset(_value_tokens(context))
                    and _entities(part).issubset(_entities(context))
                    for context in contexts
                ) for part in factual_clauses)
                if not valid or not factual_clauses or not supported:
                    issues.append(LintIssue(code="UNSUPPORTED_FACT", message="claim does not support sentence values", sentence_id=sentence.sentence_id))
            fact_originality = check_fact_originality(sentence.text, source_text)
            if fact_originality.status != "passed":
                issues.append(LintIssue(code="SOURCE_REUSE", message="verified fact reuses source expression", sentence_id=sentence.sentence_id))
    sections = [s.section for s in draft.sentences]
    if not sections or sections[0] != "hook" or _spoken_count(draft.sentences[0].text) / max(speaking_rate, 0.01) > 5:
        issues.append(LintIssue(code="HOOK_INVALID", message="hook must fit the first five seconds"))
    if "mechanism" not in sections:
        issues.append(LintIssue(code="MECHANISM_MISSING", message="mechanism section is required"))
    if not sections or sections[-1] != "core_judgment":
        issues.append(LintIssue(code="CORE_JUDGMENT_MISSING", message="final judgment is required"))
    elif (re.search(r"[？?]\s*$", draft.sentences[-1].text)
          or _spoken_count(draft.sentences[-1].text) < 12
          or re.search(r"以上就是数据|以上就是全部|这就是全部", draft.sentences[-1].text)):
        issues.append(LintIssue(code="CORE_JUDGMENT_WEAK",
                                message="final judgment must be an explicit declarative conclusion",
                                sentence_id=draft.sentences[-1].sentence_id))
        issues.append(LintIssue(code=f"CORE_JUDGMENT_WEAK__{draft.sentences[-1].sentence_id.upper()}",
                                message="final judgment must be an explicit declarative conclusion",
                                sentence_id=draft.sentences[-1].sentence_id))
    if any(re.search(r"镜头|画面|字幕|配音|storyboard|TTS", s.text, re.I) for s in draft.sentences):
        issues.append(LintIssue(code="PRODUCTION_DIRECTION", message="production directions are out of scope"))
    seen_sentences: set[str] = set()
    for sentence in draft.sentences:
        normalized = re.sub(r"[\s，。！？；：、,.!?;:]", "", sentence.text).lower()
        if normalized in seen_sentences:
            issues.append(LintIssue(code="REPEATED_SENTENCE", message="script repeats a sentence",
                                    sentence_id=sentence.sentence_id))
        seen_sentences.add(normalized)
    opener_patterns = (r"^你可以", r"^你不妨", r"^我的判断是", r"^打个比方", r"^就像")
    if any(sum(bool(re.search(pattern, sentence.text)) for sentence in draft.sentences) > 2
           for pattern in opener_patterns):
        issues.append(LintIssue(code="FORMULAIC_REPETITION",
                                message="script overuses the same discourse opener"))
    report_phrases = ("根据数据显示", "值得注意的是", "从本质上来看")
    for sentence in draft.sentences:
        if any(phrase in sentence.text for phrase in report_phrases):
            issues.append(LintIssue(code="REPORT_STYLE_LANGUAGE",
                                    message="report-style language is not suitable for spoken video",
                                    sentence_id=sentence.sentence_id))
    analogies = [sentence for sentence in draft.sentences if sentence.sentence_type == "analogy"]
    for sentence in analogies[1:]:
        issues.append(LintIssue(code="ANALOGY_OVERUSE",
                                message="Fenglei style permits at most one main analogy",
                                sentence_id=sentence.sentence_id))
    template_phrases = ("我的判断是", "你不妨想想")
    template_sentences = [sentence for sentence in draft.sentences
                          if any(phrase in sentence.text for phrase in template_phrases)]
    for sentence in template_sentences[1:]:
        issues.append(LintIssue(code="STYLE_TEMPLATE_OVERUSE",
                                message="script stacks formulaic template phrases",
                                sentence_id=sentence.sentence_id))
    combined = "".join(s.text for s in draft.sentences)
    creative_text = "".join(s.text for s in draft.sentences if not s.claim_ids)
    originality = check_originality(creative_text, source_text)
    if originality.status != "passed":
        issues.append(LintIssue(code="SOURCE_REUSE", message="script overlaps source article"))
    spoken = _spoken_count(combined)
    estimated = spoken / speaking_rate if speaking_rate > 0 else 0
    if not hard_min_duration_seconds <= estimated <= hard_max_duration_seconds:
        issues.append(LintIssue(code="DURATION_OUT_OF_RANGE", message="estimated duration must be 60–90 seconds"))
        issues.append(LintIssue(
            code="DURATION_TOO_SHORT" if estimated < hard_min_duration_seconds else "DURATION_TOO_LONG",
            message="estimated duration is outside target range",
        ))
    target_duration = target_duration_seconds or draft.target_duration_seconds
    if abs(estimated - target_duration) > 5:
        issues.append(LintIssue(code="DURATION_TARGET_MISSED",
                                message=f"estimated duration differs from the {target_duration}s editorial target",
                                severity="warning"))
    jargon = sum(combined.count(term) for term in ("边际", "流动性", "传导机制", "逆周期", "名义锚"))
    if jargon >= 3:
        issues.append(LintIssue(code="JARGON_DENSITY", message="too many unexplained terms"))
    return ScriptLintResult(passed=not any(i.severity == "error" for i in issues),
        speaking_rate_chars_per_second=speaking_rate, spoken_character_count=spoken,
        estimated_duration_seconds=round(estimated, 2), issues=issues)
