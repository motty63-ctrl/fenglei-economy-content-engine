"""Deterministic, offline angle proposals from current Research and allowed claims."""
from __future__ import annotations

import calendar
import re
from typing import TYPE_CHECKING, Any

from fanglei.content_models import AngleProposal, AngleProposalResult, ScriptReadyClaim
from fanglei.evidence_policy import is_claim_eligible_for_content

if TYPE_CHECKING:
    from fanglei.providers.content import AngleGenerationInput


_CLAIM_ID = re.compile(r"\bclaim_[A-Za-z0-9_-]+\b")
_LATIN_TOKEN = re.compile(r"month_\d{2}|[a-z][a-z0-9-]{2,}", re.I)
_CJK_RUN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
_CHINESE_MONTH = re.compile(r"(?<!\d)(1[0-2]|0?[1-9])\s*月")
_ENGLISH_MONTHS = {
    calendar.month_name[index].casefold(): f"month_{index:02d}"
    for index in range(1, 13)
}
_ENGLISH_MONTH_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(name) for name in _ENGLISH_MONTHS) + r")\b",
    re.I,
)
_STOP_WORDS = {
    "about", "across", "after", "among", "and", "are", "as", "at", "be", "been",
    "between", "by", "can", "could", "current", "did", "direct", "directly", "do",
    "does", "for", "from", "how", "in", "into", "is", "it", "its", "of", "on",
    "or", "over", "report", "reported", "reports", "the", "their", "these", "this",
    "those", "to", "use", "used", "using", "was", "were", "what", "which", "with",
    "would", "已核验", "直接", "报告", "当前", "记录", "哪些", "什么", "如何", "对于",
}

# Small language bridges for common measurement words. They normalize focus
# wording only; claim scope and authority remain sourced from structured data.
_TERM_EQUIVALENTS: dict[str, tuple[str, ...]] = {
    "平均": ("average", "mean"),
    "时薪": ("hourly", "wage"),
    "工时": ("hours", "worked", "time"),
    "就业": ("employment", "jobs", "job"),
    "行业": ("industry", "sector"),
    "修订": ("revision", "revised"),
    "变化": ("change", "changed"),
    "变动": ("change", "changed"),
    "工资": ("wage", "pay"),
}

# Deterministic, case-independent bridges for common Chinese economic measures.
# Unknown Chinese terms deliberately remain unmatched: this planner must not
# claim semantic coverage it cannot establish from its local vocabulary.
_CJK_CONCEPT_EQUIVALENTS: dict[str, tuple[str, ...]] = {
    "非农": ("nonfarm",),
    "失业率": ("unemployment", "rate"),
    "平均时薪": ("average", "hourly", "earnings"),
    "时薪": ("hourly", "earnings"),
    "平均每周工时": ("average", "workweek"),
    "每周工时": ("workweek",),
    "工时": ("workweek", "hours"),
    "零售销售": ("retail", "sales"),
    "价格指数": ("price", "index"),
    "运输量": ("freight", "volume"),
    "就业": ("employment", "jobs"),
    "行业": ("industry", "sector"),
    "修订": ("revision", "revised"),
    "修正": ("revision", "revised"),
    "变化": ("change", "changed"),
    "变动": ("change", "changed"),
}
_GENERIC_ALIGNMENT_TERMS = {
    "change", "changed", "increase", "increased", "decrease", "decreased",
    "rise", "rose", "fall", "fell", "report", "reported", "record",
    "records", "data", "value", "values", "employment", "job", "jobs",
    "month", "estimate", "estimates", "current",
}
_AGGREGATE_SUBJECT_TERMS = {"total", "overall", "aggregate", "all", "combined"}
_REVISION_TERMS = {"revision", "revised"}
_CATEGORY_QUESTION = re.compile(r"\bwhich\b|\bwhat\s+(?:types|categories)\b|哪些|哪类|哪种", re.I)

_BOUNDARY_QUESTION = re.compile(
    r"boundary|distinguish|differentiate|how\s+to\s+(?:preserve|separate)|"
    r"统计边界|如何保留|如何区分|加以区分|分别区分",
    re.I,
)


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
    palette = sorted(
        (claim for claim in request.fact_palette if is_claim_eligible_for_content(claim)),
        key=lambda item: item.claim_id,
    )
    if not cited_ids:
        return palette
    selected = [claim for claim in palette if claim.claim_id in cited_ids]
    if not selected:
        raise ValueError("RESEARCH_HAS_NO_ALLOWED_CLAIMS")
    return selected


