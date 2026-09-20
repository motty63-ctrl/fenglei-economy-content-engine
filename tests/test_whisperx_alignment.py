import importlib
import sys
from pathlib import Path

import pytest

from fanglei.narration_normalization import normalize_script
from fanglei.providers.alignment import AlignmentRequest
from fanglei.providers.whisperx_alignment import (
    LocalWhisperXAlignmentProvider,
    WhisperXLocalEngine,
    WhisperXAlignmentError,
)
from fanglei.v05_models import AudioMetadata


def _request(tmp_path: Path) -> AlignmentRequest:
    narration = normalize_script({
        "script_id": "script_001",
        "sentences": [
            {"sentence_id": "sentence_001", "text": "BEA显示百分之二点八。"},
            {"sentence_id": "sentence_002", "text": "World Bank显示2.8%。"},
        ],
    }, "run")
    audio = AudioMetadata(
        schema_version="5.1", sample_rate_hz=24000, duration_ms=7000,
        sha256="a" * 64, provider="real", provider_type="real", voice_id="voice",
    )
    audio_path = tmp_path / "narration.wav"
    audio_path.write_bytes(b"RIFF-fixture")
    return AlignmentRequest(narration=narration, audio=audio, audio_path=audio_path)


class FixtureEngine:
    def align(self, *, audio_path, reference_sentences, language, diarize):
        assert audio_path.name == "narration.wav"
        assert language == "zh-CN"
        assert diarize is False
        return {
            "model_id": "whisperx-zh-fixture",
            "model_revision": "fixture-r1",
            "recognized_text": "B E A显示百分之二点八。世界银行显示百分之二点八。",
            "sentences": [
                {"sentence_id": "sentence_001", "start_ms": 120, "end_ms": 3180,
                 "confidence": .91, "confidence_source": "ctc_acoustic_score",
                 "aligned_text": "BEA显示百分之二点八。", "interpolated": False},
                {"sentence_id": "sentence_002", "start_ms": 3300, "end_ms": 6800,
                 "confidence": .88, "confidence_source": "ctc_acoustic_score",
                 "aligned_text": "World Bank显示2.8%。", "interpolated": False},
            ],
        }


def test_candidate_keeps_reference_text_and_measured_boundary(tmp_path) -> None:
    request = _request(tmp_path)
    result = LocalWhisperXAlignmentProvider(
        engine=FixtureEngine(), model_id="whisperx-zh-fixture",
        model_revision="fixture-r1",
    ).align(request)
    assert [row.sentence_id for row in result.sentences] == ["sentence_001", "sentence_002"]
    assert result.sentences[0].text == request.narration.sentences[0].narration_text
    assert (result.sentences[0].start_ms, result.sentences[0].end_ms) == (120, 3180)
    assert result.sentences[0].confidence_source == "ctc_acoustic_score"
    assert result.sentences[0].audio_sha256 == "a" * 64
    assert result.provider == "local_whisperx"
    assert result.method == "forced_alignment"
    assert result.model_revision == "fixture-r1"


@pytest.mark.parametrize("mutation,code", [
    ({"confidence": None}, "ALIGNMENT_SCORE_MISSING"),
    ({"aligned_text": ""}, "ALIGNMENT_TEXT_UNALIGNED"),
    ({"interpolated": True}, "ALIGNMENT_INTERPOLATION_FORBIDDEN"),
])
def test_adapter_rejects_unmeasured_or_invented_boundaries(tmp_path, mutation, code) -> None:
    class BrokenEngine(FixtureEngine):
        def align(self, **kwargs):
            result = super().align(**kwargs)
            result["sentences"][0].update(mutation)
            return result

    provider = LocalWhisperXAlignmentProvider(
        engine=BrokenEngine(), model_id="whisperx-zh-fixture", model_revision="fixture-r1"
    )
    with pytest.raises(WhisperXAlignmentError, match=code):
        provider.align(_request(tmp_path))


def test_adapter_rejects_model_revision_but_preserves_asr_observation(tmp_path) -> None:
    class WrongRevision(FixtureEngine):
        def align(self, **kwargs):
            result = super().align(**kwargs)
            result["model_revision"] = "other"
            return result

    with pytest.raises(WhisperXAlignmentError, match="ALIGNMENT_MODEL_REVISION_MISMATCH"):
        LocalWhisperXAlignmentProvider(
            engine=WrongRevision(), model_id="whisperx-zh-fixture", model_revision="fixture-r1"
        ).align(_request(tmp_path))

    class ReorderedAsr(FixtureEngine):
        def align(self, **kwargs):
            result = super().align(**kwargs)
            result["recognized_text"] = "世界银行显示百分之二点八。B E A显示百分之二点八。"
            return result

    result = LocalWhisperXAlignmentProvider(
        engine=ReorderedAsr(), model_id="whisperx-zh-fixture", model_revision="fixture-r1"
    ).align(_request(tmp_path))
    assert result.recognized_text.startswith("世界银行")


