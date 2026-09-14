from fanglei.artifact_registry import ARTIFACT_GRAPH


def test_v04_artifacts_have_unique_owners_and_dependencies() -> None:
    assert ARTIFACT_GRAPH["visual_beats.json"] == (
        "visual_planning", ("script.json", "facts.json", "angle.md")
    )
    assert ARTIFACT_GRAPH["storyboard.json"] == (
        "storyboard_generation", ("visual_beats.json", "script.json", "facts.json")
    )
    assert ARTIFACT_GRAPH["visual_plan.md"] == (
        "visual_plan_render", ("storyboard.json",)
    )
