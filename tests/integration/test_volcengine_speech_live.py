"""Explicitly opt-in Volcengine TTS smoke test; skipped in offline suites."""
import os
import json
from pathlib import Path
import wave

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
    assert os.environ["VOLCENGINE_TTS_SPEAKER"] == "zh_male_liufei_uranus_bigtts"
    assert os.environ["VOLCENGINE_TTS_RESOURCE_ID"] == "seed-tts-2.0"

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

    output_dir = Path(__file__).parents[2] / "output" / "volcengine-smoke"
    output_dir.mkdir(parents=True, exist_ok=True)
    wav_path = output_dir / "narration.wav"
    wav_path.write_bytes(bundle.audio_bytes)
    with wave.open(str(wav_path), "rb") as stream:
        assert stream.getsampwidth() == 2
        assert stream.getframerate() == 24000
        assert stream.getnchannels() == 1
    report = {
        "wav_path": str(wav_path.resolve()),
        "metadata": bundle.metadata.model_dump(mode="json"),
        "quality": bundle.quality.model_dump(mode="json"),
    }
    (output_dir / "smoke-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
    )
