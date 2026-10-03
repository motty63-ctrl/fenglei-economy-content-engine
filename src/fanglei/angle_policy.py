"""Local scoring and selection for content angles."""
import re
from fanglei.content_models import AngleCandidate, AngleDiversityResult, AngleProposal, ScriptReadyClaim
from fanglei.authority_safety import authority_text_issues
from fanglei.originality import check_originality


def _evidence_strength(
    claims: list[ScriptReadyClaim],
    source_independence_keys: dict[str, str],
) -> int:
    supported = [claim for claim in claims if claim.verification_basis in {
        "independent_corroboration", "authoritative_primary_attestation"
    }]
    if not supported:
        return 0
    # Only independent-corroboration claims contribute institutional diversity.
    # Multiple official documents under one authority remain one independence key.
    independence_keys = {
        source_independence_keys[source_id]
        for claim in supported if claim.verification_basis == "independent_corroboration"
        for source_id in claim.source_ids
        if source_id in source_independence_keys and source_independence_keys[source_id]
    }
    claim_count = len({claim.claim_id for claim in supported})
    key_count = len(independence_keys)
    if claim_count >= 3 and key_count >= 3:
        return 5
    if claim_count >= 3 and key_count >= 2:
        return 4
    if claim_count >= 2 or key_count >= 2:
        return 3
    return 2


def score_angles(
    proposals: list[AngleProposal],
    palette: tuple[ScriptReadyClaim, ...],
    source_text: str,
    *,
    source_independence_keys: dict[str, str] | None = None,
    quality_metadata: dict | None = None,
) -> list[AngleCandidate]:
    allowed = {claim.claim_id: claim for claim in palette}
    source_independence_keys = source_independence_keys or {}
    seen: set[str] = set()
    quality_candidates = (quality_metadata or {}).get("candidates", {})
    structural_counts: dict[tuple[tuple[str, ...], tuple[str, ...], str], int] = {}
    if quality_metadata:
        for item in proposals:
            metadata = quality_candidates.get(item.angle_id, {}) if isinstance(quality_candidates, dict) else {}
            signature = _structural_signature(item, metadata)
            structural_counts[signature] = structural_counts.get(signature, 0) + 1
    results = []
    for proposal in proposals:
        rejected: list[str] = []
        if any(cid not in allowed for cid in proposal.supporting_claim_ids):
            rejected.append("UNKNOWN_CLAIM")
        if len(proposal.supporting_claim_ids) != len(set(proposal.supporting_claim_ids)):
            rejected.append("DUPLICATE_CLAIM_REFERENCE")
        combined = " ".join((proposal.title, proposal.hook, proposal.core_insight))
        false_conflict = bool(re.search(r"打起来|互相矛盾|互相冲突|谁在撒谎|数据造假", combined))
        controversy = 4 if false_conflict else (1 if re.search(r"差异|不一样|矛盾吗", combined) else 0)
        if false_conflict: rejected.append("FALSE_CONFLICT")
        originality_text = combined
        for claim in (allowed[cid] for cid in proposal.supporting_claim_ids if cid in allowed):
            # Verified propositions and their locatable evidence are expected to
            # recur in an angle. Keep the originality gate on creative framing.
            for literal in [claim.claim_text, *[
                item.get("evidence_text") for item in claim.evidence
                if isinstance(item.get("evidence_text"), str)
            ]]:
                if literal:
                    originality_text = originality_text.replace(literal, " ")
        originality = check_originality(originality_text, source_text)
        if originality.status != "passed": rejected.append("SOURCE_REUSE")
        semantic = re.sub(r"\W+", "", proposal.core_question + proposal.core_insight).lower()
        if semantic in seen: rejected.append("DUPLICATE_ANGLE")
        seen.add(semantic)
        usable = list({cid: allowed[cid] for cid in proposal.supporting_claim_ids if cid in allowed}.values())
        if any(claim.verification_basis == "none" for claim in usable):
            rejected.append("NO_VERIFICATION_BASIS")
        authority_claims = [claim for claim in usable
                            if claim.verification_basis == "authoritative_primary_attestation"]
        if authority_claims:
            angle_text = " ".join((proposal.title, proposal.hook, proposal.core_question,
                                   proposal.core_insight))
            related_claims = [claim.model_dump(mode="python") for claim in authority_claims]
            for claim in authority_claims:
                rejected.extend(code for code in authority_text_issues(
                    angle_text, claim.model_dump(mode="python"), related_claims=related_claims
                ) if code not in rejected)
        evidence = _evidence_strength(usable, source_independence_keys)
        if evidence < 2: rejected.append("INSUFFICIENT_EVIDENCE")
        base = evidence*5 + proposal.audience_relevance*4 + proposal.novelty*3 + proposal.hook_strength*3 + proposal.visual_potential + proposal.explainability*4
        score = base - controversy*6
        if quality_metadata is not None:
            quality_record = quality_candidates.get(proposal.angle_id) if isinstance(quality_candidates, dict) else None
            if not isinstance(quality_record, dict):
                rejected.append("ANGLE_QUALITY_METADATA_MISSING")
            else:
                editorial_issues = _editorial_quality_issues(proposal, quality_metadata, quality_record)
                rejected.extend(code for code in editorial_issues if code not in rejected)
                coverage_ratio = quality_record.get("coverage_ratio")
                support_density = quality_record.get("support_density")
                if isinstance(coverage_ratio, (int, float)) and isinstance(support_density, (int, float)):
                    covered = round(max(0.0, min(1.0, float(coverage_ratio))) * 20)
                    density = round(max(0.0, min(1.0, float(support_density))) * 4)
                    alignment = 5 if not editorial_issues else 0
                    signature = _structural_signature(proposal, quality_record)
                    redundancy = 5 if structural_counts.get(signature, 0) > 1 else 0
                    score += covered + density + alignment - redundancy
                else:
                    rejected.append("ANGLE_QUALITY_METADATA_INVALID")
        score = max(0, min(100, score))
        if proposal.explainability < 3: rejected.append("NOT_EXPLAINABLE")
        results.append(AngleCandidate(**proposal.model_dump(), evidence_strength=evidence,
            controversy_risk=controversy, total_score=score,
            eligibility="rejected" if rejected else "eligible", rejection_codes=rejected,
            originality={"status": originality.status, "max_contiguous_overlap": originality.max_contiguous_overlap,
                         "five_gram_jaccard": originality.five_gram_jaccard}))
    return results


