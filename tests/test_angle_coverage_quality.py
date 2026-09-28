from __future__ import annotations

import pytest

from fanglei.angle_policy import build_angle_quality_report, score_angles, validate_angle_diversity
from fanglei.content_models import AngleProposal, ScriptReadyClaim
from fanglei.offline_angle_planner import _text_terms, plan_offline_angles
from fanglei.providers.content import AngleGenerationInput
from fanglei.script_lint import _spoken_count


def _claim(claim_id: str, dimension: str, *, text: str | None = None) -> ScriptReadyClaim:
    source_id = f"source-{claim_id}"
    return ScriptReadyClaim(
        claim_id=claim_id,
        claim_text=text or f"Agency report recorded {dimension} at a supported value.",
        verification_status="verified",
        allowed_downstream=True,
        source_ids=[source_id],
        evidence=[{
            "source_id": source_id,
            "evidence_eligible": True,
            "evidence_text": text or f"Agency report recorded {dimension} at a supported value.",
            "evidence_target_concept": dimension,
            "evidence_kind": "narrative_sentence",
        }],
        verification_basis="independent_corroboration",
        authority_attestation={"scope": {
            "subject": dimension,
            "measure": dimension,
            "period": "March",
            "unit": "index points",
            "statistic": "reported value",
            "certainty": "reported",
        }},
    )


def _request(dimensions: list[str], claims: list[ScriptReadyClaim] | None = None) -> AngleGenerationInput:
    questions = [f"What did the report record about {dimension}?" for dimension in dimensions]
    selected = claims or [
        _claim(f"claim_{index:03d}", dimension)
        for index, dimension in enumerate(dimensions, start=1)
    ]
    refs = " ".join(f"[{claim.claim_id}]" for claim in selected)
    return AngleGenerationInput(
        run_id="synthetic-retail-run",
        core_topic="What did the synthetic report record across the selected dimensions?",
        research_questions=questions,
        research_focus={
            "schema_version": "research-focus/1.0",
            "run_id": "synthetic-retail-run",
            "case_id": "synthetic-retail-case",
            "primary_question": "What did the synthetic report record across the selected dimensions?",
            "subquestions": questions,
            "constraints": ["Use only directly supported records."],
        },
        research_md=f"# Research\n{refs}",
        fact_palette=tuple(selected),
    )


def _quality_request(dimensions: list[str]):
    request = _request(dimensions)
    planned = plan_offline_angles(request)
    return request, planned


def test_four_dimension_focus_gets_a_broad_supported_synthesis() -> None:
    request, planned = _quality_request(
        ["retail sales", "hours worked", "price index", "freight volume"]
    )

    quality = planned.quality_metadata
    broad_id = next(
        candidate.angle_id for candidate in planned.candidates
        if quality["candidates"][candidate.angle_id]["framing"] == "broad_synthesis"
    )
    broad = quality["candidates"][broad_id]

    assert set(planned.candidates[0].supporting_claim_ids) == {
        claim.claim_id for claim in request.fact_palette
    }
    assert len(broad["covered_dimension_ids"]) == 4
    assert broad["intentionally_omitted_dimension_ids"] == []
    assert broad["coverage_ratio"] == 1.0
    assert all(12 <= _spoken_count(candidate.hook) <= 18 for candidate in planned.candidates)
    candidates = score_angles(
        planned.candidates, request.fact_palette, "unrelated source text", quality_metadata=quality
    )
    report = build_angle_quality_report(quality, planned.candidates, candidates)
    assert report["candidates"][broad_id]["editorial_quality"] == "passed"


