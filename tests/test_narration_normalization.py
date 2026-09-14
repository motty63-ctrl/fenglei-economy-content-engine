from fanglei.narration_normalization import (
    normalize_script,
    render_narration_text,
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
    assert "B E A" in first.narration_text
    assert "二〇二四年" in first.narration_text
    assert "百分之二点八" in first.narration_text
    assert first.normalization_reason
    assert {item.source for item in first.normalizations} >= {"BEA", "2024年", "2.8%"}
    assert document.semantic_validation.passed
    assert document.semantic_validation.canonical_original_hash == document.semantic_validation.canonical_narration_hash


def test_narration_text_is_rendered_only_from_structured_sentences() -> None:
    document = normalize_script(_script(), "2026-09-14-001-gdp")
    assert render_narration_text(document) == "\n".join(
        sentence.narration_text for sentence in document.sentences
    ) + "\n"


def test_semantic_gate_rejects_changed_percentage() -> None:
    document = normalize_script(_script(), "2026-09-14-001-gdp")
    document.sentences[0].narration_text = document.sentences[0].narration_text.replace(
        "百分之二点八", "百分之二点九"
    )
    result = validate_narration_semantics(document)
    assert not result.passed
    assert "NARRATION_SEMANTIC_CHANGE" in result.issues


def test_normalization_keeps_sentence_ids_and_sentence_count() -> None:
    document = normalize_script(_script(), "2026-09-14-001-gdp")
    assert [row.sentence_id for row in document.sentences] == ["sentence_001", "sentence_002"]


def test_semantic_gate_handles_original_text_that_already_contains_spoken_abbreviation() -> None:
    script = {
        "script_id": "script_002",
        "sentences": [{"sentence_id": "sentence_001", "text": "先写B E A，再写BEA。"}],
    }
    document = normalize_script(script, "2026-09-14-002-abbreviation")
    assert document.sentences[0].narration_text == "先写B E A，再写B E A。"
    assert document.semantic_validation.passed is True
