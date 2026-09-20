"""Opt-in local WhisperX alignment adapter boundary.

The optional dependency is deliberately imported only after explicit opt-in.
Offline tests inject a measured-shaped engine and never load a model.
"""
from __future__ import annotations

import importlib
import gc
import os
from pathlib import Path
import unicodedata
from typing import Any, Protocol

from fanglei.alignment_matching import compare_alignment_text
from fanglei.providers.alignment import AlignmentRequest, AlignmentResult
from fanglei.v05_models import AlignedSentence


class WhisperXAlignmentError(ValueError):
    pass


class WhisperXEngine(Protocol):
    def align(self, *, audio_path, reference_sentences: list[dict[str, str]],
              language: str, diarize: bool) -> dict[str, Any]: ...


class WhisperXLocalEngine:
    """Opt-in WhisperX runtime with independent ASR and measured CTC spans."""

    _SAMPLE_RATE = 16000

    def __init__(self, *, asr_model_id: str, align_model_id: str,
                 model_revision: str, cache_dir: Path, device: str = "cpu",
                 compute_type: str = "int8", whisperx_module: Any | None = None):
        if not asr_model_id or not align_model_id or not model_revision:
            raise WhisperXAlignmentError("WHISPERX_PINNED_MODEL_REQUIRED")
        self.asr_model_id = asr_model_id
        self.align_model_id = align_model_id
        self.model_id = f"{asr_model_id}+{align_model_id}"
        self.model_revision = model_revision
        self.cache_dir = Path(cache_dir)
        self.device = device
        self.compute_type = compute_type
        self._whisperx = whisperx_module

    @staticmethod
    def _language_code(language: str) -> str:
        return language.split("-", 1)[0].lower()

    @staticmethod
    def _requires_measurement(character: str) -> bool:
        return bool(character.strip()) and unicodedata.category(character)[0] in {"L", "N"}

    def _module(self):
        if self._whisperx is not None:
            return self._whisperx
        try:
            return importlib.import_module("whisperx")
        except ModuleNotFoundError as exc:
            raise WhisperXAlignmentError("WHISPERX_DEPENDENCY_MISSING") from exc

    def align(self, *, audio_path, reference_sentences: list[dict[str, str]],
              language: str, diarize: bool) -> dict[str, Any]:
        if diarize:
            raise WhisperXAlignmentError("WHISPERX_DIARIZATION_FORBIDDEN")
        wx = self._module()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        language_code = self._language_code(language)
        audio = wx.load_audio(Path(audio_path))

        asr_model = wx.load_model(
            self.asr_model_id, self.device, compute_type=self.compute_type,
            language=language_code, download_root=str(self.cache_dir / "asr"),
        )
        transcription = asr_model.transcribe(audio, batch_size=1, language=language_code)
        recognized_text = "".join(
            str(segment.get("text", "")) for segment in transcription.get("segments", [])
        ).strip()
        if not recognized_text:
            raise WhisperXAlignmentError("ALIGNMENT_ASR_TEXT_MISSING")
        del asr_model
        gc.collect()

        align_model, metadata = wx.load_align_model(
            language_code=language_code, device=self.device,
            model_name=self.align_model_id, model_dir=str(self.cache_dir / "alignment"),
        )
        reference_text = "".join(row["text"] for row in reference_sentences)
        duration_seconds = len(audio) / self._SAMPLE_RATE
        aligned = wx.align(
            [{"start": 0.0, "end": duration_seconds, "text": reference_text}],
            align_model, metadata, audio, self.device,
            return_char_alignments=True, print_progress=False,
        )
        characters = [
            character
            for segment in aligned.get("segments", [])
            for character in (segment.get("chars") or [])
        ]
        if "".join(str(row.get("char", "")) for row in characters) != reference_text:
            raise WhisperXAlignmentError("ALIGNMENT_CHARACTER_SEQUENCE_MISMATCH")

        measured_sentences: list[dict[str, Any]] = []
        offset = 0
        for reference in reference_sentences:
            text = reference["text"]
            sentence_characters = characters[offset:offset + len(text)]
            offset += len(text)
            required = [
                row for row in sentence_characters
                if self._requires_measurement(str(row.get("char", "")))
            ]
            if not required or any(
                row.get("start") is None or row.get("end") is None or row.get("score") is None
                for row in required
            ):
                raise WhisperXAlignmentError("ALIGNMENT_CHARACTER_MEASUREMENT_MISSING")
            start_ms = round(min(float(row["start"]) for row in required) * 1000)
            end_ms = round(max(float(row["end"]) for row in required) * 1000)
            score = sum(float(row["score"]) for row in required) / len(required)
            measured_sentences.append({
                "sentence_id": reference["sentence_id"],
                "start_ms": start_ms,
                "end_ms": end_ms,
                "confidence": round(score, 6),
                "confidence_source": "ctc_acoustic_score",
                "aligned_text": text,
                "interpolated": False,
            })

        return {
            "model_id": self.model_id,
            "model_revision": self.model_revision,
            "recognized_text": recognized_text,
            "sentences": measured_sentences,
        }


