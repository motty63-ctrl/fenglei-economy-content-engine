from fanglei.content_models import ScriptReadyClaim
from fanglei.providers.content import AngleGenerationInput
from fanglei.offline_angle_planner import plan_offline_angles
from fanglei.angle_policy import validate_angle_diversity


def _claim(claim_id: str, claim_text: str, source_id: str) -> ScriptReadyClaim:
    return ScriptReadyClaim(
        claim_id=claim_id,
        claim_text=claim_text,
        source_ids=[source_id],
        evidence=[{
            "source_id": source_id,
            "evidence_eligible": True,
            "evidence_text": claim_text,
            "original_url": f"https://example.test/{source_id}",
        }],
        verification_basis="independent_corroboration",
    )


def _request() -> AngleGenerationInput:
    primary_question = "How did the published housing indicators change across the two reports?"
    return AngleGenerationInput(
        run_id="sample-housing-run",
        core_topic=primary_question,
        research_questions=[
            "What did the first report record about housing starts?",
            "What did the later report record about the same measure?",
        ],
        research_focus={
            "schema_version": "research-focus/1.0",
            "run_id": "sample-housing-run",
            "case_id": "housing-indicators",
            "primary_question": primary_question,
            "subquestions": [
                "What did the first report record about housing starts?",
                "What did the later report record about the same measure?",
                "How can the reports be compared without inferring a cause?",
            ],
            "constraints": ["Do not infer causality."],
        },
        research_md=(
            "# Research\nThe reports record different published housing measures. "
            "[claim_a] [claim_b] [claim_c]"
        ),
        fact_palette=(
            _claim("claim_a", "Agency A reported 1.2 million housing starts in March.", "source_a"),
            _claim("claim_b", "Agency B reported 1.4 million housing starts in April.", "source_b"),
            _claim("claim_c", "Agency C reported a 6 percent change in permits.", "source_c"),
            _claim("claim_not_in_research", "A verified fact not used by Research.", "source_d"),
        ),
        authority_metadata={"policy_name": "independent_sources", "independent_source_count": 3},
    )


def test_offline_planner_is_deterministic_generic_and_research_bounded() -> None:
    request = _request()
    first = plan_offline_angles(request)
    second = plan_offline_angles(request)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert 3 <= len(first.candidates) <= 5
    assert validate_angle_diversity(first.candidates).passed
    available_ids = {claim.claim_id for claim in request.fact_palette}
    for proposal in first.candidates:
        assert set(proposal.supporting_claim_ids) <= available_ids
        assert "claim_not_in_research" not in proposal.supporting_claim_ids
        assert proposal.supporting_claim_ids
    serialized = str(first.model_dump(mode="json")).casefold()
    assert "fed" not in serialized
    assert "gdp" not in serialized
    assert "sep" not in serialized


def test_offline_planner_uses_legacy_question_fallback_when_focus_absent() -> None:
    request = _request().model_copy(update={"research_focus": None})
    result = plan_offline_angles(request)
    assert 3 <= len(result.candidates) <= 5
    assert all(proposal.core_question for proposal in result.candidates)