def _scope(claim: ScriptReadyClaim) -> dict[str, Any]:
    scope = (claim.authority_attestation or {}).get("scope") or {}
    return scope if isinstance(scope, dict) else {}


def _text_terms(value: str) -> set[str]:
    value = _CHINESE_MONTH.sub(lambda match: f" month_{int(match.group(1)):02d} ", value)
    value = _ENGLISH_MONTH_PATTERN.sub(
        lambda match: f" {_ENGLISH_MONTHS[match.group(1).casefold()]} ", value
    )
    terms = {token.casefold() for token in _LATIN_TOKEN.findall(value)}
    for run in _CJK_RUN.findall(value):
        for concept, equivalents in _CJK_CONCEPT_EQUIVALENTS.items():
            if concept in run:
                terms.update(equivalents)
    normalized: set[str] = set()
    for token in terms:
        if token in _STOP_WORDS:
            continue
        if re.fullmatch(r"[a-z][a-z0-9-]*", token):
            if token.endswith("ies") and len(token) > 4:
                token = token[:-3] + "y"
            elif token.endswith("s") and not token.endswith("ss") and len(token) > 4:
                token = token[:-1]
        normalized.add(token)
        normalized.update(_TERM_EQUIVALENTS.get(token, ()))
    return normalized


def _question_terms(question: str) -> set[str]:
    return _text_terms(question)


def _claim_terms(claim: ScriptReadyClaim) -> set[str]:
    scope = _scope(claim)
    # Subject/measure are the dimension anchors. Period, units and certainty
    # constrain a claim but are too common to establish topical membership.
    parts = [str(scope[key]) for key in ("subject", "measure")
             if isinstance(scope.get(key), str) and scope[key].strip()]
    for evidence in claim.evidence:
        if not isinstance(evidence, dict):
            continue
        parts.extend(str(evidence[key]) for key in (
            "evidence_target_concept", "evidence_target_id", "evidence_kind"
        ) if isinstance(evidence.get(key), str) and evidence[key].strip())
    if not parts:
        parts.append(claim.claim_text)
    return _text_terms(" ".join(parts))


def _claim_measure_terms(claim: ScriptReadyClaim) -> set[str]:
    measure = _scope(claim).get("measure")
    return _text_terms(str(measure)) if isinstance(measure, str) else set()


def _claim_subject_terms(claim: ScriptReadyClaim) -> set[str]:
    subject = _scope(claim).get("subject")
    return _text_terms(str(subject)) if isinstance(subject, str) else set()


def _claim_is_revision(claim: ScriptReadyClaim) -> bool:
    return any(
        str(evidence.get("evidence_kind", "")).casefold() in {"revision", "estimate_revision"}
        or bool(_REVISION_TERMS & _text_terms(" ".join(
            str(evidence.get(key, "")) for key in ("evidence_target_concept", "evidence_target_id")
        )))
        for evidence in claim.evidence if isinstance(evidence, dict)
    )


def _question_claim_match(question: str, claim: ScriptReadyClaim) -> tuple[bool, str]:
    terms = _question_terms(question)
    if _BOUNDARY_QUESTION.search(question):
        return False, "method_boundary"

    revision_query = bool(terms & _REVISION_TERMS)
    if _claim_is_revision(claim) and not revision_query:
        return False, "revision_claim_requires_revision_focus"
    if revision_query:
        if not _claim_is_revision(claim):
            return False, "revision_type_mismatch"
        question_months = {term for term in terms if term.startswith("month_")}
        claim_months = _text_terms(" ".join([
            str(_scope(claim).get("subject", "")),
            str(_scope(claim).get("period", "")),
            *[str(item.get("evidence_target_id", "")) for item in claim.evidence if isinstance(item, dict)],
        ]))
        claim_months = {term for term in claim_months if term.startswith("month_")}
        if question_months and not question_months.intersection(claim_months):
            return False, "revision_period_mismatch"
        return True, "revision_period_and_evidence_kind"

    if _CATEGORY_QUESTION.search(question):
        measure_terms = terms - {
            "change", "changed", "increase", "increased", "decrease", "decreased",
            "rise", "rose", "fall", "fell", "industry", "sector", "month",
        }
        if not (measure_terms & _claim_measure_terms(claim)):
            return False, "category_measure_mismatch"
        if _claim_subject_terms(claim) & _AGGREGATE_SUBJECT_TERMS:
            return False, "aggregate_not_category_member"
        return True, "disaggregated_measure_match"

    claim_terms = _claim_terms(claim)
    question_months = {term for term in terms if term.startswith("month_")}
    informative_question_terms = terms - _GENERIC_ALIGNMENT_TERMS - question_months
    informative_claim_terms = claim_terms - _GENERIC_ALIGNMENT_TERMS - {
        term for term in claim_terms if term.startswith("month_")
    }
    if informative_question_terms.intersection(informative_claim_terms):
        return True, "distinctive_scope_or_evidence_terms"

    # A question consisting primarily of one explicit measure can still map
    # directly by measure, while broad questions require a more specific anchor.
    if len(informative_question_terms) <= 1 and terms.intersection(_claim_measure_terms(claim)):
        return True, "single_measure_match"
    return False, "no_distinctive_scope_match"


