from fanglei.providers.content import RepairIssue
from fanglei.script_patch import (
    ScriptPatch,
    apply_script_patches,
    build_repair_scope,
)
from tests.test_script_quality import _draft


def test_hook_invalid_authorizes_only_hook_sentence() -> None:
    draft = _draft()
    scope = build_repair_scope(draft, [RepairIssue(code="HOOK_INVALID")])

    assert scope.editable_sentence_ids == ["sentence_001"]
    assert "sentence_002" in scope.protected_sentence_ids
    result = apply_script_patches(draft, scope, [
        ScriptPatch(sentence_id="sentence_001", operation="replace", new_text="新闻数字藏着什么？"),
        ScriptPatch(sentence_id="sentence_003", operation="replace", new_text="越权修改。"),
    ])
    assert result.draft.sentences[0].text == "新闻数字藏着什么？"
    assert [item.reason for item in result.rejected] == ["SENTENCE_PROTECTED"]


def test_duration_too_short_never_authorizes_verified_fact_hook_or_conclusion() -> None:
    draft = _draft()
    scope = build_repair_scope(draft, [RepairIssue(
        code="DURATION_TOO_SHORT", current_seconds=55, min_seconds=60, target_seconds=75
    )])

    assert "sentence_002" not in scope.editable_sentence_ids
    assert "sentence_001" in scope.protected_sentence_ids
    assert draft.sentences[-1].sentence_id in scope.protected_sentence_ids
    result = apply_script_patches(draft, scope, [ScriptPatch(
        sentence_id="sentence_002", operation="replace", new_text="美国GDP增长3%。"
    )])
    assert not result.applied
    assert result.rejected[0].reason == "SENTENCE_PROTECTED"


def test_patch_for_protected_sentence_is_rejected() -> None:
    draft = _draft()
    scope = build_repair_scope(draft, [RepairIssue(
        code="REPEATED_SENTENCE", sentence_id="sentence_003"
    )])
    result = apply_script_patches(draft, scope, [ScriptPatch(
        sentence_id="sentence_004", operation="replace", new_text="不应生效。"
    )])
    assert result.rejected[0].reason == "SENTENCE_PROTECTED"
    assert result.draft.sentences[3].text == draft.sentences[3].text


def test_patch_for_unknown_sentence_is_rejected() -> None:
    draft = _draft()
    scope = build_repair_scope(draft, [RepairIssue(
        code="REPEATED_SENTENCE", sentence_id="sentence_003"
    )])
    result = apply_script_patches(draft, scope, [ScriptPatch(
        sentence_id="sentence_missing", operation="replace", new_text="不存在。"
    )])
    assert result.rejected[0].reason == "SENTENCE_NOT_FOUND"


def test_duration_patch_can_add_explanation_after_editable_mechanism_sentence() -> None:
    draft = _draft()
    scope = build_repair_scope(draft, [RepairIssue(
        code="DURATION_TOO_SHORT", current_seconds=55, min_seconds=60, target_seconds=75
    )])
    result = apply_script_patches(draft, scope, [ScriptPatch(
        sentence_id="sentence_003", operation="add_after",
        new_sentence_id="sentence_repair_001", new_text="再把来源和指标名称放在一起核对。",
        new_sentence_type="explanation", new_section="mechanism",
    )])

    assert not result.rejected
    added = next(item for item in result.draft.sentences if item.sentence_id == "sentence_repair_001")
    assert added.sentence_type == "explanation"
    assert added.claim_ids == []


def test_protected_sentence_hashes_remain_unchanged_after_authorized_patch() -> None:
    draft = _draft()
    scope = build_repair_scope(draft, [RepairIssue(
        code="REPEATED_SENTENCE", sentence_id="sentence_003"
    )])
    result = apply_script_patches(draft, scope, [ScriptPatch(
        sentence_id="sentence_003", operation="replace", new_text="先核对指标名称，再讨论数字。"
    )])

    assert result.protected_hashes_unchanged is True
    assert result.protected_hashes_before == result.protected_hashes_after


def test_sentence_type_change_requires_explicit_mismatch_issue() -> None:
    draft = _draft()
    scope = build_repair_scope(draft, [RepairIssue(
        code="REPEATED_SENTENCE", sentence_id="sentence_003"
    )])
    result = apply_script_patches(draft, scope, [ScriptPatch(
        sentence_id="sentence_003", operation="replace", new_text="打个比方，这像一把尺子。",
        new_sentence_type="analogy",
    )])
    assert result.rejected[0].reason == "SENTENCE_TYPE_CHANGE_NOT_AUTHORIZED"


def test_sentence_type_mismatch_can_authorize_type_correction_for_same_sentence() -> None:
    draft = _draft()
    scope = build_repair_scope(draft, [RepairIssue(
        code="SENTENCE_TYPE_MISMATCH", sentence_id="sentence_003",
        current_type="explanation", expected_constraint="use analogy",
    )])
    result = apply_script_patches(draft, scope, [ScriptPatch(
        sentence_id="sentence_003", operation="replace", new_text="打个比方，这像一把尺子。",
        new_sentence_type="analogy",
    )])
    assert not result.rejected
    assert result.draft.sentences[2].sentence_type == "analogy"


def test_analogy_overuse_can_authorize_removing_analogy_type() -> None:
    draft = _draft()
    analogy = next(sentence for sentence in draft.sentences if sentence.sentence_type == "analogy")
    scope = build_repair_scope(draft, [RepairIssue(
        code="ANALOGY_OVERUSE", sentence_id=analogy.sentence_id,
    )])
    result = apply_script_patches(draft, scope, [ScriptPatch(
        sentence_id=analogy.sentence_id,
        operation="replace",
        new_text="换个顺序，先确认问题，再比较两种写法。",
        new_sentence_type="explanation",
    )])

    assert not result.rejected
    assert result.draft.sentences[4].sentence_type == "explanation"
