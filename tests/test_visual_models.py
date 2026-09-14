import pytest
from pydantic import ValidationError

from fanglei.visual_models import VisualBeat, VisualBeatPlan


def _beat(**overrides):
    data = {
        "beat_id": "beat_001",
        "order": 1,
        "cognitive_purpose": "建立数字反差",
        "narrative_role": "hook",
        "sentence_ids": ["sentence_001", "sentence_002"],
        "narration_summary": "同一个 GDP 出现两个数字",
        "core_visual_relationship": "2.8% 与 2.7932% 并列",
        "key_objects": ["bea_value", "world_bank_value"],
        "emphasis_objects": ["decimal_digits"],
        "claim_ids": ["claim_007"],
        "recommended_renderer": "program_animation",
        "estimated_duration_seconds": 10.0,
    }
    data.update(overrides)
    return VisualBeat.model_validate(data)


def test_visual_beat_is_renderer_agnostic() -> None:
    beat = _beat()
    assert "layout" not in beat.model_dump()
    with pytest.raises(ValidationError):
        _beat(svg_path="M0 0", x=100, y=200)


def test_visual_beat_plan_requires_unique_ordered_sentence_coverage() -> None:
    with pytest.raises(ValidationError, match="sentence IDs"):
        VisualBeatPlan(run_id="run", script_id="script", beats=[
            _beat(), _beat(beat_id="beat_002", order=2, sentence_ids=["sentence_002"])
        ])


def test_visual_timing_is_estimated_not_absolute() -> None:
    plan = VisualBeatPlan(run_id="run", script_id="script", beats=[_beat()])
    payload = plan.model_dump(mode="json")
    assert payload["timing_basis"] == "estimated_speech"
    assert "start_seconds" not in payload["beats"][0]
    assert "end_seconds" not in payload["beats"][0]
