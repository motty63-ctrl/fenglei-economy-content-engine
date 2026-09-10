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
        "source_ids": ["src_1"],
        "evidence": [{"evidence_eligible": True, "evidence_text": "2024 real GDP grew 2.8 percent",
                      "source_id": "src_1", "original_url": "https://example.test/data", "observation": 2.7938}]}]}


def _draft(extra: str = "") -> ScriptDraft:
    sentences = [
        ScriptSentence(sentence_id="sentence_001", section="hook", sentence_type="interpretation", text="同一个增长率，为什么有两个数字？"),
        ScriptSentence(sentence_id="sentence_002", section="phenomenon", sentence_type="verified_fact", text="美国2024年实际GDP增长2.8%。", claim_ids=["claim_007"]),
    ]
    mechanism_texts = (
        "你可以先把两个结果的指标名称放在一起认真核对。",
        "你不妨再看年份，别把不同时间的结果直接放在一起。",
        "我的判断是，比较之前先把问题拆成名称、时间和表达方式。",
        "打个比方，这像看两张地图，先确认比例尺再判断远近。",
        "你可以把小数位当成显示层次，不要急着解释成方向变化。",
        "你不妨追到原始来源，再决定新闻标题有没有省略信息。",
        "我的判断是，核对过程比盯着末尾几位小数更有价值。",
        "就像读药品标签，先看单位，再看数量，最后才下结论。",
    )
    for index, text in enumerate(mechanism_texts, 3):
        sentence_type = "analogy" if text.startswith(("打个比方", "就像")) else "explanation"
        sentences.append(ScriptSentence(sentence_id=f"sentence_{index:03d}", section="mechanism",
            sentence_type=sentence_type, text=text))
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


def test_repeated_sentence_fails_quality_gate() -> None:
    draft = _draft()
    draft.sentences[-1].text = draft.sentences[-2].text
    result = lint_script(draft, _angle(), _facts(), "完全不同的原始文章", speaking_rate=4.0)
    assert "REPEATED_SENTENCE" in {issue.code for issue in result.issues}


def test_obvious_analogy_must_be_labeled_as_analogy() -> None:
    draft = _draft()
    draft.sentences[-2].sentence_type = "interpretation"
    result = lint_script(draft, _angle(), _facts(), "完全不同的原始文章", speaking_rate=4.0)
    assert "SENTENCE_TYPE_MISMATCH" in {issue.code for issue in result.issues}


def test_core_judgment_must_be_an_explicit_conclusion_not_a_question() -> None:
    draft = _draft()
    draft.sentences[-1].text = "你是否只盯着那个醒目的数字？"
    result = lint_script(draft, _angle(), _facts(), "完全不同的原始文章", speaking_rate=4.0)
    assert "CORE_JUDGMENT_WEAK" in {issue.code for issue in result.issues}


def test_formulaic_openers_cannot_repeat_more_than_twice() -> None:
    draft = _draft()
    for sentence in draft.sentences[2:5]:
        sentence.text = "你不妨先核对来源，再决定怎么理解。"
    result = lint_script(draft, _angle(), _facts(), "完全不同的原始文章", speaking_rate=4.0)
    assert "FORMULAIC_REPETITION" in {issue.code for issue in result.issues}


def test_unsupported_number_and_bad_rate_fail_quality_gate() -> None:
    bad = _draft(extra="某机构预计明年增长3.6%。")
    result = lint_script(bad, _angle(), _facts(), "原文", speaking_rate=4.0)
    assert result.passed is False
    assert "UNDECLARED_FACT" in {issue.code for issue in result.issues}
    assert lint_script(_draft(), _angle(), _facts(), "原文", speaking_rate=2.0).passed is False


def test_originality_gate_excludes_traceable_verified_fact_wording() -> None:
    result = lint_script(_draft(), _angle(), _facts(), "美国2024年实际GDP增长2.8%", speaking_rate=4.0)
    assert "SOURCE_REUSE" not in {issue.code for issue in result.issues}


def test_originality_gate_still_blocks_distinctive_copy_inside_verified_fact() -> None:
    draft = _draft()
    draft.sentences[1].text = "美国2024年实际GDP增长2.8%，这串数字像一面照进普通人钱包冷暖的镜子。"
    source = "美国2024年实际GDP增长2.8%，这串数字像一面照进普通人钱包冷暖的镜子。"
    result = lint_script(draft, _angle(), _facts(), source, speaking_rate=4.0)
    assert "SOURCE_REUSE" in {issue.code for issue in result.issues}


