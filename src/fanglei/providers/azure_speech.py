"""Azure Speech adapter; Azure SDK types never cross this module boundary."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol
from xml.sax.saxutils import escape, quoteattr

from fanglei.providers.narration import NarrationAudioResult, NarrationRequest
from fanglei.security import safe_error_message
from fanglei.v05_models import NativeTimingEvent, NarrationSynthesisConfig


@dataclass(frozen=True)
class AzureSynthesisPayload:
    audio_bytes: bytes
    request_id: str | None
    events: tuple[NativeTimingEvent, ...]


class AzureClient(Protocol):
    def synthesize(self, text: str, config: NarrationSynthesisConfig) -> AzureSynthesisPayload: ...


class AzureSpeechNarrationProvider:
    name = "azure_speech"
    model = "azure-speech-sdk"
    provider_type = "real"

    def __init__(self, key: str, region: str, *, client: AzureClient | None = None):
        if not key or not region:
            raise ValueError("AZURE_SPEECH_CREDENTIALS_MISSING")
        self._key = key
        self.region = region
        self._client = client or _AzureSdkClient(key, region)

    def __repr__(self) -> str:
        return f"AzureSpeechNarrationProvider(region={self.region!r})"

    def synthesize(self, request: NarrationRequest,
                   config: NarrationSynthesisConfig) -> NarrationAudioResult:
        try:
            payload = self._client.synthesize(request.narration_text, config)
        except Exception as error:
            raise RuntimeError(f"AZURE_SPEECH_SYNTHESIS_FAILED: {safe_error_message(error)}") from None
        return NarrationAudioResult(audio_bytes=payload.audio_bytes,
                                    native_timestamps=payload.events,
                                    provider_request_id=payload.request_id)


class _AzureSdkClient:
    def __init__(self, key: str, region: str, *, sdk_module=None):
        self._key = key
        self._region = region
        self._sdk_module = sdk_module

    def synthesize(self, text: str, config: NarrationSynthesisConfig) -> AzureSynthesisPayload:
        if self._sdk_module is None:
            try:
                import azure.cognitiveservices.speech as speechsdk
            except ImportError as error:
                raise RuntimeError("AZURE_SPEECH_SDK_NOT_INSTALLED") from error
        else:
            speechsdk = self._sdk_module
        speech = speechsdk.SpeechConfig(subscription=self._key, region=self._region)
        speech.speech_synthesis_voice_name = config.voice_id
        speech.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm)
        events: list[NativeTimingEvent] = []
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech, audio_config=None)
        def boundary(event):
            duration = getattr(event, "duration", None)
            if isinstance(duration, timedelta):
                duration_ms = round(duration.total_seconds() * 1000)
            elif isinstance(duration, int):
                duration_ms = round(duration / 10000)
            else:
                duration_ms = None
            boundary_name = str(getattr(event, "boundary_type", "Word")).lower()
            event_type = (
                "sentence" if "sentence" in boundary_name else
                "punctuation" if "punctuation" in boundary_name else "word"
            )
            events.append(NativeTimingEvent(
                event_type=event_type, audio_offset_ms=round(event.audio_offset / 10000),
                duration_ms=duration_ms,
                text_offset=event.text_offset, text_length=event.word_length,
                text=getattr(event, "text", ""),
            ))
        synthesizer.synthesis_word_boundary.connect(boundary)
        escaped = escape(text)
        rate = f"{(config.speaking_rate - 1) * 100:+.0f}%"
        pitch = f"{config.pitch_semitones:+g}st"
        volume = f"{config.volume_gain_db:+g}dB"
        ssml = (f'<speak version="1.0" xml:lang={quoteattr(config.language)}>'
                f'<voice name={quoteattr(config.voice_id)}>'
                f'<prosody rate={quoteattr(rate)} pitch={quoteattr(pitch)} '
                f'volume={quoteattr(volume)}>{escaped}</prosody>'
                '</voice></speak>')
        result = synthesizer.speak_ssml_async(ssml).get()
        if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
            raise RuntimeError("AZURE_SPEECH_SYNTHESIS_NOT_COMPLETED")
        return AzureSynthesisPayload(bytes(result.audio_data), getattr(result, "result_id", None),
                                     tuple(events))
