from fanglei.narration_normalization import (
    normalize_script,
    render_narration_text,
    render_tts_text,
    validate_narration_semantics,
)


def _script():
    return {
        "script_id": "script_001",
        "sentences": [
            {
                "sentence_id": "sentence_001",
                "text": "BEA公布的2024年美国实际GDP增长率是2.8%。",
            },
            {
                "sentence_id": "sentence_002",
                "text": "世界银行API保留的数值约为2.7932%。",
            },
        ],
    }


def test_normalization_records_original_narration_and_reasons_without_numeric_change() -> None:
    document = normalize_script(_script(), "2026-09-14-001-gdp")
    first = document.sentences[0]
    assert first.original_text == _script()["sentences"][0]["text"]
    assert first.narration_text == first.original_text
    assert "B E A" in first.tts_spoken_text
    assert "二〇二四年" in first.tts_spoken_text
    assert "百分之二点八" in first.tts_spoken_text
    assert first.normalization_reason
    assert {item.source for item in first.normalizations} >= {"BEA", "2024年", "2.8%"}
    assert document.semantic_validation.passed
    assert document.semantic_validation.canonical_original_hash == document.semantic_validation.canonical_narration_hash


def test_narration_text_is_rendered_only_from_structured_sentences() -> None:
    document = normalize_script(_script(), "2026-09-14-001-gdp")
    assert render_narration_text(document) == "\n".join(
        sentence.narration_text for sentence in document.sentences
    ) + "\n"
    assert render_tts_text(document) == "\n".join(
        sentence.tts_spoken_text for sentence in document.sentences
    ) + "\n"


def test_semantic_gate_rejects_changed_percentage() -> None:
    document = normalize_script(_script(), "2026-09-14-001-gdp")
    document.sentences[0].tts_spoken_text = document.sentences[0].tts_spoken_text.replace(
        "百分之二点八", "百分之二点九"
    )
    result = validate_narration_semantics(document)
    assert not result.passed
    assert "TTS_SPOKEN_TEXT_MISMATCH" in result.issues


def test_normalization_keeps_sentence_ids_and_sentence_count() -> None:
    document = normalize_script(_script(), "2026-09-14-001-gdp")
    assert [row.sentence_id for row in document.sentences] == ["sentence_001", "sentence_002"]


def test_semantic_gate_handles_original_text_that_already_contains_spoken_abbreviation() -> None:
    script = {
        "script_id": "script_002",
        "sentences": [{"sentence_id": "sentence_001", "text": "先写B E A，再写BEA。"}],
    }
    document = normalize_script(script, "2026-09-14-002-abbreviation")
    assert document.sentences[0].narration_text == "先写B E A，再写BEA。"
    assert document.sentences[0].tts_spoken_text == "先写B E A，再写B E A。"
    assert document.semantic_validation.passed is True


def test_zh_cn_tts_uses_cardinal_number_words_and_preserves_display_text() -> None:
    script = {
        "script_id": "script_numbers",
        "sentences": [{
            "sentence_id": "sentence_001",
            "text": (
                "8月非农就业增加16.2万，时薪上涨10美分至37.75美元，"
                "工时为34.4小时，失业率是4.1%，编号claim_067，日期2026-09-27。"
            ),
        }],
    }

    document = normalize_script(script, "run", language="zh-CN")
    sentence = document.sentences[0]

    assert document.schema_version == "5.1"
    assert sentence.original_text == script["sentences"][0]["text"]
    assert sentence.narration_text == script["sentences"][0]["text"]
    assert sentence.tts_spoken_text == (
        "八月非农就业增加十六点二万，时薪上涨十美分至三十七点七五美元，"
        "工时为三十四点四小时，失业率是百分之四点一，编号claim_067，日期2026-09-27。"
    )
    assert render_narration_text(document) == sentence.narration_text + "\n"
    assert render_tts_text(document) == sentence.tts_spoken_text + "\n"
    assert {change.source for change in sentence.normalizations} >= {
        "8", "16.2", "10", "37.75", "34.4", "4.1%",
    }
    assert document.semantic_validation.passed


def test_zh_cn_tts_preserves_year_digit_reading_and_month_words() -> None:
    script = {
        "script_id": "script_dates",
        "sentences": [{"sentence_id": "sentence_001", "text": "2026年8月，6月到7月。"}],
    }
    document = normalize_script(script, "run", language="zh-CN")
    assert document.sentences[0].tts_spoken_text == "二〇二六年八月，六月到七月。"


def test_non_zh_cn_tts_text_is_not_pronunciation_normalized() -> None:
    script = {
        "script_id": "script_english",
        "sentences": [{"sentence_id": "sentence_001", "text": "The rate is 4.1%."}],
    }
    document = normalize_script(script, "run", language="en-US")
    assert document.language == "en-US"
    assert document.sentences[0].tts_spoken_text == "The rate is 4.1%."


def test_zh_hans_is_not_normalized_by_zh_cn_only_formatter() -> None:
    script = {
        "script_id": "script_hans",
        "sentences": [{"sentence_id": "sentence_001", "text": "失业率是4.1%。"}],
    }
    document = normalize_script(script, "run", language="zh-Hans")
    assert document.sentences[0].tts_spoken_text == "失业率是4.1%。"


def test_large_chinese_cardinal_has_internal_zero_and_section_tens() -> None:
    script = {
        "script_id": "script_large_number",
        "sentences": [{"sentence_id": "sentence_001", "text": "新增10010人，合计110000人。"}],
    }
    document = normalize_script(script, "run", language="zh-CN")
    assert document.sentences[0].tts_spoken_text == "新增一万零一十人，合计十一万人。"


def test_legacy_v50_narration_keeps_legacy_spoken_text_semantics() -> None:
    from fanglei.v05_models import NarrationDocument, NarrationSentence, SemanticValidation

    document = NarrationDocument(
        schema_version="5.0", run_id="run", script_id="script", language="zh-CN",
        sentences=[NarrationSentence(
            sentence_id="sentence_001", original_text="2.8%", narration_text="百分之二点八",
            normalization_reason="legacy", normalizations=[{
                "type": "percentage_pronunciation", "source": "2.8%",
                "replacement": "百分之二点八", "reason": "legacy",
            }],
        )],
        semantic_validation=SemanticValidation(
            passed=True, canonical_original_hash="", canonical_narration_hash="",
        ),
    )
    assert document.sentences[0].spoken_text == "百分之二点八"
    assert validate_narration_semantics(document).passed


def test_v2_tts_text_must_match_deterministic_normalization() -> None:
    document = normalize_script(_script(), "run")
    document.sentences[0].tts_spoken_text = "美国劳工统计局报告的数值被篡改。"
    result = validate_narration_semantics(document)
    assert not result.passed
    assert "TTS_SPOKEN_TEXT_MISMATCH" in result.issues
