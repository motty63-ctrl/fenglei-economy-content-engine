"""Provider-neutral narration synthesis interface and deterministic fake."""
from __future__ import annotations

from dataclasses import dataclass
import io
from typing import Protocol
import wave

from fanglei.v05_models import NativeTimingEvent, NarrationSentence, NarrationSynthesisConfig


@dataclass(frozen=True)
class NarrationRequest:
    run_id: str
    narration_text: str
    sentences: list[NarrationSentence]
    sample_rate_hz: int = 24000
    channels: int = 1
    codec: str = "pcm_s16le"


@dataclass(frozen=True)
class NarrationAudioResult:
    audio_bytes: bytes
    native_timestamps: tuple[NativeTimingEvent, ...] = ()
    provider_request_id: str | None = None


class NarrationProvider(Protocol):
    name: str
    model: str
    provider_type: str

    def synthesize(self, request: NarrationRequest,
                   config: NarrationSynthesisConfig) -> NarrationAudioResult: ...


class FakeNarrationProvider:
    name = "fake"
    model = "deterministic-silence-v1"
    provider_type = "fake"

    def synthesize(self, request: NarrationRequest,
                   config: NarrationSynthesisConfig | None = None) -> NarrationAudioResult:
        spoken_characters = sum(1 for char in request.narration_text if not char.isspace())
        duration_ms = max(500, spoken_characters * 250)
        frame_count = round(request.sample_rate_hz * duration_ms / 1000)
        output = io.BytesIO()
        with wave.open(output, "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(request.sample_rate_hz)
            stream.writeframes(b"\x00\x00" * frame_count)
        return NarrationAudioResult(audio_bytes=output.getvalue())
