"""Deterministic factual, duration, structure, and oral-quality gates."""
from __future__ import annotations
from decimal import Decimal
import re
from fanglei.content_models import AngleCandidate, LintIssue, ScriptDraft, ScriptLintResult
from fanglei.originality import check_fact_originality, check_originality


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
    "metric:interest_rate": r"\binterest rate\b|政策利率|利率",
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
    for name in re.findall(r"([\u4e00-\u9fff]{2,10})(?:称|表示|显示|认为|预计|宣布)", text):
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


def lint_script(draft: ScriptDraft, angle: AngleCandidate, facts: dict, source_text: str,
                *, speaking_rate: float = 4.0) -> ScriptLintResult:
    issues: list[LintIssue] = []
    if not 2.5 <= speaking_rate <= 6.0:
        issues.append(LintIssue(code="INVALID_SPEAKING_RATE", message="speaking rate must be 2.5–6.0"))
    claims = {item["claim_id"]: item for item in facts.get("claims", [])}
    for sentence in draft.sentences:
        count = _spoken_count(sentence.text)
        if count > 48 or len(re.findall(r"[，；;：:]", sentence.text)) > 3:
            issues.append(LintIssue(code="COMPLEX_LONG_SENTENCE", message="sentence is too complex for speech", sentence_id=sentence.sentence_id))
        has_fact_signal = bool(re.search(r"\d|(?:BEA|IMF|OECD|世界银行|央行|政府).*(?:显示|认为|预计|宣布|结论)", sentence.text, re.I))
        if sentence.sentence_type != "verified_fact" and has_fact_signal:
            issues.append(LintIssue(code="UNDECLARED_FACT", message="factual-looking sentence lacks claim", sentence_id=sentence.sentence_id))
        if sentence.sentence_type == "verified_fact":
            contexts: list[str] = []
            valid = True
            for claim_id in sentence.claim_ids:
                claim = claims.get(claim_id)
                if not claim or claim.get("verification_status") != "verified" or claim.get("allowed_downstream") is not True:
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
    if any(re.search(r"镜头|画面|字幕|配音|storyboard|TTS", s.text, re.I) for s in draft.sentences):
        issues.append(LintIssue(code="PRODUCTION_DIRECTION", message="production directions are out of scope"))
    combined = "".join(s.text for s in draft.sentences)
    creative_text = "".join(s.text for s in draft.sentences if s.sentence_type != "verified_fact")
    originality = check_originality(creative_text, source_text)
    if originality.status != "passed":
        issues.append(LintIssue(code="SOURCE_REUSE", message="script overlaps source article"))
    spoken = _spoken_count(combined)
    estimated = spoken / speaking_rate if speaking_rate > 0 else 0
    if not 60 <= estimated <= 90:
        issues.append(LintIssue(code="DURATION_OUT_OF_RANGE", message="estimated duration must be 60–90 seconds"))
    jargon = sum(combined.count(term) for term in ("边际", "流动性", "传导机制", "逆周期", "名义锚"))
    if jargon >= 3:
        issues.append(LintIssue(code="JARGON_DENSITY", message="too many unexplained terms"))
    return ScriptLintResult(passed=not any(i.severity == "error" for i in issues),
        speaking_rate_chars_per_second=speaking_rate, spoken_character_count=spoken,
        estimated_duration_seconds=round(estimated, 2), issues=issues)
