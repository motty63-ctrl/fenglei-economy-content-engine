"""Offline convergence tests for the generic translated-script repair contract."""
from __future__ import annotations

import json

from fanglei.content_models import ScriptDraft, ScriptReadyClaim, ScriptSentence
from fanglei.content_pipeline import _repair_issues
from fanglei.providers.content import (
    DeepSeekContentPlanningProvider,
    RepairIssue,
    ScriptRepairInput,
)
from fanglei.script_lint import lint_script
from fanglei.script_patch import apply_script_patches, build_repair_scope
from tests.test_script_terminology import (
    _angle,
    _approved_map,
    _beta_claim,
    _claim,
    _map_with_beta,
)


def _revision_alpha() -> dict:
    from fanglei.evidence_targets import atomic_proposition_spans

    claim = _claim()
    excerpt = "Metric Alpha was revised from 100 units to 120 units, a revision of 20 units."
    scope = claim["authority_attestation"]["scope"]
    scope.update(unit="units", certainty="increased")
    evidence = claim["evidence"][0]
    evidence.update(
        evidence_text=excerpt,
        proposition_span=atomic_proposition_spans(excerpt)[0],
        authority_scope_candidate=dict(scope),
        explicit_values=[{"value": value, "unit": "units"} for value in ("100", "120", "20")],
        revision_values={
            "previous_value": "100 units",
            "revised_value": "120 units",
            "revision_amount": "20 units",
            "direction": "up",
        },
    )
    claim["claim_text"] = f'Data Office reports: "{excerpt}"'
    return claim


def _authority_facts() -> tuple[dict, dict, dict]:
    alpha = _revision_alpha()
    beta = _beta_claim()
    beta["authority_attestation"]["scope"]["unit"] = "units"
    beta["evidence"][0]["authority_scope_candidate"]["unit"] = "units"
    beta["evidence"][0]["explicit_values"] = [{"value": "10", "unit": "units"}]
    facts = {"schema_version": "2.2", "claims": [alpha, beta]}
    angle = _angle(["claim_alpha", "claim_beta"])
    terminology = _map_with_beta(beta)
    rows = []
    for row in terminology["entries"]:
        copy = dict(row)
        if copy["claim_ids"] == ["claim_alpha"] and copy["semantic_role"] == "unit":
            copy["source_term"] = "units"
            copy["proposed_target_terms"] = ["单位"]
            copy["approved_target_terms"] = ["单位"]
        rows.append(copy)
    terminology["entries"] = rows
    return facts, angle.model_dump(mode="python"), terminology


def _initial_script() -> ScriptDraft:
    sentences = [
        ScriptSentence(sentence_id="s001", section="hook", sentence_type="interpretation",
                       text="两个指标的记录有哪些不同？"),
        ScriptSentence(sentence_id="s002", section="phenomenon", sentence_type="verified_fact",
                       text="数据署报告，8月乙指标从120单位修正为100单位，上修20岗位。",
                       claim_ids=["claim_alpha"], attribution_context_id="ctx_alpha"),
        ScriptSentence(sentence_id="s003", section="mechanism", sentence_type="explanation",
                       text="再把两个指标分别放回各自的问题。", attribution_context_id="ctx_alpha"),
        ScriptSentence(sentence_id="s004", section="phenomenon", sentence_type="verified_fact",
                       text="数据署报告，8月就业调查的乙指标增加10岗位。",
                       claim_ids=["claim_beta"], attribution_context_id="ctx_beta"),
        ScriptSentence(sentence_id="s005", section="mechanism", sentence_type="explanation",
                       text="先把正在比较的对象与问题说清楚。"),
        ScriptSentence(sentence_id="s006", section="mechanism", sentence_type="explanation",
                       text="再确认每个数字对应的时间范围。"),
        ScriptSentence(sentence_id="s007", section="mechanism", sentence_type="explanation",
                       text="不同记录要保留各自原有的范围边界。"),
        ScriptSentence(sentence_id="s008", section="mechanism", sentence_type="explanation",
                       text="表达顺序也要跟着问题和证据一起推进。"),
        ScriptSentence(sentence_id="s009", section="mechanism", sentence_type="explanation",
                       text="不要让相邻说法彼此替代或混为一谈。"),
        ScriptSentence(sentence_id="s010", section="mechanism", sentence_type="explanation",
                       text="先把具体记录与对应的讨论范围读完整。"),
        ScriptSentence(sentence_id="s011", section="mechanism", sentence_type="explanation",
                       text="最后再决定怎样收束这组比较内容。"),
        ScriptSentence(sentence_id="s012", section="core_judgment", sentence_type="interpretation",
                       text="先说出自己的理解。"),
    ]
    return ScriptDraft(
        angle_id="angle_synthetic", title="Synthetic metric comparison",
        target_duration_seconds=75, target_language="zh-Hans", sentences=sentences,
    )


def _lint(draft: ScriptDraft, facts: dict, angle, terminology: dict):
    return lint_script(
        draft, angle, facts, "RAW_CORPUS_SHOULD_NOT_LEAK", speaking_rate=3.5,
        target_language="zh-Hans", terminology_map=terminology,
        current_facts_sha256="b" * 64, run_id="synthetic-run-001",
        case_id="synthetic-retail-case",
    )


