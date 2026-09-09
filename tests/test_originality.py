from fanglei.originality import check_fact_originality, check_originality


def test_blocks_long_unique_source_expression() -> None:
    phrase = "这是一段来自原文而且足够独特的连续表达"
    result = check_originality("开头" + phrase + "结尾", "标题\n" + phrase)
    assert result.status == "blocked"


def test_common_economic_term_does_not_block() -> None:
    assert check_originality("实际国内生产总值增长", "实际国内生产总值增长").status == "passed"


def test_verified_fact_still_blocks_long_verbatim_fact_sentence() -> None:
    fact = "World Bank: United States real GDP growth rate was 2.7938% in 2024."
    assert check_fact_originality(fact, fact).status == "blocked"


def test_verified_fact_allows_short_required_names_metrics_and_values() -> None:
    fact = "BEA称美国2024年实际GDP增长2.8%。"
    assert check_fact_originality(fact, fact).status == "passed"
