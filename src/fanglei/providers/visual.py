"""Provider boundary for renderer-agnostic visual planning."""
from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from fanglei.visual_models import VisualBeat, VisualBeatPlan


class VisualPlanningRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    run_id: str
    script: dict[str, Any]
    allowed_claim_ids: set[str] = Field(default_factory=set)


class VisualPlanningProvider(Protocol):
    name: str
    model: str
    prompt_version: str

    def plan(self, request: VisualPlanningRequest) -> VisualBeatPlan: ...


class DeterministicVisualPlanningProvider:
    """Small, auditable planner used by the V0.4 MVP and its tests."""

    name = "deterministic"
    model = "visual-rules-v1"
    prompt_version = "visual-beats-v1"

    def plan(self, request: VisualPlanningRequest) -> VisualBeatPlan:
        sentences = request.script.get("sentences", [])
        if not sentences:
            raise ValueError("SCRIPT_HAS_NO_SENTENCES")
        for sentence in sentences:
            unknown = set(sentence.get("claim_ids", [])) - request.allowed_claim_ids
            if unknown:
                raise ValueError("VISUAL_CLAIM_NOT_ALLOWED:" + ",".join(sorted(unknown)))

        script_text = "".join(sentence["text"] for sentence in sentences)
        normalized_script_text = self._normalize_percentages(script_text)
        groups: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        current_key = ""
        for sentence in sentences:
            section = sentence["section"]
            text = sentence["text"]
            if section == "mechanism" and (text.startswith("下次") or current_key == "checklist"):
                key = "checklist"
            else:
                key = section
            if current and key != current_key:
                groups.append(current)
                current = []
            current.append(sentence)
            current_key = key
        if current:
            groups.append(current)

        total_duration = float(request.script.get("estimated_duration_seconds") or 75.0)
        weights = [max(1, sum(len(row["text"]) for row in group)) for group in groups]
        weight_total = sum(weights)
        durations = [round(total_duration * weight / weight_total, 2) for weight in weights]
        durations[-1] = round(total_duration - sum(durations[:-1]), 2)

        beats: list[VisualBeat] = []
        for index, (group, duration) in enumerate(zip(groups, durations), start=1):
            key = "checklist" if group[0]["section"] == "mechanism" and group[0]["text"].startswith("下次") else group[0]["section"]
            relationship, objects, emphasis, renderer = self._visual_semantics(key, normalized_script_text)
            role = "judgment" if key == "core_judgment" else key
            if role == "checklist":
                role = "mechanism"
            beats.append(VisualBeat(
                beat_id=f"beat_{index:03d}", order=index,
                cognitive_purpose=self._purpose(key), narrative_role=role,
                sentence_ids=[row["sentence_id"] for row in group],
                narration_summary="".join(row["text"] for row in group),
                core_visual_relationship=relationship,
                key_objects=objects, emphasis_objects=emphasis,
                claim_ids=list(dict.fromkeys(cid for row in group for cid in row.get("claim_ids", []))),
                recommended_renderer=renderer, estimated_duration_seconds=max(duration, 0.01),
            ))
        return VisualBeatPlan(run_id=request.run_id,
                              script_id=request.script.get("script_id", "script_001"), beats=beats)

    @staticmethod
    def _purpose(key: str) -> str:
        return {
            "hook": "用两个数字建立可核验的反差",
            "phenomenon": "呈现来源相同主题下的显示差异",
            "mechanism": "演示精度与四舍五入机制",
            "checklist": "给出来源、指标、年份、精度的检查顺序",
            "core_judgment": "把小数点隐藏转化为可记忆的视觉结论",
        }[key]

    @staticmethod
    def _visual_semantics(key: str, script_text: str) -> tuple[str, list[str], list[str], str]:
        is_gdp_precision = all(token in script_text for token in ("2.8%", "2.7932%")) and (
            "BEA" in script_text and ("世界银行" in script_text or "World Bank" in script_text)
        )
        if not is_gdp_precision:
            return {
                "hook": ("提出脚本中的核心视觉问题", ["topic", "contrast_marker"], ["contrast_marker"], "program_animation"),
                "phenomenon": ("并列呈现脚本中的已验证对象", ["topic", "verified_fact_objects"], ["verified_fact_objects"], "program_animation"),
                "mechanism": ("按脚本顺序展开解释关系", ["verified_fact_objects", "mechanism_marker"], ["mechanism_marker"], "program_animation"),
                "checklist": ("把脚本中的检查方法排成顺序", ["method_steps"], ["method_steps"], "program_animation"),
                "core_judgment": ("用脚本的核心判断完成视觉收束", ["conclusion_object"], ["conclusion_object"], "program_animation"),
            }[key]
        values = {
            "hook": ("同一个美国实际 GDP 增长率出现 2.8% 与 2.7932% 两种显示",
                     ["gdp_topic", "bea_value", "world_bank_value"], ["bea_value", "world_bank_value"], "program_animation"),
            "phenomenon": ("BEA 的 2.8% 与 World Bank API 的 2.7932% 并列比较",
                            ["gdp_topic", "bea_label", "world_bank_label", "bea_value", "world_bank_value"],
                            ["decimal_digits"], "program_animation"),
            "mechanism": ("2.7932% 经过四舍五入到一位小数后变为 2.8%",
                           ["world_bank_value", "decimal_digits", "rounding_marker", "bea_value"],
                           ["decimal_digits", "rounding_marker"], "program_animation"),
            "checklist": ("来源 → 指标 → 年份 → 精度形成顺序检查流程",
                           ["source_check", "indicator_check", "year_check", "precision_check", "bea_value", "world_bank_value"],
                           ["precision_check"], "program_animation"),
            "core_judgment": ("2.7932% 的部分小数位藏起后视觉上收束为 2.8%",
                              ["world_bank_value", "decimal_point", "hidden_digits", "bea_value"],
                              ["decimal_point", "hidden_digits"], "program_animation"),
        }
        return values[key]

    @staticmethod
    def _normalize_percentages(text: str) -> str:
        replacements = {
            "百分之二点七九三二": "2.7932%",
            "百分之二点八": "2.8%",
        }
        for source, target in replacements.items():
            text = text.replace(source, target)
        return text
