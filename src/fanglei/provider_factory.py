"""Credential-safe provider construction."""
from __future__ import annotations

import os

from fanglei.providers.azure_speech import AzureClient, AzureSpeechNarrationProvider


def build_narration_provider(name: str, *, client: AzureClient | None = None):
    if name != "azure":
        raise ValueError("UNSUPPORTED_NARRATION_PROVIDER")
    key = os.environ.get("AZURE_SPEECH_KEY", "")
    region = os.environ.get("AZURE_SPEECH_REGION", "")
    if not key or not region:
        raise ValueError("AZURE_SPEECH_CREDENTIALS_MISSING")
    return AzureSpeechNarrationProvider(key, region, client=client)
