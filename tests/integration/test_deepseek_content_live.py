import os
import json
from pathlib import Path

import pytest

from fanglei.providers.content import DeepSeekContentPlanningProvider
from fanglei.content_pipeline import run_content_pipeline


@pytest.mark.integration
def test_deepseek_live_smoke() -> None:
    if os.environ.get("RUN_DEEPSEEK_INTEGRATION") != "1":
        pytest.skip("set RUN_DEEPSEEK_INTEGRATION=1 to run DeepSeek integration")
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        pytest.skip("DEEPSEEK_API_KEY is not configured")
    result = DeepSeekContentPlanningProvider(api_key).smoke_test()
    assert result["authenticated"] is True


@pytest.mark.integration
def test_deepseek_live_content_acceptance_uses_existing_verified_run_only() -> None:
    if os.environ.get("RUN_DEEPSEEK_CONTENT_ACCEPTANCE") != "1":
        pytest.skip("set RUN_DEEPSEEK_CONTENT_ACCEPTANCE=1 to run content acceptance")
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        pytest.skip("DEEPSEEK_API_KEY is not configured")
    runs_dir = Path(os.environ["FANGLEI_DEEPSEEK_ACCEPTANCE_RUNS_DIR"])
    run_id = os.environ["FANGLEI_DEEPSEEK_ACCEPTANCE_RUN_ID"]
    run_dir = runs_dir / run_id
    before = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    protected = ("facts.json", "research.md", "angles.json", "angle.md")
    upstream_hashes = {name: before["artifacts"][name]["content_hash"] for name in protected}
    angle_attempts = before["stages"]["angle_generation"]["attempts"]
    selection_attempts = before["stages"]["angle_selection"]["attempts"]

    provider = DeepSeekContentPlanningProvider(
        api_key, model=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")
    )
    class ScriptOnlyDeepSeekProvider:
        name = provider.name
        model = provider.model
        angle_prompt_version = provider.angle_prompt_version
        script_prompt_version = provider.script_prompt_version
        angle_temperature = provider.angle_temperature
        script_temperature = provider.script_temperature
        repair_temperature = provider.repair_temperature

        def generate_angles(self, _request):
            raise AssertionError("existing valid angles must not be regenerated")

        def generate_script(self, request):
            return provider.generate_script(request.model_copy(update={"research_md": ""}))

        def repair_script(self, request):
            return provider.repair_script(request)

    run_content_pipeline(run_id, runs_dir, ScriptOnlyDeepSeekProvider(), force_stage="script_generation")

    after = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert {name: after["artifacts"][name]["content_hash"] for name in upstream_hashes} == upstream_hashes
    assert after["stages"]["angle_generation"]["attempts"] == angle_attempts
    assert after["stages"]["angle_selection"]["attempts"] == selection_attempts
    angles = json.loads((run_dir / "angles.json").read_text(encoding="utf-8"))
    script = json.loads((run_dir / "script.json").read_text(encoding="utf-8"))
    assert angles["provider"]["name"] == "deepseek"
    assert angles["diversity_gate"]["passed"] is True
    assert 3 <= len(angles["candidates"]) <= 5
    assert 60 <= script["estimated_duration_seconds"] <= 90
    assert script["repair_audit"]["final_status"] == "passed"
    assert len(script["repair_audit"]["repairs"]) <= 2
    assert script["generation_config"] == {
        "angle_temperature": provider.angle_temperature,
        "script_temperature": provider.script_temperature,
        "repair_temperature": provider.repair_temperature,
        "max_repair_attempts": 2,
    }
    assert all(after["artifacts"][name]["status"] == "valid"
               for name in ("angles.json", "angle.md", "script.json", "script.md"))
