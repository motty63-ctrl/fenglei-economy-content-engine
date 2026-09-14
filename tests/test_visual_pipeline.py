import json

from fanglei.artifact_registry import ArtifactRegistry
from fanglei.content_pipeline import run_content_pipeline
from fanglei.models import RunManifest
from fanglei.providers.content import MockContentPlanningProvider
from fanglei.providers.visual import DeterministicVisualPlanningProvider
from fanglei.visual_pipeline import run_visual_pipeline
from tests.test_content_pipeline import _prepared_run


def _visual_ready_run(tmp_path):
    run = _prepared_run(tmp_path)
    run_content_pipeline(run.name, tmp_path, MockContentPlanningProvider())
    return run


def _manifest(run):
    return json.loads((run / "run.json").read_text(encoding="utf-8"))


def test_visual_pipeline_writes_three_valid_artifacts(tmp_path) -> None:
    run = _visual_ready_run(tmp_path)
    run_visual_pipeline(run.name, tmp_path, DeterministicVisualPlanningProvider())
    manifest = _manifest(run)
    for name in ("visual_beats.json", "storyboard.json", "visual_plan.md"):
        assert (run / name).is_file()
        assert manifest["artifacts"][name]["status"] == "valid"
    storyboard = json.loads((run / "storyboard.json").read_text(encoding="utf-8"))
    assert storyboard["quality_gate"]["passed"] is True
    assert manifest["status"] == "visual_planned"


def test_visual_pipeline_reuses_valid_artifacts_by_default(tmp_path) -> None:
    run = _visual_ready_run(tmp_path)
    provider = DeterministicVisualPlanningProvider()
    run_visual_pipeline(run.name, tmp_path, provider)
    before = _manifest(run)
    run_visual_pipeline(run.name, tmp_path, provider)
    after = _manifest(run)
    assert after["stages"]["visual_planning"]["attempts"] == before["stages"]["visual_planning"]["attempts"]
    assert after["stages"]["storyboard_generation"]["attempts"] == before["stages"]["storyboard_generation"]["attempts"]


def test_script_hash_change_marks_visual_artifacts_stale(tmp_path) -> None:
    run = _visual_ready_run(tmp_path)
    run_visual_pipeline(run.name, tmp_path, DeterministicVisualPlanningProvider())
    manifest = RunManifest.model_validate(_manifest(run))
    registry = ArtifactRegistry(run, manifest)
    script = registry.read_json("script.json")
    script["title"] = script["title"] + "（修订）"
    registry.write_json("script.json", script, "script_generation", force=True)
    registry.save_manifest()
    after = _manifest(run)
    assert after["artifacts"]["visual_beats.json"]["status"] == "stale"
    assert after["artifacts"]["storyboard.json"]["status"] == "stale"
    assert after["artifacts"]["visual_plan.md"]["status"] == "stale"


def test_force_storyboard_does_not_rerun_visual_planning(tmp_path) -> None:
    run = _visual_ready_run(tmp_path)
    provider = DeterministicVisualPlanningProvider()
    run_visual_pipeline(run.name, tmp_path, provider)
    before = _manifest(run)
    run_visual_pipeline(run.name, tmp_path, provider, force_stage="storyboard_generation")
    after = _manifest(run)
    assert after["stages"]["visual_planning"]["attempts"] == before["stages"]["visual_planning"]["attempts"]
    assert after["stages"]["storyboard_generation"]["attempts"] == before["stages"]["storyboard_generation"]["attempts"] + 1
