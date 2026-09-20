import io
import json
import struct
import wave

from fanglei.artifact_registry import ArtifactRegistry
from fanglei.artifacts import sha256_bytes, sha256_text
from fanglei.audio_alignment import run_alignment_candidate
from fanglei.models import RunManifest
from fanglei.narration_normalization import normalize_script
from fanglei.providers.alignment import AlignmentResult
from fanglei.v05_models import AlignedSentence, AudioQualityDocument, AudioQualityThresholdsModel
from fanglei.voice_review import approve_voice


def _wav_bytes() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(24000)
        stream.writeframes(struct.pack("<h", 7000) * 24000)
    return output.getvalue()


def _mark_json(registry, name, value):
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    path = registry.run_dir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    state = registry.manifest.artifacts[name]
    state.status = "valid"
    state.content_hash = sha256_text(text)
    state.dependencies = {}


def _production_ready_run(tmp_path):
    run = tmp_path / "2026-09-19-001-gdp"
    run.mkdir()
    manifest = RunManifest(
        run_id=run.name, created_at="2026-09-19T00:00:00+08:00",
        updated_at="2026-09-19T00:00:00+08:00", status="voice_approved",
    )
    registry = ArtifactRegistry(run, manifest)
    narration = normalize_script({
        "script_id": "script", "sentences": [
            {"sentence_id": "sentence_001", "text": "第一句。"},
            {"sentence_id": "sentence_002", "text": "第二句。"},
        ],
    }, run.name)
    audio_bytes = _wav_bytes()
    audio_sha = sha256_bytes(audio_bytes)
    _mark_json(registry, "narration.json", narration.model_dump(mode="json"))
    audio_path = run / "audio" / "narration.wav"
    audio_path.parent.mkdir(parents=True)
    audio_path.write_bytes(audio_bytes)
    state = registry.manifest.artifacts["audio/narration.wav"]
    state.status = "valid"; state.content_hash = audio_sha; state.dependencies = {}
    metadata = {
        "schema_version": "5.1", "path": "audio/narration.wav", "format": "wav",
        "codec": "pcm_s16le", "sample_rate_hz": 24000, "channels": 1,
        "duration_ms": 1000, "sha256": audio_sha, "provider": "real",
        "provider_type": "real", "voice_id": "voice",
    }
    _mark_json(registry, "audio/metadata.json", metadata)
    quality = AudioQualityDocument(
        audio_sha256=audio_sha, provider="real", provider_type="real", duration_ms=1000,
        peak=.2, peak_dbfs=-14, rms=.1, rms_dbfs=-20, voiced_duration_ms=900,
        voiced_ratio=.9, thresholds=AudioQualityThresholdsModel(
            min_peak=.01, min_rms_dbfs=-50, voiced_frame_rms_dbfs=-45,
            min_voiced_duration_ms=100, min_voiced_ratio=.1,
        ), passed=True, production_eligible=True,
    )
    _mark_json(registry, "audio/quality.json", quality.model_dump(mode="json"))
    review = approve_voice(run.name, audio_sha, reviewer="human")
    _mark_json(registry, "audio/review.json", review.model_dump(mode="json"))
    registry.save_manifest()
    return run, audio_sha


class MeasuredProvider:
    name = "local_whisperx"
    method = "forced_alignment"

    def align(self, request):
        rows = []
        for sentence_id, text, start, end in (
            ("sentence_001", "第一句。", 50, 450),
            ("sentence_002", "第二句。", 500, 950),
        ):
            rows.append(AlignedSentence(
                sentence_id=sentence_id, start_ms=start, end_ms=end, confidence=.4,
                timing_source="forced_alignment", text=text,
                confidence_source="ctc_acoustic_score", provider=self.name,
                method=self.method, audio_sha256=request.audio_sha256,
                normalized_ref=text.rstrip("。"), normalized_asr=text.rstrip("。"),
                measured=True, interpolated=False,
            ))
        return AlignmentResult(
            sentences=rows, confidence=.4, provider=self.name, method=self.method,
            model_id="zh-ctc", model_revision="r1", score_source="ctc_acoustic_score",
            recognized_text="第一句。第二句。",
        )


