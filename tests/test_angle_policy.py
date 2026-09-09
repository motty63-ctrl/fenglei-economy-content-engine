from fanglei.angle_policy import score_angles, select_angle
from fanglei.content_models import AngleProposal, ScriptReadyClaim


def _claim() -> ScriptReadyClaim:
    return ScriptReadyClaim(claim_id="claim_007", claim_text="美国2024年实际GDP增长2.8%",
                            source_ids=["bea", "worldbank", "oecd"],
                            evidence=[{"source_id": "bea", "evidence_eligible": True}])


def _proposal(angle_id: str, insight: str, hook: str = "2.8和2.7938，真的矛盾吗？") -> AngleProposal:
    return AngleProposal(angle_id=angle_id, title=f"角度{angle_id}", hook=hook,
                         core_question=f"问题{angle_id}", core_insight=insight,
                         supporting_claim_ids=["claim_007"], audience_relevance=5,
                         novelty=4, hook_strength=4, visual_potential=3, explainability=5)


def test_scoring_uses_all_dimensions_and_recommendation_is_overridable() -> None:
    candidates = score_angles([
        _proposal("angle_001", "显示精度不等于经济分歧"),
        _proposal("angle_002", "小数位让人误判数据冲突"),
        _proposal("angle_003", "普通人应先看指标口径"),
    ], (_claim(),), "完全不同的原文")
    assert all(c.eligibility == "eligible" for c in candidates)
    assert all(0 <= c.total_score <= 100 and c.explainability == 5 for c in candidates)
    recommended = select_angle(candidates)
    selected = select_angle(candidates, "angle_003")
    assert recommended.angle_id == "angle_001"
    assert selected.angle_id == "angle_003"


def test_unknown_claim_and_false_conflict_are_rejected() -> None:
    unknown = _proposal("angle_001", "新结论").model_copy(update={"supporting_claim_ids": ["claim_999"]})
    false_conflict = _proposal("angle_002", "两个机构结论互相矛盾", "BEA和世界银行打起来了")
    results = score_angles([unknown, false_conflict, _proposal("angle_003", "精度差异")], (_claim(),), "原文")
    assert "UNKNOWN_CLAIM" in results[0].rejection_codes
    assert "FALSE_CONFLICT" in results[1].rejection_codes
