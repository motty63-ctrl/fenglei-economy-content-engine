from __future__ import annotations

import pytest

from fanglei.evidence_targets import (
    EvidenceTargetSetV1,
    build_authority_claim_proposals,
    extract_targeted_evidence,
    parse_evidence_target_set,
)
from fanglei.evidence_policy import gate_evidence
from fanglei.research import FetchedDocument, RuleBasedEvidenceExtractor, evidence_claim_key


def _document(text: str, *, source_id: str = "src_001") -> FetchedDocument:
    return FetchedDocument(
        source_id=source_id,
        url=f"https://example.test/{source_id}",
        title="Synthetic release",
        text=text,
        source_type="official",
        published_at="2026-09-01",
        retrieved_at="2026-09-02T10:00:00+00:00",
        document_hash="a" * 64,
    )


def _scope(*, subject: str, measure: str, period: str, unit: str | None, statistic: str | None, certainty: str) -> dict:
    return {
        "subject": subject,
        "measure": measure,
        "period": period,
        "unit": unit,
        "statistic": statistic,
        "certainty": certainty,
    }


def _target_set(targets: list[dict]) -> dict:
    return {
        "schema_version": "evidence-targets/1.0",
        "run_id": "synthetic-run",
        "case_id": "synthetic-case",
        "targets": targets,
    }


def _target(
    *,
    target_id: str = "retail-sales",
    concept: str = "monthly retail sales",
    aliases: list[str] | None = None,
    periods: list[str] | None = None,
    source_roles: list[str] | None = None,
    evidence_kinds: list[str] | None = None,
    expected_unit_family: str | None = "percent",
    required_source_section: str | None = None,
    scope: dict | None = None,
) -> dict:
    return {
        "target_id": target_id,
        "concept": concept,
        "aliases": aliases or ["retail sales", "sales at retailers"],
        "periods": periods or ["August 2026"],
        "source_roles": source_roles or ["monthly-release"],
        "statistic": "month-over-month change",
        "expected_unit_family": expected_unit_family,
        "required_source_section": required_source_section,
        "evidence_kinds": evidence_kinds or ["narrative_sentence", "table_cell", "revision"],
        "authority_scope": scope or _scope(
            subject="retail sales",
            measure="monthly change",
            period="August 2026",
            unit="percent",
            statistic="month-over-month change",
            certainty="increased",
        ),
    }


def test_target_set_requires_explicit_identity_and_strict_target_fields() -> None:
    parsed = parse_evidence_target_set(
        _target_set([_target()]), run_id="synthetic-run", case_id="synthetic-case"
    )
    assert isinstance(parsed, EvidenceTargetSetV1)
    assert parsed.targets[0].target_id == "retail-sales"

    with pytest.raises(ValueError, match="run_id"):
        parse_evidence_target_set(_target_set([_target()]), run_id="other-run", case_id="synthetic-case")

    incomplete = _target_set([_target()])
    del incomplete["targets"][0]["expected_unit_family"]
    with pytest.raises(ValueError):
        parse_evidence_target_set(incomplete, run_id="synthetic-run", case_id="synthetic-case")

    unknown = _target_set([_target()])
    unknown["targets"][0]["guess_value"] = "2.4"
    with pytest.raises(ValueError):
        parse_evidence_target_set(unknown, run_id="synthetic-run", case_id="synthetic-case")

    duplicate_ids = _target_set([_target(), _target()])
    with pytest.raises(ValueError, match="unique"):
        EvidenceTargetSetV1.model_validate(duplicate_ids)


def test_wrapped_sentence_is_emitted_with_exact_contiguous_line_range() -> None:
    document = _document(
        "Retail sales increased by 2.4 percent in August 2026,\n"
        "the largest monthly change since the previous spring.\n"
        "\n"
        "A separate paragraph has no relevant measure."
    )
    targets = parse_evidence_target_set(
        _target_set([_target()]), run_id="synthetic-run", case_id="synthetic-case"
    )

    found = extract_targeted_evidence(
        [document], targets, document_roles={"src_001": "monthly-release"}
    )
    assert len(found) == 1
    item = found[0]
    assert item["paragraph_locator"] == "line:1-2"
    assert item["evidence_text"] == (
        "Retail sales increased by 2.4 percent in August 2026,\n"
        "the largest monthly change since the previous spring."
    )
    assert "\n".join(document.text.splitlines()[0:2]) == item["evidence_text"]
    assert item["evidence_target_id"] == "retail-sales"
    assert item["explicit_values"] == [{"value": "2.4", "unit": "percent"}]

    through_owner = RuleBasedEvidenceExtractor().extract(
        [document], [], evidence_targets=targets, document_roles={"src_001": "monthly-release"},
        target_set_sha256="b" * 64,
    )
    assert any(item.get("evidence_target_sha256") == "b" * 64 for item in through_owner)