def _focused_editorial_fields(
    dimension: dict[str, Any], claims: list[ScriptReadyClaim],
) -> tuple[str, str, str, str, str, str]:
    """Choose a generic editorial lens from evidence structure and question form."""
    if claims and all(_claim_is_revision(claim) for claim in claims):
        return (
            "revision_history", "trace_revision_values",
            "原始估计与后续修订，分开核对",
            "前次估计与修订值如何对应？",
            "历史估计的修订前后数值如何对应？",
            "区分此前发布值、修订值和修订幅度。",
        )

    sections = {
        str(item.get("source_section", "")).strip()
        for claim in claims for item in claim.evidence
        if isinstance(item, dict) and str(item.get("source_section", "")).strip()
    }
    if len(sections) > 1:
        return (
            "cross_section_records", "compare_source_sections",
            "同一报告的不同栏目，各自记录什么？",
            "不同栏目各记录了什么？",
            "同一报告的不同栏目各自记录了什么？",
            "保留不同栏目各自的统计范围。",
        )

    measure_signatures = set()
    for claim in claims:
        terms = _claim_measure_terms(claim)
        if terms & {"employment", "jobs", "job"}:
            signature = ("employment",)
        else:
            signature = tuple(sorted(terms))
        if signature:
            measure_signatures.add(signature)
    if len(measure_signatures) > 1:
        return (
            "paired_measures", "compare_related_measures",
            "两项指标，分别有哪些已核验读数？",
            "两项指标各自记录了什么？",
            "现有记录分别支持关于这些指标的哪些描述？",
            "逐项呈现指标及其各自的统计范围。",
        )

    if len(claims) > 1 and _CATEGORY_QUESTION.search(str(dimension.get("label", ""))):
        return (
            "category_examples", "review_disaggregated_records",
            "分类记录里有哪些具体变化？",
            "报告提到的行业变化有哪些？",
            "哪些分类记录有直接证据支持？",
            "只呈现有证据支持的具体分类，并保留覆盖边界。",
        )

    labels = list(dict.fromkeys(_scope_label(claim) for claim in claims))
    label_text = " / ".join(labels)
    return (
        "focused_record", "scoped_record_reading",
        f"已核验记录：{label_text}",
        "这条记录能直接支持哪些内容？",
        f"这条记录具体给出了关于 {label_text} 的什么信息？",
        "把讨论限制在当前记录明确覆盖的范围内。",
    )


