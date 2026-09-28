from importlib import import_module
from importlib.util import find_spec

import pytest


def _api(name: str):
    assert find_spec("fanglei.script_terminology") is not None, "versioned terminology module is missing"
    module = import_module("fanglei.script_terminology")
    assert hasattr(module, name), f"script terminology API {name} is missing"
    return getattr(module, name)


def test_versioned_script_terminology_contract_module_exists() -> None:
    assert find_spec("fanglei.script_terminology") is not None


def _claim(claim_id: str = "claim_alpha", *, subject: str = "Metric Alpha") -> dict:
    from fanglei.evidence_targets import atomic_proposition_spans

    excerpt = f"{subject} increased by 10 units in August."
    span = atomic_proposition_spans(excerpt)[0]
    scope = {
        "subject": subject,
        "measure": subject,
        "period": "August",
        "unit": "units",
        "statistic": None,
        "certainty": "increased",
        "reporting_scope": "Retail Survey",
    }
    return {
        "claim_id": claim_id,
        "claim_text": f'Data Office reports: "{excerpt}"',
        "claim_type": "fact",
        "verification_status": "verified",
        "verification_basis": "authoritative_primary_attestation",
        "allowed_downstream": True,
        "source_ids": ["src_alpha"],
        "authority_attestation": {
            "kind": "document_report",
            "source_ids": ["src_alpha"],
            "attribution": "Data Office reports",
            "scope": scope,
        },
        "evidence": [{
            "evidence_eligible": True,
            "evidence_text": excerpt,
            "proposition_span": span,
            "evidence_kind": "narrative_sentence",
            "authority_scope_candidate": scope,
            "source_id": "src_alpha",
            "document_hash": "a" * 64,
            "paragraph_locator": "line:4",
            "original_url": "https://example.test/alpha",
            "source_section": "Retail Survey",
            "explicit_values": [{"value": "10", "unit": "units"}],
            "evidence_period_matches": ["August"],
        }],
    }


def _facts() -> dict:
    return {"schema_version": "2.2", "claims": [_claim()]}


def _angle(claim_ids: list[str] | None = None):
    from fanglei.content_models import AngleCandidate

    ids = claim_ids or ["claim_alpha"]
    return AngleCandidate(
        angle_id="angle_synthetic", title="Synthetic comparison", hook="Read the record",
        core_question="What changed?", core_insight="Compare the recorded measures",
        supporting_claim_ids=ids, audience_relevance=3, novelty=3, hook_strength=3,
        visual_potential=3, explainability=3, evidence_strength=3, controversy_risk=0,
        total_score=60, eligibility="eligible",
    )


def _draft(fact_text: str, claim_ids: list[str] | None = None, **sentence_fields):
    from fanglei.content_models import ScriptDraft, ScriptSentence

    factual_fields = {"sentence_id": "sentence_fact", "section": "phenomenon",
                      "sentence_type": "verified_fact", "text": fact_text,
                      "claim_ids": claim_ids or ["claim_alpha"], **sentence_fields}
    opening = [
        ScriptSentence(sentence_id="sentence_hook", section="hook", sentence_type="interpretation",
                       text="先看这份记录。"),
        ScriptSentence(**factual_fields),
        ScriptSentence(sentence_id="sentence_mechanism", section="mechanism", sentence_type="explanation",
                       text="再把对象和时间放在一起核对。"),
    ]
    filler = [
        "表达之前先把对象和范围分开来看，再决定哪些内容需要并列呈现。",
        "不同问题可以先分别核对，避免把相邻的信息误当成同一件事。",
        "每一段都应围绕当前的问题展开，保留清楚的阅读顺序。",
        "如果两个概念边界不同，就应在表述中继续区分。",
        "先说明材料讨论的对象，再进入具体内容的比较。",
        "把表达层次安排清楚，才能看出每个部分各自回答什么。",
        "阅读时保留这些界限，有助于避免混淆不同问题。",
        "结尾回到问题本身，不额外扩展为更大的判断。",
    ]
    middle = [ScriptSentence(sentence_id=f"sentence_padding_{index:02}", section="mechanism",
                             sentence_type="explanation", text=text)
              for index, text in enumerate(filler, start=1)]
    return ScriptDraft(angle_id="angle_synthetic", title="Synthetic", sentences=[
        *opening,
        *middle,
        ScriptSentence(sentence_id="sentence_close", section="core_judgment", sentence_type="interpretation",
                       text="结论是，记录中的对象和变化应放在同一范围理解。"),
    ])


