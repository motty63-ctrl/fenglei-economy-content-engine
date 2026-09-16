"""Explicitly opt-in smoke test. Never included in offline tests."""
import os

import pytest

from fanglei.audio_generation import generate_audio
from fanglei.narration_normalization import normalize_script
from fanglei.provider_factory import build_narration_provider
from fanglei.v05_models import NarrationSynthesisConfig


@pytest.mark.integration
def test_real_azure_speech_one_sentence() -> None:
    if os.environ.get("RUN_AZURE_SPEECH_INTEGRATION") != "1":
        pytest.skip("explicit Azure Speech opt-in required")
    if not all(os.environ.get(name) for name in
               ("AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION", "AZURE_SPEECH_VOICE")):
        pytest.skip("Azure Speech environment not configured")
    document = normalize_script({
        "script_id": "azure-smoke", "sentences": [
            {"sentence_id": "s_001", "text": "你好，这是语音质量测试。"},
        ],
    }, "azure-smoke")
    bundle = generate_audio(
        document, build_narration_provider("azure"),
        NarrationSynthesisConfig(voice_id=os.environ["AZURE_SPEECH_VOICE"]),
        production=True,
    )
    assert bundle.quality.production_eligible
    assert bundle.metadata.provider_type == "real"