def test_inline_sentences_get_exact_column_locator_without_neighboring_sentences() -> None:
    from fanglei.evidence_targets import resolve_text_locator

    text = (
        "Release overview. Retail sales increased by 2.4 percent in August 2026, "
        "above the prior month. A separate sentence follows."
    )
    document = _document(text)
    targets = parse_evidence_target_set(
        _target_set([_target(aliases=["retail sales increased"], periods=["August 2026"])]),
        run_id="synthetic-run", case_id="synthetic-case",
    )
    found = extract_targeted_evidence(
        [document], targets, document_roles={"src_001": "monthly-release"}
    )
    assert len(found) == 1
    item = found[0]
    assert item["evidence_text"] == "Retail sales increased by 2.4 percent in August 2026, above the prior month."
    assert item["paragraph_locator"].startswith("line:1;columns:")
    assert resolve_text_locator(text, item["paragraph_locator"]) == item["evidence_text"]


def test_source_section_context_is_explicitly_required_and_exactly_located() -> None:
    from fanglei.evidence_targets import resolve_text_locator

    text = (
        "Household Survey Data\n\n"
        "The unemployment rate was unchanged at 4.1 percent in August 2026.\n\n"
        "Establishment Survey Data\n\n"
        "Private payrolls added 100,000 jobs in August 2026."
    )
    document = _document(text)
    unemployment = _target(
        target_id="unemployment",
        aliases=["unemployment rate was unchanged"],
        required_source_section="Household Survey Data",
        periods=["August 2026"],
        expected_unit_family="percent",
        scope=_scope(
            subject="unemployment rate", measure="unemployment rate",
            period="August 2026", unit="percent", statistic=None,
            certainty="unchanged",
        ),
    )
    unemployment["statistic"] = None
    targets = parse_evidence_target_set(
        _target_set([unemployment]), run_id="synthetic-run", case_id="synthetic-case"
    )
    found = extract_targeted_evidence(
        [document], targets, document_roles={"src_001": "monthly-release"}
    )
    assert len(found) == 1
    item = found[0]
    assert item["source_section"] == "Household Survey Data"
    assert item["source_section_locator"] == "line:1"
    assert resolve_text_locator(text, item["source_section_locator"]) == item["source_section"]

    wrong_section = _target(
        target_id="unemployment-wrong-section",
        aliases=["unemployment rate was unchanged"],
        required_source_section="Establishment Survey Data",
        periods=["August 2026"],
        expected_unit_family="percent",
    )
    wrong_targets = parse_evidence_target_set(
        _target_set([wrong_section]), run_id="synthetic-run", case_id="synthetic-case"
    )
    assert extract_targeted_evidence(
        [document], wrong_targets, document_roles={"src_001": "monthly-release"}
    ) == []


def test_incomplete_sentence_does_not_stitch_across_blank_paragraph_boundary() -> None:
    document = _document(
        "Retail sales increased by 2.4 percent in August 2026,\n"
        "\n"
        "the largest monthly change since the previous spring."
    )
    targets = parse_evidence_target_set(
        _target_set([_target()]), run_id="synthetic-run", case_id="synthetic-case"
    )

    assert extract_targeted_evidence(
        [document], targets, document_roles={"src_001": "monthly-release"}
    ) == []


def test_generic_multilevel_table_binds_row_column_path_value_and_locator() -> None:
    text = "\n".join(
        [
            "Regional Economic Indicators",
            "Table 1. Retail sales index",
            "Unit: index points",
            "| Region | 2025 | 2025 | 2026 | 2026 |",
            "| Measure | Q1 | Q2 | Q1 | Q2 |",
            "| North region retail sales | 101 | 104 | 107 | 109 |",
        ]
    )
    document = _document(text)
    target = _target(
        aliases=["North region retail sales"],
        periods=["2026 Q2"],
        evidence_kinds=["table_cell"],
        scope=_scope(
            subject="North region retail sales",
            measure="retail sales index",
            period="2026 Q2",
            unit="index points",
            statistic=None,
            certainty="reported",
        ),
    )
    target["statistic"] = None
    target["expected_unit_family"] = "index points"
    targets = parse_evidence_target_set(
        _target_set([target]), run_id="synthetic-run", case_id="synthetic-case"
    )

    found = extract_targeted_evidence(
        [document], targets, document_roles={"src_001": "monthly-release"}
    )
    assert len(found) == 1
    cell = found[0]
    context = cell["table_context"]
    assert context["table_identity"] == "Table 1. Retail sales index"
    assert context["row_label"] == "North region retail sales"
    assert context["column_header_path"] == ["2026", "Q2"]
    assert context["value"] == "109"
    assert context["unit"] == "index points"
    assert context["statistic"] is None
    assert context["period"] == "2026 Q2"
    assert context["row_locator"] == "line:6"
    assert context["header_locator"] == "line:4-5"
    assert cell["evidence_text"] in document.text


