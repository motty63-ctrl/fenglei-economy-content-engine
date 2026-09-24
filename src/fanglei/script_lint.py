"""Deterministic factual, duration, structure, and oral-quality gates."""
from __future__ import annotations
from decimal import Decimal
import re
from fanglei.authority_safety import authority_text_issues
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
                *, speaking_rate: float = 4.0) -> ScriptLintResult:
    issues: list[LintIssue] = []
    if not 2.5 <= speaking_rate <= 6.0:
        issues.append(LintIssue(code="INVALID_SPEAKING_RATE", message="speaking rate must be 2.5–6.0"))
    claims = {item["claim_id"]: item for item in facts.get("claims", [])}
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
                if claim.get("verification_basis") == "authoritative_primary_attestation":
                    for code in authority_text_issues(sentence.text, claim):
                        issues.append(LintIssue(
                            code=code,
                            message="authority-backed claim attribution and scope must remain intact",
                            sentence_id=sentence.sentence_id,
                        ))
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
          or not re.search(r"我的判断|所以|核心|结论|真正|总之", draft.sentences[-1].text)):
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
                                message="Fanglei style permits at most one main analogy",
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
    if not 60 <= estimated <= 90:
        issues.append(LintIssue(code="DURATION_OUT_OF_RANGE", message="estimated duration must be 60–90 seconds"))
        issues.append(LintIssue(code="DURATION_TOO_SHORT" if estimated < 60 else "DURATION_TOO_LONG",
                                message="estimated duration is outside target range"))
    jargon = sum(combined.count(term) for term in ("边际", "流动性", "传导机制", "逆周期", "名义锚"))
    if jargon >= 3:
        issues.append(LintIssue(code="JARGON_DENSITY", message="too many unexplained terms"))
    return ScriptLintResult(passed=not any(i.severity == "error" for i in issues),
        speaking_rate_chars_per_second=speaking_rate, spoken_character_count=spoken,
        estimated_duration_seconds=round(estimated, 2), issues=issues)