def test_candidate_stage_binds_approved_audio_and_never_writes_final_alignment(tmp_path) -> None:
    run, audio_sha = _production_ready_run(tmp_path)
    output = run_alignment_candidate(run.name, tmp_path, MeasuredProvider())
    payload = json.loads(output.read_text(encoding="utf-8"))
    manifest = json.loads((run / "run.json").read_text(encoding="utf-8"))
    assert output.name == "alignment_candidate.json"
    assert payload["schema_version"] == "5.2"
    assert payload["audio_sha256"] == audio_sha
    assert payload["voice_review_hash"] == manifest["artifacts"]["audio/review.json"]["content_hash"]
    assert payload["confidence"] == .4
    assert manifest["artifacts"]["alignment_candidate.json"]["status"] == "valid"
    assert manifest["stages"]["audio_alignment"]["status"] == "succeeded"
    assert manifest["artifacts"]["alignment.json"]["status"] != "valid"
    assert manifest["artifacts"]["timeline.json"]["status"] != "valid"


def test_valid_candidate_is_reused_without_provider_execution(tmp_path) -> None:
    run, _ = _production_ready_run(tmp_path)
    first = run_alignment_candidate(run.name, tmp_path, MeasuredProvider())
    before = json.loads((run / "run.json").read_text(encoding="utf-8"))

    class MustNotRun(MeasuredProvider):
        def align(self, request):
            raise AssertionError("valid candidate must be reused")

    second = run_alignment_candidate(run.name, tmp_path, MustNotRun())
    after = json.loads((run / "run.json").read_text(encoding="utf-8"))
    assert second == first
    assert after["stages"]["audio_alignment"]["attempts"] == before["stages"]["audio_alignment"]["attempts"]


def test_candidate_stage_rejects_stale_voice_approval_before_provider_call(tmp_path) -> None:
    run, _ = _production_ready_run(tmp_path)
    review = json.loads((run / "audio" / "review.json").read_text(encoding="utf-8"))
    review["audio_sha256"] = "b" * 64
    registry = ArtifactRegistry(run, RunManifest.model_validate(
        json.loads((run / "run.json").read_text(encoding="utf-8"))
    ))
    _mark_json(registry, "audio/review.json", review)
    registry.save_manifest()

    class MustNotRun(MeasuredProvider):
        def align(self, request):
            raise AssertionError("provider must not run")

    import pytest
    with pytest.raises(ValueError, match="VOICE_APPROVAL_STALE"):
        run_alignment_candidate(run.name, tmp_path, MustNotRun())
    manifest = json.loads((run / "run.json").read_text(encoding="utf-8"))
    assert manifest["stages"]["audio_alignment"]["status"] == "failed"
    assert manifest["artifacts"]["alignment_candidate.json"]["status"] == "failed"


def test_asr_mismatch_persists_failed_candidate_for_human_diagnostics(tmp_path) -> None:
    run, _ = _production_ready_run(tmp_path)

    class MismatchedAsrProvider(MeasuredProvider):
        def align(self, request):
            result = super().align(request)
            return AlignmentResult(
                **{**result.__dict__, "recognized_text": "第二句。第一句。"}
            )

    import pytest
    with pytest.raises(ValueError, match="ALIGNMENT_ASR_REFERENCE_MISMATCH"):
        run_alignment_candidate(run.name, tmp_path, MismatchedAsrProvider())
    manifest = json.loads((run / "run.json").read_text(encoding="utf-8"))
    assert (run / "alignment_candidate.json").is_file()
    assert manifest["artifacts"]["alignment_candidate.json"]["status"] == "failed"
    assert manifest["artifacts"]["alignment_candidate.json"]["content_hash"]
    assert manifest["artifacts"]["alignment.json"]["status"] != "valid"
