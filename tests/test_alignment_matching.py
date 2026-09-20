from fanglei.alignment_matching import (
    ALIGNMENT_NORMALIZATION_VERSION,
    compare_alignment_text,
    normalize_alignment_text,
)


def test_spoken_numbers_and_acronyms_normalize_without_changing_value() -> None:
    original = "二〇二四年 G D P 增速百分之二点八。"
    assert normalize_alignment_text(original) == "2024年gdp增速2.8%"
    assert original == "二〇二四年 G D P 增速百分之二点八。"
    assert normalize_alignment_text("2024年GDP增速2.9%") != "2024年gdp增速2.8%"


def test_explicit_institution_equivalences_are_matching_only() -> None:
    pairs = [
        ("B E A", "BEA"),
        ("World Bank", "世界银行"),
        ("百分之二点八", "2.8%"),
        ("二〇二四年", "2024年"),
    ]
    for spoken, written in pairs:
        result = compare_alignment_text(written, spoken)
        assert result.matched
        assert result.cer == 0
        assert result.rule_version == ALIGNMENT_NORMALIZATION_VERSION


def test_normalization_never_guesses_different_numbers_or_years() -> None:
    assert not compare_alignment_text("2.8%", "百分之二点九").matched
    assert not compare_alignment_text("2024年", "二〇二五年").matched


def test_comparison_preserves_both_source_strings() -> None:
    reference = "World Bank 显示 2.8%。"
    recognized = "世界银行显示百分之二点八"
    result = compare_alignment_text(reference, recognized)
    assert result.reference == reference
    assert result.recognized == recognized
    assert result.normalized_ref == "世界银行显示2.8%"
    assert result.normalized_asr == "世界银行显示2.8%"


def test_sentence_period_is_removed_but_decimal_point_is_preserved() -> None:
    result = compare_alignment_text("GDP增长2.8%。", "G D P 增长百分之二点八.")
    assert result.matched
    assert result.normalized_ref == "gdp增长2.8%"
