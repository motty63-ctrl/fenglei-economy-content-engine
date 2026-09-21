from __future__ import annotations

import pytest
from pydantic import ValidationError

from fanglei.v1b_models import (
    AudioMasteringDocument,
    SubtitleCue,
    SubtitleTrack,
)


def _cue(**overrides):
    value = {
        "cue_id": "subtitle_sentence_001",
        "sentence_id": "sentence_001",
        "text": "同一个GDP，两个数字，到底谁错了？",
        "start_ms": 500,
        "end_ms": 3521,
        "font_size_px": 52,
        "lines": [
            {"line_id": "line_01", "text": "同一个GDP，两个数字，", "start_char": 0, "end_char": 12},
            {"line_id": "line_02", "text": "到底谁错了？", "start_char": 12, "end_char": 18},
        ],
        "emphasis_spans": [
            {"start_char": 3, "end_char": 6, "text": "GDP", "kind": "keyword"}
        ],
    }
    value.update(overrides)
    return value


def _track(**overrides):
    value = {
        "schema_version": "subtitle_track.v1",
        "run_id": "gdp-run",
        "script_id": "script_001",
        "timing_source": "approved_sentence_alignment",
        "source": {
            "script_path": "script.json",
            "script_sha256": "a" * 64,
            "alignment_path": "alignment.json",
            "alignment_sha256": "b" * 64,
            "alignment_audio_sha256": "c" * 64,
        },
        "layout": {
            "canvas_width": 1080,
            "canvas_height": 1920,
            "reserved_zone": {"x": 96, "y": 1480, "width": 888, "height": 260},
            "maximum_lines": 2,
            "default_font_size_px": 52,
            "minimum_font_size_px": 40,
            "line_height": 1.28,
            "horizontal_padding_px": 36,
            "vertical_padding_px": 24,
        },
        "cues": [_cue()],
        "validation": {
            "passed": True,
            "sentence_coverage": 1.0,
            "text_exact_match": True,
            "timing_exact_match": True,
            "issues": [],
        },
    }
    value.update(overrides)
    return value


def _mastering_report(**overrides):
    value = {
        "schema_version": "audio_mastering.v1",
        "run_id": "gdp-run",
        "engine": "ffmpeg_loudnorm",
        "method": "ebu_r128_two_pass",
        "config": {
            "target_integrated_lufs": -16.0,
            "maximum_true_peak_dbtp": -1.0,
            "maximum_duration_delta_ms": 20,
            "maximum_edge_silence_delta_ms": 20,
            "output_format": "wav",
            "output_codec": "pcm_s16le",
            "sample_rate_hz": 24000,
            "channels": 1,
        },
        "input": {
            "path": "audio/narration.wav",
            "sha256": "a" * 64,
            "duration_ms": 60611,
            "leading_silence_ms": 500,
            "trailing_silence_ms": 40,
            "integrated_lufs": -21.4,
            "true_peak_dbtp": -6.1,
            "format": "wav",
            "codec": "pcm_s16le",
            "sample_rate_hz": 24000,
            "channels": 1,
        },
        "output": {
            "path": "audio/mastered_narration.wav",
            "sha256": "b" * 64,
            "duration_ms": 60611,
            "leading_silence_ms": 500,
            "trailing_silence_ms": 40,
            "integrated_lufs": -16.0,
            "true_peak_dbtp": -1.2,
            "format": "wav",
            "codec": "pcm_s16le",
            "sample_rate_hz": 24000,
            "channels": 1,
        },
        "duration_delta_ms": 0,
        "leading_silence_delta_ms": 0,
        "trailing_silence_delta_ms": 0,
        "gate": {"passed": True, "issues": []},
    }
    value.update(overrides)
    return value


def test_subtitle_cue_rejects_more_than_two_lines() -> None:
    lines = [
        {"line_id": f"line_{index}", "text": text, "start_char": index - 1, "end_char": index}
        for index, text in enumerate("同一个", start=1)
    ]
    with pytest.raises(ValidationError):
        SubtitleCue.model_validate(_cue(text="同一个", lines=lines, emphasis_spans=[]))


def test_subtitle_cue_lines_must_strictly_reconstruct_text() -> None:
    broken = _cue()
    broken["lines"][1]["text"] = "到底谁对了？"
    with pytest.raises(ValidationError, match="reconstruct"):
        SubtitleCue.model_validate(broken)


def test_subtitle_emphasis_must_be_exact_continuous_substring() -> None:
    broken = _cue(emphasis_spans=[
        {"start_char": 3, "end_char": 6, "text": "G-D", "kind": "keyword"}
    ])
    with pytest.raises(ValidationError, match="substring"):
        SubtitleCue.model_validate(broken)


def test_subtitle_track_accepts_strict_valid_contract() -> None:
    track = SubtitleTrack.model_validate(_track())
    assert track.schema_version == "subtitle_track.v1"
    assert track.cues[0].font_size_px == 52


def test_mastering_report_records_temporal_integrity() -> None:
    report = AudioMasteringDocument.model_validate(_mastering_report())
    assert report.duration_delta_ms == 0
    assert report.leading_silence_delta_ms == 0
    assert report.trailing_silence_delta_ms == 0
    assert report.output.sample_rate_hz == 24000
    assert report.output.channels == 1


def test_mastering_report_rejects_inconsistent_delta() -> None:
    with pytest.raises(ValidationError, match="duration delta"):
        AudioMasteringDocument.model_validate(_mastering_report(duration_delta_ms=8))

