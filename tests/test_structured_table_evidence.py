from __future__ import annotations

from fanglei.research import FetchedDocument, RuleBasedEvidenceExtractor


def _document(source_id: str, title: str, table: str) -> FetchedDocument:
    text = f"{title}\n{table}"
    return FetchedDocument(
        source_id=source_id,
        url=f"https://example.gov/{source_id}",
        title=title,
        text=text,
        source_type="official",
        published_at="2026-09-16",
        retrieved_at="2026-09-24T23:00:00+08:00",
        original_url=None,
        document_hash=None,
    )


def _table() -> str:
    return "\n".join(
        [
            "Percent",
            "Variable",
            "Median1",
            "Range2",
            "2026",
            "2027",
            "2026",
            "2027",
            "Real GDP growth",
            "2.2",
            "2.5",
            "2.0-2.4",
            "2.2-2.8",
        ]
    )


def test_extractor_binds_multilevel_table_row_statistic_period_value_and_unit() -> None:
    document = _document(
        "src_a",
        "Table 1. Economic projections for September 2026",
        _table(),
    )

    evidence = RuleBasedEvidenceExtractor().extract([document], ["What changed?"])
    cells = [item for item in evidence if item.get("table_context")]
    median_2026 = next(
        item
        for item in cells
        if item["table_context"]["row_label"] == "Real GDP growth"
        and item["table_context"]["statistic"] == "Median"
        and item["table_context"]["period"] == "2026"
    )

    assert median_2026["evidence_text"] == "Real GDP growth\n2.2"
    assert median_2026["table_context"]["value"] == "2.2"
    assert median_2026["table_context"]["unit"] == "Percent"
    assert median_2026["table_context"]["header_excerpt"] in document.text
    assert median_2026["evidence_text"] in document.text
    assert median_2026["paragraph_locator"].startswith("line:")


def test_table_claim_key_matches_same_semantic_table_across_release_dates() -> None:
    june = _document(
        "src_june",
        "Table 1. Economic projections for June 2026",
        _table(),
    )
    september = _document(
        "src_september",
        "Table 1. Economic projections for September 2026",
        _table().replace("2.2\n2.5", "2.3\n2.6", 1),
    )

    evidence = RuleBasedEvidenceExtractor().extract([june, september], ["What changed?"])
    selected = [
        item
        for item in evidence
        if item.get("table_context", {}).get("row_label") == "Real GDP growth"
        and item.get("table_context", {}).get("statistic") == "Median"
        and item.get("table_context", {}).get("period") == "2026"
    ]

    assert len(selected) == 2
    assert selected[0]["claim_key"] == selected[1]["claim_key"]
    assert {item["table_context"]["value"] for item in selected} == {"2.2", "2.3"}
    assert {item["source_id"] for item in selected} == {"src_june", "src_september"}


def test_malformed_multilevel_header_fails_closed() -> None:
    malformed = _table().replace(
        "2026\n2027\n2026\n2027",
        "2026\n2027\n2026\n2028",
        1,
    )
    document = _document("src_bad", "Table 2. Economic projections", malformed)

    evidence = RuleBasedEvidenceExtractor().extract([document], ["What changed?"])

    assert not [item for item in evidence if item.get("table_context")]


def test_unrelated_numeric_table_does_not_become_authority_table_evidence() -> None:
    document = _document(
        "src_unrelated",
        "Table 4. Contacts by year",
        "Year\n2026\n2027\nGDP contacts\n2.2\n2.5",
    )

    evidence = RuleBasedEvidenceExtractor().extract([document], ["What changed?"])

    assert not [item for item in evidence if item.get("table_context")]


def test_structured_table_support_does_not_change_paragraph_evidence() -> None:
    document = _document(
        "src_paragraph",
        "A report",
        "Real GDP increased 2.2 percent in 2026.",
    )

    evidence = RuleBasedEvidenceExtractor().extract([document], ["GDP in 2026?"])

    assert len(evidence) == 1
    assert evidence[0]["evidence_text"] == "Real GDP increased 2.2 percent in 2026."
    assert "table_context" not in evidence[0]