def test_narrow_single_claim_angle_remains_valid_and_scored() -> None:
    request, planned = _quality_request(
        ["retail sales", "hours worked", "price index", "freight volume"]
    )
    broad_quality = planned.quality_metadata
    dimensions = broad_quality["dimensions"]
    claim = request.fact_palette[0]
    dimension_id = next(
        item["dimension_id"] for item in dimensions
        if claim.claim_id in item["supporting_claim_ids"]
    )
    narrow = AngleProposal(
        angle_id="angle_narrow",
        title="retail sales: one recorded measure",
        hook="What does this single measure establish?",
        core_question="What did the report record about retail sales?",
        core_insight=claim.claim_text,
        hook_mechanism="single_measure_zoom",
        audience_takeaway="Read one measure within its stated scope.",
        narrative_framing="narrow_record",
        supporting_claim_ids=[claim.claim_id],
        audience_relevance=4,
        novelty=3,
        hook_strength=3,
        visual_potential=2,
        explainability=4,
    )
    metadata = {
        "dimensions": dimensions,
        "claim_dimension_map": broad_quality["claim_dimension_map"],
        "candidates": {
            narrow.angle_id: {
                "framing": "narrow_record",
                "covered_dimension_ids": [dimension_id],
                "intentionally_omitted_dimension_ids": [
                    item["dimension_id"] for item in dimensions
                    if item["dimension_id"] != dimension_id
                ],
                "partially_covered_dimension_ids": [dimension_id],
                "coverage_ratio": 0.25,
                "support_density": 1.0,
            }
        },
    }

    scored = score_angles([narrow], request.fact_palette, "unrelated source text", quality_metadata=metadata)[0]

    assert scored.eligibility == "eligible", scored.rejection_codes
    assert scored.total_score > 0


def test_title_hook_dimension_overreach_fails_editorial_scope_check() -> None:
    dimensions = [
        {"dimension_id": "d1", "label": "retail sales", "supporting_claim_ids": ["claim_a"]},
        {"dimension_id": "d2", "label": "price index", "supporting_claim_ids": ["claim_b"]},
        {"dimension_id": "d3", "label": "labor demand", "supporting_claim_ids": []},
    ]
    claim = _claim("claim_a", "retail sales")
    proposal = AngleProposal(
        angle_id="angle_overreach",
        title="Retail sales, price index, and labor demand",
        hook="What changed across retail, prices, and labor?",
        core_question="What did the report record about retail sales?",
        core_insight=claim.claim_text,
        hook_mechanism="comparison",
        audience_takeaway="Read the supported measure.",
        narrative_framing="overbroad",
        supporting_claim_ids=[claim.claim_id],
        audience_relevance=4,
        novelty=3,
        hook_strength=3,
        visual_potential=2,
        explainability=4,
    )
    metadata = {
        "dimensions": dimensions,
        "claim_dimension_map": {"claim_a": ["d1"], "claim_b": ["d2"]},
        "candidates": {proposal.angle_id: {
            "framing": "overbroad",
            "covered_dimension_ids": ["d1"],
            "intentionally_omitted_dimension_ids": ["d2", "d3"],
            "partially_covered_dimension_ids": ["d1"],
            "coverage_ratio": 1 / 3,
            "support_density": 1.0,
        }},
    }

    scored = score_angles([proposal], (claim,), "unrelated source text", quality_metadata=metadata)[0]

    assert scored.eligibility == "rejected"
    assert "EDITORIAL_SCOPE_UNSUPPORTED" in scored.rejection_codes


def test_redundancy_gate_uses_support_and_coverage_not_only_wording() -> None:
    proposals = [
        AngleProposal(
            angle_id=f"angle_{index}", title=f"different title {index}",
            hook=f"different hook {index}", core_question=f"question {index}",
            core_insight="same insight", hook_mechanism=f"mechanism_{index}",
            audience_takeaway=f"takeaway_{index}", narrative_framing="same_frame",
            supporting_claim_ids=["claim_a", "claim_b"], audience_relevance=4,
            novelty=3, hook_strength=3, visual_potential=3, explainability=4,
        ) for index in range(5)
    ]
    metadata = {"candidates": {
        proposal.angle_id: {"covered_dimension_ids": ["d1", "d2"]}
        for proposal in proposals
    }}

    result = validate_angle_diversity(proposals, metadata)

    assert not result.passed
    assert "CANDIDATE_SET_REDUNDANT" in result.issue_codes


