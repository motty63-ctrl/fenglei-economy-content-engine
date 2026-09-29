"""Typed V0.5 narration, alignment, timeline, and renderer contracts."""
from __future__ import annotations

from datetime import datetime
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from fanglei.v1b_models import SubtitleLayout


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
    tts_spoken_text: str | None = None
    normalization_reason: str
    normalizations: list[NarrationNormalization] = Field(default_factory=list)
    pause_after_ms: int = Field(default=0, ge=0)

    @property
    def spoken_text(self) -> str:
        """Return provider-bound speech text, falling back for legacy 5.0 artifacts."""
        return self.tts_spoken_text if self.tts_spoken_text is not None else self.narration_text


class SemanticValidation(StrictModel):
    passed: bool
    canonical_original_hash: str
    canonical_narration_hash: str
    issues: list[str] = Field(default_factory=list)


class NarrationDocument(StrictModel):
    schema_version: Literal["5.0", "5.1"] = "5.0"
    run_id: str
    script_id: str
    language: str = "zh-CN"
    sentences: list[NarrationSentence] = Field(min_length=1)
    semantic_validation: SemanticValidation

    @model_validator(mode="after")
    def require_explicit_spoken_text_in_v51(self) -> "NarrationDocument":
        if self.schema_version == "5.1" and any(
            row.tts_spoken_text is None or row.narration_text != row.original_text
            for row in self.sentences
        ):
            raise ValueError("NARRATION_V51_REQUIRES_DISPLAY_AND_TTS_TEXT")
        return self


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
    schema_version: Literal["5.1", "5.2"] = "5.1"
    run_id: str
    audio_sha256: str
    script_sha256: str | None = None
    status: Literal["approved", "test_only", "changes_required"]
    reviewer: str
    reviewed_at: str
    voice_approved: bool
    rate_approved: bool
    pauses_approved: bool
    number_pronunciation_approved: bool
    reason_code: str | None = None
    findings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_v52_human_review(self) -> "VoiceReviewDocument":
        if self.schema_version == "5.1" and self.status == "changes_required":
            raise ValueError("CHANGES_REQUIRED_REVIEW_REQUIRES_SCHEMA_5_2")
        if self.schema_version == "5.2":
            if not self.script_sha256 or not re.fullmatch(r"[0-9a-f]{64}", self.script_sha256):
                raise ValueError("VOICE_REVIEW_SCRIPT_HASH_REQUIRED")
            if not self.reviewer.strip():
                raise ValueError("VOICE_REVIEWER_REQUIRED")
            try:
                reviewed = datetime.fromisoformat(self.reviewed_at)
            except ValueError as error:
                raise ValueError("VOICE_REVIEW_TIMESTAMP_INVALID") from error
            if reviewed.tzinfo is None or reviewed.utcoffset() is None:
                raise ValueError("VOICE_REVIEW_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
            if self.status == "changes_required":
                if not self.reason_code or not self.reason_code.strip():
                    raise ValueError("VOICE_REVIEW_REASON_REQUIRED")
                if not self.findings or any(not item.strip() for item in self.findings):
                    raise ValueError("VOICE_REVIEW_FINDINGS_REQUIRED")
                if all((self.voice_approved, self.rate_approved, self.pauses_approved,
                        self.number_pronunciation_approved)):
                    raise ValueError("CHANGES_REQUIRED_REVIEW_MUST_REJECT_A_CHECK")
            elif self.status == "approved" and not all((
                self.voice_approved, self.rate_approved, self.pauses_approved,
                self.number_pronunciation_approved,
            )):
                raise ValueError("VOICE_REVIEW_CHECKS_INCOMPLETE")
        return self


class AlignedSentence(StrictModel):
    sentence_id: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    confidence: float = Field(ge=0, le=1)
    timing_source: Literal[
        "native_timestamp", "forced_alignment", "sentence_asr", "deterministic_fake",
        "proportional_sentence",
    ]
    text: str | None = None
    confidence_source: str | None = None
    provider: str | None = None
    method: str | None = None
    audio_sha256: str | None = None
    normalized_ref: str | None = None
    normalized_asr: str | None = None
    measured: bool | None = None
    interpolated: bool | None = None

    @model_validator(mode="after")
    def timing_advances(self) -> "AlignedSentence":
        if self.end_ms <= self.start_ms:
            raise ValueError("sentence timing must advance")
        return self


class HumanAlignmentOverride(StrictModel):
    reviewer_status: Literal["approved"] = "approved"
    reviewer: str
    reviewed_sentences: int = Field(gt=0)
    total_sentences: int = Field(gt=0)
    candidate_hash: str
    audio_sha256: str
    automatic_text_consistency_passed: Literal[False] = False
    automatic_text_consistency_issue: Literal["ALIGNMENT_TEXT_MISMATCH"] = "ALIGNMENT_TEXT_MISMATCH"
    override_scope: Literal["candidate_and_audio_sha"] = "candidate_and_audio_sha"
    global_gate_changed: Literal[False] = False


class AlignmentReviewDocument(HumanAlignmentOverride):
    schema_version: Literal["5.2"] = "5.2"
    artifact_type: Literal["alignment_review"] = "alignment_review"
    run_id: str
    reviewed_at: str
    reviewed_sentence_ids: list[str] = Field(min_length=1)
    reviewed_coverage: str
    voice_review_hash: str
    model_id: str
    model_revision: str
    timestamps_modified: Literal[False] = False
    raw_measurements_modified: Literal[False] = False


class AlignmentDocument(StrictModel):
    schema_version: Literal["5.0", "5.2"] = "5.0"
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
    model_id: str | None = None
    model_revision: str | None = None
    confidence_source: str | None = None
    recognized_text: str | None = None
    normalized_ref: str | None = None
    normalized_asr: str | None = None
    text_match_cer: float | None = Field(default=None, ge=0)
    voice_review_hash: str | None = None
    review_hash: str | None = None
    human_review_override: HumanAlignmentOverride | None = None

    @model_validator(mode="after")
    def require_v52_provenance(self) -> "AlignmentDocument":
        if self.schema_version == "5.2" and not all((
            self.model_id, self.model_revision, self.confidence_source,
            self.recognized_text, self.normalized_ref, self.normalized_asr,
            self.voice_review_hash,
        )):
            raise ValueError("schema 5.2 requires alignment provenance")
        if self.schema_version == "5.2" and any(
            sentence.text is None
            or not sentence.confidence_source
            or not sentence.provider
            or not sentence.method
            or not sentence.audio_sha256
            or sentence.measured is not True
            or sentence.interpolated is not False
            for sentence in self.sentences
        ):
            raise ValueError("schema 5.2 requires alignment provenance")
        return self


class AlignmentCandidateDocument(AlignmentDocument):
    schema_version: Literal["5.2"] = "5.2"
    artifact_type: Literal["alignment_candidate"] = "alignment_candidate"
    model_id: str
    model_revision: str
    confidence_source: str
    recognized_text: str
    normalized_ref: str
    normalized_asr: str
    text_match_cer: float = Field(ge=0)
    voice_review_hash: str

    @model_validator(mode="after")
    def require_measured_sentence_provenance(self) -> "AlignmentCandidateDocument":
        for sentence in self.sentences:
            if (
                sentence.text is None
                or not sentence.confidence_source
                or not sentence.provider
                or not sentence.method
                or not sentence.audio_sha256
                or sentence.measured is not True
                or sentence.interpolated is not False
            ):
                raise ValueError("schema 5.2 requires measured sentence provenance")
        return self


class TimelineSpan(StrictModel):
    sentence_id: str | None = None
    beat_id: str | None = None
    scene_id: str | None = None
    sentence_ids: list[str] = Field(default_factory=list)
    beat_ids: list[str] = Field(default_factory=list)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    timing_source: Literal["real_sentence_alignment", "proportional_sentence_timing"] = "real_sentence_alignment"

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


class TimelineMotionCue(StrictModel):
    """A bounded presentation-only entrance for one existing SVG object."""

    object_id: str = Field(min_length=1)
    effect: Literal["fade_in"] = "fade_in"
    delay_ms: int = Field(ge=0)
    duration_ms: int = Field(gt=0, le=500)


class TimelineSceneVisual(StrictModel):
    scene_id: str = Field(min_length=1)
    order: int = Field(gt=0)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    asset_path: str = Field(min_length=1)
    asset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    claim_ids: list[str] = Field(default_factory=list)
    sentence_ids: list[str] = Field(default_factory=list)
    object_ids: list[str] = Field(min_length=1)
    motion: list[TimelineMotionCue] = Field(min_length=1)

    @model_validator(mode="after")
    def scene_ranges_and_motion_are_valid(self) -> "TimelineSceneVisual":
        if self.end_ms <= self.start_ms:
            raise ValueError("timeline visual scene must have a positive range")
        if len(self.object_ids) != len(set(self.object_ids)):
            raise ValueError("timeline visual object IDs must be unique")
        motion_ids = [item.object_id for item in self.motion]
        if len(motion_ids) != len(set(motion_ids)) or set(motion_ids) != set(self.object_ids):
            raise ValueError("timeline motion must cover each approved object exactly once")
        duration = self.end_ms - self.start_ms
        if any(item.delay_ms + item.duration_ms > duration for item in self.motion):
            raise ValueError("timeline motion exceeds its scene range")
        return self


class TimelineSubtitleCue(StrictModel):
    cue_id: str = Field(min_length=1)
    sentence_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    lines: list[str] = Field(min_length=1, max_length=2)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    font_size_px: int = Field(ge=40)

    @model_validator(mode="after")
    def cue_is_valid(self) -> "TimelineSubtitleCue":
        if (
            self.end_ms <= self.start_ms
            or any(not line.strip() for line in self.lines)
            or "".join(self.lines) != self.text
        ):
            raise ValueError("timeline subtitle cue must preserve exact display text and timing")
        return self


class TimelineComposition(StrictModel):
    """Hash-bound V0.2 composition metadata; the V0.1 timeline remains schema 5.0."""

    schema_version: Literal["timeline-composition/1.0"] = "timeline-composition/1.0"
    visual_candidate_id: int = Field(gt=0)
    visual_bundle_artifact: str = Field(min_length=1)
    visual_review_artifact: str = Field(min_length=1)
    visual_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    visual_review_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    storyboard_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    storyboard_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    storyboard_approval_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    script_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    script_approval_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    audio_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    audio_review_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    alignment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    subtitle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dependency_hashes: dict[str, str]
    alignment_method: str = Field(min_length=1)
    timing_quality: Literal["estimated", "measured"]
    scene_visuals: list[TimelineSceneVisual] = Field(min_length=1)
    subtitle_layout: SubtitleLayout
    subtitle_cues: list[TimelineSubtitleCue] = Field(min_length=1)
    preview_review_status: Literal["pending_human_preview_review"] = "pending_human_preview_review"
    preview_only: Literal[True] = True

    @model_validator(mode="after")
    def composition_bindings_are_valid(self) -> "TimelineComposition":
        expected_bundle = "visual_assets" if self.visual_candidate_id == 1 else (
            f"visual_assets_candidate_{self.visual_candidate_id}"
        )
        expected_review = f"human_visual_asset_review_candidate_{self.visual_candidate_id}.json"
        if self.visual_bundle_artifact != expected_bundle or self.visual_review_artifact != expected_review:
            raise ValueError("timeline composition visual artifact identity is invalid")
        if not self.dependency_hashes or any(
            not key.strip() or not re.fullmatch(r"[0-9a-f]{64}", value)
            for key, value in self.dependency_hashes.items()
        ):
            raise ValueError("timeline composition dependencies must be named lowercase SHA-256 values")
        required = {
            self.visual_bundle_artifact: self.visual_bundle_sha256,
            self.visual_review_artifact: self.visual_review_sha256,
            "human_storyboard_candidate.json": self.storyboard_artifact_sha256,
            "human_storyboard_approval.json": self.storyboard_approval_sha256,
            "script.json": self.script_sha256,
            "human_script_approval.json": self.script_approval_sha256,
            "audio/narration.wav": self.audio_sha256,
            "audio/review.json": self.audio_review_sha256,
            "alignment.json": self.alignment_sha256,
            "subtitle_track.json": self.subtitle_sha256,
        }
        if any(self.dependency_hashes.get(name) != digest for name, digest in required.items()):
            raise ValueError("timeline composition does not match its dependency hash map")
        scene_ids = [item.scene_id for item in self.scene_visuals]
        if (
            len(scene_ids) != len(set(scene_ids))
            or [item.order for item in self.scene_visuals] != list(range(1, len(scene_ids) + 1))
        ):
            raise ValueError("timeline composition scene IDs must be unique and ordered")
        cue_ids = [item.cue_id for item in self.subtitle_cues]
        sentence_ids = [item.sentence_id for item in self.subtitle_cues]
        if len(cue_ids) != len(set(cue_ids)) or len(sentence_ids) != len(set(sentence_ids)):
            raise ValueError("timeline subtitle cue identities must be unique")
        previous_end = -1
        for cue in self.subtitle_cues:
            if cue.start_ms < previous_end:
                raise ValueError("timeline subtitle cues must remain ordered and non-overlapping")
            previous_end = cue.end_ms
        return self


class TimelineDocument(StrictModel):
    schema_version: Literal["5.0", "5.1"] = "5.0"
    run_id: str
    timing_authority: Literal["real_narration_audio"] = "real_narration_audio"
    audio: dict
    alignment: dict
    sentences: list[TimelineSpan]
    beats: list[TimelineSpan]
    scenes: list[TimelineSpan]
    gaps: list[TimelineGap] = Field(default_factory=list)
    validation: TimelineValidation
    composition: TimelineComposition | None = None

    @model_validator(mode="after")
    def composition_matches_timeline(self) -> "TimelineDocument":
        if self.schema_version == "5.0" and self.composition is not None:
            raise ValueError("timeline schema 5.0 cannot carry V0.2 composition metadata")
        if self.schema_version == "5.1" and self.composition is None:
            raise ValueError("timeline schema 5.1 requires approved composition metadata")
        if self.composition is not None:
            bound_scenes = self.composition.scene_visuals
            if [(row.scene_id, row.start_ms, row.end_ms) for row in bound_scenes] != [
                (row.scene_id, row.start_ms, row.end_ms) for row in self.scenes
            ]:
                raise ValueError("timeline composition scene mapping differs from compiled scenes")
            if any(
                current.start_ms < previous.end_ms
                for previous, current in zip(bound_scenes, bound_scenes[1:])
            ):
                raise ValueError("timeline composition scene ranges overlap")
            sentence_ids = [row.sentence_id for row in self.sentences if row.sentence_id]
            if [row.sentence_id for row in self.composition.subtitle_cues] != sentence_ids:
                raise ValueError("timeline composition subtitle coverage differs from sentences")
            if any(row.end_ms > int(self.audio.get("duration_ms", 0)) for row in self.composition.subtitle_cues):
                raise ValueError("timeline subtitle cue exceeds audio duration")
        return self
