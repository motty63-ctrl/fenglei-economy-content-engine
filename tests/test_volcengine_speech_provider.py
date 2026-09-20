import base64
import io
import json
import math
import struct
import wave
from urllib.error import HTTPError

import pytest

from fanglei.audio_generation import generate_audio
from fanglei.narration_normalization import normalize_script
from fanglei.provider_factory import build_narration_provider
from fanglei.providers.narration import NarrationRequest
from fanglei.providers.volcengine_speech import (
    VolcengineHttpClient, VolcengineNarrationProvider, VolcengineSynthesisPayload,
    _UrllibSseTransport, parse_volcengine_sse,
)
from fanglei.v05_models import NarrationSynthesisConfig


def _pcm(duration_ms: int = 1200, amplitude: float = .2) -> bytes:
    rows = []
    for index in range(24000 * duration_ms // 1000):
        value = int(32767 * amplitude * math.sin(2 * math.pi * 440 * index / 24000))
        rows.append(struct.pack("<h", value))
    return b"".join(rows)


class FakeVolcengineClient:
    def __init__(self, pcm: bytes | None = None):
        self.pcm = pcm or _pcm()

    def synthesize(self, text, config):
        return VolcengineSynthesisPayload(
            pcm_s16le=self.pcm, request_id="request-1", sample_rate_hz=24000, channels=1,
        )


def _document():
    return normalize_script({
        "script_id": "script_001",
        "sentences": [{"sentence_id": "s_001", "text": "美国GDP增长百分之二点八。"}],
    }, "gdp-run")


def test_provider_wraps_pcm_as_canonical_wav() -> None:
    client = FakeVolcengineClient()
    provider = VolcengineNarrationProvider(client=client)
    result = provider.synthesize(
        NarrationRequest(run_id="run", narration_text="你好", sentences=[]),
        NarrationSynthesisConfig(voice_id="configured-speaker"),
    )
    assert provider.provider_type == "real"
    assert result.provider_request_id == "request-1"
    with wave.open(io.BytesIO(result.audio_bytes), "rb") as stream:
        assert stream.getnchannels() == 1
        assert stream.getsampwidth() == 2
        assert stream.getframerate() == 24000
        assert stream.readframes(stream.getnframes()) == client.pcm


def test_generated_audio_passes_existing_production_quality_gate() -> None:
    provider = VolcengineNarrationProvider(client=FakeVolcengineClient())
    bundle = generate_audio(
        _document(), provider, NarrationSynthesisConfig(voice_id="configured-speaker"),
        production=True,
    )
    assert bundle.metadata.provider == "volcengine_tts"
    assert bundle.metadata.provider_type == "real"
    assert bundle.metadata.provider_model == "volcengine-v3-sse"
    assert bundle.quality.production_eligible
    assert bundle.quality.voiced_duration_ms >= 1000


def test_sse_parser_combines_chunks_and_rejects_provider_error() -> None:
    first, second = _pcm(20), _pcm(20)
    lines = [
        "event: message",
        "data:" + json.dumps({"code": 20000000, "data": base64.b64encode(first).decode(),
                              "reqid": "req-1"}),
        "data:" + json.dumps({"code": 0, "data": base64.b64encode(second).decode()}),
        "data:[DONE]",
    ]
    payload = parse_volcengine_sse(lines)
    assert payload.pcm_s16le == first + second
    assert payload.request_id == "req-1"
    with pytest.raises(RuntimeError, match="VOLCENGINE_TTS_PROVIDER_ERROR"):
        parse_volcengine_sse(["data:" + json.dumps({"code": 55000000, "message": "denied"})])


def test_parser_accepts_chunked_ndjson_lines() -> None:
    pcm = _pcm(20)
    payload = parse_volcengine_sse([
        json.dumps({
            "code": 20000000,
            "data": base64.b64encode(pcm).decode(),
            "reqid": "chunked-response",
        }),
    ])
    assert payload.pcm_s16le == pcm
    assert payload.request_id == "chunked-response"


def test_http_client_builds_minimal_v3_http_chunked_request() -> None:
    captured = {}

    class Transport:
        def post_sse(self, endpoint, headers, body, timeout_seconds):
            captured.update(endpoint=endpoint, headers=headers, body=body,
                            timeout_seconds=timeout_seconds)
            return ["data:" + json.dumps({
                "code": 20000000, "data": base64.b64encode(_pcm(20)).decode(),
                "reqid": "response-id",
            })]

    client = VolcengineHttpClient(
        api_key="sentinel-secret", speaker="configured-speaker",
        resource_id="configured-resource", transport=Transport(),
    )
    result = client.synthesize("你好，这是一次语音合成测试。", NarrationSynthesisConfig(
        voice_id="configured-speaker", language="zh-CN", speaking_rate=.9,
    ))
    assert result.request_id == "response-id"
    assert captured["endpoint"] == (
        "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
    )
    assert set(captured["headers"]) == {
        "Content-Type", "X-Api-Key", "X-Api-Resource-Id", "X-Api-Request-Id",
    }
    assert captured["headers"]["Content-Type"] == "application/json"
    assert captured["headers"]["X-Api-Key"] == "sentinel-secret"
    assert captured["headers"]["X-Api-Resource-Id"] == "configured-resource"
    assert captured["body"] == {
        "req_params": {
            "text": "你好，这是一次语音合成测试。",
            "speaker": "configured-speaker",
            "audio_params": {"format": "pcm", "sample_rate": 24000},
        },
    }


def test_transport_surfaces_sanitizable_http_error_details(monkeypatch) -> None:
    response = io.BytesIO(json.dumps({
        "code": 3001, "message": "invalid request parameters",
        "request_id": "request-diagnostic",
    }).encode("utf-8"))

    headers = {
        "X-Api-Status-Code": "40000001",
        "X-Api-Message": "invalid speaker",
        "X-Tt-Logid": "safe-log-id",
    }

    def fail_request(*args, **kwargs):
        raise HTTPError("https://example.invalid", 400, "Bad Request", headers, response)

    monkeypatch.setattr("fanglei.providers.volcengine_speech.urlopen", fail_request)
    with pytest.raises(RuntimeError) as error:
        list(_UrllibSseTransport().post_sse(
            "https://example.invalid", {"X-Api-Key": "sentinel-secret"}, {}, 1,
        ))
    message = str(error.value)
    assert message == (
        "VOLCENGINE_TTS_HTTP_ERROR:400:40000001:invalid speaker:safe-log-id"
    )
    assert "sentinel-secret" not in message


def test_factory_reads_environment_and_redacts_provider_failure(monkeypatch) -> None:
    sentinel = "sentinel-volcengine-secret"
    monkeypatch.setenv("VOLCENGINE_TTS_API_KEY", sentinel)
    monkeypatch.setenv("VOLCENGINE_TTS_SPEAKER", "configured-speaker")
    monkeypatch.setenv("VOLCENGINE_TTS_RESOURCE_ID", "configured-resource")

    class FailingClient:
        def synthesize(self, text, config):
            raise RuntimeError(f"X-Api-Key: {sentinel}")

    provider = build_narration_provider("volcengine", client=FailingClient())
    assert sentinel not in repr(provider)
    with pytest.raises(RuntimeError) as error:
        provider.synthesize(
            NarrationRequest(run_id="run", narration_text="你好", sentences=[]),
            NarrationSynthesisConfig(voice_id="configured-speaker"),
        )
    assert sentinel not in str(error.value)
    assert "VOLCENGINE_TTS_SYNTHESIS_FAILED" in str(error.value)


def test_provider_redacts_secret_from_value_error(monkeypatch) -> None:
    sentinel = "sentinel-value-error-secret"
    monkeypatch.setenv("VOLCENGINE_TTS_API_KEY", sentinel)

    class FailingClient:
        def synthesize(self, text, config):
            raise ValueError(f"invalid credential {sentinel}")

    provider = VolcengineNarrationProvider(client=FailingClient())
    with pytest.raises(RuntimeError) as error:
        provider.synthesize(
            NarrationRequest(run_id="run", narration_text="你好", sentences=[]),
            NarrationSynthesisConfig(voice_id="configured-speaker"),
        )
    assert sentinel not in str(error.value)
    assert "VOLCENGINE_TTS_SYNTHESIS_FAILED" in str(error.value)


def test_factory_requires_all_environment(monkeypatch) -> None:
    for name in ("VOLCENGINE_TTS_API_KEY", "VOLCENGINE_TTS_SPEAKER",
                 "VOLCENGINE_TTS_RESOURCE_ID"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValueError, match="VOLCENGINE_TTS_CONFIGURATION_MISSING"):
        build_narration_provider("volcengine")


def test_adapter_rejects_unverified_pitch_and_volume_mapping() -> None:
    provider = VolcengineNarrationProvider(client=FakeVolcengineClient())
    request = NarrationRequest(run_id="run", narration_text="你好", sentences=[])
    with pytest.raises(ValueError, match="VOLCENGINE_TTS_PITCH_UNSUPPORTED"):
        provider.synthesize(request, NarrationSynthesisConfig(
            voice_id="speaker", pitch_semitones=1,
        ))
    with pytest.raises(ValueError, match="VOLCENGINE_TTS_VOLUME_UNSUPPORTED"):
        provider.synthesize(request, NarrationSynthesisConfig(
            voice_id="speaker", volume_gain_db=1,
        ))