def _semantic_key(value: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]", "", value).lower()


def _structural_signature(
    proposal: AngleProposal, metadata: dict | None,
) -> tuple[tuple[str, ...], tuple[str, ...], str]:
    row = metadata if isinstance(metadata, dict) else {}
    covered = row.get("covered_dimension_ids", [])
    return (
        tuple(sorted(proposal.supporting_claim_ids)),
        tuple(sorted(item for item in covered if isinstance(item, str)))
        if isinstance(covered, list) else (),
        str(row.get("framing", proposal.narrative_framing)),
    )


def validate_angle_diversity(
    proposals: list[AngleProposal], quality_metadata: dict | None = None,
) -> AngleDiversityResult:
    questions = {_semantic_key(item.core_question) for item in proposals}
    hooks = {_semantic_key(item.hook) for item in proposals}
    mechanisms = {_semantic_key(item.hook_mechanism) for item in proposals}
    takeaways = {_semantic_key(item.audience_takeaway) for item in proposals}
    framings = {_semantic_key(item.narrative_framing) for item in proposals}
    issues = []
    if not 3 <= len(proposals) <= 5:
        issues.append("ANGLE_COUNT_OUT_OF_RANGE")
    if len(questions) < 3:
        issues.append("CORE_QUESTION_NOT_DIVERSE")
    if len(hooks) < 3:
        issues.append("HOOK_NOT_DIVERSE")
    if len(mechanisms) < 3:
        issues.append("HOOK_MECHANISM_NOT_DIVERSE")
    if len(takeaways) < 3:
        issues.append("AUDIENCE_TAKEAWAY_NOT_DIVERSE")
    if len(framings) < 3:
        issues.append("NARRATIVE_FRAMING_NOT_DIVERSE")
    if quality_metadata is not None:
        by_id = quality_metadata.get("candidates", {})
        signatures = set()
        for item in proposals:
            metadata = by_id.get(item.angle_id, {}) if isinstance(by_id, dict) else {}
            signatures.add(_structural_signature(item, metadata))
        if len(proposals) >= 3 and len(signatures) < min(3, len(proposals)):
            issues.append("CANDIDATE_SET_REDUNDANT")
    return AngleDiversityResult(
        passed=not issues,
        candidate_count=len(proposals),
        distinct_core_questions=len(questions),
        distinct_hooks=len(hooks),
        distinct_hook_mechanisms=len(mechanisms),
        distinct_audience_takeaways=len(takeaways),
        distinct_framings=len(framings),
        issue_codes=issues,
    )


