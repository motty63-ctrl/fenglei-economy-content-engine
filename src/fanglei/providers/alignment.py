"""Independent narration-to-audio alignment provider boundary."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from fanglei.v05_models import (
    AlignedSentence, AudioMetadata, NarrationDocument, VoiceReviewDocument,
)


@dataclass(frozen=True)
class AlignmentRequest:
    narration: NarrationDocument
    audio: AudioMetadata
    audio_path: Path | None = None
    audio_sha256: str | None = None
    audio_duration_ms: int | None = None
    approved_review: VoiceReviewDocument | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "audio_path", self.audio_path or Path(self.audio.path))
        object.__setattr__(self, "audio_sha256", self.audio_sha256 or self.audio.sha256)
        object.__setattr__(self, "audio_duration_ms", self.audio_duration_ms or self.audio.duration_ms)


@dataclass(frozen=True)
class AlignmentResult:
    sentences: list[AlignedSentence]
    confidence: float
    warnings: tuple[str, ...] = ()
    provider: str | None = None
    method: str | None = None
    model_id: str | None = None
    model_revision: str | None = None
    score_source: str | None = None
    recognized_text: str | None = None


class AlignmentProvider(Protocol):
    name: str
    method: str

    def align(self, request: AlignmentRequest) -> AlignmentResult: ...


class FakeAlignmentProvider:
    method = "deterministic_fake"

    def __init__(self, confidence: float = .99, name: str = "fake"):
        self.confidence = confidence
        self.name = name

    def align(self, request: AlignmentRequest) -> AlignmentResult:
        weights = [max(1, len(row.narration_text.strip())) for row in request.narration.sentences]
        total_weight = sum(weights)
        elapsed = 0
        consumed_weight = 0
        sentences: list[AlignedSentence] = []
        for index, (row, weight) in enumerate(zip(request.narration.sentences, weights)):
            consumed_weight += weight
            end = request.audio.duration_ms if index == len(weights) - 1 else round(
                request.audio.duration_ms * consumed_weight / total_weight
            )
            sentences.append(AlignedSentence(
                sentence_id=row.sentence_id,
                start_ms=elapsed,
                end_ms=end,
                confidence=self.confidence,
                timing_source="deterministic_fake",
            ))
            elapsed = end
        return AlignmentResult(sentences=sentences, confidence=self.confidence)


class NativeTimestampAlignmentProvider:
    name = "native_timestamp"
    method = "native_timestamp"

    def align(self, request: AlignmentRequest) -> AlignmentResult:
        timestamps = request.audio.native_timestamps or []
        sentences = [AlignedSentence.model_validate(item) for item in timestamps]
        confidence = min((row.confidence for row in sentences), default=0.0)
        return AlignmentResult(sentences=sentences, confidence=confidence)