def _lint(draft, facts=None, terminology_map=None, **kwargs):
    from fanglei.script_lint import lint_script

    options = {
        "terminology_map": terminology_map,
        "current_facts_sha256": "b" * 64,
        "run_id": "synthetic-run-001",
        "case_id": "synthetic-retail-case",
        "target_language": "zh-Hans",
    }
    options.update(kwargs)
    speaking_rate = options.pop("speaking_rate", 4.0)
    return lint_script(
        draft, _angle(), facts or _facts(), "Synthetic unrelated source", speaking_rate=speaking_rate,
        **options,
    )


def _entry(role: str, field: str, source: str, target: str, suffix: str | None = None) -> dict:
    return {
        "entry_id": f"entry_{role}_{suffix or field.rsplit('.', 1)[-1]}",
        "claim_ids": ["claim_alpha"],
        "source_term": source,
        "source_field": field,
        "semantic_role": role,
        "proposed_target_terms": [target],
        "approved_target_terms": [target],
        "review_status": "approved",
    }


def _approved_map(**overrides) -> dict:
    payload = {
        "schema_version": "script-terminology-map/1.0",
        "case_id": "synthetic-retail-case",
        "run_id": "synthetic-run-001",
        "facts_sha256": "b" * 64,
        "source_language": "en",
        "target_language": "zh-Hans",
        "review_status": "approved",
        "reviewer": "reviewer-1",
        "reviewed_at": "2026-09-28T10:00:00+08:00",
        "entries": [
            _entry("subject", "authority_attestation.scope.subject", "Metric Alpha", "甲指标"),
            _entry("metric", "authority_attestation.scope.measure", "Metric Alpha", "甲指标"),
            _entry("period", "authority_attestation.scope.period", "August", "8月"),
            _entry("unit", "authority_attestation.scope.unit", "units", "单位"),
            _entry("unit", "evidence.explicit_values.unit", "units", "单位", "explicit"),
            _entry("direction", "authority_attestation.scope.certainty", "increased", "增加"),
            _entry("reporting_scope", "evidence.source_section", "Retail Survey", "零售调查"),
            _entry("source_attribution", "authority_attestation.attribution", "Data Office reports", "数据署报告"),
        ],
    }
    payload.update(overrides)
    return payload


def test_pending_terminology_proposal_is_never_accepted_as_trusted() -> None:
    model = _api("ScriptTerminologyMapV1")
    validate = _api("validate_script_terminology_map")
    pending = _approved_map(
        review_status="pending", reviewer=None, reviewed_at=None,
        entries=[{**row, "review_status": "pending", "approved_target_terms": []}
                 for row in _approved_map()["entries"]],
    )
    parsed = model.model_validate(pending)
    assert parsed.review_status == "pending"
    with pytest.raises(ValueError, match="APPROVAL_REQUIRED"):
        validate(pending, _facts(), expected_run_id="synthetic-run-001",
                 expected_case_id="synthetic-retail-case", facts_sha256="b" * 64)


def test_approved_map_is_bound_to_run_case_and_exact_facts_hash() -> None:
    validate = _api("validate_script_terminology_map")
    valid = validate(_approved_map(), _facts(), expected_run_id="synthetic-run-001",
                     expected_case_id="synthetic-retail-case", facts_sha256="b" * 64)
    assert valid.review_status == "approved"
    for field, value, expected in (
        ("facts_sha256", "c" * 64, "b" * 64),
        ("run_id", "other-run", "synthetic-run-001"),
        ("case_id", "other-case", "synthetic-retail-case"),
    ):
        kwargs = {field: value}
        with pytest.raises(ValueError, match="IDENTITY_OR_FACTS_HASH_MISMATCH"):
            validate(_approved_map(**kwargs), _facts(), expected_run_id=expected,
                     expected_case_id="synthetic-retail-case", facts_sha256="b" * 64)


def test_approved_term_must_be_bound_to_the_exact_claim_field() -> None:
    validate = _api("validate_script_terminology_map")
    foreign_entry = _entry("subject", "authority_attestation.scope.subject", "Other Metric", "甲指标")
    payload = _approved_map(entries=[foreign_entry])
    with pytest.raises(ValueError, match="SOURCE_TERM_NOT_IN_BOUND_CLAIM"):
        validate(payload, _facts(), expected_run_id="synthetic-run-001",
                 expected_case_id="synthetic-retail-case", facts_sha256="b" * 64)


