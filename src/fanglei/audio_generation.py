"""Canonical PCM WAV validation for provider-generated narration."""
from __future__ import annotations

import io
import wave

from fanglei.artifacts import sha256_bytes
from fanglei.providers.narration import NarrationProvider, NarrationRequest
from fanglei.v05_models import AudioMetadata, NarrationDocument


CANONICAL_SAMPLE_RATE_HZ = 24000


def generate_audio(document: NarrationDocument, provider: NarrationProvider,
                   voice_id: str) -> tuple[bytes, AudioMetadata]:
    request = NarrationRequest(
        run_id=document.run_id,
        narration_text="\n".join(row.narration_text for row in document.sentences),
        sentences=document.sentences,
        voice_id=voice_id,
    )
    result = provider.synthesize(request)
    try:
        with wave.open(io.BytesIO(result.audio_bytes), "rb") as stream:
            channels = stream.getnchannels()
            sample_width = stream.getsampwidth()
            sample_rate = stream.getframerate()
            frame_count = stream.getnframes()
    except (wave.Error, EOFError) as error:
        raise ValueError("AUDIO_WAV_INVALID") from error
    if channels != 1:
        raise ValueError("AUDIO_CHANNELS_INVALID")
    if sample_width != 2:
        raise ValueError("AUDIO_CODEC_INVALID")
    if sample_rate != CANONICAL_SAMPLE_RATE_HZ:
        raise ValueError("AUDIO_SAMPLE_RATE_INVALID")
    duration_ms = round(frame_count * 1000 / sample_rate)
    if duration_ms <= 0:
        raise ValueError("AUDIO_EMPTY")
    metadata = AudioMetadata(
        sample_rate_hz=sample_rate,
        channels=channels,
        duration_ms=duration_ms,
        sha256=sha256_bytes(result.audio_bytes),
        provider=provider.name,
        voice_id=voice_id,
        native_timestamps=result.native_timestamps,
    )
    return result.audio_bytes, metadata