def test_candidate_redundancy_penalty_is_reported_in_score_components() -> None:
    claims = (_claim("claim_a", "retail sales"), _claim("claim_b", "price index"))
    proposals = [
        AngleProposal(
            angle_id=f"angle_{index}", title=f"Same lens {index}",
            hook=f"Same structure {index}", core_question=f"Question {index}",
            core_insight=f"Insight {index}", hook_mechanism=f"lens_{index}",
            audience_takeaway=f"Takeaway {index}", narrative_framing="same_frame",
            supporting_claim_ids=["claim_a", "claim_b"], audience_relevance=4,
            novelty=3, hook_strength=3, visual_potential=3, explainability=4,
        ) for index in range(2)
    ]
    metadata = {
        "dimensions": [
            {"dimension_id": "d1", "label": "retail sales"},
            {"dimension_id": "d2", "label": "price index"},
        ],
        "claim_dimension_map": {"claim_a": ["d1"], "claim_b": ["d2"]},
        "candidates": {
            proposal.angle_id: {
                "framing": "same_frame",
                "covered_dimension_ids": ["d1", "d2"],
                "intentionally_omitted_dimension_ids": [],
                "partially_covered_dimension_ids": ["d1", "d2"],
                "coverage_ratio": 1.0,
                "support_density": 1.0,
            } for proposal in proposals
        },
    }

    scored = score_angles(proposals, claims, "unrelated source material", quality_metadata=metadata)
    report = build_angle_quality_report(metadata, proposals, scored)

    assert all(
        report["candidates"][candidate.angle_id]["score_components"]["candidate_redundancy_penalty"] == 5
        for candidate in scored
    )


def test_partial_evidence_is_reported_as_partial_and_omits_unsupported_dimension() -> None:
    request, planned = _quality_request(["retail sales", "price index", "hours worked"])
    quality = planned.quality_metadata
    # Re-plan with the third dimension absent from the eligible evidence.
    partial_request = _request(
        ["retail sales", "price index", "hours worked"],
        [_claim("claim_a", "retail sales"), _claim("claim_b", "price index")],
    )
    partial = plan_offline_angles(partial_request).quality_metadata
    broad_id = next(
        key for key, value in partial["candidates"].items()
        if value["framing"] == "broad_synthesis"
    )
    broad = partial["candidates"][broad_id]
    dimension_labels = {row["dimension_id"]: row["label"] for row in partial["dimensions"]}

    assert broad["coverage_ratio"] == pytest.approx(2 / 3)
    assert broad["partially_covered_dimension_ids"] == broad["covered_dimension_ids"]
    assert len(broad["intentionally_omitted_dimension_ids"]) == 1
    omitted = broad["intentionally_omitted_dimension_ids"][0]
    assert dimension_labels[omitted] == "What did the report record about hours worked?"
    assert quality["dimensions"]


def test_rich_single_claim_can_support_multiple_dimensions_without_count_threshold() -> None:
    rich = _claim(
        "claim_rich", "retail sales and price index",
        text="The report records a retail sales index and a price index with multiple values.",
    ).model_copy(update={
        "evidence": [{
            "source_id": "source-claim_rich", "evidence_eligible": True,
            "evidence_text": "The report records a retail sales index and a price index with multiple values.",
            "evidence_target_concept": "retail sales price index",
            "evidence_kind": "narrative_sentence",
            "explicit_values": [{"value": "101"}, {"value": "104"}, {"value": "107"}],
        }],
        "authority_attestation": {"scope": {
            "subject": "retail sales and price index",
            "measure": "retail sales price index",
            "period": "March",
            "unit": "index points",
            "statistic": "reported value",
            "certainty": "reported",
        }},
    })
    request = _request(["retail sales", "price index"], [rich])
    planned = plan_offline_angles(request)
    broad = planned.candidates[0]
    broad_quality = planned.quality_metadata["candidates"][broad.angle_id]

    assert broad.supporting_claim_ids == [rich.claim_id]
    assert len(broad_quality["covered_dimension_ids"]) == 2
    assert broad_quality["support_density"] == 2.0