def test_model_proposed_alias_is_not_promoted_to_approved_alias() -> None:
    model = _api("ScriptTerminologyMapV1")
    validate = _api("validate_script_terminology_map")
    pending = _approved_map(
        review_status="pending", reviewer=None, reviewed_at=None,
        entries=[{**row, "approved_target_terms": [], "review_status": "pending"}
                 for row in _approved_map()["entries"]],
    )
    parsed = model.model_validate(pending)
    assert parsed.entries[0].proposed_target_terms == ["甲指标"]
    assert parsed.entries[0].approved_target_terms == []
    with pytest.raises(ValueError, match="APPROVAL_REQUIRED"):
        validate(parsed.model_dump(mode="json"), _facts(), expected_run_id="synthetic-run-001",
                 expected_case_id="synthetic-retail-case", facts_sha256="b" * 64)


def test_proposal_builder_is_deterministic_and_scoped_to_selected_claims() -> None:
    build = _api("build_script_terminology_proposal")
    kwargs = dict(
        facts=_facts(), run_id="synthetic-run-001", case_id="synthetic-retail-case",
        facts_sha256="b" * 64, selected_claim_ids=["claim_alpha"], source_language="en",
        target_language="zh-Hans",
        proposed_terms={
            ("subject", "authority_attestation.scope.subject", "Metric Alpha"): ["甲指标"],
        },
    )
    left = build(**kwargs)
    right = build(**kwargs)
    assert left.model_dump(mode="json") == right.model_dump(mode="json")
    assert left.review_status == "pending"
    assert left.reviewer is None and left.reviewed_at is None
    assert all(row.review_status == "pending" and not row.approved_target_terms for row in left.entries)
    assert all(row.claim_ids == ["claim_alpha"] for row in left.entries)


def test_proposal_builder_limits_rows_to_claim_scope_terms_needed_by_validator() -> None:
    proposal = _api("build_script_terminology_proposal")(
        facts=_facts(), run_id="synthetic-run-001", case_id="synthetic-retail-case",
        facts_sha256="b" * 64, selected_claim_ids=["claim_alpha"],
        source_language="en", target_language="zh-Hans",
    )
    assert all(entry.semantic_role != "industry_category" for entry in proposal.entries)
    assert all(entry.source_field != "evidence.evidence_target_concept" for entry in proposal.entries)
    assert {entry.semantic_role for entry in proposal.entries} >= {
        "subject", "metric", "reporting_scope", "unit", "period", "direction",
        "source_attribution",
    }


def test_terminology_artifact_is_opt_in_and_hash_depends_on_facts() -> None:
    from fanglei.artifact_registry import ArtifactRegistry
    from fanglei.models import RunManifest

    run_dir = __import__("pathlib").Path(".")
    manifest = RunManifest(run_id="test-run", created_at="2026-09-28T00:00:00+00:00",
                           updated_at="2026-09-28T00:00:00+00:00")
    legacy = ArtifactRegistry(run_dir, manifest.model_copy(deep=True))
    assert "script_terminology.json" not in legacy.graph

    enabled = ArtifactRegistry(run_dir, manifest.model_copy(deep=True), script_terminology_mode=True)
    assert enabled.graph["script_terminology.json"] == (
        "script_terminology_review", ("facts.json",)
    )
    assert "script_terminology.json" in enabled.graph["script.json"][1]


def test_registered_terminology_map_becomes_stale_when_facts_change(tmp_path) -> None:
    from fanglei.artifact_registry import ArtifactRegistry
    from fanglei.models import RunManifest

    run_dir = tmp_path / "synthetic-run-001"
    run_dir.mkdir()
    manifest = RunManifest(
        run_id=run_dir.name, created_at="2026-09-28T00:00:00+00:00",
        updated_at="2026-09-28T00:00:00+00:00",
    )
    registry = ArtifactRegistry(run_dir, manifest, script_terminology_mode=True)
    registry.write_text("source.md", "Synthetic source text.", "ingest")
    registry.write_json("questions.json", {"core_topic": "Synthetic metric"}, "analyze")
    registry.write_json("search_results.json", {"results": []}, "search")
    registry.write_json("source_documents/index.json", {"documents": []}, "source_fetch")
    registry.write_json("sources.json", {"schema_version": "2.0", "sources": []}, "source_selection")
    registry.write_json("facts.json", _facts(), "factcheck")
    registry.write_json("script_terminology.json", _approved_map(), "script_terminology_review")
    registry.validate("script_terminology.json")

    changed = _facts()
    changed["claims"][0]["claim_text"] += " Updated exact fact binding."
    registry.write_json("facts.json", changed, "factcheck", force=True)

    assert registry.manifest.artifacts["script_terminology.json"].status == "stale"
    with pytest.raises(Exception, match="stale"):
        registry.validate("script_terminology.json")


