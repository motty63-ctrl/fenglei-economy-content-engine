"""Strict V1.0b subtitle and audio-mastering artifact contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SubtitleRect(StrictModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class SubtitleSource(StrictModel):
    script_path: Literal["script.json"] = "script.json"
    script_sha256: str = Field(min_length=64, max_length=64)
    alignment_path: Literal["alignment.json"] = "alignment.json"
    alignment_sha256: str = Field(min_length=64, max_length=64)
    alignment_audio_sha256: str = Field(min_length=64, max_length=64)


class SubtitleLayout(StrictModel):
    canvas_width: int = 1080
    canvas_height: int = 1920
    reserved_zone: SubtitleRect = Field(
        default_factory=lambda: SubtitleRect(x=96, y=1480, width=888, height=260)
    )
    maximum_lines: Literal[2] = 2
    default_font_size_px: int = Field(default=52, ge=40)
    minimum_font_size_px: int = Field(default=40, ge=40)
    line_height: float = Field(default=1.28, gt=1.0, le=1.6)
    horizontal_padding_px: int = Field(default=36, ge=0)
    vertical_padding_px: int = Field(default=24, ge=0)

    @model_validator(mode="after")
    def font_range_is_valid(self) -> "SubtitleLayout":
        if self.minimum_font_size_px > self.default_font_size_px:
            raise ValueError("minimum font size exceeds default font size")
        return self


class SubtitleLine(StrictModel):
    line_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)

    @model_validator(mode="after")
    def range_advances(self) -> "SubtitleLine":
        if self.end_char <= self.start_char:
            raise ValueError("subtitle line range must advance")
        return self


class EmphasisSpan(StrictModel):
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)
    text: str = Field(min_length=1)
    kind: Literal["number", "acronym", "keyword"]

    @model_validator(mode="after")
    def range_advances(self) -> "EmphasisSpan":
        if self.end_char <= self.start_char:
            raise ValueError("emphasis range must advance")
        return self


class SubtitleCue(StrictModel):
    cue_id: str = Field(min_length=1)
    sentence_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    font_size_px: int = Field(ge=40)
    lines: list[SubtitleLine] = Field(min_length=1, max_length=2)
    emphasis_spans: list[EmphasisSpan] = Field(default_factory=list, max_length=2)

    @model_validator(mode="after")
    def validate_integrity(self) -> "SubtitleCue":
        if self.end_ms <= self.start_ms:
            raise ValueError("subtitle cue timing must advance")
        cursor = 0
        rebuilt: list[str] = []
        for line in self.lines:
            if line.start_char != cursor or line.end_char > len(self.text):
                raise ValueError("subtitle lines must form contiguous ranges")
            if self.text[line.start_char:line.end_char] != line.text:
                raise ValueError("subtitle lines must reconstruct approved text")
            rebuilt.append(line.text)
            cursor = line.end_char
        if cursor != len(self.text) or "".join(rebuilt) != self.text:
            raise ValueError("subtitle lines must reconstruct approved text")

        previous_end = -1
        emphasized = 0
        for span in sorted(self.emphasis_spans, key=lambda item: item.start_char):
            if span.start_char < previous_end:
                raise ValueError("subtitle emphasis spans must not overlap")
            if span.end_char > len(self.text) or self.text[span.start_char:span.end_char] != span.text:
                raise ValueError("subtitle emphasis must be an exact continuous substring")
            previous_end = span.end_char
            emphasized += span.end_char - span.start_char
        if self.emphasis_spans and emphasized / len(self.text) > 0.4:
            raise ValueError("subtitle emphasis exceeds forty percent")
        return self


class SubtitleValidation(StrictModel):
    passed: bool
    sentence_coverage: float = Field(ge=0, le=1)
    text_exact_match: bool
    timing_exact_match: bool
    issues: list[str] = Field(default_factory=list)


class SubtitleTrack(StrictModel):
    schema_version: Literal["subtitle_track.v1"] = "subtitle_track.v1"
    run_id: str = Field(min_length=1)
    script_id: str = Field(min_length=1)
    timing_source: Literal["approved_sentence_alignment"] = "approved_sentence_alignment"
    source: SubtitleSource
    layout: SubtitleLayout = Field(default_factory=SubtitleLayout)
    cues: list[SubtitleCue] = Field(min_length=1)
    validation: SubtitleValidation

    @model_validator(mode="after")
    def unique_cues(self) -> "SubtitleTrack":
        cue_ids = [cue.cue_id for cue in self.cues]
        sentence_ids = [cue.sentence_id for cue in self.cues]
        if len(cue_ids) != len(set(cue_ids)) or len(sentence_ids) != len(set(sentence_ids)):
            raise ValueError("subtitle cue and sentence IDs must be unique")
        return self


class AudioMasteringConfig(StrictModel):
    target_integrated_lufs: float = -16.0
    maximum_true_peak_dbtp: float = -1.0
    true_peak_headroom_db: float = Field(default=0.2, ge=0)
    loudness_tolerance_lu: float = Field(default=0.5, gt=0)
    maximum_duration_delta_ms: int = Field(default=20, ge=0)
    maximum_edge_silence_delta_ms: int = Field(default=20, ge=0)
    silence_threshold_dbfs: float = -45.0
    edge_activity_below_95th_db: float = Field(default=18.0, gt=0)
    output_format: Literal["wav"] = "wav"
    output_codec: Literal["pcm_s16le"] = "pcm_s16le"
    sample_rate_hz: Literal[24000] = 24000
    channels: Literal[1] = 1


class AudioMeasurement(StrictModel):
    path: str = Field(min_length=1)
    sha256: str = Field(min_length=64, max_length=64)
    duration_ms: int = Field(gt=0)
    leading_silence_ms: int = Field(ge=0)
    trailing_silence_ms: int = Field(ge=0)
    integrated_lufs: float
    true_peak_dbtp: float
    format: Literal["wav"] = "wav"
    codec: Literal["pcm_s16le"] = "pcm_s16le"
    sample_rate_hz: int = Field(gt=0)
    channels: int = Field(gt=0)


class MasteringGate(StrictModel):
    passed: bool
    issues: list[str] = Field(default_factory=list)


class AudioMasteringDocument(StrictModel):
    schema_version: Literal["audio_mastering.v1"] = "audio_mastering.v1"
    run_id: str = Field(min_length=1)
    engine: str = Field(min_length=1)
    method: Literal["ebu_r128_two_pass"] = "ebu_r128_two_pass"
    config: AudioMasteringConfig = Field(default_factory=AudioMasteringConfig)
    input: AudioMeasurement
    output: AudioMeasurement
    duration_delta_ms: int
    leading_silence_delta_ms: int
    trailing_silence_delta_ms: int
    gate: MasteringGate

    @model_validator(mode="after")
    def deltas_match_measurements(self) -> "AudioMasteringDocument":
        if self.duration_delta_ms != self.output.duration_ms - self.input.duration_ms:
            raise ValueError("duration delta does not match measurements")
        if (
            self.leading_silence_delta_ms
            != self.output.leading_silence_ms - self.input.leading_silence_ms
        ):
            raise ValueError("leading silence delta does not match measurements")
        if (
            self.trailing_silence_delta_ms
            != self.output.trailing_silence_ms - self.input.trailing_silence_ms
        ):
            raise ValueError("trailing silence delta does not match measurements")
        return self
