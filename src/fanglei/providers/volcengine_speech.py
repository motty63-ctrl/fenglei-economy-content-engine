"""Volcengine V3 SSE narration adapter with provider-neutral WAV output."""
from __future__ import annotations

from dataclasses import dataclass
import base64
import binascii
import io
import json
from typing import Iterable, Protocol
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import uuid
import wave

from fanglei.providers.narration import NarrationAudioResult, NarrationRequest
from fanglei.security import safe_error_message
from fanglei.v05_models import NarrationSynthesisConfig


VOLCENGINE_V3_SSE_ENDPOINT = (
    "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
)


@dataclass(frozen=True)
class VolcengineSynthesisPayload:
    pcm_s16le: bytes
    request_id: str | None
    sample_rate_hz: int = 24000
    channels: int = 1


class VolcengineClient(Protocol):
    def synthesize(self, text: str,
                   config: NarrationSynthesisConfig) -> VolcengineSynthesisPayload: ...


class VolcengineSseTransport(Protocol):
    def post_sse(self, endpoint: str, headers: dict[str, str], body: dict,
                 timeout_seconds: float) -> Iterable[str]: ...


def parse_volcengine_sse(lines: Iterable[str]) -> VolcengineSynthesisPayload:
    chunks: list[bytes] = []
    request_id: str | None = None
    for raw_line in lines:
        line = raw_line.strip()
        if line.startswith(("event:", ":")):
            continue
        value = line[5:].strip() if line.startswith("data:") else line
        if not value or value == "[DONE]":
            continue
        try:
            event = json.loads(value)
        except json.JSONDecodeError as error:
            raise RuntimeError("VOLCENGINE_TTS_RESPONSE_INVALID") from error
        code = event.get("code", 0)
        if code not in (0, 20000000):
            raise RuntimeError(f"VOLCENGINE_TTS_PROVIDER_ERROR:{code}")
        request_id = request_id or event.get("reqid") or event.get("request_id")
        encoded = event.get("data")
        if encoded:
            try:
                chunks.append(base64.b64decode(encoded, validate=True))
            except (binascii.Error, ValueError) as error:
                raise RuntimeError("VOLCENGINE_TTS_AUDIO_BASE64_INVALID") from error
    pcm = b"".join(chunks)
    if not pcm:
        raise RuntimeError("VOLCENGINE_TTS_AUDIO_EMPTY")
    if len(pcm) % 2:
        raise RuntimeError("VOLCENGINE_TTS_PCM_INVALID")
    return VolcengineSynthesisPayload(pcm_s16le=pcm, request_id=request_id)


class VolcengineHttpClient:
    def __init__(self, api_key: str, speaker: str, resource_id: str, *,
                 transport: VolcengineSseTransport | None = None,
                 endpoint: str = VOLCENGINE_V3_SSE_ENDPOINT,
                 timeout_seconds: float = 60.0):
        if not api_key or not speaker or not resource_id:
            raise ValueError("VOLCENGINE_TTS_CONFIGURATION_MISSING")
        self._api_key = api_key
        self.speaker = speaker
        self.resource_id = resource_id
        self._transport = transport or _UrllibSseTransport()
        self._endpoint = endpoint
        self._timeout_seconds = timeout_seconds

    def __repr__(self) -> str:
        return (f"VolcengineHttpClient(speaker={self.speaker!r}, "
                f"resource_id={self.resource_id!r})")

    def synthesize(self, text: str,
                   config: NarrationSynthesisConfig) -> VolcengineSynthesisPayload:
        if config.language.lower() not in {"zh-cn", "zh_cn"}:
            raise ValueError("VOLCENGINE_TTS_LANGUAGE_UNSUPPORTED")
        headers = {
            "Content-Type": "application/json",
            "X-Api-Key": self._api_key,
            "X-Api-Resource-Id": self.resource_id,
            "X-Api-Request-Id": str(uuid.uuid4()),
        }
        body = {
            "req_params": {
                "text": text,
                "speaker": self.speaker,
                "audio_params": {"format": "pcm", "sample_rate": 24000},
            },
        }
        return parse_volcengine_sse(self._transport.post_sse(
            self._endpoint, headers, body, self._timeout_seconds,
        ))


class VolcengineNarrationProvider:
    name = "volcengine_tts"
    model = "volcengine-v3-sse"
    provider_type = "real"

    def __init__(self, *, client: VolcengineClient, speaker_id: str | None = None):
        self._client = client
        self.speaker_id = speaker_id

    def __repr__(self) -> str:
        return f"VolcengineNarrationProvider(speaker_id={self.speaker_id!r})"

    def synthesize(self, request: NarrationRequest,
                   config: NarrationSynthesisConfig) -> NarrationAudioResult:
        if config.pitch_semitones != 0:
            raise ValueError("VOLCENGINE_TTS_PITCH_UNSUPPORTED")
        if config.volume_gain_db != 0:
            raise ValueError("VOLCENGINE_TTS_VOLUME_UNSUPPORTED")
        if self.speaker_id is not None and config.voice_id != self.speaker_id:
            raise ValueError("VOLCENGINE_TTS_SPEAKER_MISMATCH")
        try:
            payload = self._client.synthesize(request.narration_text, config)
            audio = _pcm_to_wav(payload)
        except Exception as error:
            raise RuntimeError(
                f"VOLCENGINE_TTS_SYNTHESIS_FAILED: {safe_error_message(error)}"
            ) from None
        return NarrationAudioResult(audio_bytes=audio,
                                    provider_request_id=payload.request_id)


def _pcm_to_wav(payload: VolcengineSynthesisPayload) -> bytes:
    if payload.sample_rate_hz != 24000 or payload.channels != 1:
        raise ValueError("VOLCENGINE_TTS_PCM_FORMAT_INVALID")
    if not payload.pcm_s16le or len(payload.pcm_s16le) % 2:
        raise ValueError("VOLCENGINE_TTS_PCM_INVALID")
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(24000)
        stream.writeframes(payload.pcm_s16le)
    return output.getvalue()


class _UrllibSseTransport:
    def post_sse(self, endpoint: str, headers: dict[str, str], body: dict,
                 timeout_seconds: float) -> Iterable[str]:
        request = Request(
            endpoint, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=headers, method="POST",
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                for line in response:
                    yield line.decode("utf-8", errors="strict")
        except HTTPError as error:
            response_headers = error.headers or {}
            provider_code = response_headers.get("X-Api-Status-Code", "unknown")
            provider_message = response_headers.get("X-Api-Message", "request rejected")
            request_id = response_headers.get("X-Tt-Logid", "unknown")
            try:
                detail = json.loads(error.read(4096).decode("utf-8"))
                if provider_code == "unknown":
                    provider_code = str(detail.get("code", provider_code))
                if provider_message == "request rejected":
                    provider_message = str(detail.get("message", provider_message))
                if request_id == "unknown":
                    request_id = str(detail.get("request_id", request_id))
            except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
                pass
            raise RuntimeError(
                f"VOLCENGINE_TTS_HTTP_ERROR:{error.code}:{provider_code}:"
                f"{provider_message}:{request_id}"
            ) from None