def test_versioned_map_json_schema_accepts_valid_contract() -> None:
    import json
    from pathlib import Path

    import jsonschema

    schema_path = Path(__file__).parents[1] / "docs" / "v0.3" / "script-terminology-map.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.validate(_approved_map(), schema)


def test_cross_language_fact_accepts_approved_scoped_terms_and_exact_value() -> None:
    draft = _draft("数据署报告，8月零售调查的甲指标增加了10单位。",
                   attribution_context_id="ctx_alpha")
    result = _lint(draft, terminology_map=_approved_map())
    codes = {issue.code for issue in result.issues}
    assert "SCRIPT_TERMINOLOGY_INVALID" not in codes
    assert "TERMINOLOGY_TERM_MISSING" not in codes
    assert "UNSUPPORTED_NUMERIC_VALUE" not in codes
    assert "AUTHORITY_ATTRIBUTION_MISSING" not in codes


def test_cross_language_claim_without_approved_terminology_fails_closed() -> None:
    result = _lint(_draft("数据署报告，8月甲指标增加了10单位。"))
    assert "SCRIPT_TERMINOLOGY_REVIEW_REQUIRED" in {issue.code for issue in result.issues}


def test_unapproved_model_alias_does_not_satisfy_cross_language_validation() -> None:
    pending = _approved_map(
        review_status="pending", reviewer=None, reviewed_at=None,
        entries=[{**row, "review_status": "pending", "approved_target_terms": []}
                 for row in _approved_map()["entries"]],
    )
    result = _lint(_draft("数据署报告，8月甲指标增加了10单位。"), terminology_map=pending)
    assert "SCRIPT_TERMINOLOGY_REVIEW_REQUIRED" in {issue.code for issue in result.issues}


def test_approved_alias_from_another_claim_does_not_authorize_metric() -> None:
    result = _lint(_draft("数据署报告，8月乙指标增加了10单位。"), terminology_map=_approved_map())
    assert "TERMINOLOGY_TERM_MISSING" in {issue.code for issue in result.issues}


def test_changed_facts_hash_invalidates_terminology_map() -> None:
    result = _lint(_draft("数据署报告，8月甲指标增加了10单位。"),
                   terminology_map=_approved_map(), current_facts_sha256="c" * 64)
    assert "SCRIPT_TERMINOLOGY_REVIEW_REQUIRED" in {issue.code for issue in result.issues}


def test_supported_exact_number_does_not_authorize_an_unsupported_number() -> None:
    result = _lint(_draft("数据署报告，8月甲指标增加了11单位。"), terminology_map=_approved_map())
    assert "UNSUPPORTED_NUMERIC_VALUE" in {issue.code for issue in result.issues}


def test_exact_chinese_magnitude_normalization_preserves_numeric_meaning() -> None:
    claim = _claim()
    claim["evidence"][0]["explicit_values"] = [{"value": "162,000", "unit": None}]
    claim["evidence"][0]["evidence_text"] = "Metric Alpha increased by 162,000 in August."
    claim["evidence"][0]["proposition_span"] = {
        "start": 0, "end": len(claim["evidence"][0]["evidence_text"]),
        "text": claim["evidence"][0]["evidence_text"],
    }
    result = _lint(
        _draft("数据署报告，8月甲指标增加了16.2万。"),
        facts={"claims": [claim]}, terminology_map=_approved_map(
            entries=[row for row in _approved_map()["entries"] if row["semantic_role"] != "unit"]
        ),
    )
    assert "UNSUPPORTED_NUMERIC_VALUE" not in {issue.code for issue in result.issues}