def test_whisperx_is_lazy_and_requires_explicit_opt_in(tmp_path, monkeypatch) -> None:
    sys.modules.pop("whisperx", None)
    importlib.import_module("fanglei.providers.whisperx_alignment")
    assert "whisperx" not in sys.modules

    monkeypatch.delenv("RUN_WHISPERX_ALIGNMENT", raising=False)
    provider = LocalWhisperXAlignmentProvider(
        model_id="pinned-model", model_revision="pinned-revision"
    )
    with pytest.raises(WhisperXAlignmentError, match="WHISPERX_ALIGNMENT_OPT_IN_REQUIRED"):
        provider.align(_request(tmp_path))


def test_opt_in_reports_missing_optional_dependency(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUN_WHISPERX_ALIGNMENT", "1")
    real_import = importlib.import_module

    def missing(name, *args, **kwargs):
        if name == "whisperx":
            raise ModuleNotFoundError("No module named whisperx")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", missing)
    provider = LocalWhisperXAlignmentProvider(
        model_id="pinned-model", model_revision="pinned-revision"
    )
    with pytest.raises(WhisperXAlignmentError, match="WHISPERX_DEPENDENCY_MISSING"):
        provider.align(_request(tmp_path))


class FakeAsrModel:
    def transcribe(self, audio, **kwargs):
        assert audio == [0.0] * 16000
        assert kwargs["language"] == "zh"
        return {
            "language": "zh",
            "segments": [
                {"start": 0.1, "end": 1.9,
                 "text": "B E A显示百分之二点八。世界银行显示百分之二点八。"},
            ],
        }


class FakeWhisperXModule:
    def load_audio(self, path):
        assert path.name == "narration.wav"
        return [0.0] * 16000

    def load_model(self, model_id, device, **kwargs):
        assert model_id == "asr-model"
        assert device == "cpu"
        assert kwargs["compute_type"] == "int8"
        return FakeAsrModel()

    def load_align_model(self, *, language_code, device, model_name, model_dir):
        assert (language_code, device, model_name) == ("zh", "cpu", "ctc-model")
        return object(), {"language": "zh"}

    def align(self, transcript, model, metadata, audio, device, **kwargs):
        assert transcript == [{
            "start": 0.0,
            "end": 1.0,
            "text": "BEA显示百分之二点八。World Bank显示百分之二点八。",
        }]
        assert kwargs["return_char_alignments"] is True
        chars = []
        cursor = .1
        for char in transcript[0]["text"]:
            row = {"char": char}
            if char.strip() and char not in "。":
                row.update(start=cursor, end=cursor + .02, score=.9)
                cursor += .025
            chars.append(row)
        return {"segments": [{"text": transcript[0]["text"], "chars": chars}]}


def test_real_engine_uses_asr_only_for_consistency_and_ctc_for_boundaries(tmp_path) -> None:
    engine = WhisperXLocalEngine(
        asr_model_id="asr-model",
        align_model_id="ctc-model",
        model_revision="fixture-r1",
        cache_dir=tmp_path / "models",
        device="cpu",
        compute_type="int8",
        whisperx_module=FakeWhisperXModule(),
    )
    payload = engine.align(
        audio_path=_request(tmp_path).audio_path,
        reference_sentences=[
            {"sentence_id": "sentence_001", "text": "BEA显示百分之二点八。"},
            {"sentence_id": "sentence_002", "text": "World Bank显示百分之二点八。"},
        ],
        language="zh-CN",
        diarize=False,
    )
    assert payload["recognized_text"].startswith("B E A")
    assert [row["sentence_id"] for row in payload["sentences"]] == [
        "sentence_001", "sentence_002",
    ]
    assert all(row["confidence_source"] == "ctc_acoustic_score" for row in payload["sentences"])
    assert all(row["interpolated"] is False for row in payload["sentences"])
    assert payload["sentences"][0]["end_ms"] <= payload["sentences"][1]["start_ms"]


def test_real_engine_rejects_missing_measured_content_character(tmp_path) -> None:
    class MissingCharacterModule(FakeWhisperXModule):
        def align(self, *args, **kwargs):
            result = super().align(*args, **kwargs)
            target = next(row for row in result["segments"][0]["chars"] if row["char"] == "显")
            target.pop("start")
            target.pop("end")
            target.pop("score")
            return result

    engine = WhisperXLocalEngine(
        asr_model_id="asr-model", align_model_id="ctc-model",
        model_revision="fixture-r1", cache_dir=tmp_path / "models",
        device="cpu", compute_type="int8", whisperx_module=MissingCharacterModule(),
    )
    with pytest.raises(WhisperXAlignmentError, match="ALIGNMENT_CHARACTER_MEASUREMENT_MISSING"):
        engine.align(
            audio_path=_request(tmp_path).audio_path,
            reference_sentences=[
                {"sentence_id": "sentence_001", "text": "BEA显示百分之二点八。"},
                {"sentence_id": "sentence_002", "text": "World Bank显示百分之二点八。"},
            ],
            language="zh-CN", diarize=False,
        )
