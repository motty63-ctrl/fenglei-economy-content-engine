import json

import pytest

from fanglei.errors import ProviderError
from fanglei.content_models import AngleCandidate, ScriptDraft
from fanglei.providers.content import (
    AngleGenerationInput,
    DeepSeekContentPlanningProvider,
    RepairIssue,
    ScriptRepairInput,
    ScriptGenerationInput,
)
from fanglei.script_patch import ScriptPatchResult
from tests.test_angle_policy import _claim, _proposal


SENTINEL = "deepseek-sentinel-secret-123"


def _response(payload: dict) -> dict:
    return {"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]}


def _candidate() -> AngleCandidate:
    proposal = _proposal("angle_001", "纠正误解")
    return AngleCandidate(**proposal.model_dump(), evidence_strength=3, controversy_risk=0,
                          total_score=80, eligibility="eligible")


def test_deepseek_angles_use_json_mode_and_only_verified_palette() -> None:
    captured = {}
    angles = {"candidates": [
        _proposal("angle_001", "纠正误解", framing="misconception_correction").model_dump(),
        _proposal("angle_002", "解释精度", framing="economic_data_literacy").model_dump(),
        _proposal("angle_003", "训练媒体素养", framing="media_literacy").model_dump(),
    ]}

    def transport(payload):
        captured.update(payload)
        return _response(angles)

    provider = DeepSeekContentPlanningProvider(SENTINEL, model="deepseek-test", transport=transport)
    result = provider.generate_angles(AngleGenerationInput(
        run_id="run", core_topic="GDP", research_questions=["为什么不同"],
        research_md="UNVERIFIED SHOULD NEVER ENTER PROMPT", fact_palette=(_claim(),),
    ))
    assert len(result.candidates) == 3
    assert captured["response_format"] == {"type": "json_object"}
    assert captured["temperature"] == 0.6
    serialized = json.dumps(captured, ensure_ascii=False)
    assert SENTINEL not in serialized
    assert "UNVERIFIED SHOULD NEVER ENTER PROMPT" not in serialized
    assert "claim_007" in serialized


def test_deepseek_normalizes_explicit_ten_point_scores_at_provider_boundary() -> None:
    proposal = _proposal("angle_001", "纠正误解").model_dump()
    for field in ("audience_relevance", "novelty", "hook_strength", "visual_potential", "explainability"):
        proposal[field] = 9
    provider = DeepSeekContentPlanningProvider(
        SENTINEL, transport=lambda _: _response({"candidates": [proposal]})
    )
    result = provider.generate_angles(AngleGenerationInput(
        run_id="run", core_topic="GDP", research_questions=[], research_md="",
        fact_palette=(_claim(),),
    ))
    assert result.candidates[0].audience_relevance == 5
    assert all(getattr(result.candidates[0], field) <= 5 for field in (
        "audience_relevance", "novelty", "hook_strength", "visual_potential", "explainability"
    ))


def test_deepseek_script_parses_structured_sentences() -> None:
    draft = {"angle_id": "angle_001", "title": "数字为何不同", "sentences": [
        {"sentence_id": "sentence_001", "section": "hook", "sentence_type": "interpretation",
         "text": "为什么两个数字看着不同？", "claim_ids": []},
        {"sentence_id": "sentence_002", "section": "phenomenon", "sentence_type": "verified_fact",
         "text": "美国2024年实际GDP增长2.8%。", "claim_ids": ["claim_007"]},
        {"sentence_id": "sentence_003", "section": "mechanism", "sentence_type": "analogy",
         "text": "打个比方，这像两把刻度不同的尺子。", "claim_ids": []},
        {"sentence_id": "sentence_004", "section": "core_judgment", "sentence_type": "interpretation",
         "text": "我的判断是，先核对定义再比较数字。", "claim_ids": []},
    ]}
    provider = DeepSeekContentPlanningProvider(SENTINEL, transport=lambda _: _response(draft))
    result = provider.generate_script(ScriptGenerationInput(
        run_id="run", selected_angle=_candidate(),
        research_md="UNVERIFIED", fact_palette=(_claim(),),
    ))
    assert result.sentences[1].claim_ids == ["claim_007"]


def test_deepseek_normalizes_core_insight_section_alias() -> None:
    draft = {"angle_id": "angle_001", "title": "结论", "sentences": [
        {"sentence_id": "sentence_001", "section": "hook", "sentence_type": "interpretation",
         "text": "为什么数字不同？", "claim_ids": []},
        {"sentence_id": "sentence_002", "section": "core_insight", "sentence_type": "interpretation",
         "text": "我的判断是先核对定义。", "claim_ids": []},
    ]}
    provider = DeepSeekContentPlanningProvider(SENTINEL, transport=lambda _: _response(draft))
    result = provider.generate_script(ScriptGenerationInput(
        run_id="run", selected_angle=_candidate(), research_md="", fact_palette=(_claim(),),
    ))
    assert result.sentences[-1].section == "core_judgment"


def test_deepseek_normalizes_core_judgment_used_as_sentence_type() -> None:
    draft = {"angle_id": "angle_001", "title": "结论", "sentences": [
        {"sentence_id": "sentence_001", "section": "hook", "sentence_type": "interpretation",
         "text": "为什么数字不同？", "claim_ids": []},
        {"sentence_id": "sentence_002", "section": "core_judgment", "sentence_type": "core_judgment",
         "text": "我的判断是先核对定义。", "claim_ids": []},
    ]}
    provider = DeepSeekContentPlanningProvider(SENTINEL, transport=lambda _: _response(draft))
    result = provider.generate_script(ScriptGenerationInput(
        run_id="run", selected_angle=_candidate(), research_md="", fact_palette=(_claim(),),
    ))
    assert result.sentences[-1].sentence_type == "interpretation"


def test_deepseek_error_redacts_key_and_does_not_chain_raw_exception() -> None:
    def fail(_payload):
        raise RuntimeError(f"Authorization: Bearer {SENTINEL}")

    provider = DeepSeekContentPlanningProvider(SENTINEL, transport=fail)
    with pytest.raises(ProviderError) as captured:
        provider.smoke_test()
    assert SENTINEL not in str(captured.value)
    assert captured.value.__cause__ is None


def test_deepseek_repair_sends_only_allowlisted_context_and_issue_codes() -> None:
    captured = {}
    draft = {
        "angle_id": "angle_001", "title": "数字为何不同", "sentences": [
            {"sentence_id": "sentence_001", "section": "hook", "sentence_type": "interpretation",
             "text": "为什么两个数字看着不同？", "claim_ids": []},
            {"sentence_id": "sentence_002", "section": "phenomenon", "sentence_type": "verified_fact",
             "text": "美国2024年实际GDP增长2.8%。", "claim_ids": ["claim_007"]},
            {"sentence_id": "sentence_003", "section": "mechanism", "sentence_type": "analogy",
             "text": "打个比方，这像两把刻度不同的尺子。", "claim_ids": []},
            {"sentence_id": "sentence_004", "section": "core_judgment", "sentence_type": "interpretation",
             "text": "我的判断是，先核对定义再比较数字。", "claim_ids": []},
        ],
    }
    patch_response = {"patches": [{
        "sentence_id": "sentence_001", "operation": "replace",
        "new_text": "新闻数字藏着什么？",
    }]}

    def transport(payload):
        captured.update(payload)
        return _response(patch_response)

    provider = DeepSeekContentPlanningProvider(SENTINEL, transport=transport)
    current = ScriptDraft.model_validate(draft)
    captured.clear()
    repaired = provider.repair_script(ScriptRepairInput(
        run_id="run", repair_attempt=1, selected_angle=_candidate(), current_script=current,
        editable_sentence_ids=["sentence_001", "sentence_003", "sentence_004", "sentence_009"],
        protected_sentence_ids=["sentence_002"], allow_additions=False,
        fact_palette=(_claim(),), issues=[
            RepairIssue(code="HOOK_INVALID"),
            RepairIssue(code="CLAIM_BINDING_MISSING", sentence_id="sentence_003",
                        trigger_category="data_methodology"),
            RepairIssue(code="CLAIM_BINDING_MISSING", sentence_id="sentence_001",
                        trigger_category="numeric_or_date"),
            RepairIssue(code="CLAIM_BINDING_MISSING", sentence_id="sentence_004",
                        trigger_category="numeric_or_date"),
            RepairIssue(code="CORE_JUDGMENT_MISSING"),
            RepairIssue(code="REPEATED_SENTENCE", sentence_id="sentence_009"),
        ],
    ))
    serialized = json.dumps(captured, ensure_ascii=False)
    assert isinstance(repaired, ScriptPatchResult)
    assert repaired.patches[0].sentence_id == "sentence_001"
    assert "HOOK_INVALID" in serialized
    assert "claim_007" in serialized
    user_payload = json.loads(captured["messages"][1]["content"])
    assert "selected_angle" in user_payload and "editable_sentences" in user_payload
    assert "current_script" not in user_payload
    assert user_payload["protected_sentence_ids"] == ["sentence_002"]
    assert {row["sentence_id"] for row in user_payload["editable_sentences"]} == {
        "sentence_001", "sentence_003", "sentence_004"
    }
    assert user_payload["valid_duration_character_range"] == {"min": 240, "max": 360, "target": 300}
    assert user_payload["current_spoken_character_count"] > 0
    assert user_payload["patch_contract"]["operations"] == ["replace", "add_after"]
    assert {row["code"] for row in user_payload["structured_issues"]} >= {
        "HOOK_INVALID", "CLAIM_BINDING_MISSING", "CORE_JUDGMENT_MISSING", "REPEATED_SENTENCE"
    }
    assert captured["temperature"] == 0.0
    assert SENTINEL not in serialized
    assert "Authorization" not in serialized


def test_deepseek_uses_independent_configurable_temperatures() -> None:
    captured = []
    angles = {"candidates": [_proposal("angle_001", "纠正误解").model_dump()]}

    def transport(payload):
        captured.append(payload["temperature"])
        return _response(angles)

    provider = DeepSeekContentPlanningProvider(
        SENTINEL, transport=transport, angle_temperature=0.7,
        script_temperature=0.15, repair_temperature=0.0,
    )
    provider.generate_angles(AngleGenerationInput(
        run_id="run", core_topic="GDP", research_questions=[], research_md="",
        fact_palette=(_claim(),),
    ))
    assert captured == [0.7]
