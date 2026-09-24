"""Local scoring and selection for content angles."""
import re
from fanglei.content_models import AngleCandidate, AngleDiversityResult, AngleProposal, ScriptReadyClaim
from fanglei.authority_safety import authority_text_issues
from fanglei.originality import check_originality


def score_angles(proposals: list[AngleProposal], palette: tuple[ScriptReadyClaim, ...], source_text: str) -> list[AngleCandidate]:
    allowed = {claim.claim_id: claim for claim in palette}
    seen: set[str] = set()
    results = []
    for proposal in proposals:
        rejected: list[str] = []
        if any(cid not in allowed for cid in proposal.supporting_claim_ids):
            rejected.append("UNKNOWN_CLAIM")
        combined = " ".join((proposal.title, proposal.hook, proposal.core_insight))
        false_conflict = bool(re.search(r"打起来|互相矛盾|互相冲突|谁在撒谎|数据造假", combined))
        controversy = 4 if false_conflict else (1 if re.search(r"差异|不一样|矛盾吗", combined) else 0)
        if false_conflict: rejected.append("FALSE_CONFLICT")
        originality = check_originality(combined, source_text)
        if originality.status != "passed": rejected.append("SOURCE_REUSE")
        semantic = re.sub(r"\W+", "", proposal.core_question + proposal.core_insight).lower()
        if semantic in seen: rejected.append("DUPLICATE_ANGLE")
        seen.add(semantic)
        usable = [allowed[cid] for cid in proposal.supporting_claim_ids if cid in allowed]
        authority_claims = [claim for claim in usable
                            if claim.verification_basis == "authoritative_primary_attestation"]
        if authority_claims:
            angle_text = " ".join((proposal.title, proposal.hook, proposal.core_question,
                                   proposal.core_insight))
            for claim in authority_claims:
                rejected.extend(code for code in authority_text_issues(
                    angle_text, claim.model_dump(mode="python")
                ) if code not in rejected)
        institutions = {sid for claim in usable for sid in claim.source_ids}
        evidence = 0 if not usable else (4 if len(usable) >= 2 and len(institutions) >= 3 else 3 if len(institutions) >= 3 else 2)
        if evidence < 2: rejected.append("INSUFFICIENT_EVIDENCE")
        base = evidence*5 + proposal.audience_relevance*4 + proposal.novelty*3 + proposal.hook_strength*3 + proposal.visual_potential + proposal.explainability*4
        score = max(0, min(100, base - controversy*6))
        if proposal.explainability < 3: rejected.append("NOT_EXPLAINABLE")
        results.append(AngleCandidate(**proposal.model_dump(), evidence_strength=evidence,
            controversy_risk=controversy, total_score=score,
            eligibility="rejected" if rejected else "eligible", rejection_codes=rejected,
            originality={"status": originality.status, "max_contiguous_overlap": originality.max_contiguous_overlap,
                         "five_gram_jaccard": originality.five_gram_jaccard}))
    return results


def _semantic_key(value: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]", "", value).lower()


def validate_angle_diversity(proposals: list[AngleProposal]) -> AngleDiversityResult:
    questions = {_semantic_key(item.core_question) for item in proposals}
    mechanisms = {_semantic_key(item.hook_mechanism) for item in proposals}
    takeaways = {_semantic_key(item.audience_takeaway) for item in proposals}
    framings = {_semantic_key(item.narrative_framing) for item in proposals}
    issues = []
    if not 3 <= len(proposals) <= 5:
        issues.append("ANGLE_COUNT_OUT_OF_RANGE")
    if len(questions) < 3:
        issues.append("CORE_QUESTION_NOT_DIVERSE")
    if len(mechanisms) < 3:
        issues.append("HOOK_MECHANISM_NOT_DIVERSE")
    if len(takeaways) < 3:
        issues.append("AUDIENCE_TAKEAWAY_NOT_DIVERSE")
    if len(framings) < 3:
        issues.append("NARRATIVE_FRAMING_NOT_DIVERSE")
    required = {"misconception_correction", "economic_data_literacy", "media_literacy"}
    if not required.issubset({item.narrative_framing for item in proposals}):
        issues.append("REQUIRED_GDP_FRAMINGS_MISSING")
    return AngleDiversityResult(
        passed=not issues,
        candidate_count=len(proposals),
        distinct_core_questions=len(questions),
        distinct_hook_mechanisms=len(mechanisms),
        distinct_audience_takeaways=len(takeaways),
        distinct_framings=len(framings),
        issue_codes=issues,
    )


def select_angle(candidates: list[AngleCandidate], requested_id: str | None = None) -> AngleCandidate:
    eligible = [item for item in candidates if item.eligibility == "eligible"]
    if requested_id:
        match = next((item for item in eligible if item.angle_id == requested_id), None)
        if not match: raise ValueError(f"Angle is not eligible: {requested_id}")
        return match
    if not eligible: raise ValueError("No eligible content angle")
    return sorted(eligible, key=lambda c: (-c.total_score, -c.evidence_strength, -c.audience_relevance,
                                           -c.explainability, -c.novelty, c.angle_id))[0]
