"""Deterministic factual, duration, structure, and oral-quality gates."""
from __future__ import annotations
import re
from fanglei.content_models import AngleCandidate, LintIssue, ScriptDraft, ScriptLintResult
from fanglei.originality import check_originality


def _spoken_count(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", text))


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
            context = ""
            valid = True
            for claim_id in sentence.claim_ids:
                claim = claims.get(claim_id)
                if not claim or claim.get("verification_status") != "verified" or claim.get("allowed_downstream") is not True:
                    valid = False
                    continue
                eligible = [e for e in claim.get("evidence", []) if e.get("evidence_eligible")]
                if not eligible: valid = False
                context += claim.get("claim_text", "") + " " + " ".join(str(e) for e in eligible)
            numbers = re.findall(r"\d+(?:\.\d+)?", sentence.text)
            if not valid or any(number not in context for number in numbers):
                issues.append(LintIssue(code="UNSUPPORTED_FACT", message="claim does not support sentence values", sentence_id=sentence.sentence_id))
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
    originality = check_originality(combined, source_text)
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
