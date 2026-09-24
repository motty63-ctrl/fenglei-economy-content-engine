from fanglei.angle_policy import score_angles, select_angle, validate_angle_diversity
from fanglei.content_models import AngleProposal, ScriptReadyClaim


def _claim() -> ScriptReadyClaim:
    return ScriptReadyClaim(claim_id="claim_007", claim_text="美国2024年实际GDP增长2.8%",
                            source_ids=["bea", "worldbank", "oecd"],
                            evidence=[{"source_id": "bea", "evidence_eligible": True}])


def _authority_claim() -> ScriptReadyClaim:
    return ScriptReadyClaim(
        claim_id="claim_authority",
        claim_text="Federal Reserve FOMC participants (SEP): published Median projection for Federal funds rate (2026) changed from 3.8 Percent in June SEP to 4.1 Percent in September SEP.",
        source_ids=["src_june", "src_september"],
        evidence=[
            {"source_id": "src_june", "evidence_eligible": True,
             "evidence_text": "Federal funds rate\n3.8", "original_url": "https://example.test/june"},
            {"source_id": "src_september", "evidence_eligible": True,
             "evidence_text": "Federal funds rate\n4.1", "original_url": "https://example.test/september"},
        ],
        verification_basis="authoritative_primary_attestation",
        authority_attestation={
            "kind": "deterministic_document_comparison",
            "source_ids": ["src_june", "src_september"],
            "attribution": "Federal Reserve FOMC participants (SEP)",
            "scope": {
                "subject": "Federal funds rate",
                "measure": "projection",
                "period": "2026",
                "unit": "Percent",
                "statistic": "Median",
                "certainty": "projection",
            },
        },
    )


def _proposal(angle_id: str, insight: str, hook: str = "2.8和2.7938，真的矛盾吗？",
              framing: str = "misconception_correction") -> AngleProposal:
    return AngleProposal(angle_id=angle_id, title=f"角度{angle_id}", hook=hook,
                         core_question=f"问题{angle_id}", core_insight=insight,
                         hook_mechanism=f"hook_{angle_id}", audience_takeaway=f"收获{angle_id}",
                         narrative_framing=framing,
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


def test_authority_angle_preserves_attribution_scope_and_rejects_expansion() -> None:
    valid = _proposal(
        "angle_authority",
        "\u7f8e\u8054\u50a8FOMC\u53c2\u4e0e\u8005\u7684SEP\u4e2d\u4f4d\u6570\u9884\u6d4b\uff0c2026\u5e74\u8054\u90a6\u57fa\u91d1\u5229\u7387\u4ece3.8%\u8c03\u6574\u52304.1%",
        hook="\u7f8e\u8054\u50a8FOMC\u53c2\u4e0e\u8005\u7684SEP\u4e2d\u4f4d\u6570\u9884\u6d4b\uff0c2026\u5e74\u8054\u90a6\u57fa\u91d1\u5229\u7387\u600e\u4e48\u53d8\uff1f",
    ).model_copy(update={"supporting_claim_ids": ["claim_authority"]})
    unsafe = valid.model_copy(update={
        "angle_id": "angle_unsafe",
        "title": "Why inflation forced a rate-path revision",
        "hook": "Because inflation worsened, the Fed was forced to raise its forecast?",
        "core_question": "How did inflation cause the Fed to increase rates?",
        "core_insight": "Inflation forced the Fed to raise its rate path",
    })

    candidates = score_angles([valid, unsafe], (_authority_claim(),), "unrelated source text")

    assert candidates[0].eligibility == "eligible"
    assert "AUTHORITY_ATTRIBUTION_MISSING" in candidates[1].rejection_codes
    assert "AUTHORITY_SCOPE_EXPANSION" in candidates[1].rejection_codes


def test_diversity_requires_distinct_question_hook_takeaway_and_framing() -> None:
    diverse = [
        _proposal("angle_001", "纠正数字冲突误解", framing="misconception_correction"),
        _proposal("angle_002", "解释统计精度", framing="economic_data_literacy"),
        _proposal("angle_003", "教读者阅读媒体数字", framing="media_literacy"),
    ]
    result = validate_angle_diversity(diverse)
    assert result.passed is True
    assert result.distinct_framings == 3

    clones = [item.model_copy(update={
        "core_question": "为什么两个GDP数字不同",
        "hook_mechanism": "same_hook",
        "audience_takeaway": "同一个收获",
        "narrative_framing": "misconception_correction",
    }) for item in diverse]
    rejected = validate_angle_diversity(clones)
    assert rejected.passed is False
    assert {"CORE_QUESTION_NOT_DIVERSE", "HOOK_MECHANISM_NOT_DIVERSE",
            "AUDIENCE_TAKEAWAY_NOT_DIVERSE", "NARRATIVE_FRAMING_NOT_DIVERSE"}.issubset(rejected.issue_codes)