def test_focus_mapping_uses_specific_concepts_and_claim_structure() -> None:
    def scoped_claim(
        claim_id: str, subject: str, measure: str, target: str, *,
        evidence_kind: str = "narrative_sentence",
    ) -> ScriptReadyClaim:
        base = _claim(claim_id, subject)
        return base.model_copy(update={
            "authority_attestation": {"scope": {
                "subject": subject, "measure": measure, "period": "August",
                "unit": None, "statistic": None, "certainty": "reported",
            }},
            "evidence": [{
                "source_id": base.source_ids[0], "evidence_eligible": True,
                "evidence_text": f"The report records {target}.",
                "evidence_target_concept": target,
                "evidence_target_id": f"target-{claim_id}",
                "evidence_kind": evidence_kind,
            }],
        })

    claims = [
        scoped_claim("claim_retail", "retail sales", "sales", "retail sales change"),
        scoped_claim("claim_rate", "unemployment rate", "unemployment rate", "unemployment rate"),
        scoped_claim("claim_hourly", "average hourly earnings", "hourly earnings", "average hourly earnings"),
        scoped_claim("claim_hours", "average workweek", "workweek", "average workweek"),
        scoped_claim("claim_june", "June", "change", "June payroll estimate revision", evidence_kind="revision"),
        scoped_claim("claim_july", "July", "change", "July payroll estimate revision", evidence_kind="revision"),
        scoped_claim("claim_food", "food services and drinking places", "employment", "employment change for food services and drinking places"),
        scoped_claim("claim_education", "local government education", "jobs", "jobs added in local government education"),
        scoped_claim("claim_information", "information employment", "employment", "information-sector employment change"),
        scoped_claim("claim_total", "total nonfarm payroll employment", "payroll employment", "total payroll employment change"),
    ]
    questions = [
        "报告分别记录零售销售和失业率的变化是什么？",
        "报告关于平均时薪和平均每周工时的内容是什么？",
        "6 月和 7 月修订值分别是多少？",
        "哪些行业就业变化被报告？",
        "如何区分不同调查方式并保留统计边界？",
    ]
    request = _request(questions, claims).model_copy(update={
        "research_questions": questions,
        "research_focus": {
            "schema_version": "research-focus/1.0",
            "run_id": "synthetic-retail-run",
            "case_id": "synthetic-retail-case",
            "primary_question": "What did the synthetic report record?",
            "subquestions": questions,
            "constraints": ["Use only directly supported records."],
        },
    })
    planned = plan_offline_angles(request)
    dimensions = planned.quality_metadata["dimensions"]
    mapped = {
        row["label"]: set(row["supporting_claim_ids"])
        for row in dimensions
    }

    assert mapped[questions[0]] == {"claim_retail", "claim_rate"}
    assert mapped[questions[1]] == {"claim_hourly", "claim_hours"}
    assert mapped[questions[2]] == {"claim_june", "claim_july"}
    assert mapped[questions[3]] == {"claim_food", "claim_education", "claim_information"}
    assert mapped[questions[4]] == set()


def test_named_month_normalization_is_calendar_wide_not_case_specific() -> None:
    assert "month_08" in _text_terms("August")
    assert "month_07" in _text_terms("July")
    assert "month_03" in _text_terms("March")


def test_unstructured_claim_values_do_not_leak_into_angle_surface_copy() -> None:
    claim = ScriptReadyClaim(
        claim_id="claim_unstructured",
        claim_text="The report recorded an index value of 103 in March.",
        verification_status="verified",
        allowed_downstream=True,
        verification_basis="independent_corroboration",
        source_ids=["source-unstructured"],
        evidence=[{
            "source_id": "source-unstructured",
            "evidence_eligible": True,
            "evidence_text": "Index value: 103.",
        }],
    )
    request = _request(["What value did the release record?"], [claim]).model_copy(update={
        "research_focus": {
            "schema_version": "research-focus/1.0",
            "run_id": "synthetic-retail-run",
            "case_id": "synthetic-retail-case",
            "primary_question": "What did the report record about the retail index?",
            "subquestions": ["What value did the release record?"],
            "constraints": ["Use only directly supported records."],
        },
        "research_questions": ["What value did the release record?"],
    })

    planned = plan_offline_angles(request)

    assert len(planned.candidates) >= 3
    for proposal in planned.candidates:
        assert "103" not in proposal.title
        assert "103" not in proposal.hook
        assert "103" not in proposal.core_question
    fallback_hooks = [
        proposal.hook for proposal in planned.candidates
        if proposal.narrative_framing in {"source_record_boundary", "single_record_detail"}
    ]
    assert fallback_hooks
    assert all(len(hook) <= 20 for hook in fallback_hooks)