def test_local_repair_contract_converges_without_adding_facts_or_leaking_corpus() -> None:
    facts, angle_data, terminology = _authority_facts()
    from fanglei.content_models import AngleCandidate

    angle = AngleCandidate.model_validate(angle_data)
    draft = _initial_script()
    initial = _lint(draft, facts, angle, terminology)
    issues = _repair_issues(initial, draft)
    codes = {issue.code for issue in issues}
    assert {"TERMINOLOGY_TERM_MISSING", "REVISION_ROLE_MISMATCH", "UNIT_SCOPE_MISMATCH",
            "ATTRIBUTION_CONTEXT_INVALID", "CORE_JUDGMENT_WEAK"} <= codes

    fact_palette = tuple(ScriptReadyClaim.model_validate(claim) for claim in facts["claims"])
    scope = build_repair_scope(draft, issues, allowed_claim_ids=angle.supporting_claim_ids)
    captured: dict = {}

    def local_transport(payload: dict) -> dict:
        captured.update(payload)
        return {"choices": [{"message": {"content": json.dumps({"patches": [
            {"sentence_id": "s002", "operation": "replace",
             "new_text": "数据署报告，8月甲指标从100单位修正为120单位，上修20单位。"},
            {"sentence_id": "s003", "operation": "replace",
             "new_text": "再把两个指标分别放回各自的问题。",
             "clear_attribution_context": True},
            {"sentence_id": "s004", "operation": "replace",
             "new_text": "数据署报告，8月就业调查的乙指标增加10单位。"},
            {"sentence_id": "s012", "operation": "replace",
             "new_text": "数据署报告中的甲指标和乙指标应放回各自范围内比较。",
             "new_claim_ids": ["claim_alpha", "claim_beta"]},
        ]}, ensure_ascii=False)}}]}

    provider = DeepSeekContentPlanningProvider(
        "offline-test-key-never-sent", transport=local_transport,
    )
    request = ScriptRepairInput(
        run_id="synthetic-run-001", repair_attempt=1, selected_angle=angle,
        current_script=draft,
        editable_sentence_ids=scope.editable_sentence_ids,
        protected_sentence_ids=scope.protected_sentence_ids,
        fact_palette=fact_palette, issues=issues, target_language="zh-Hans",
        terminology_map=terminology,
        clear_attribution_context_sentence_ids=scope.clear_attribution_context_sentence_ids,
        closing_claim_bind_sentence_ids=scope.closing_claim_bind_sentence_ids,
        allowed_closing_claim_ids=scope.allowed_closing_claim_ids,
    )
    patch_result = provider.repair_script(request)
    user_payload = json.loads(captured["messages"][1]["content"])
    serialized_payload = json.dumps(user_payload, ensure_ascii=False)
    assert "RAW_CORPUS_SHOULD_NOT_LEAK" not in serialized_payload
    assert "offline-test-key-never-sent" not in serialized_payload
    assert user_payload["repair_permissions"]["clear_attribution_context_sentence_ids"] == ["s003"]
    assert user_payload["repair_permissions"]["closing_claim_bind_sentence_ids"] == ["s012"]
    issue_rows = {row["code"]: row for row in user_payload["structured_issues"]}
    assert issue_rows["REVISION_ROLE_MISMATCH"]["diagnostics"]["expected_values"]["previous_value"] == "100 units"
    assert issue_rows["UNIT_SCOPE_MISMATCH"]["diagnostics"]["expected_unit"] == "units"
    assert issue_rows["ATTRIBUTION_CONTEXT_INVALID"]["diagnostics"]["claimless"] is True
    assert any("approved_target_terms" in row.get("diagnostics", {})
               for row in user_payload["structured_issues"] if row["code"] == "TERMINOLOGY_TERM_MISSING")
    assert all("verified_claims_only" not in row for row in user_payload["structured_issues"])
    fact_payload = user_payload["verified_claims_only"]
    alpha_fact = next(row for row in fact_payload if row["claim_id"] == "claim_alpha")
    assert alpha_fact["evidence"][0]["revision_values"]["previous_value"] == "100 units"

    repaired = apply_script_patches(draft, scope, patch_result.patches)
    assert not repaired.rejected
    assert repaired.draft.sentences[2].attribution_context_id is None
    assert repaired.draft.sentences[-1].claim_ids == ["claim_alpha", "claim_beta"]
    final = _lint(repaired.draft, facts, angle, terminology)
    assert final.passed, [(item.code, item.sentence_id, item.diagnostics) for item in final.issues]


def test_repair_issue_rules_explain_generic_contract_without_case_specific_answers() -> None:
    facts, angle_data, terminology = _authority_facts()
    from fanglei.content_models import AngleCandidate

    angle = AngleCandidate.model_validate(angle_data)
    captured: dict = {}

    def local_transport(payload: dict) -> dict:
        captured.update(payload)
        return {"choices": [{"message": {"content": json.dumps({"patches": []})}}]}

    provider = DeepSeekContentPlanningProvider("local-key", transport=local_transport)
    provider.repair_script(ScriptRepairInput(
        run_id="synthetic-run-001", repair_attempt=1, selected_angle=angle,
        current_script=_initial_script(), editable_sentence_ids=["s002"],
        protected_sentence_ids=[], fact_palette=tuple(
            ScriptReadyClaim.model_validate(claim) for claim in facts["claims"]
        ), terminology_map=terminology,
        issues=[RepairIssue(code=code, sentence_id="s002", diagnostics={"example": "structured only"})
                for code in (
                    "TERMINOLOGY_TERM_MISSING", "REVISION_ROLE_MISMATCH",
                    "UNSUPPORTED_NUMERIC_FORMAT", "UNSUPPORTED_NUMERIC_VALUE",
                    "UNIT_SCOPE_MISMATCH", "ATTRIBUTION_CONTEXT_INVALID", "CORE_JUDGMENT_WEAK",
                )],
    ))
    user_payload = json.loads(captured["messages"][1]["content"])
    rules = " ".join(user_payload["rules_for_current_issue_codes"])
    for phrase in ("approved_target_terms", "previous/revised/delta", "精确支持的数值和单位",
                   "claimless", "new_claim_ids"):
        assert phrase in rules
    assert "BLS" not in rules and "GDP" not in rules
