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


ProviderType = Literal["fake", "real"]


class NarrationSynthesisConfig(StrictModel):
    language: str = "zh-CN"
    voice_id: str
    speaking_rate: float = Field(default=1.0, ge=.5, le=2.0)
    pitch_semitones: float = Field(default=0.0, ge=-12, le=12)
    volume_gain_db: float = Field(default=0.0, ge=-20, le=10)


class NativeTimingEvent(StrictModel):
    event_type: Literal["word", "punctuation", "sentence"]
    audio_offset_ms: int = Field(ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    text_offset: int = Field(ge=0)
    text_length: int = Field(ge=0)
    text: str
    source: Literal["provider_native"] = "provider_native"


class AudioMetadata(StrictModel):
    schema_version: Literal["5.0", "5.1"] = "5.0"
    path: Literal["audio/narration.wav"] = "audio/narration.wav"
    format: Literal["wav"] = "wav"
    codec: Literal["pcm_s16le"] = "pcm_s16le"
    sample_rate_hz: int = Field(gt=0)
    channels: Literal[1] = 1
    duration_ms: int = Field(gt=0)
    sha256: str
    provider: str
    provider_type: ProviderType | None = None
    provider_model: str | None = None
    voice_id: str
    language: str | None = None
    speaking_rate: float | None = None
    pitch_semitones: float | None = None
    volume_gain_db: float | None = None
    native_timestamps: list[NativeTimingEvent] | list[dict] | None = None

    @model_validator(mode="after")
    def require_explicit_real_classification(self) -> "AudioMetadata":
        if self.schema_version == "5.1" and self.provider_type is None:
            raise ValueError("provider_type is required for schema 5.1")
        if self.schema_version == "5.0" and self.provider_type is None and self.provider == "fake":
            self.provider_type = "fake"
        return self


class AudioQualityThresholdsModel(StrictModel):
    min_peak: float
    min_rms_dbfs: float
    voiced_frame_rms_dbfs: float
    min_voiced_duration_ms: int
    min_voiced_ratio: float


class AudioQualityDocument(StrictModel):
    schema_version: Literal["5.1"] = "5.1"
    audio_sha256: str
    provider: str
    provider_type: ProviderType
    duration_ms: int = Field(gt=0)
    peak: float = Field(ge=0, le=1)
    peak_dbfs: float | None
    rms: float = Field(ge=0, le=1)
    rms_dbfs: float | None
    voiced_duration_ms: int = Field(ge=0)
    voiced_ratio: float = Field(ge=0, le=1)
    frame_duration_ms: int = 20
    thresholds: AudioQualityThresholdsModel
    passed: bool
    gate_reasons: list[str] = Field(default_factory=list)
    production_eligible: bool


class VoiceReviewDocument(StrictModel):
    schema_version: Literal["5.1"] = "5.1"
    run_id: str
    audio_sha256: str
    status: Literal["approved", "test_only"]
    reviewer: str
    reviewed_at: str
    voice_approved: bool
    rate_approved: bool
    pauses_approved: bool
    number_pronunciation_approved: bool


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
