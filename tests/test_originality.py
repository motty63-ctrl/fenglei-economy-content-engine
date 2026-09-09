from fanglei.originality import check_originality


def test_blocks_long_unique_source_expression() -> None:
    phrase = "这是一段来自原文而且足够独特的连续表达"
    result = check_originality("开头" + phrase + "结尾", "标题\n" + phrase)
    assert result.status == "blocked"


def test_common_economic_term_does_not_block() -> None:
    assert check_originality("实际国内生产总值增长", "实际国内生产总值增长").status == "passed"