@pytest.mark.parametrize(
    ("value", "unit", "alias", "spoken"),
    [("4.1", "percent", "%", "4.1%"),
     ("0.1", "hour", "小时", "0.1小时")],
)
def test_exact_percent_and_hour_unit_renderings_pass(value, unit, alias, spoken) -> None:
    from fanglei.script_lint import _cross_language_claim_issues
    from fanglei.script_terminology import ScriptTerminologyMapV1

    claim = _claim()
    scope = claim["authority_attestation"]["scope"]
    scope["unit"] = unit
    claim["evidence"][0]["authority_scope_candidate"] = dict(scope)
    claim["evidence"][0]["explicit_values"] = [{"value": value, "unit": unit}]
    map_rows = []
    for row in _approved_map()["entries"]:
        copy = dict(row)
        if copy["semantic_role"] == "unit":
            copy["source_term"] = unit
            copy["proposed_target_terms"] = [alias]
            copy["approved_target_terms"] = [alias]
        map_rows.append(copy)
    terminology = ScriptTerminologyMapV1.model_validate(_approved_map(entries=map_rows))
    issues = _cross_language_claim_issues(
        f"数据署报告，8月零售调查的甲指标增加{spoken}。", claim, terminology,
    )
    assert "UNSUPPORTED_NUMERIC_VALUE" not in issues
    assert "UNIT_SCOPE_MISMATCH" not in issues


def test_revision_numbers_require_their_structured_roles() -> None:
    from fanglei.evidence_targets import atomic_proposition_spans
    from fanglei.script_lint import _cross_language_claim_issues
    from fanglei.script_terminology import ScriptTerminologyMapV1

    claim = _claim()
    excerpt = "June nonfarm payroll employment was revised up by 11,000 from +20,000 to +31,000."
    claim["claim_text"] = f'Data Office reports: "{excerpt}"'
    scope = claim["authority_attestation"]["scope"]
    scope.update(subject="June", measure="change", period="June", unit=None, certainty="revised up")
    evidence = claim["evidence"][0]
    evidence.update(
        evidence_text=excerpt,
        proposition_span=atomic_proposition_spans(excerpt)[0],
        authority_scope_candidate=dict(scope),
        explicit_values=[
            {"value": "11,000", "unit": None},
            {"value": "+20,000", "unit": None},
            {"value": "+31,000", "unit": None},
        ],
        revision_values={
            "previous_value": "+20,000", "revised_value": "+31,000",
            "revision_amount": "11,000", "direction": "up",
        },
    )
    entries = []
    for row in _approved_map()["entries"]:
        if row["semantic_role"] == "unit":
            continue
        copy = dict(row)
        source_field = copy["source_field"]
        terms = {
            "authority_attestation.scope.subject": ("June", "6月"),
            "authority_attestation.scope.measure": ("change", "变动"),
            "authority_attestation.scope.period": ("June", "6月"),
            "authority_attestation.scope.certainty": ("revised up", "上调"),
            "evidence.source_section": ("Retail Survey", "零售调查"),
        }
        if source_field in terms:
            copy["source_term"], target = terms[source_field]
            copy["proposed_target_terms"] = [target]
            copy["approved_target_terms"] = [target]
        entries.append(copy)
    for role, source_field, source_term, alias in (
        ("revision_previous", "evidence.revision_values.previous_value", "+20,000", "此前估值"),
        ("revision_revised", "evidence.revision_values.revised_value", "+31,000", "修订后估值"),
        ("revision_delta", "evidence.revision_values.revision_amount", "11,000", "修订幅度"),
        ("direction", "evidence.revision_values.direction", "up", "上调"),
    ):
        entries.append(_entry(role, source_field, source_term, alias))
    terminology = ScriptTerminologyMapV1.model_validate(_approved_map(entries=entries))
    valid = "数据署报告：6月零售调查，此前估值+20,000，修订后估值+31,000，修订幅度11,000，上调。"
    invalid = "数据署报告：6月零售调查，修订后估值+20,000，此前估值+31,000，修订幅度11,000，上调。"
    assert "REVISION_ROLE_MISMATCH" not in _cross_language_claim_issues(valid, claim, terminology)
    assert "REVISION_ROLE_MISMATCH" in _cross_language_claim_issues(invalid, claim, terminology)


def _beta_claim(*, different_source: bool = False) -> dict:
    claim = _claim("claim_beta", subject="Metric Beta")
    claim["authority_attestation"]["scope"]["reporting_scope"] = "Employment Survey"
    evidence = claim["evidence"][0]
    evidence["authority_scope_candidate"] = dict(claim["authority_attestation"]["scope"])
    evidence["source_section"] = "Employment Survey"
    evidence["evidence_target_id"] = "beta-target"
    evidence["evidence_target_concept"] = "August Metric Beta change"
    if different_source:
        claim["source_ids"] = ["src_beta"]
        claim["authority_attestation"]["source_ids"] = ["src_beta"]
        claim["authority_attestation"]["attribution"] = "Second Office reports"
        evidence["source_id"] = "src_beta"
        evidence["original_url"] = "https://example.test/beta"
    return claim