def test_ambiguous_table_width_does_not_emit_structured_cell() -> None:
    text = "\n".join(
        [
            "Table 1. Regional sales",
            "| Region | 2025 | 2026 |",
            "| North retail sales | 100 | not reported |",
        ]
    )
    document = _document(text)
    target = _target(
        aliases=["North retail sales"],
        periods=["2026"],
        evidence_kinds=["table_cell"],
        scope=_scope(
            subject="North retail sales", measure="sales", period="2026",
            unit="index points", statistic="index level", certainty="reported",
        ),
    )
    target["statistic"] = "index level"
    target["expected_unit_family"] = "index points"
    targets = parse_evidence_target_set(
        _target_set([target]), run_id="synthetic-run", case_id="synthetic-case"
    )
    assert extract_targeted_evidence(
        [document], targets, document_roles={"src_001": "monthly-release"}
    ) == []


def test_generic_line_cell_table_recovers_explicit_month_columns_and_cell_locator() -> None:
    text = "\n".join(
        [
            "Table 1. City service index",
            "[In index points]",
            "Series",
            "January",
            "2025",
            "January",
            "2026",
            "East service index",
            "20",
            "23",
        ]
    )
    document = _document(text)
    target = _target(
        aliases=["East service index"],
        periods=["January 2026"],
        evidence_kinds=["table_cell"],
        scope=_scope(
            subject="East service index", measure="service index", period="January 2026",
            unit="index points", statistic=None, certainty="reported",
        ),
    )
    target["statistic"] = None
    target["expected_unit_family"] = "index points"
    targets = parse_evidence_target_set(
        _target_set([target]), run_id="synthetic-run", case_id="synthetic-case"
    )

    found = extract_targeted_evidence(
        [document], targets, document_roles={"src_001": "monthly-release"}
    )
    assert len(found) == 1
    context = found[0]["table_context"]
    assert context["table_identity"] == "Table 1. City service index"
    assert context["row_label"] == "East service index"
    assert context["period"] == "January 2026"
    assert context["column_header_path"] == ["January 2026"]
    assert context["value"] == "23"
    assert context["unit"] == "index points"
    assert context["header_locator"] == "line:4-7"
    assert context["row_locator"] == "line:8-10"


def test_revision_values_require_explicit_previous_and_revised_amounts() -> None:
    document = _document(
        "The June estimate was revised up by 11,000, from +20,000 to +31,000.\n"
        "The July estimate was revised up by 44,000."
    )
    targets = [
        _target(
            target_id="june-revision",
            concept="revision to June estimate",
            aliases=["June estimate", "revised up"],
            periods=["June"],
            evidence_kinds=["revision"],
            expected_unit_family=None,
            scope=_scope(
                subject="June estimate", measure="revision", period="June",
                unit="jobs", statistic="revision amount", certainty="revised up",
            ),
        ),
        _target(
            target_id="july-revision",
            concept="revision to July estimate",
            aliases=["July estimate", "revised up"],
            periods=["July"],
            evidence_kinds=["revision"],
            expected_unit_family=None,
            scope=_scope(
                subject="July estimate", measure="revision", period="July",
                unit="jobs", statistic="revision amount", certainty="revised up",
            ),
        ),
    ]
    parsed = parse_evidence_target_set(
        _target_set(targets), run_id="synthetic-run", case_id="synthetic-case"
    )
    found = extract_targeted_evidence(
        [document], parsed, document_roles={"src_001": "monthly-release"}
    )
    june = next(item for item in found if item["evidence_target_id"] == "june-revision")
    july = next(item for item in found if item["evidence_target_id"] == "july-revision")

    assert june["revision_values"] == {
        "previous_value": "+20,000",
        "revised_value": "+31,000",
        "revision_amount": "11,000",
        "direction": "up",
    }
    assert july["revision_values"] == {
        "previous_value": None,
        "revised_value": None,
        "revision_amount": "44,000",
        "direction": "up",
    }