def _research_dimensions(
    primary: str, questions: list[str], claims: list[ScriptReadyClaim],
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    labels = questions or [primary]
    dimensions: list[dict[str, Any]] = []
    claim_dimension_map: dict[str, list[str]] = {claim.claim_id: [] for claim in claims}
    for index, label in enumerate(labels, start=1):
        dimension_id = f"focus_{index:03d}"
        matching_claims: list[str] = []
        methodological = bool(_BOUNDARY_QUESTION.search(label))
        mapping_modes: set[str] = set()
        for claim in claims:
            matched, mapping_mode = _question_claim_match(label, claim)
            if not matched and not methodological and len(labels) == 1 and primary:
                matched, mapping_mode = _question_claim_match(primary, claim)
                if matched:
                    mapping_mode = "single_dimension_primary_context"
            matched = not methodological and matched
            if matched:
                matching_claims.append(claim.claim_id)
                claim_dimension_map[claim.claim_id].append(dimension_id)
                mapping_modes.add(mapping_mode)
        dimensions.append({
            "dimension_id": dimension_id,
            "label": label,
            "supporting_claim_ids": matching_claims,
            "status": "supported" if matching_claims else "unsupported_by_eligible_claims",
            # Presence means at least one claim maps to the question. It does
            # not assert exhaustive coverage of the underlying topic.
            "coverage_semantics": "partial_evidence_presence",
            "mapping_modes": sorted(mapping_modes),
        })
    return dimensions, claim_dimension_map


def _unique(claims: list[ScriptReadyClaim]) -> list[ScriptReadyClaim]:
    seen: set[str] = set()
    result = []
    for claim in claims:
        if claim.claim_id not in seen:
            seen.add(claim.claim_id)
            result.append(claim)
    return result


def _scope_label(claim: ScriptReadyClaim) -> str:
    scope = _scope(claim)
    subject = scope.get("subject")
    subject_terms = _text_terms(subject) if isinstance(subject, str) else set()
    period_only_subject = len(subject_terms) == 1 and next(iter(subject_terms)).startswith("month_")
    if isinstance(subject, str) and subject.strip() and not period_only_subject:
        return subject.strip()
    if period_only_subject:
        for evidence in claim.evidence:
            if isinstance(evidence, dict) and isinstance(evidence.get("evidence_target_concept"), str):
                target = evidence["evidence_target_concept"].strip()
                if target:
                    return target
    measure = scope.get("measure")
    if isinstance(measure, str) and measure.strip():
        return measure.strip()
    for evidence in claim.evidence:
        if isinstance(evidence, dict) and isinstance(evidence.get("evidence_target_concept"), str):
            target = evidence["evidence_target_concept"].strip()
            if target:
                return target
    # A claim sentence may contain values and dates. Without structured scope,
    # use a non-factual label rather than copying those propositions into an
    # angle title or hook where they would lack claim binding.
    return "已核验记录"


def _proposal(
    *, index: int, framing: str, mechanism: str, title: str, hook: str,
    question: str, takeaway: str, claims: list[ScriptReadyClaim], focus_present: bool,
) -> AngleProposal:
    selected = _unique(claims)
    if not selected:
        raise ValueError("NO_ALLOWED_CLAIMS_FOR_ANGLE_PLANNING")
    # This repeats only verified propositions and adds no interpretation.
    insight = "\n\n".join(claim.claim_text for claim in selected)
    has_document_pair = any(len(set(claim.source_ids)) >= 2 for claim in selected)
    audience_relevance = 4 if focus_present else 3
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
        novelty=3,
        hook_strength=3 if "?" in hook or "？" in hook else 2,
        visual_potential=3 if len(selected) >= 2 or has_document_pair else 2,
        explainability=4 if len(selected) <= 3 else 3,
        risk_notes=["Scores are deterministic planning heuristics; eligibility is calculated locally."],
    )


def _coverage_entry(
    proposal: AngleProposal,
    dimensions: list[dict[str, Any]],
    claim_dimension_map: dict[str, list[str]],
    *, framing: str,
) -> dict[str, Any]:
    all_ids = {item["dimension_id"] for item in dimensions}
    covered = {
        dimension_id
        for claim_id in proposal.supporting_claim_ids
        for dimension_id in claim_dimension_map.get(claim_id, [])
    }
    omitted = all_ids - covered
    ratio = len(covered) / len(all_ids) if all_ids else 0.0
    density = len(covered) / len(proposal.supporting_claim_ids) if proposal.supporting_claim_ids else 0.0
    return {
        "framing": framing,
        "covered_dimension_ids": sorted(covered),
        "intentionally_omitted_dimension_ids": sorted(omitted),
        # Without explicit exhaustive coverage metadata, presence is always partial.
        "partially_covered_dimension_ids": sorted(covered),
        "coverage_ratio": round(ratio, 6),
        "support_density": round(density, 6),
    }