def _map_with_beta(beta: dict, *, target_alias: str = "乙指标") -> dict:
    payload = _approved_map()
    beta_entries = []
    replacements = {
        "subject": ("Metric Beta", target_alias),
        "metric": ("Metric Beta", target_alias),
        "reporting_scope": ("Employment Survey", "就业调查"),
        "source_attribution": (
            beta["authority_attestation"]["attribution"],
            "第二数据署报告" if beta["authority_attestation"]["attribution"] == "Second Office reports" else "数据署报告",
        ),
    }
    for row in payload["entries"]:
        copy = dict(row)
        copy["entry_id"] += "_beta"
        copy["claim_ids"] = ["claim_beta"]
        if copy["semantic_role"] in replacements:
            copy["source_term"], alias = replacements[copy["semantic_role"]]
            copy["proposed_target_terms"] = [alias]
            copy["approved_target_terms"] = [alias]
        beta_entries.append(copy)
    payload["entries"] = [*payload["entries"], *beta_entries]
    return payload


def test_approved_aliases_are_explicit_and_scope_bound() -> None:
    entries = _approved_map()["entries"]
    for entry in entries:
        if entry["semantic_role"] in {"subject", "metric"}:
            entry["approved_target_terms"].append("甲指数")
            entry["proposed_target_terms"].append("甲指数")
    result = _lint(_draft("数据署报告，8月零售调查的甲指数增加了10单位。"),
                   terminology_map=_approved_map(entries=entries))
    assert "TERMINOLOGY_TERM_MISSING" not in {issue.code for issue in result.issues}


def test_alias_approved_for_another_claim_cannot_authorize_bound_metric() -> None:
    beta = _beta_claim()
    result = _lint(_draft("数据署报告，8月零售调查的乙指标增加了10单位。"),
                   facts={"claims": [_claim(), beta]}, terminology_map=_approved_map())
    assert "TERMINOLOGY_TERM_MISSING" in {issue.code for issue in result.issues}


def test_exact_numeric_traceability_rejects_rounding_and_chinese_numerals() -> None:
    claim = _claim()
    evidence = claim["evidence"][0]
    evidence["explicit_values"] = [{"value": "162,000", "unit": None}]
    evidence["evidence_text"] = "Metric Alpha increased by 162,000 in August."
    evidence["proposition_span"] = {
        "start": 0, "end": len(evidence["evidence_text"]), "text": evidence["evidence_text"],
    }
    map_without_unit = _approved_map(entries=[
        row for row in _approved_map()["entries"] if row["semantic_role"] != "unit"
    ])
    rounded = _lint(_draft("数据署报告，8月零售调查的甲指标增加了16万。"),
                    facts={"claims": [claim]}, terminology_map=map_without_unit)
    assert "UNSUPPORTED_NUMERIC_VALUE" in {issue.code for issue in rounded.issues}
    chinese = _lint(_draft("数据署报告，8月零售调查的甲指标增加了十单位。"),
                    terminology_map=_approved_map())
    assert "UNSUPPORTED_NUMERIC_FORMAT" in {issue.code for issue in chinese.issues}


def test_reporting_scope_is_validated_per_claim_with_shared_institution() -> None:
    beta = _beta_claim()
    parsed = _api("ScriptTerminologyMapV1").model_validate(_map_with_beta(beta))
    from fanglei.script_lint import _cross_language_claim_issues

    correct = "数据署报告，8月就业调查的乙指标增加了10单位。"
    wrong_scope = "数据署报告，8月零售调查的乙指标增加了10单位。"
    assert "TERMINOLOGY_TERM_MISSING" not in _cross_language_claim_issues(correct, beta, parsed)
    assert "TERMINOLOGY_TERM_MISSING" in _cross_language_claim_issues(wrong_scope, beta, parsed)


