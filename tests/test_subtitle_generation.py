from __future__ import annotations

import pytest

from fanglei.content_models import ScriptDraft
from fanglei.subtitle_generation import compile_subtitle_track, measure_display_units
from fanglei.v05_models import AlignmentDocument


SCRIPT_SHA = "a" * 64
ALIGNMENT_SHA = "b" * 64
AUDIO_SHA = "c" * 64


def _script(texts: list[str] | None = None) -> ScriptDraft:
    texts = texts or [
        "同一个GDP，两个数字，到底谁错了？",
        "BEA公布的2024年美国实际GDP增长率是2.8%。",
    ]
    sentences = []
    for index, text in enumerate(texts, start=1):
        sentences.append({
            "sentence_id": f"sentence_{index:03d}",
            "section": "hook" if index == 1 else "phenomenon",
            "sentence_type": "interpretation",
            "text": text,
            "claim_ids": [],
        })
    return ScriptDraft.model_validate({
        "script_id": "script_001", "angle_id": "angle_001", "title": "GDP",
        "sentences": sentences,
    })


def _alignment(script: ScriptDraft, *, recognized_text: str = "ASR错误文本") -> AlignmentDocument:
    rows = []
    cursor = 500
    for index, sentence in enumerate(script.sentences):
        duration = 3000 + index * 500
        rows.append({
            "sentence_id": sentence.sentence_id,
            "start_ms": cursor,
            "end_ms": cursor + duration,
            "confidence": 0.9,
            "timing_source": "forced_alignment",
            "text": recognized_text,
        })
        cursor += duration + 500
    return AlignmentDocument.model_validate({
        "schema_version": "5.0",
        "run_id": "gdp-run",
        "audio_sha256": AUDIO_SHA,
        "audio_duration_ms": cursor,
        "provider": "local_whisperx",
        "method": "forced_alignment",
        "sentences": rows,
        "coverage_ratio": 1.0,
        "confidence": 0.9,
        "fallback_used": False,
    })


def _compile(script: ScriptDraft, alignment: AlignmentDocument):
    return compile_subtitle_track(
        script,
        alignment,
        run_id="gdp-run",
        script_sha256=SCRIPT_SHA,
        alignment_sha256=ALIGNMENT_SHA,
    )


def test_compiler_uses_approved_script_text_not_asr_text() -> None:
    script = _script()
    track = _compile(script, _alignment(script, recognized_text="完全不相关的识别结果"))

    assert [cue.text for cue in track.cues] == [row.text for row in script.sentences]
    assert all("识别结果" not in cue.text for cue in track.cues)


def test_compiler_copies_exact_sentence_alignment_timing() -> None:
    script = _script()
    alignment = _alignment(script)
    track = _compile(script, alignment)

    assert [
        (cue.sentence_id, cue.start_ms, cue.end_ms) for cue in track.cues
    ] == [
        (row.sentence_id, row.start_ms, row.end_ms) for row in alignment.sentences
    ]


def test_reordered_alignment_fails_closed() -> None:
    script = _script()
    alignment = _alignment(script)
    alignment.sentences.reverse()

    with pytest.raises(ValueError, match="SUBTITLE_SENTENCE_ORDER_MISMATCH"):
        _compile(script, alignment)


def test_missing_sentence_fails_closed() -> None:
    script = _script()
    alignment = _alignment(script)
    alignment.sentences.pop()

    with pytest.raises(ValueError, match="SUBTITLE_SENTENCE_ORDER_MISMATCH"):
        _compile(script, alignment)


def test_line_breaking_only_inserts_newline_metadata() -> None:
    text = "其实，美国GDP增长率百分之二点七九三二四舍五入到一位小数，结果就是百分之二点八。"
    script = _script([text])
    cue = _compile(script, _alignment(script)).cues[0]

    assert 1 <= len(cue.lines) <= 2
    assert cue.font_size_px >= 40
    assert "".join(line.text for line in cue.lines) == text
    assert [(line.start_char, line.end_char) for line in cue.lines][0][0] == 0
    assert cue.lines[-1].end_char == len(text)


def test_text_that_cannot_fit_two_lines_at_minimum_size_fails() -> None:
    script = _script(["经" * 60])

    with pytest.raises(ValueError, match="SUBTITLE_TEXT_OVERFLOW"):
        _compile(script, _alignment(script))


def test_emphasis_spans_are_exact_substrings_and_limited() -> None:
    script = _script(["BEA公布的2024年美国实际GDP增长率是2.8%。"])
    cue = _compile(script, _alignment(script)).cues[0]

    assert 1 <= len(cue.emphasis_spans) <= 2
    for span in cue.emphasis_spans:
        assert cue.text[span.start_char:span.end_char] == span.text


def test_measure_display_units_treats_ascii_as_narrower_than_cjk() -> None:
    assert measure_display_units("GDP") < measure_display_units("增长率")


def test_gdp_hook_does_not_use_unmeasured_full_width_single_line() -> None:
    # Browser calibration measured this 52 px single line at 891.75 px, beyond
    # the 888 px reserved zone despite the approximate unit estimate.
    script = _script(["同一个GDP，两个数字，到底谁错了？"])
    cue = _compile(script, _alignment(script)).cues[0]
    assert cue.font_size_px < 52 or len(cue.lines) == 2


def test_non_monotonic_or_overlapping_timing_fails() -> None:
    script = _script()
    alignment = _alignment(script)
    alignment.sentences[1].start_ms = alignment.sentences[0].end_ms - 1

    with pytest.raises(ValueError, match="SUBTITLE_ALIGNMENT_OVERLAP"):
        _compile(script, alignment)
