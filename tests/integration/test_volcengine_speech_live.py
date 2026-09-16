"""Explicitly opt-in Volcengine TTS smoke test; skipped in offline suites."""
import os

import pytest

from fanglei.audio_generation import generate_audio
from fanglei.narration_normalization import normalize_script
from fanglei.provider_factory import build_narration_provider
from fanglei.v05_models import NarrationSynthesisConfig


@pytest.mark.integration
def test_real_volcengine_speech_one_sentence() -> None:
    if os.environ.get("RUN_VOLCENGINE_TTS_INTEGRATION") != "1":
        pytest.skip("explicit Volcengine TTS opt-in required")
    required = (
        "VOLCENGINE_TTS_API_KEY",
        "VOLCENGINE_TTS_SPEAKER",
        "VOLCENGINE_TTS_RESOURCE_ID",
    )
    if not all(os.environ.get(name) for name in required):
        pytest.skip("Volcengine TTS environment not configured")

    document = normalize_script({
        "script_id": "volcengine-smoke",
        "sentences": [
            {"sentence_id": "s_001", "text": "你好，这是语音质量测试。"},
        ],
    }, "volcengine-smoke")
    bundle = generate_audio(
        document,
        build_narration_provider("volcengine"),
        NarrationSynthesisConfig(
            voice_id=os.environ["VOLCENGINE_TTS_SPEAKER"], language="zh-CN",
        ),
        production=True,
    )
    assert bundle.quality.production_eligible
    assert bundle.metadata.provider == "volcengine_tts"
    assert bundle.metadata.provider_type == "real"