def test_revision_values_bind_to_the_matching_period_clause() -> None:
    document = _document(
        "The estimate for June was revised up by 11,000, from +20,000 to +31,000, "
        "and the estimate for July was revised down by 4,000, from +40,000 to +36,000."
    )
    targets = parse_evidence_target_set(_target_set([
        _target(
            target_id="june-revision", aliases=["estimate for June"], periods=["June"],
            evidence_kinds=["revision"], expected_unit_family=None,
        ),
        _target(
            target_id="july-revision", aliases=["estimate for July"], periods=["July"],
            evidence_kinds=["revision"], expected_unit_family=None,
        ),
    ]), run_id="synthetic-run", case_id="synthetic-case")
    found = extract_targeted_evidence([document], targets, document_roles={"src_001": "monthly-release"})
    by_id = {item["evidence_target_id"]: item["revision_values"] for item in found}
    assert by_id["june-revision"] == {
        "previous_value": "+20,000", "revised_value": "+31,000",
        "revision_amount": "11,000", "direction": "up",
    }
    assert by_id["july-revision"] == {
        "previous_value": "+40,000", "revised_value": "+36,000",
        "revision_amount": "4,000", "direction": "down",
    }


def test_numeric_locator_parser_keeps_terminal_decimal_values_and_currency() -> None:
    document = _document(
        "Average hourly earnings rose to $37.75 in August 2026, a measured change of 0.3 percent."
    )
    targets = parse_evidence_target_set(_target_set([_target(
        aliases=["average hourly earnings"], periods=["August 2026"],
        evidence_kinds=["narrative_sentence"], expected_unit_family="currency",
    )]), run_id="synthetic-run", case_id="synthetic-case")
    found = extract_targeted_evidence([document], targets, document_roles={"src_001": "monthly-release"})
    assert len(found) == 1
    assert {value["value"] for value in found[0]["explicit_values"]} == {"$37.75", "0.3"}
    assert {value["unit"] for value in found[0]["explicit_values"]} == {"$", "percent"}


def test_targeted_propositions_split_two_independent_metrics_but_keep_full_evidence() -> None:
    text = "Metric A rose to 10 units in the reference period, while Metric B remained at 5 units in the reference period."
    targets = parse_evidence_target_set(_target_set([
        _target(
            target_id="metric-a", aliases=["Metric A rose"], periods=["the reference period"],
            expected_unit_family="units",
            scope=_scope(subject="Metric A", measure="units", period="the reference period", unit="units", statistic=None, certainty="rose"),
        ),
        _target(
            target_id="metric-b", aliases=["Metric B remained"], periods=["the reference period"],
            expected_unit_family="units",
            scope=_scope(subject="Metric B", measure="units", period="the reference period", unit="units", statistic=None, certainty="remained"),
        ),
    ]), run_id="synthetic-run", case_id="synthetic-case")

    found = extract_targeted_evidence(
        [_document(text)], targets, document_roles={"src_001": "monthly-release"}
    )
    by_target = {item["evidence_target_id"]: item for item in found}

    assert by_target["metric-a"]["evidence_text"] == text
    assert by_target["metric-a"]["proposition_span"]["text"] == "Metric A rose to 10 units in the reference period"
    assert by_target["metric-a"]["explicit_values"] == [{"value": "10", "unit": "units"}]
    assert by_target["metric-b"]["evidence_text"] == text
    assert by_target["metric-b"]["proposition_span"]["text"] == "Metric B remained at 5 units in the reference period."
    assert by_target["metric-b"]["explicit_values"] == [{"value": "5", "unit": "units"}]

    for item in found:
        item["evidence_eligible"] = True
    proposals = build_authority_claim_proposals(
        found, targets, institution_display_name="Synthetic Statistical Office"
    )
    proposal_texts = [candidate["claim_text"] for candidate in proposals.values()]
    assert any('"Metric A rose to 10 units in the reference period"' in value for value in proposal_texts)
    assert any('"Metric B remained at 5 units in the reference period."' in value for value in proposal_texts)
    assert all(not ("Metric A" in value and "Metric B" in value) for value in proposal_texts)