def test_attribution_context_is_bounded_and_resets_on_source_change_or_end() -> None:
    from fanglei.content_models import ScriptSentence
    from fanglei.script_lint import _validate_cross_language_attribution_contexts
    from fanglei.script_terminology import ScriptTerminologyMapV1

    alpha, beta = _claim(), _beta_claim()
    terminology = ScriptTerminologyMapV1.model_validate(_map_with_beta(beta))
    anchor = ScriptSentence(sentence_id="s1", section="phenomenon", sentence_type="verified_fact",
                            text="数据署报告发布了这份记录。", claim_ids=["claim_alpha"],
                            attribution_context_id="ctx_a")
    inherited = ScriptSentence(sentence_id="s2", section="phenomenon", sentence_type="verified_fact",
                               text="8月就业调查的乙指标增加了10单位。", claim_ids=["claim_beta"],
                               attribution_context_id="ctx_a")
    failures, inherited_ids = _validate_cross_language_attribution_contexts(
        [anchor, inherited], {"claim_alpha": alpha, "claim_beta": beta}, terminology,
    )
    assert not failures
    assert inherited_ids == {"s2"}

    other_source = _beta_claim(different_source=True)
    failures, _ = _validate_cross_language_attribution_contexts(
        [anchor, inherited], {"claim_alpha": alpha, "claim_beta": other_source},
        ScriptTerminologyMapV1.model_validate(_map_with_beta(other_source)),
    )
    assert "ATTRIBUTION_CONTEXT_ANCHOR_REQUIRED" in failures["s2"]

    ended = ScriptSentence(sentence_id="s_end", section="mechanism", sentence_type="explanation",
                           text="先停下来核对表达范围。")
    resumed = ScriptSentence(sentence_id="s4", section="phenomenon", sentence_type="verified_fact",
                             text="8月零售调查的甲指标增加了10单位。", claim_ids=["claim_alpha"],
                             attribution_context_id="ctx_a")
    failures, _ = _validate_cross_language_attribution_contexts(
        [anchor, ended, resumed], {"claim_alpha": alpha},
        ScriptTerminologyMapV1.model_validate(_approved_map()),
    )
    assert "ATTRIBUTION_CONTEXT_ANCHOR_REQUIRED" in failures["s4"]


def test_two_dimension_closing_is_supported_and_rejects_causal_or_weak_closures() -> None:
    from fanglei.content_models import ScriptDraft, ScriptSentence
    from fanglei.script_lint import _cross_language_closing_issues
    from fanglei.script_terminology import ScriptTerminologyMapV1

    alpha, beta = _claim(), _beta_claim()
    terminology = ScriptTerminologyMapV1.model_validate(_map_with_beta(beta))
    angle = _angle(["claim_alpha", "claim_beta"])
    close = ScriptSentence(sentence_id="close", section="core_judgment", sentence_type="interpretation",
                           text="8月零售调查的甲指标与就业调查的乙指标应分开理解。",
                           claim_ids=["claim_alpha", "claim_beta"])
    draft = ScriptDraft(angle_id=angle.angle_id, title=angle.title, sentences=[close])
    claims = {"claim_alpha": alpha, "claim_beta": beta}
    assert not _cross_language_closing_issues(draft, angle, claims, terminology)
    causal = close.model_copy(update={"text": "甲指标与乙指标因为同一个原因而变化。"})
    assert "AUTHORITY_SCOPE_EXPANSION" in _cross_language_closing_issues(
        draft.model_copy(update={"sentences": [causal]}), angle, claims, terminology,
    )
    weak = close.model_copy(update={"claim_ids": ["claim_alpha"]})
    assert "CORE_JUDGMENT_WEAK" in _cross_language_closing_issues(
        draft.model_copy(update={"sentences": [weak]}), angle, claims, terminology,
    )
    prediction = close.model_copy(update={"text": "预测甲指标和乙指标下个月会继续上升。"})
    assert "AUTHORITY_SCOPE_EXPANSION" in _cross_language_closing_issues(
        draft.model_copy(update={"sentences": [prediction]}), angle, claims, terminology,
    )
    wrong_angle = close.model_copy(update={"claim_ids": ["claim_alpha", "claim_outside"]})
    assert "CORE_JUDGMENT_WEAK" in _cross_language_closing_issues(
        draft.model_copy(update={"sentences": [wrong_angle]}), angle, claims, terminology,
    )


def test_trivial_final_phrase_is_rejected_as_weak_closing() -> None:
    draft = _draft("数据署报告，8月零售调查的甲指标增加了10单位。")
    last = draft.sentences[-1].model_copy(update={"text": "以上就是数据。"})
    draft = draft.model_copy(update={"sentences": [*draft.sentences[:-1], last]})
    result = _lint(draft, terminology_map=_approved_map())
    assert "CORE_JUDGMENT_WEAK" in {issue.code for issue in result.issues}


