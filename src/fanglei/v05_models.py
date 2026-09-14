"""Typed V0.5 narration, alignment, timeline, and renderer contracts."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NarrationNormalization(StrictModel):
    type: Literal[
        "abbreviation_pronunciation", "number_pronunciation", "percentage_pronunciation",
        "year_pronunciation", "institution_pronunciation", "pause",
    ]
    source: str
    replacement: str
    reason: str


class NarrationSentence(StrictModel):
    sentence_id: str
    original_text: str
    narration_text: str
    normalization_reason: str
    normalizations: list[NarrationNormalization] = Field(default_factory=list)
    pause_after_ms: int = Field(default=0, ge=0)


class SemanticValidation(StrictModel):
    passed: bool
    canonical_original_hash: str
    canonical_narration_hash: str
    issues: list[str] = Field(default_factory=list)


class NarrationDocument(StrictModel):
    schema_version: Literal["5.0"] = "5.0"
    run_id: str
    script_id: str
    language: str = "zh-CN"
    sentences: list[NarrationSentence] = Field(min_length=1)
    semantic_validation: SemanticValidation


class AudioMetadata(StrictModel):
    schema_version: Literal["5.0"] = "5.0"
    path: Literal["audio/narration.wav"] = "audio/narration.wav"
    format: Literal["wav"] = "wav"
    codec: Literal["pcm_s16le"] = "pcm_s16le"
    sample_rate_hz: int = Field(gt=0)
    channels: Literal[1] = 1
    duration_ms: int = Field(gt=0)
    sha256: str
    provider: str
    voice_id: str
    native_timestamps: list[dict] | None = None


class AlignedSentence(StrictModel):
    sentence_id: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    confidence: float = Field(ge=0, le=1)
    timing_source: Literal["native_timestamp", "forced_alignment", "sentence_asr", "deterministic_fake"]

    @model_validator(mode="after")
    def timing_advances(self) -> "AlignedSentence":
        if self.end_ms <= self.start_ms:
            raise ValueError("sentence timing must advance")
        return self


class AlignmentDocument(StrictModel):
    schema_version: Literal["5.0"] = "5.0"
    run_id: str
    audio_path: Literal["audio/narration.wav"] = "audio/narration.wav"
    audio_sha256: str
    audio_duration_ms: int = Field(gt=0)
    provider: str
    method: str
    sentences: list[AlignedSentence] = Field(min_length=1)
    coverage_ratio: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    fallback_used: bool = False
    warnings: list[str] = Field(default_factory=list)


class TimelineSpan(StrictModel):
    sentence_id: str | None = None
    beat_id: str | None = None
    scene_id: str | None = None
    sentence_ids: list[str] = Field(default_factory=list)
    beat_ids: list[str] = Field(default_factory=list)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    timing_source: Literal["real_sentence_alignment"] = "real_sentence_alignment"

    @model_validator(mode="after")
    def timing_advances(self) -> "TimelineSpan":
        if self.end_ms <= self.start_ms:
            raise ValueError("timeline timing must advance")
        return self


class TimelineGap(StrictModel):
    after_sentence_id: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    duration_ms: int = Field(gt=0)
    visual_policy: Literal["hold_previous_canvas"] = "hold_previous_canvas"


class TimelineValidation(StrictModel):
    passed: bool
    actual_audio_duration_ms: int
    estimated_duration_reference_ms: int | None = None
    forced_to_estimate: Literal[False] = False
    issues: list[str] = Field(default_factory=list)


class TimelineDocument(StrictModel):
    schema_version: Literal["5.0"] = "5.0"
    run_id: str
    timing_authority: Literal["real_narration_audio"] = "real_narration_audio"
    audio: dict
    alignment: dict
    sentences: list[TimelineSpan]
    beats: list[TimelineSpan]
    scenes: list[TimelineSpan]
    gaps: list[TimelineGap] = Field(default_factory=list)
    validation: TimelineValidation