def test_targeted_revision_propositions_split_periods_and_keep_shared_evidence_span() -> None:
    text = (
        "The estimate for June was revised up by 11,000, from +20,000 to +31,000, "
        "and the estimate for July was revised down by 4,000, from +40,000 to +36,000."
    )
    targets = parse_evidence_target_set(_target_set([
        _target(
            target_id="june-revision", aliases=["estimate for June"], periods=["June"],
            evidence_kinds=["revision"], expected_unit_family=None,
            scope=_scope(subject="June estimate", measure="revision", period="June", unit="jobs", statistic="revision amount", certainty="revised up"),
        ),
        _target(
            target_id="july-revision", aliases=["estimate for July"], periods=["July"],
            evidence_kinds=["revision"], expected_unit_family=None,
            scope=_scope(subject="July estimate", measure="revision", period="July", unit="jobs", statistic="revision amount", certainty="revised down"),
        ),
    ]), run_id="synthetic-run", case_id="synthetic-case")

    found = extract_targeted_evidence(
        [_document(text)], targets, document_roles={"src_001": "monthly-release"}
    )
    by_target = {item["evidence_target_id"]: item for item in found}

    assert by_target["june-revision"]["evidence_text"] == text
    assert "July" not in by_target["june-revision"]["proposition_span"]["text"]
    assert by_target["june-revision"]["revision_values"] == {
        "previous_value": "+20,000", "revised_value": "+31,000",
        "revision_amount": "11,000", "direction": "up",
    }
    assert by_target["july-revision"]["evidence_text"] == text
    assert "June" not in by_target["july-revision"]["proposition_span"]["text"]
    assert by_target["july-revision"]["revision_values"] == {
        "previous_value": "+40,000", "revised_value": "+36,000",
        "revision_amount": "4,000", "direction": "down",
    }


def test_current_period_proposition_excludes_unattested_historical_comparison() -> None:
    text = (
        "Sector employment rose by 5,000 jobs in the current period, "
        "compared with an average gain of 1,000 jobs over the prior year."
    )
    target = _target(
        target_id="sector-employment-current", aliases=["Sector employment rose"],
        periods=["the current period"], expected_unit_family="count",
        scope=_scope(subject="Sector employment", measure="employment", period="the current period", unit="jobs", statistic=None, certainty="rose"),
    )
    targets = parse_evidence_target_set(
        _target_set([target]), run_id="synthetic-run", case_id="synthetic-case"
    )

    item = extract_targeted_evidence(
        [_document(text)], targets, document_roles={"src_001": "monthly-release"}
    )[0]

    assert item["evidence_text"] == text
    assert item["proposition_span"]["text"] == "Sector employment rose by 5,000 jobs in the current period"
    assert item["explicit_values"] == [{"value": "5,000", "unit": "jobs"}]


def test_explicit_count_unit_is_retained_in_targeted_structured_values() -> None:
    text = "Sector A added 42,000 jobs in the current period."
    targets = parse_evidence_target_set(_target_set([_target(
        target_id="sector-a-jobs", aliases=["Sector A added"], periods=["the current period"],
        expected_unit_family="count",
        scope=_scope(subject="Sector A", measure="employment", period="the current period", unit="jobs", statistic=None, certainty="added"),
    )]), run_id="synthetic-run", case_id="synthetic-case")

    item = extract_targeted_evidence(
        [_document(text)], targets, document_roles={"src_001": "monthly-release"}
    )[0]

    assert item["proposition_span"]["text"] == text
    assert item["explicit_values"] == [{"value": "42,000", "unit": "jobs"}]


def test_case_targets_are_candidates_and_do_not_bypass_exact_authority_verification_input() -> None:
    document = _document("Retail sales increased by 2.4 percent in August 2026.")
    targets = parse_evidence_target_set(
        _target_set([_target()]), run_id="synthetic-run", case_id="synthetic-case"
    )
    raw = extract_targeted_evidence(
        [document], targets, document_roles={"src_001": "monthly-release"}
    )
    assert len(raw) == 1
    assert raw[0]["claim_type"] == "fact"
    assert raw[0]["evidence_text"] == "Retail sales increased by 2.4 percent in August 2026."
    assert "verification_status" not in raw[0]

    gated = gate_evidence(raw, [document])
    proposals = build_authority_claim_proposals(
        gated, targets, institution_display_name="National Statistical Office"
    )
    assert set(proposals) == {evidence_claim_key(gated[0])}
    assert proposals[evidence_claim_key(gated[0])]["claim_text"] == (
        'National Statistical Office: "Retail sales increased by 2.4 percent in August 2026."'
    )
    assert proposals[evidence_claim_key(gated[0])]["authority_attestation"]["scope"]["period"] == "August 2026"
