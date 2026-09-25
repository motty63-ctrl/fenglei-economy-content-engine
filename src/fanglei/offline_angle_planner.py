"""Deterministic, offline angle proposals from current Research and allowed claims."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from fanglei.content_models import AngleProposal, AngleProposalResult, ScriptReadyClaim

if TYPE_CHECKING:
    from fanglei.providers.content import AngleGenerationInput


_CLAIM_ID = re.compile(r"\bclaim_[A-Za-z0-9_-]+\b")
_WORD = re.compile(r"[a-z][a-z0-9-]{2,}", re.I)


def _focus_questions(request: AngleGenerationInput) -> tuple[str, list[str]]:
    focus = request.research_focus
    if focus:
        primary = str(focus.get("primary_question", "")).strip()
        subquestions = [str(item).strip() for item in focus.get("subquestions", []) if str(item).strip()]
        if primary and subquestions:
            return primary, subquestions
    primary = request.core_topic.strip() or "What do the current verified records show?"
    return primary, [item.strip() for item in request.research_questions if item.strip()]


def _research_bounded_claims(request: AngleGenerationInput) -> list[ScriptReadyClaim]:
    cited_ids = set(_CLAIM_ID.findall(request.research_md))
    palette = sorted(request.fact_palette, key=lambda item: item.claim_id)
    if not cited_ids:
        return palette
    selected = [claim for claim in palette if claim.claim_id in cited_ids]
    if not selected:
        raise ValueError("RESEARCH_HAS_NO_ALLOWED_CLAIMS")
    return selected


def _kind(claim: ScriptReadyClaim) -> str:
    attestation = claim.authority_attestation or {}
    return str(attestation.get("kind", ""))


def _subject(claim: ScriptReadyClaim) -> str:
    scope = (claim.authority_attestation or {}).get("scope") or {}
    if isinstance(scope, dict) and isinstance(scope.get("subject"), str) and scope["subject"].strip():
        return scope["subject"].strip()
    return "the reported measure"


def _period(claim: ScriptReadyClaim) -> str:
    scope = (claim.authority_attestation or {}).get("scope") or {}
    if isinstance(scope, dict) and isinstance(scope.get("period"), str):
        return scope["period"].strip()
    return "the reported period"


def _matching_question(claim: ScriptReadyClaim, questions: list[str]) -> str | None:
    if not questions:
        return None
    terms = {word.casefold() for word in _WORD.findall(_subject(claim))}
    if not terms:
        return questions[0]
    ranked = sorted(
        enumerate(questions),
        key=lambda pair: (-len(terms & {word.casefold() for word in _WORD.findall(pair[1])}), pair[0]),
    )
    matches = len(terms & {word.casefold() for word in _WORD.findall(ranked[0][1])})
    return ranked[0][1] if matches else None


def _unique(claims: list[ScriptReadyClaim]) -> list[ScriptReadyClaim]:
    seen: set[str] = set()
    result = []
    for claim in claims:
        if claim.claim_id not in seen:
            seen.add(claim.claim_id)
            result.append(claim)
    return result


def _proposal(
    *,
    index: int,
    framing: str,
    mechanism: str,
    title: str,
    hook: str,
    question: str,
    takeaway: str,
    claims: list[ScriptReadyClaim],
    focus_present: bool,
) -> AngleProposal:
    selected = _unique(claims)
    if not selected:
        raise ValueError("NO_ALLOWED_CLAIMS_FOR_ANGLE_PLANNING")
    # This block only repeats verified propositions; it adds no interpretation.
    insight = "\n\n".join(claim.claim_text for claim in selected)
    has_document_pair = any(len(set(claim.source_ids)) >= 2 for claim in selected)
    audience_relevance = 4 if focus_present else 3
    novelty = 3
    hook_strength = 3 if "?" in hook or "？" in hook else 2
    visual_potential = 3 if len(selected) >= 2 or has_document_pair else 2
    explainability = 4 if len(selected) <= 3 else 3
    return AngleProposal(
        angle_id=f"angle_{index:03d}",
        title=title,
        hook=hook,
        core_question=question,
        core_insight=insight,
        hook_mechanism=mechanism,
        audience_takeaway=takeaway,
        narrative_framing=framing,
        supporting_claim_ids=[claim.claim_id for claim in selected],
        audience_relevance=audience_relevance,
        novelty=novelty,
        hook_strength=hook_strength,
        visual_potential=visual_potential,
        explainability=explainability,
        risk_notes=["Scores are deterministic planning heuristics; eligibility is calculated locally."],
    )


def plan_offline_angles(request: AngleGenerationInput) -> AngleProposalResult:
    """Create replayable framing proposals without network/provider access."""
    claims = _research_bounded_claims(request)
    if not claims:
        raise ValueError("NO_ALLOWED_CLAIMS_FOR_ANGLE_PLANNING")
    primary, questions = _focus_questions(request)
    comparisons = [claim for claim in claims if _kind(claim) == "deterministic_document_comparison"]
    reports = [claim for claim in claims if _kind(claim) == "document_report"]
    comparison_pool = comparisons or claims
    proposals: list[AngleProposal] = []

    proposals.append(_proposal(
        index=1,
        framing="overview_map",
        mechanism="multi_claim_map",
        title="把已核验记录并排看",
        hook="这些记录能回答哪些问题，又有哪些边界？",
        question=primary,
        takeaway="按来源和范围阅读一组已核验记录。",
        claims=comparison_pool[:5],
        focus_present=bool(request.research_focus),
    ))

    first = comparison_pool[0]
    first_question = _matching_question(first, questions) or f"What do the documents report about {_subject(first)}?"
    proposals.append(_proposal(
        index=2,
        framing="focused_record_comparison",
        mechanism="single_measure_zoom",
        title=f"{_subject(first)}：先看一项记录",
        hook="这一项记录的范围和变化，具体是什么？",
        question=first_question,
        takeaway="沿一项获准引用的记录核对指标、期间和统计口径。",
        claims=[first],
        focus_present=bool(request.research_focus),
    ))

    if comparisons and reports:
        contrast_claims = [comparisons[0], reports[0]]
    else:
        contrast_claims = [claims[min(1, len(claims) - 1)]]
    contrast_question = (
        questions[-1] if request.research_focus and len(questions) > 1
        else "What can different evidence types directly establish?"
    )
    proposals.append(_proposal(
        index=3,
        framing="evidence_class_contrast",
        mechanism="evidence_role_pairing",
        title="不同证据各自能说明什么",
        hook="不同类型的正式记录，分别能支持哪类表述？",
        question=contrast_question,
        takeaway="区分比较记录与单份文件的直接记载。",
        claims=contrast_claims,
        focus_present=bool(request.research_focus),
    ))

    if len(reports) >= 2:
        report_claims = reports[:2]
    else:
        report_claims = [comparison_pool[min(1, len(comparison_pool) - 1)]]
    report_question = _matching_question(report_claims[0], questions) or "What do the cited records state directly?"
    proposals.append(_proposal(
        index=4,
        framing="document_attestation",
        mechanism="direct_record_reading",
        title="原文记载与解释之间的边界",
        hook="哪些内容是文件直接写明的？",
        question=report_question,
        takeaway="在转述文件时保留归因和原文范围。",
        claims=report_claims,
        focus_present=bool(request.research_focus),
    ))

    boundary_claims = [comparison_pool[-1]]
    if reports:
        boundary_claims.append(reports[-1])
    boundary_question = (
        "How can the records be presented together without adding an unsupported explanation?"
    )
    proposals.append(_proposal(
        index=5,
        framing="scope_boundary",
        mechanism="attestation_boundary_check",
        title="从记录到结论，证据边界在哪里",
        hook="直接记载到哪一步，解释又从哪里开始？",
        question=boundary_question,
        takeaway="把文件记载与未获支持的推断分开。",
        claims=boundary_claims,
        focus_present=bool(request.research_focus),
    ))
    return AngleProposalResult(candidates=proposals)
