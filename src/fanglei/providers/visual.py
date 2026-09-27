"""Provider boundary for renderer-agnostic visual planning."""
from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from fanglei.visual_models import VisualBeat, VisualBeatPlan
from fanglei.visual_semantics import extract_numeric_comparison, is_numeric_comparison


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
    requires_structured_comparison = True

    def plan(self, request: VisualPlanningRequest) -> VisualBeatPlan:
        sentences = request.script.get("sentences", [])
        if not sentences:
            raise ValueError("SCRIPT_HAS_NO_SENTENCES")
        for sentence in sentences:
            unknown = set(sentence.get("claim_ids", [])) - request.allowed_claim_ids
            if unknown:
                raise ValueError("VISUAL_CLAIM_NOT_ALLOWED:" + ",".join(sorted(unknown)))

        def section_groups(rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
            result: list[list[dict[str, Any]]] = []
            current: list[dict[str, Any]] = []
            current_key = ""
            for sentence in rows:
                section = sentence["section"]
                text = sentence["text"]
                if section == "mechanism" and (text.startswith("下次") or current_key == "checklist"):
                    key = "checklist"
                else:
                    key = section
                if current and key != current_key:
                    result.append(current)
                    current = []
                current.append(sentence)
                current_key = key
            if current:
                result.append(current)
            return result

        comparison_indexes = [
            index for index, sentence in enumerate(sentences)
            if sentence.get("sentence_type") == "verified_fact"
            and self._is_comparison_sentence(sentence["text"])
        ]
        groups: list[list[dict[str, Any]]] = []
        if comparison_indexes:
            cursor = 0
            for index in comparison_indexes:
                groups.extend(section_groups(sentences[cursor:index]))
                groups.append([sentences[index]])
                cursor = index + 1
            if cursor < len(sentences):
                # Keep the closing interpretation and its supporting document report
                # together after the numeric comparison sequence.
                groups.append(sentences[cursor:])
        else:
            groups = section_groups(sentences)

        total_duration = float(request.script.get("estimated_duration_seconds") or 75.0)
        weights = [max(1, sum(len(row["text"]) for row in group)) for group in groups]
        weight_total = sum(weights)
        durations = [round(total_duration * weight / weight_total, 2) for weight in weights]
        durations[-1] = round(total_duration - sum(durations[:-1]), 2)

        beats: list[VisualBeat] = []
        for index, (group, duration) in enumerate(zip(groups, durations), start=1):
            if (len(group) == 1 and group[0].get("sentence_type") == "verified_fact"
                    and self._is_comparison_sentence(group[0]["text"])):
                key = "comparison"
            else:
                key = "checklist" if group[0]["section"] == "mechanism" and group[0]["text"].startswith("下次") else group[0]["section"]
            if group[-1]["section"] == "core_judgment":
                key = "core_judgment"
            comparison = (
                extract_numeric_comparison(group[0]["text"])
                if key == "comparison" and len(group) == 1 else None
            )
            if key == "comparison" and comparison is None and self.requires_structured_comparison:
                # Keep exact-sentence rendering as the safe fallback when a broad
                # comparison cue cannot be represented by the typed visual contract.
                key = "phenomenon"
            relationship, objects, emphasis, renderer = self._visual_semantics(key)
            role = "judgment" if key == "core_judgment" else (
                "phenomenon" if key == "comparison" else key
            )
            if role == "checklist":
                role = "mechanism"
            beats.append(VisualBeat(
                beat_id=f"beat_{index:03d}", order=index,
                cognitive_purpose=self._purpose(key), narrative_role=role,
                sentence_ids=[row["sentence_id"] for row in group],
                narration_summary="".join(row["text"] for row in group),
                core_visual_relationship=relationship,
                key_objects=objects, emphasis_objects=emphasis,
                comparison=comparison,
                claim_ids=list(dict.fromkeys(cid for row in group for cid in row.get("claim_ids", []))),
                recommended_renderer=renderer, estimated_duration_seconds=max(duration, 0.01),
            ))
        return VisualBeatPlan(run_id=request.run_id,
                              script_id=request.script.get("script_id", "script_001"), beats=beats)

    @staticmethod
    def _purpose(key: str) -> str:
        return {
            "hook": "提出脚本中的核心问题",
            "phenomenon": "并列呈现脚本中的已核验信息",
            "comparison": "按原句呈现脚本中的数值比较",
            "mechanism": "按脚本顺序展开事实与说明",
            "checklist": "按脚本明确给出的检查步骤逐项呈现",
            "core_judgment": "用脚本中的结论完成视觉收束",
        }[key]

    @staticmethod
    def _visual_semantics(key: str) -> tuple[str, list[str], list[str], str]:
        return {
            "hook": ("提出脚本中的核心视觉问题", ["topic", "contrast_marker"], ["contrast_marker"], "program_animation"),
            "phenomenon": ("并列呈现脚本中的已验证对象", ["topic", "verified_fact_objects"], ["verified_fact_objects"], "program_animation"),
            "comparison": (
                "按脚本原句并列呈现输入中的指标与数值变化",
                ["metric_label", "before_value", "after_value", "change"],
                ["after_value"], "program_animation",
            ),
            "mechanism": ("按脚本顺序展开解释关系", ["verified_fact_objects", "mechanism_marker"], ["mechanism_marker"], "program_animation"),
            "checklist": ("把脚本中的检查方法排成顺序", ["method_steps"], ["method_steps"], "program_animation"),
            "core_judgment": ("用脚本的核心判断完成视觉收束", ["conclusion_object"], ["conclusion_object"], "program_animation"),
        }[key]

    @staticmethod
    def _is_comparison_sentence(text: str) -> bool:
        return is_numeric_comparison(text)

class LegacyGDPCalibrationVisualPlanningProvider(DeterministicVisualPlanningProvider):
    """Explicit adapter for the historical GDP precision calibration fixture."""

    requires_structured_comparison = False

    def plan(self, request: VisualPlanningRequest) -> VisualBeatPlan:
        script_text = "".join(row.get("text", "") for row in request.script.get("sentences", []))
        if not ("2.8%" in script_text and "2.7932%" in script_text and "BEA" in script_text
                and ("世界银行" in script_text or "World Bank" in script_text)):
            raise ValueError("LEGACY_GDP_CALIBRATION_PROVIDER_REQUIRES_GDP_FIXTURE")
        return super().plan(request)

    @staticmethod
    def _is_comparison_sentence(text: str) -> bool:
        import re

        numeric_value = re.compile(r"\d+(?:[.,]\d+)?%?")
        comparison_marker = re.compile(r"(?:变化|从|到|由|至|→|->|\bfrom\b|\bto\b|\bchanged\b)", re.I)
        period_marker = re.compile(r"(?:20\d{2}|\d{1,2}月|\bQ[1-4]\b|\b(?:year|quarter|period)\b|年)", re.I)
        return bool(
            len(numeric_value.findall(text)) >= 2
            and comparison_marker.search(text)
            and period_marker.search(text)
        )

    @staticmethod
    def _visual_semantics(key: str) -> tuple[str, list[str], list[str], str]:
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