def _propose(
    request: AngleGenerationInput,
    claims: list[ScriptReadyClaim],
    primary: str,
    dimensions: list[dict[str, Any]],
    claim_dimension_map: dict[str, list[str]],
) -> tuple[list[AngleProposal], dict[str, dict[str, Any]]]:
    proposals: list[AngleProposal] = []
    metadata: dict[str, dict[str, Any]] = {}

    def add(framing: str, mechanism: str, title: str, hook: str, question: str,
            takeaway: str, supporting: list[ScriptReadyClaim]) -> None:
        proposal = _proposal(
            index=len(proposals) + 1,
            framing=framing,
            mechanism=mechanism,
            title=title,
            hook=hook,
            question=question,
            takeaway=takeaway,
            claims=supporting,
            focus_present=bool(request.research_focus),
        )
        quality = _coverage_entry(
            proposal, dimensions, claim_dimension_map, framing=framing
        )
        proposals.append(proposal)
        metadata[proposal.angle_id] = quality

    add(
        framing="broad_synthesis",
        mechanism="coverage_map",
        title="从已核验记录看核心问题的几个部分",
        hook="当前证据能直接回答核心问题的哪些部分？",
        question="围绕当前研究问题，现有已核验记录分别支持哪些范围？",
        takeaway="先说明证据覆盖面，再并列呈现各项记录。",
        supporting=claims,
    )

    question_groups = [
        (item, [claim for claim in claims if item["dimension_id"] in claim_dimension_map.get(claim.claim_id, [])])
        for item in dimensions
    ]
    question_groups = [(dimension, group) for dimension, group in question_groups if group]
    question_groups.sort(key=lambda pair: (-len(pair[1]), pair[0]["dimension_id"]))
    for dimension, group in question_groups[:4]:
        framing, mechanism, title, hook, question, takeaway = _focused_editorial_fields(
            dimension, group
        )
        add(
            framing=framing,
            mechanism=mechanism,
            title=title,
            hook=hook,
            question=question,
            takeaway=takeaway,
            supporting=group,
        )

    # When the Focus has too few usable subquestions, offer further narrow
    # views from distinct claims rather than padded variants of one support set.
    existing_sets = {tuple(sorted(item.supporting_claim_ids)) for item in proposals}
    if len(proposals) < 3:
        ranked_claims = sorted(
            claims,
            key=lambda claim: (
                -sum(len(item.get("explicit_values", [])) for item in claim.evidence
                     if isinstance(item, dict) and isinstance(item.get("explicit_values", []), list)),
                -len(claim.claim_text),
                claim.claim_id,
            ),
        )
        for claim in ranked_claims:
            signature = (claim.claim_id,)
            if signature in existing_sets:
                continue
            label = _scope_label(claim)
            add(
                framing="single_claim_detail",
                mechanism="single_record_zoom",
                title=f"一条记录中的 {label}",
                hook="这条记录具体写了什么内容？",
                question=f"这条记录能支持关于 {label} 的哪些描述？",
                takeaway="保留单条事实自身的范围、期间和统计口径。",
                supporting=[claim],
            )
            existing_sets.add(signature)
            if len(proposals) >= 5:
                break
    if len(proposals) < 3:
        # Preserve the existing minimum candidate contract for a sparse but
        # useful one-claim Research run. These are distinct editorial lenses;
        # none is selected automatically, and identical framing is still
        # caught by the structural diversity check.
        anchor = claims[0]
        label = _scope_label(anchor)
        add(
            framing="source_record_boundary",
            mechanism="direct_record_scope",
            title="已核验记录的证据边界",
            hook="这条记录的证据边界在哪里？",
            question=f"当前记录能支持关于 {label} 的哪些描述？",
            takeaway="保留单条记录的来源、统计范围和遗漏边界。",
            supporting=claims,
        )
    if len(proposals) < 3:
        anchor = claims[0]
        label = _scope_label(anchor)
        add(
            framing="single_record_detail",
            mechanism="single_record_zoom",
            title=f"聚焦一条记录：{label}",
            hook=f"先核对这条记录本身写了什么。",
            question=f"这条已核验记录能直接回答关于 {label} 的什么问题？",
            takeaway="围绕一条事实讲清其已记录的范围。",
            supporting=[anchor],
        )
    return proposals[:5], metadata


def plan_offline_angles(request: AngleGenerationInput) -> AngleProposalResult:
    """Create replayable proposals and auditable Research Focus coverage metadata."""
    claims = _research_bounded_claims(request)
    if not claims:
        raise ValueError("NO_ALLOWED_CLAIMS_FOR_ANGLE_PLANNING")
    primary, questions = _focus_questions(request)
    dimensions, claim_dimension_map = _research_dimensions(primary, questions, claims)
    proposals, candidate_quality = _propose(
        request, claims, primary, dimensions, claim_dimension_map
    )
    return AngleProposalResult(
        candidates=proposals,
        quality_metadata={
            "schema_version": "angle-planning-quality/1.0",
            "dimension_basis": "Research Focus subquestions matched against structured claim scope and evidence targets",
            "coverage_ratio_semantics": "supported focus dimensions divided by all focus dimensions; this is presence, not exhaustive coverage",
            "dimensions": dimensions,
            "claim_dimension_map": claim_dimension_map,
            "candidates": candidate_quality,
        },
    )
