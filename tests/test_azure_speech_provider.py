import os
from datetime import timedelta
from types import SimpleNamespace
from xml.etree import ElementTree

import pytest

from fanglei.provider_factory import build_narration_provider
from fanglei.providers.azure_speech import (
    AzureSpeechNarrationProvider, AzureSynthesisPayload, _AzureSdkClient,
)
from fanglei.providers.narration import NarrationRequest
from fanglei.v05_models import NarrationSynthesisConfig


class FakeAzureClient:
    def synthesize(self, text, config):
        assert config.voice_id == "zh-CN-test"
        return AzureSynthesisPayload(audio_bytes=b"RIFF-test", request_id="request-1", events=())


def test_azure_adapter_is_configured_and_provider_neutral() -> None:
    provider = AzureSpeechNarrationProvider("secret", "eastasia", client=FakeAzureClient())
    request = NarrationRequest(run_id="run", narration_text="你好", sentences=[])
    result = provider.synthesize(request, NarrationSynthesisConfig(voice_id="zh-CN-test"))
    assert provider.provider_type == "real"
    assert result.provider_request_id == "request-1"


def test_factory_requires_environment_without_echoing_secret(monkeypatch) -> None:
    monkeypatch.delenv("AZURE_SPEECH_KEY", raising=False)
    monkeypatch.delenv("AZURE_SPEECH_REGION", raising=False)
    with pytest.raises(ValueError, match="AZURE_SPEECH_CREDENTIALS_MISSING"):
        build_narration_provider("azure")

    sentinel = "sentinel-never-print"
    monkeypatch.setenv("AZURE_SPEECH_KEY", sentinel)
    monkeypatch.setenv("AZURE_SPEECH_REGION", "eastasia")
    provider = build_narration_provider("azure", client=FakeAzureClient())
    assert sentinel not in repr(provider)


def test_azure_factory_remains_available_after_provider_extension(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_SPEECH_KEY", "azure-sentinel")
    monkeypatch.setenv("AZURE_SPEECH_REGION", "eastasia")
    assert isinstance(build_narration_provider("azure", client=FakeAzureClient()),
                      AzureSpeechNarrationProvider)


def test_adapter_redacts_provider_exception_sentinel(monkeypatch) -> None:
    sentinel = "sentinel-never-print"
    monkeypatch.setenv("AZURE_SPEECH_KEY", sentinel)

    class FailingClient:
        def synthesize(self, text, config):
            raise RuntimeError(f"network failed with Authorization: Bearer {sentinel}")

    provider = AzureSpeechNarrationProvider(sentinel, "eastasia", client=FailingClient())
    with pytest.raises(RuntimeError) as error:
        provider.synthesize(
            NarrationRequest(run_id="run", narration_text="你好", sentences=[]),
            NarrationSynthesisConfig(voice_id="configured"),
        )
    assert sentinel not in str(error.value)
    assert "AZURE_SPEECH_SYNTHESIS_FAILED" in str(error.value)


def test_mock_sdk_converts_word_boundaries_and_escapes_ssml() -> None:
    captured = {}

    class Config:
        def __init__(self, subscription, region):
            captured["region"] = region

        def set_speech_synthesis_output_format(self, value):
            captured["format"] = value

    class EventHook:
        def connect(self, callback):
            captured["boundary"] = callback

    class Synthesizer:
        def __init__(self, speech_config, audio_config):
            self.synthesis_word_boundary = EventHook()

        def speak_ssml_async(self, ssml):
            captured["ssml"] = ssml
            captured["boundary"](SimpleNamespace(
                audio_offset=1_200_000, duration=timedelta(milliseconds=300),
                text_offset=0, word_length=2, text="你好", boundary_type="Word",
            ))
            return SimpleNamespace(get=lambda: SimpleNamespace(
                reason="completed", audio_data=b"RIFF-test", result_id="req"))

    sdk = SimpleNamespace(
        SpeechConfig=Config, SpeechSynthesizer=Synthesizer,
        SpeechSynthesisOutputFormat=SimpleNamespace(Riff24Khz16BitMonoPcm="riff24"),
        ResultReason=SimpleNamespace(SynthesizingAudioCompleted="completed"),
    )
    result = _AzureSdkClient("secret", "eastasia", sdk_module=sdk).synthesize(
        "你好 <GDP> & 增长", NarrationSynthesisConfig(voice_id='voice"bad', speaking_rate=.9))
    assert captured["format"] == "riff24"
    assert "&lt;GDP&gt; &amp;" in captured["ssml"]
    assert ElementTree.fromstring(captured["ssml"]).find("voice").attrib["name"] == 'voice"bad'
    assert result.events[0].audio_offset_ms == 120
    assert result.events[0].duration_ms == 300
