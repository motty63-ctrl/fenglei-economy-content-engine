from __future__ import annotations

import pytest

from fanglei.content_models import AngleCandidate, ScriptReadyClaim
from fanglei.content_policy import build_fact_palette
from fanglei.offline_angle_planner import _research_bounded_claims
from fanglei.pipeline import _render_research, _render_research_focus
from fanglei.providers.content import (
    AngleGenerationInput,
    DeepSeekContentPlanningProvider,
    MockContentPlanningProvider,
    RepairIssue,
    ScriptRepairInput,
    ScriptGenerationInput,
    _supporting_claims,
)
from fanglei.research_focus import ResearchFocusV1
from fanglei.script_lint import lint_script
from fanglei.evidence_policy import claim_eligibility_reason, is_claim_eligible_for_content
from tests.test_script_quality import _angle, _draft, _facts


def _raw_claim(claim_id: str, *, status: object = "verified", allowed: object = True) -> dict:
    text = f"Synthetic Statistics Office reports the monthly retail index for March was 103 ({claim_id})."
    return {
        "claim_id": claim_id,
        "claim_type": "fact",
        "claim_text": text,
        "verification_status": status,
        "allowed_downstream": allowed,
        "verification_basis": "independent_corroboration",
        "source_ids": ["synthetic-retail-release"],
        "evidence": [{
            "source_id": "synthetic-retail-release",
            "evidence_eligible": True,
            "original_url": "https://synthetic.example/retail/march",
            "evidence_text": text,
        }],
    }


def _palette_claim(claim_id: str, *, status: str = "verified", allowed: bool = True) -> ScriptReadyClaim:
    raw = _raw_claim(claim_id, status=status, allowed=allowed)
    return ScriptReadyClaim(
        claim_id=claim_id,
        claim_text=raw["claim_text"],
        source_ids=raw["source_ids"],
        evidence=raw["evidence"],
        verification_basis="independent_corroboration",
        verification_status=status,
        allowed_downstream=allowed,
    )


@pytest.mark.parametrize(
    ("claim", "reason"),
    [
        ({"verification_status": "verified", "allowed_downstream": True}, "eligible"),
        ({"verification_status": "verified", "allowed_downstream": False}, "downstream_not_allowed"),
        ({"verification_status": "unverified", "allowed_downstream": True}, "unverified"),
        ({"verification_status": "conflicted", "allowed_downstream": True}, "conflicted"),
        ({"allowed_downstream": True}, "invalid_status"),
        ({"verification_status": "verified"}, "downstream_not_allowed"),
        ({"verification_status": "pending", "allowed_downstream": True}, "invalid_status"),
    ],
)
def test_shared_claim_eligibility_is_fail_closed(claim: dict, reason: str) -> None:
    assert claim_eligibility_reason(claim) == reason
    assert is_claim_eligible_for_content(claim) is (reason == "eligible")


def test_nonfed_retail_claims_are_filtered_once_and_remain_bounded_across_layers() -> None:
    eligible = _raw_claim("claim_retail_eligible")
    verified_but_blocked = _raw_claim("claim_retail_blocked", allowed=False)
    unverified = _raw_claim("claim_retail_unverified", status="unverified", allowed=True)
    facts = {"claims": [eligible, verified_but_blocked, unverified]}

    palette = build_fact_palette(facts)
    assert [claim.claim_id for claim in palette] == ["claim_retail_eligible"]

    request = AngleGenerationInput(
        run_id="synthetic-retail-run",
        core_topic="How did the synthetic monthly retail index change?",
        research_questions=["What did the March release report?"],
        research_md="Research cites [claim_retail_eligible] [claim_retail_blocked] [claim_retail_unverified].",
        fact_palette=(
            *palette,
            _palette_claim("claim_retail_blocked", allowed=False),
            _palette_claim("claim_retail_unverified", status="unverified", allowed=True),
        ),
    )
    assert [claim.claim_id for claim in _research_bounded_claims(request)] == ["claim_retail_eligible"]

    selected_angle = AngleCandidate(
        angle_id="angle_retail_001",
        title="Synthetic retail change",
        hook="What did the monthly release report?",
        core_question="What did the synthetic report record?",
        core_insight="The release records one monthly index value.",
        supporting_claim_ids=["claim_retail_eligible"],
        audience_relevance=3,
        novelty=3,
        hook_strength=3,
        visual_potential=3,
        explainability=4,
        evidence_strength=2,
        controversy_risk=0,
        total_score=60,
        eligibility="eligible",
    )
    script = MockContentPlanningProvider().generate_script(ScriptGenerationInput(
        run_id="synthetic-retail-run",
        selected_angle=selected_angle,
        research_md=request.research_md,
        fact_palette=palette,
    ))
    factual = [sentence for sentence in script.sentences if sentence.sentence_type == "verified_fact"]
    assert [claim_id for sentence in factual for claim_id in sentence.claim_ids] == ["claim_retail_eligible"]
    assert verified_but_blocked["claim_text"] not in " ".join(sentence.text for sentence in script.sentences)
    assert unverified["claim_text"] not in " ".join(sentence.text for sentence in script.sentences)


