from tests.test_script_quality import _angle, _draft, _facts
from fanglei.script_lint import lint_script


def _codes(text: str, sentence_type: str = "explanation", claim_ids=None) -> set[str]:
    draft = _draft()
    draft.sentences[2].text = text
    draft.sentences[2].sentence_type = sentence_type
    draft.sentences[2].claim_ids = claim_ids or []
    return {item.code for item in lint_script(
        draft, _angle(), _facts(), "完全不同的原始文章", speaking_rate=4.0
    ).issues if item.sentence_id == "sentence_003"}


def _has_semantic(codes: set[str]) -> bool:
    return any(code.startswith("SEMANTIC_FACTUALITY_UNSUPPORTED") for code in codes)


def test_provider_label_cannot_hide_numeric_or_institution_fact() -> None:
    assert _has_semantic(_codes("世界银行数据显示，2024年增长率是2.8%。", "interpretation"))


def test_data_methodology_causality_and_usual_behavior_require_claims() -> None:
    examples = (
        "这两个结果采用不同的数据口径。",
        "保留更多小数会导致结论更准确。",
        "不必纠结，因为统计误差可能更大。",
        "媒体通常会把数字四舍五入后发布。",
    )
    for text in examples:
        assert _has_semantic(_codes(text))


def test_explicit_analogy_or_personal_interpretation_is_not_external_fact() -> None:
    assert not _has_semantic(_codes("打个比方，这像用两把刻度不同的尺子。", "analogy"))
    assert not _has_semantic(_codes("我更愿意把它看成显示精度问题。", "interpretation"))


def test_semantic_fact_may_bind_supported_claim_even_when_labeled_explanation() -> None:
    assert not _has_semantic(_codes(
        "美国2024年实际GDP增长2.8%。", "explanation", ["claim_007"]
    ))


def test_rounding_methodology_requires_a_claim() -> None:
    assert _has_semantic(_codes(
        "BEA把这个数四舍五入到一位小数。", "explanation"
    ))


def test_explicit_reader_advice_about_checks_is_not_an_external_fact() -> None:
    assert not _has_semantic(_codes(
        "下次看到两个结果，建议先看统计口径，再核对显示精度。", "interpretation"
    ))
    assert not _has_semantic(_codes(
        "我的判断是，先看口径，再决定两个结果能不能比较。", "interpretation"
    ))
    assert not _has_semantic(_codes(
        "你可以先看统计口径，再把显示精度放到第二步。", "interpretation"
    ))


def test_reader_advice_prefix_cannot_hide_a_methodology_assertion() -> None:
    assert _has_semantic(_codes(
        "你可以核对一下，原始数据其实还带着更多小数位。", "interpretation"
    ))


def test_personal_opinion_does_not_excuse_named_institution_or_number() -> None:
    assert _has_semantic(_codes(
        "我的判断是，BEA把结果四舍五入到2.8%。", "interpretation"
    ))


def test_institution_storing_or_providing_data_is_an_external_fact() -> None:
    assert _has_semantic(_codes(
        "世界银行数据库里存着更精确的数字。", "explanation"
    ))
    assert _has_semantic(_codes(
        "你不妨去世界银行官网查原始数值。", "interpretation"
    ))


def test_subject_habit_wording_is_an_external_fact_even_in_a_question() -> None:
    assert _has_semantic(_codes(
        "媒体常用的数字总让你放心吗？", "interpretation"
    ))
    assert _has_semantic(_codes(
        "媒体里的数字是不是常被简写？", "interpretation"
    ))


def test_quantified_analogy_cannot_introduce_a_new_magnitude() -> None:
    assert _has_semantic(_codes(
        "打个比方，就像把一杯水倒掉一半再给你看。", "analogy"
    ))
