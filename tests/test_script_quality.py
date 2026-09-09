from fanglei.content_models import AngleCandidate, ScriptDraft, ScriptSentence
from fanglei.script_lint import lint_script
from fanglei.content_render import render_script_json, render_script_markdown


def _angle() -> AngleCandidate:
    return AngleCandidate(angle_id="angle_001", title="小数点不是分歧", hook="同一个增长率，为什么有两个数字？",
        core_question="精度为什么不同？", core_insight="显示精度不等于结论冲突", supporting_claim_ids=["claim_007"],
        audience_relevance=5, novelty=4, hook_strength=4, visual_potential=3, explainability=5,
        evidence_strength=3, controversy_risk=1, total_score=80, eligibility="eligible")


def _facts() -> dict:
    return {"claims": [{"claim_id": "claim_007", "claim_text": "美国2024年实际GDP增长2.8%",
        "claim_type": "fact", "verification_status": "verified", "allowed_downstream": True,
        "evidence": [{"evidence_eligible": True, "evidence_text": "2024 real GDP grew 2.8 percent", "observation": 2.7938}]}]}


def _draft(extra: str = "") -> ScriptDraft:
    sentences = [
        ScriptSentence(sentence_id="sentence_001", section="hook", sentence_type="interpretation", text="同一个增长率，为什么有两个数字？"),
        ScriptSentence(sentence_id="sentence_002", section="phenomenon", sentence_type="verified_fact", text="美国2024年实际GDP增长2.8%。", claim_ids=["claim_007"]),
    ]
    for index in range(3, 11):
        sentences.append(ScriptSentence(sentence_id=f"sentence_{index:03d}", section="mechanism",
            sentence_type="explanation", text="统计结果可以保留不同精度，短一些方便传播，长一些方便研究者继续计算。"))
    sentences.append(ScriptSentence(sentence_id="sentence_012", section="mechanism", sentence_type="analogy",
        text="这像把同一段距离分别写成约数和更细的刻度，表达层级不同，方向并没有改变。"))
    sentences.append(ScriptSentence(sentence_id="sentence_013", section="core_judgment", sentence_type="interpretation",
        text="所以核心判断是，先核对指标口径和精度，再讨论经济含义。" + extra))
    return ScriptDraft(angle_id="angle_001", title="小数点不是分歧", sentences=sentences)


def test_valid_script_has_configurable_duration_and_clean_markdown() -> None:
    result = lint_script(_draft(), _angle(), _facts(), "完全不同的原始文章", speaking_rate=4.0)
    assert result.passed is True
    assert 60 <= result.estimated_duration_seconds <= 90
    payload = render_script_json(_draft(), result)
    assert payload["speaking_rate_chars_per_second"] == 4.0
    assert payload["sentences"][1]["claim_ids"] == ["claim_007"]
    spoken = render_script_markdown(_draft(), result)
    assert "claim_" not in spoken and "sentence_" not in spoken and "---" not in spoken


def test_unsupported_number_and_bad_rate_fail_quality_gate() -> None:
    bad = _draft(extra="某机构预计明年增长3.6%。")
    result = lint_script(bad, _angle(), _facts(), "原文", speaking_rate=4.0)
    assert result.passed is False
    assert "UNDECLARED_FACT" in {issue.code for issue in result.issues}
    assert lint_script(_draft(), _angle(), _facts(), "原文", speaking_rate=2.0).passed is False