def _editorial_quality_issues(
    proposal: AngleProposal,
    quality_metadata: dict,
    candidate_quality: dict,
) -> list[str]:
    """Validate structured coverage claims and deterministic title/hook bounds."""
    issues: list[str] = []
    dimensions = quality_metadata.get("dimensions")
    claim_dimension_map = quality_metadata.get("claim_dimension_map")
    if (not isinstance(dimensions, list) or not all(isinstance(row, dict) for row in dimensions)
            or not isinstance(claim_dimension_map, dict)):
        return ["ANGLE_QUALITY_METADATA_INVALID"]
    dimension_ids = {row.get("dimension_id") for row in dimensions
                     if isinstance(row.get("dimension_id"), str)}
    covered = candidate_quality.get("covered_dimension_ids")
    omitted = candidate_quality.get("intentionally_omitted_dimension_ids")
    partial = candidate_quality.get("partially_covered_dimension_ids")
    if (not isinstance(covered, list) or not all(isinstance(item, str) for item in covered)
            or not isinstance(omitted, list) or not all(isinstance(item, str) for item in omitted)
            or not isinstance(partial, list) or not all(isinstance(item, str) for item in partial)):
        return ["ANGLE_QUALITY_METADATA_INVALID"]
    expected_covered = {
        dimension_id
        for claim_id in proposal.supporting_claim_ids
        for dimension_id in claim_dimension_map.get(claim_id, [])
        if isinstance(dimension_id, str)
    }
    all_dimensions = set(dimension_ids)
    if (not expected_covered <= all_dimensions
            or set(covered) != expected_covered
            or set(omitted) != all_dimensions - expected_covered
            or set(partial) != expected_covered):
        issues.append("ANGLE_COVERAGE_MAPPING_MISMATCH")
    if len(covered) + len(omitted) != len(all_dimensions):
        issues.append("ANGLE_COVERAGE_MAPPING_MISMATCH")

    try:
        from fanglei.offline_angle_planner import _text_terms
        term_by_dimension = {
            row["dimension_id"]: _text_terms(str(row.get("label", "")))
            for row in dimensions if isinstance(row.get("dimension_id"), str)
        }
    except Exception:
        return issues + ["ANGLE_QUALITY_METADATA_INVALID"]
    declared_terms = set().union(*(term_by_dimension.get(item, set()) for item in covered)) if covered else set()
    surface_terms = _text_terms(f"{proposal.title} {proposal.hook}")
    for dimension_id in omitted:
        distinguishing_terms = term_by_dimension.get(dimension_id, set()) - declared_terms
        if distinguishing_terms & surface_terms:
            issues.append("EDITORIAL_SCOPE_UNSUPPORTED")
            break
    return list(dict.fromkeys(issues))


def build_angle_quality_report(
    quality_metadata: dict,
    proposals: list[AngleProposal],
    candidates: list[AngleCandidate],
) -> dict:
    """Add score components and quality results beside strict candidate rows."""
    from copy import deepcopy

    result = deepcopy(quality_metadata)
    proposal_by_id = {item.angle_id: item for item in proposals}
    candidate_by_id = {item.angle_id: item for item in candidates}
    rows = result.get("candidates", {})
    signature_counts: dict[tuple[tuple[str, ...], tuple[str, ...], str], int] = {}
    for proposal in proposals:
        row = rows.get(proposal.angle_id, {}) if isinstance(rows, dict) else {}
        signature = _structural_signature(proposal, row)
        signature_counts[signature] = signature_counts.get(signature, 0) + 1
    for angle_id, row in rows.items():
        proposal = proposal_by_id.get(angle_id)
        candidate = candidate_by_id.get(angle_id)
        if proposal is None or candidate is None or not isinstance(row, dict):
            continue
        issues = _editorial_quality_issues(proposal, result, row)
        base_score = (candidate.evidence_strength * 5 + candidate.audience_relevance * 4
                      + candidate.novelty * 3 + candidate.hook_strength * 3
                      + candidate.visual_potential + candidate.explainability * 4
                      - candidate.controversy_risk * 6)
        redundancy_penalty = 5 if signature_counts.get(
            _structural_signature(proposal, row), 0
        ) > 1 else 0
        row["scope_alignment"] = "passed" if not issues else "failed"
        row["editorial_quality"] = "passed" if not issues else "failed"
        row["editorial_issue_codes"] = issues
        row["score_components"] = {
            "base_score": base_score,
            "research_coverage_bonus": round(max(0.0, min(1.0, float(row["coverage_ratio"]))) * 20),
            "support_density_bonus": round(max(0.0, min(1.0, float(row["support_density"]))) * 4),
            "scope_alignment_bonus": 5 if not issues else 0,
            "candidate_redundancy_penalty": redundancy_penalty,
            "final_score": candidate.total_score,
        }
    return result


def select_angle(candidates: list[AngleCandidate], requested_id: str | None = None) -> AngleCandidate:
    eligible = [item for item in candidates if item.eligibility == "eligible"]
    if requested_id:
        match = next((item for item in eligible if item.angle_id == requested_id), None)
        if not match: raise ValueError(f"Angle is not eligible: {requested_id}")
        return match
    if not eligible: raise ValueError("No eligible content angle")
    return sorted(eligible, key=lambda c: (-c.total_score, -c.evidence_strength, -c.audience_relevance,
                                           -c.explainability, -c.novelty, c.angle_id))[0]