def test_duration_target_miss_is_warning_inside_hard_range() -> None:
    from fanglei.script_lint import lint_script

    draft = _draft("数据署报告，8月零售调查的甲指标增加了10单位。")
    result = lint_script(
        draft, _angle(), _facts(), "unrelated source text", speaking_rate=4.0,
        target_duration_seconds=90, target_language="zh-Hans",
        terminology_map=_approved_map(), current_facts_sha256="b" * 64,
        run_id="synthetic-run-001", case_id="synthetic-retail-case",
    )
    issue = next(item for item in result.issues if item.code == "DURATION_TARGET_MISSED")
    assert issue.severity == "warning"
    assert 60 <= result.estimated_duration_seconds <= 90
    assert "DURATION_OUT_OF_RANGE" not in {item.code for item in result.issues}


@pytest.mark.parametrize(
    ("duration_seconds", "passed", "target_warning"),
    [
        (59.0, False, True),
        (60.0, True, True),
        (72.5, True, False),
        (75.0, True, False),
        (85.0, True, True),
        (90.0, True, True),
        (90.5, False, True),
    ],
)
def test_hard_duration_range_is_separate_from_target_quality(
    duration_seconds: float, passed: bool, target_warning: bool,
) -> None:
    from fanglei.script_lint import _spoken_count, lint_script

    draft = _draft("数据署报告，8月零售调查的甲指标增加了10单位。")
    spoken_count = _spoken_count("".join(sentence.text for sentence in draft.sentences))
    speaking_rate = spoken_count / duration_seconds

    result = lint_script(
        draft, _angle(), _facts(), "Synthetic unrelated source", speaking_rate=speaking_rate,
        target_duration_seconds=75, target_language="zh-Hans", terminology_map=_approved_map(),
        current_facts_sha256="b" * 64, run_id="synthetic-run-001", case_id="synthetic-retail-case",
    )

    issue_codes = {issue.code for issue in result.issues}
    assert result.estimated_duration_seconds == duration_seconds
    assert result.passed is passed
    assert ("DURATION_OUT_OF_RANGE" in issue_codes) is (not passed)
    assert ("DURATION_TARGET_MISSED" in issue_codes) is target_warning
    target_issue = next((issue for issue in result.issues if issue.code == "DURATION_TARGET_MISSED"), None)
    if target_issue is not None:
        assert target_issue.severity == "warning"


def test_duration_repair_can_edit_bound_fact_without_losing_binding_or_context() -> None:
    from fanglei.content_models import ScriptDraft, ScriptSentence
    from fanglei.providers.content import RepairIssue
    from fanglei.script_patch import ScriptPatch, apply_script_patches, build_repair_scope

    draft = ScriptDraft(angle_id="angle_synthetic", title="Synthetic", sentences=[
        ScriptSentence(sentence_id="fact", section="phenomenon", sentence_type="verified_fact",
                       text="数据署报告，8月零售调查的甲指标增加了10单位。",
                       claim_ids=["claim_alpha"], attribution_context_id="ctx_alpha"),
        ScriptSentence(sentence_id="close", section="core_judgment", sentence_type="interpretation",
                       text="这一比较仍需保留原有范围边界。"),
    ])
    scope = build_repair_scope(draft, [RepairIssue(
        code="DURATION_TARGET_MISSED", current_seconds=84, target_seconds=75,
    )])
    assert "fact" in scope.editable_sentence_ids
    patched = apply_script_patches(draft, scope, [ScriptPatch(
        sentence_id="fact", operation="replace", new_text="数据署报告：8月甲指标增加10单位。",
    )]).draft
    assert patched.sentences[0].claim_ids == ["claim_alpha"]
    assert patched.sentences[0].attribution_context_id == "ctx_alpha"


def test_legacy_lint_does_not_require_terminology_without_explicit_cross_language_contract() -> None:
    from fanglei.script_lint import lint_script

    draft = _draft("Data Office reports: Metric Alpha increased by 10 units in August.")
    draft = draft.model_copy(update={"target_language": "zh-Hans"})
    result = lint_script(draft, _angle(), _facts(), "unrelated source text")
    assert "SCRIPT_TERMINOLOGY_REVIEW_REQUIRED" not in {issue.code for issue in result.issues}
