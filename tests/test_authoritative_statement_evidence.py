from __future__ import annotations

from pathlib import Path

from fanglei.artifacts import sha256_text
from fanglei.research import FetchedDocument, extract_qualitative_primary_evidence


def test_qualitative_authority_evidence_keeps_exact_lines_and_requires_explicit_source_set() -> None:
    text = "Header\nEconomic activity is expanding at a solid pace.\nInflation remains elevated.\nA policy action followed."
    document = FetchedDocument(
        source_id="src_003", url="https://example.test/statement", title="Statement", text=text,
        source_type="official", published_at="2026-09-16", retrieved_at="2026-09-25T10:00:00+08:00",
        original_url="https://example.test/statement", document_hash=sha256_text(text),
    )

    rows = extract_qualitative_primary_evidence([document], approved_source_ids={"src_003"})

    assert [(row["evidence_text"], row["paragraph_locator"]) for row in rows] == [
        ("Economic activity is expanding at a solid pace.", "line:2"),
        ("Inflation remains elevated.", "line:3"),
    ]
    assert all(row["source_id"] == "src_003" for row in rows)
    assert all(row["claim_type"] == "fact" and row["claim_key"] is None for row in rows)
    assert extract_qualitative_primary_evidence([document], approved_source_ids=set()) == []