def test_verified_fact_requires_evidence_source_and_original_url() -> None:
    facts = _facts()
    del facts["claims"][0]["evidence"][0]["original_url"]
    result = lint_script(_draft(), _angle(), facts, "完全不同的原始文章", speaking_rate=4.0)
    assert "UNSUPPORTED_FACT" in {issue.code for issue in result.issues}


def test_claim_number_match_uses_whole_values_not_substrings() -> None:
    draft = _draft()
    draft.sentences[1].text = "美国2024年实际GDP增长8%。"
    result = lint_script(draft, _angle(), _facts(), "完全不同的原始文章", speaking_rate=4.0)
    assert "UNSUPPORTED_FACT" in {issue.code for issue in result.issues}


def test_verified_fact_entities_must_be_supported_by_bound_claim() -> None:
    draft = _draft()
    draft.sentences[1].text = "IMF称中国2024年通胀率为2.8%。"
    result = lint_script(draft, _angle(), _facts(), "完全不同的原始文章", speaking_rate=4.0)
    assert "UNSUPPORTED_FACT" in {issue.code for issue in result.issues}


def test_evidence_source_must_belong_to_claim_sources() -> None:
    facts = _facts()
    facts["claims"][0]["evidence"][0]["source_id"] = "src_other"
    result = lint_script(_draft(), _angle(), facts, "完全不同的原始文章", speaking_rate=4.0)
    assert "UNSUPPORTED_FACT" in {issue.code for issue in result.issues}


def test_verified_fact_preserves_direction_sign_and_unit() -> None:
    for text in ("美国2024年实际GDP下降2.8%。", "美国2024年实际GDP增长-2.8%。",
                 "美国2024年实际GDP增长2.8个百分点。"):
        draft = _draft()
        draft.sentences[1].text = text
        result = lint_script(draft, _angle(), _facts(), "完全不同的原始文章", speaking_rate=4.0)
        assert "UNSUPPORTED_FACT" in {issue.code for issue in result.issues}


def test_unregistered_institution_country_and_metric_fail_closed() -> None:
    draft = _draft()
    draft.sentences[1].text = "美联储称加拿大就业增长2.8%。"
    result = lint_script(draft, _angle(), _facts(), "完全不同的原始文章", speaking_rate=4.0)
    assert "UNSUPPORTED_FACT" in {issue.code for issue in result.issues}


def test_currency_units_and_magnitudes_are_not_interchangeable() -> None:
    facts = _facts()
    facts["claims"][0]["claim_text"] = "金额为2.8元"
    facts["claims"][0]["evidence"][0]["evidence_text"] = "金额为2.8元"
    draft = _draft()
    draft.sentences[1].text = "金额为2.8万亿美元。"
    result = lint_script(draft, _angle(), facts, "完全不同的原始文章", speaking_rate=4.0)
    assert "UNSUPPORTED_FACT" in {issue.code for issue in result.issues}


def test_values_cannot_be_swapped_between_bound_claims() -> None:
    facts = {"claims": [
        {"claim_id": "claim_007", "claim_text": "BEA reports growth of 2.8%", "claim_type": "fact",
         "verification_status": "verified", "allowed_downstream": True, "source_ids": ["bea"],
         "evidence": [{"source_id": "bea", "original_url": "https://bea.test", "evidence_text": "BEA 2.8%", "evidence_eligible": True}]},
        {"claim_id": "claim_008", "claim_text": "World Bank reports growth of 2.7938%", "claim_type": "fact",
         "verification_status": "verified", "allowed_downstream": True, "source_ids": ["wb"],
         "evidence": [{"source_id": "wb", "original_url": "https://wb.test", "evidence_text": "World Bank 2.7938%", "evidence_eligible": True}]},
    ]}
    draft = _draft()
    draft.sentences[1].claim_ids = ["claim_007", "claim_008"]
    draft.sentences[1].text = "BEA显示增长2.7938%，世界银行显示增长2.8%。"
    result = lint_script(draft, _angle(), facts, "完全不同的原始文章", speaking_rate=4.0)
    assert "UNSUPPORTED_FACT" in {issue.code for issue in result.issues}


def test_unknown_country_metric_and_title_case_institution_fail_closed() -> None:
    for text in ("德国工资增长2.8%。", "European Central Bank said Brazil wages rose 2.8%."):
        draft = _draft()
        draft.sentences[1].text = text
        result = lint_script(draft, _angle(), _facts(), "完全不同的原始文章", speaking_rate=4.0)
        assert "UNSUPPORTED_FACT" in {issue.code for issue in result.issues}
