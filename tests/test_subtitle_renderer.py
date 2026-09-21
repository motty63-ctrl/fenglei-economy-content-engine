from fanglei.subtitle_renderer import render_subtitle_layer
from fanglei.v1b_models import SubtitleTrack
from fanglei.visual_system_v1 import VisualTheme


def _track() -> SubtitleTrack:
    text = "同一个GDP，两个数字，到底谁错了？"
    return SubtitleTrack.model_validate({
        "run_id": "run-1", "script_id": "script-1",
        "source": {"script_sha256": "a" * 64, "alignment_sha256": "b" * 64,
                   "alignment_audio_sha256": "c" * 64},
        "cues": [{"cue_id": "cue-1", "sentence_id": "sentence_001", "text": text,
                  "start_ms": 500, "end_ms": 3521, "font_size_px": 52,
                  "lines": [{"line_id": "line-1", "text": text[:12], "start_char": 0,
                             "end_char": 12},
                            {"line_id": "line-2", "text": text[12:], "start_char": 12,
                             "end_char": len(text)}],
                  "emphasis_spans": [{"start_char": 3, "end_char": 6, "text": "GDP",
                                       "kind": "acronym"}]}],
        "validation": {"passed": True, "sentence_coverage": 1.0,
                       "text_exact_match": True, "timing_exact_match": True}
    })


def test_layer_uses_reserved_zone_and_does_not_target_primitives():
    bundle = render_subtitle_layer(_track(), VisualTheme())
    assert "left:96px" in bundle.css and "top:1480px" in bundle.css
    assert ".hook-stage" not in bundle.css
    assert ".number-transform" not in bundle.css
    assert "pointer-events:none" in bundle.css


def test_layer_keeps_exact_gap_timing_and_accessible_text():
    bundle = render_subtitle_layer(_track(), VisualTheme())
    assert 'data-start-ms="500"' in bundle.html
    assert 'data-end-ms="3521"' in bundle.html
    assert 'aria-label="同一个GDP，两个数字，到底谁错了？"' in bundle.html
    assert "[start,end)" in bundle.javascript


def test_emphasis_markup_preserves_plain_text_and_line_boundaries():
    bundle = render_subtitle_layer(_track(), VisualTheme())
    assert '<span class="subtitle-emphasis subtitle-emphasis-acronym">GDP</span>' in bundle.html
    assert bundle.qa_metadata["cue_count"] == 1
    assert bundle.qa_metadata["line_counts"] == [2]
    assert bundle.qa_metadata["minimum_font_size_px"] == 52


def test_qa_probe_exports_actual_dom_bounds_hook():
    bundle = render_subtitle_layer(_track(), VisualTheme())
    assert "getBoundingClientRect" in bundle.javascript
    assert "v1b-layout-qa" in bundle.html
    assert bundle.qa_metadata["reserved_zone"] == {"x": 96, "y": 1480, "width": 888, "height": 260}
