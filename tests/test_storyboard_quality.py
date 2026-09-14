from fanglei.storyboard_quality import lint_storyboard
from tests.test_storyboard import _board, _facts
from tests.test_visual_planning import _script


def _codes(board):
    return {issue.code for issue in lint_storyboard(board, _script(), _facts()).issues}


def test_valid_gdp_storyboard_passes_all_gates() -> None:
    result = lint_storyboard(_board(), _script(), _facts())
    assert result.passed
    assert result.issues == []
    assert result.sentence_coverage_ratio == 1


def test_gate_rejects_one_sentence_per_scene_pattern() -> None:
    board = _board()
    board.scenes = [scene.model_copy(update={"sentence_ids": [f"sentence_{i:03d}"], "order": i})
                    for i, scene in enumerate((board.scenes * 3)[:8], start=1)]
    assert "PPT_SCENE_DENSITY" in _codes(board)


def test_gate_rejects_unsupported_or_nondeterministic_fact() -> None:
    board = _board()
    target = next(obj for obj in board.scenes[1].objects if obj.object_id == "bea_value")
    target.claim_ids = ["claim_unverified"]
    target.deterministic_render = False
    codes = _codes(board)
    assert "VISUAL_FACT_CLAIM_NOT_ALLOWED" in codes
    assert "FACTUAL_TEXT_NOT_DETERMINISTIC" in codes


def test_gate_rejects_missing_sentence_coverage_and_invalid_inheritance() -> None:
    board = _board()
    board.scenes[1].sentence_ids = ["sentence_003", "sentence_004"]
    board.scenes[0].inherited_objects = ["future_object"]
    codes = _codes(board)
    assert "SCRIPT_SENTENCE_NOT_COVERED" in codes
    assert "OBJECT_INHERITED_BEFORE_INTRODUCTION" in codes


def test_gate_rejects_non_contiguous_relative_timing() -> None:
    board = _board()
    board.scenes[1].relative_start = .4
    assert "RELATIVE_TIMING_GAP_OR_OVERLAP" in _codes(board)


def test_gate_rejects_invalid_persistence_and_appearance_order() -> None:
    board = _board()
    board.scenes[2].persistent_objects.append("not_inherited")
    board.scenes[2].appearance_sequence = []
    codes = _codes(board)
    assert "PERSISTENT_OBJECT_NOT_INHERITED" in codes
    assert "APPEARANCE_SEQUENCE_INVALID" in codes
