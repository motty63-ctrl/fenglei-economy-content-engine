"""Credential-safe provider construction."""
from __future__ import annotations

import os

from fanglei.providers.azure_speech import AzureClient, AzureSpeechNarrationProvider
from fanglei.providers.volcengine_speech import (
    VolcengineClient, VolcengineHttpClient, VolcengineNarrationProvider,
)


def build_narration_provider(
    name: str, *, client: AzureClient | VolcengineClient | None = None,
):
    if name == "azure":
        key = os.environ.get("AZURE_SPEECH_KEY", "")
        region = os.environ.get("AZURE_SPEECH_REGION", "")
        if not key or not region:
            raise ValueError("AZURE_SPEECH_CREDENTIALS_MISSING")
        return AzureSpeechNarrationProvider(key, region, client=client)
    if name == "volcengine":
        key = os.environ.get("VOLCENGINE_TTS_API_KEY", "")
        speaker = os.environ.get("VOLCENGINE_TTS_SPEAKER", "")
        resource_id = os.environ.get("VOLCENGINE_TTS_RESOURCE_ID", "")
        if not key or not speaker or not resource_id:
            raise ValueError("VOLCENGINE_TTS_CONFIGURATION_MISSING")
        transport_client = client or VolcengineHttpClient(key, speaker, resource_id)
        return VolcengineNarrationProvider(client=transport_client, speaker_id=speaker)
    raise ValueError("UNSUPPORTED_NARRATION_PROVIDER")
