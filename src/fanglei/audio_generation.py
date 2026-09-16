"""Canonical PCM WAV validation for provider-generated narration."""
from __future__ import annotations

import io
import wave
from dataclasses import dataclass

from fanglei.artifacts import sha256_bytes
from fanglei.audio_quality import AudioQualityThresholds, analyze_audio_quality
from fanglei.providers.narration import NarrationProvider, NarrationRequest
from fanglei.v05_models import (
    AudioMetadata, AudioQualityDocument, NarrationDocument, NarrationSynthesisConfig,
)


CANONICAL_SAMPLE_RATE_HZ = 24000


@dataclass(frozen=True)
class GeneratedAudioBundle:
    audio_bytes: bytes
    metadata: AudioMetadata
    quality: AudioQualityDocument

    def __iter__(self):
        """Keep the V0.5 two-value unpacking contract during migration."""
        yield self.audio_bytes
        yield self.metadata


def generate_audio(document: NarrationDocument, provider: NarrationProvider,
                   config: NarrationSynthesisConfig | str, *, production: bool = False,
                   quality_thresholds: AudioQualityThresholds | None = None) -> GeneratedAudioBundle:
    if isinstance(config, str):
        config = NarrationSynthesisConfig(voice_id=config)
    provider_type = getattr(provider, "provider_type", "fake")
    if production and provider_type != "real":
        raise ValueError("AUDIO_PROVIDER_NOT_REAL")
    request = NarrationRequest(
        run_id=document.run_id,
        narration_text="\n".join(row.narration_text for row in document.sentences),
        sentences=document.sentences,
    )
    result = provider.synthesize(request, config)
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
    for event in result.native_timestamps:
        if (event.text_offset + event.text_length > len(request.narration_text)
            or event.audio_offset_ms > duration_ms
            or (event.duration_ms is not None
                and event.audio_offset_ms + event.duration_ms > duration_ms)):
            raise ValueError("NATIVE_TIMESTAMP_OUT_OF_BOUNDS")
    metadata = AudioMetadata(
        schema_version="5.1",
        sample_rate_hz=sample_rate,
        channels=channels,
        duration_ms=duration_ms,
        sha256=sha256_bytes(result.audio_bytes),
        provider=provider.name,
        provider_type=provider_type,
        provider_model=getattr(provider, "model", None),
        voice_id=config.voice_id,
        language=config.language,
        speaking_rate=config.speaking_rate,
        pitch_semitones=config.pitch_semitones,
        volume_gain_db=config.volume_gain_db,
        native_timestamps=list(result.native_timestamps),
    )
    quality = analyze_audio_quality(result.audio_bytes, metadata.sha256, provider.name,
                                    provider_type, quality_thresholds)
    if production and not quality.production_eligible:
        raise ValueError(",".join(quality.gate_reasons))
    return GeneratedAudioBundle(result.audio_bytes, metadata, quality)