class LocalWhisperXAlignmentProvider:
    name = "local_whisperx"
    method = "forced_alignment"

    def __init__(self, *, model_id: str, model_revision: str,
                 engine: WhisperXEngine | None = None):
        if not model_id or not model_revision:
            raise WhisperXAlignmentError("WHISPERX_PINNED_MODEL_REQUIRED")
        self.model_id = model_id
        self.model_revision = model_revision
        self._engine = engine

    def _load_engine(self) -> WhisperXEngine:
        if os.environ.get("RUN_WHISPERX_ALIGNMENT") != "1":
            raise WhisperXAlignmentError("WHISPERX_ALIGNMENT_OPT_IN_REQUIRED")
        try:
            importlib.import_module("whisperx")
        except ModuleNotFoundError as exc:
            raise WhisperXAlignmentError("WHISPERX_DEPENDENCY_MISSING") from exc
        raise WhisperXAlignmentError("WHISPERX_ENGINE_CONFIGURATION_REQUIRED")

    def align(self, request: AlignmentRequest) -> AlignmentResult:
        engine = self._engine or self._load_engine()
        references = [
            {"sentence_id": row.sentence_id, "text": row.narration_text}
            for row in request.narration.sentences
        ]
        payload = engine.align(
            audio_path=request.audio_path,
            reference_sentences=references,
            language=request.narration.language,
            diarize=False,
        )
        if payload.get("model_id") != self.model_id or payload.get("model_revision") != self.model_revision:
            raise WhisperXAlignmentError("ALIGNMENT_MODEL_REVISION_MISMATCH")

        recognized_text = payload.get("recognized_text")
        if not isinstance(recognized_text, str) or not recognized_text.strip():
            raise WhisperXAlignmentError("ALIGNMENT_ASR_TEXT_MISSING")

        measured_rows = payload.get("sentences")
        if not isinstance(measured_rows, list):
            raise WhisperXAlignmentError("ALIGNMENT_SENTENCES_MISSING")
        expected_ids = [row.sentence_id for row in request.narration.sentences]
        if [row.get("sentence_id") for row in measured_rows] != expected_ids:
            raise WhisperXAlignmentError("ALIGNMENT_COVERAGE_INVALID")

        sentences: list[AlignedSentence] = []
        for reference, measured in zip(request.narration.sentences, measured_rows):
            if measured.get("confidence") is None or not measured.get("confidence_source"):
                raise WhisperXAlignmentError("ALIGNMENT_SCORE_MISSING")
            if measured.get("interpolated") is True:
                raise WhisperXAlignmentError("ALIGNMENT_INTERPOLATION_FORBIDDEN")
            aligned_text = measured.get("aligned_text")
            if not isinstance(aligned_text, str) or not aligned_text:
                raise WhisperXAlignmentError("ALIGNMENT_TEXT_UNALIGNED")
            text_match = compare_alignment_text(reference.narration_text, aligned_text)
            if not text_match.matched:
                raise WhisperXAlignmentError("ALIGNMENT_TEXT_UNALIGNED")
            try:
                sentence = AlignedSentence(
                    sentence_id=reference.sentence_id,
                    start_ms=measured["start_ms"],
                    end_ms=measured["end_ms"],
                    confidence=measured["confidence"],
                    timing_source="forced_alignment",
                    text=reference.narration_text,
                    confidence_source=measured["confidence_source"],
                    provider=self.name,
                    method=self.method,
                    audio_sha256=request.audio_sha256,
                    normalized_ref=text_match.normalized_ref,
                    normalized_asr=text_match.normalized_asr,
                    measured=True,
                    interpolated=False,
                )
            except (KeyError, ValueError) as exc:
                raise WhisperXAlignmentError("ALIGNMENT_BOUNDARY_INVALID") from exc
            sentences.append(sentence)

        return AlignmentResult(
            sentences=sentences,
            confidence=min(row.confidence for row in sentences),
            provider=self.name,
            method=self.method,
            model_id=self.model_id,
            model_revision=self.model_revision,
            score_source=sentences[0].confidence_source,
            recognized_text=recognized_text,
        )
