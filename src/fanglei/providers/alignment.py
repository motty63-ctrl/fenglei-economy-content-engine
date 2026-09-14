"""Independent narration-to-audio alignment provider boundary."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from fanglei.v05_models import AlignedSentence, AudioMetadata, NarrationDocument


@dataclass(frozen=True)
class AlignmentRequest:
    narration: NarrationDocument
    audio: AudioMetadata


@dataclass(frozen=True)
class AlignmentResult:
    sentences: list[AlignedSentence]
    confidence: float
    warnings: tuple[str, ...] = ()


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