def test_deepseek_angle_context_revalidates_palette_before_prompt() -> None:
    captured: dict = {}

    def transport(payload: dict) -> dict:
        captured.update(payload)
        return {"choices": [{"message": {"content": '{"candidates": []}'}}]}

    provider = DeepSeekContentPlanningProvider("not-a-real-key", transport=transport)
    eligible = _palette_claim("claim_retail_eligible")
    blocked = _palette_claim("claim_retail_blocked", allowed=False)
    unverified = _palette_claim("claim_retail_unverified", status="unverified", allowed=True)
    provider.generate_angles(AngleGenerationInput(
        run_id="synthetic-retail-run",
        core_topic="How did the synthetic monthly retail index change?",
        research_questions=["What did the March release report?"],
        research_md="Research cites all three claim records.",
        fact_palette=(eligible, blocked, unverified),
    ))
    user = captured["messages"][1]["content"]
    assert "claim_retail_eligible" in user
    assert "claim_retail_blocked" not in user
    assert "claim_retail_unverified" not in user


def test_script_generation_and_repair_context_reject_ineligible_support() -> None:
    blocked = _palette_claim("claim_retail_blocked", allowed=False)
    selected = _angle().model_copy(update={"supporting_claim_ids": [blocked.claim_id]})
    with pytest.raises(ValueError, match="SCRIPT_ANGLE_SUPPORTING_CLAIM_INELIGIBLE"):
        _supporting_claims(selected, (blocked,))
    with pytest.raises(ValueError, match="SCRIPT_ANGLE_SUPPORTING_CLAIM_INELIGIBLE"):
        MockContentPlanningProvider().generate_script(ScriptGenerationInput(
            run_id="synthetic-retail-run",
            selected_angle=selected,
            research_md="Synthetic research.",
            fact_palette=(blocked,),
        ))

    provider = DeepSeekContentPlanningProvider(
        "not-a-real-key",
        transport=lambda _payload: pytest.fail("repair must reject before provider transport"),
    )
    with pytest.raises(ValueError, match="SCRIPT_ANGLE_SUPPORTING_CLAIM_INELIGIBLE"):
        provider.repair_script(ScriptRepairInput(
            run_id="synthetic-retail-run",
            repair_attempt=1,
            selected_angle=selected,
            current_script=_draft(),
            editable_sentence_ids=["sentence_001"],
            protected_sentence_ids=["sentence_002"],
            allow_additions=False,
            fact_palette=(blocked,),
            issues=[RepairIssue(code="HOOK_INVALID", sentence_id="sentence_001")],
        ))


def test_script_lint_rejects_verified_claim_without_downstream_permission() -> None:
    facts = _facts()
    facts["claims"][0]["allowed_downstream"] = False
    result = lint_script(_draft(), _angle(), facts, "Synthetic unrelated source text", speaking_rate=4.0)
    assert any(issue.code == "UNSUPPORTED_FACT" for issue in result.issues)


def test_research_focus_lists_shared_exclusion_reasons_for_synthetic_claims() -> None:
    focus = ResearchFocusV1(
        schema_version="research-focus/1.0",
        run_id="synthetic-retail-run",
        case_id="synthetic-retail",
        primary_question="What did the monthly retail release report?",
        subquestions=["What was the recorded March index?"],
        constraints=["Do not infer causes."],
        created_at="2026-09-27T12:00:00+08:00",
        created_by="test",
    )
    eligible = _raw_claim("claim_retail_eligible")
    blocked = _raw_claim("claim_retail_blocked", allowed=False)
    unverified = _raw_claim("claim_retail_unverified", status="unverified", allowed=True)
    source_artifact = {"sources": [{
        "source_id": "synthetic-retail-release",
        "title": "Synthetic monthly retail release",
        "url": "https://synthetic.example/retail/march",
        "credibility_tier": "A",
    }]}
    rendered = _render_research_focus(
        "synthetic-retail-run", focus, source_artifact,
        {"claims": [eligible, blocked, unverified]},
    )
    assert eligible["claim_text"] in rendered
    assert blocked["claim_text"] not in rendered
    assert unverified["claim_text"] not in rendered
    assert "claim_retail_blocked" not in rendered
    assert "claim_retail_unverified" not in rendered
    assert claim_eligibility_reason(blocked) == "downstream_not_allowed"
    assert claim_eligibility_reason(unverified) == "unverified"


def test_legacy_research_renderer_retains_verified_only_compatibility() -> None:
    verified_not_allowed = _raw_claim("claim_legacy_verified", allowed=False)
    sources = [{
        "source_id": "synthetic-retail-release",
        "title": "Synthetic monthly retail release",
        "url": "https://synthetic.example/retail/march",
        "credibility_tier": "A",
    }]
    rendered = _render_research(
        "synthetic-retail-run", [], sources, {"claims": [verified_not_allowed]},
    )
    assert verified_not_allowed["claim_text"] in rendered
