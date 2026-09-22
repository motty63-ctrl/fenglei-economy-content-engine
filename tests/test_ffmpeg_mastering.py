from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from fanglei.providers.mastering import FFmpegLoudnormMasteringEngine
from fanglei.v1b_models import AudioMasteringConfig


class RecordingRunner:
    def __init__(self, source: Path):
        self.source = source
        self.calls = []

    def run(self, argv, *, phase):
        self.calls.append((phase, list(argv)))
        if phase in {"measure_input", "measure_output"}:
            values = {"input_i": "-22.00" if phase == "measure_input" else "-16.00",
                      "input_tp": "-7.00" if phase == "measure_input" else "-1.20",
                      "input_lra": "2.0", "input_thresh": "-32.0", "target_offset": "0.0"}
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": json.dumps(values)})()
        if phase == "normalize":
            shutil.copyfile(self.source, Path(argv[-1]))
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        if phase == "probe_output":
            payload = {"streams": [{"codec_name": "pcm_s16le", "sample_rate": "24000",
                                     "channels": 1}], "format": {"format_name": "wav", "duration": "2.0"}}
            return type("R", (), {"returncode": 0, "stdout": json.dumps(payload), "stderr": ""})()
        raise AssertionError(phase)


def test_ffmpeg_engine_uses_measure_then_apply_then_verify(tmp_path: Path):
    source = tmp_path / "input.wav"; source.write_bytes(b"not-used-by-runner")
    runner = RecordingRunner(source)
    result = FFmpegLoudnormMasteringEngine(runner=runner, ffmpeg="ffmpeg", ffprobe="ffprobe").master(
        source, AudioMasteringConfig())
    assert [phase for phase, _ in runner.calls] == [
        "measure_input", "normalize", "measure_output", "probe_output"]
    assert all("atempo" not in " ".join(argv) and "atrim" not in " ".join(argv)
               for _, argv in runner.calls)
    assert result.output_integrated_lufs == -16.0
    normalized_argv = runner.calls[1][1]
    assert "TP=-1.2" in " ".join(normalized_argv)


def test_ffmpeg_rejects_wrong_post_probe_contract(tmp_path: Path):
    source = tmp_path / "input.wav"; source.write_bytes(b"x")
    runner = RecordingRunner(source)
    original_run = runner.run
    def bad_run(argv, *, phase):
        result = original_run(argv, phase=phase)
        if phase == "probe_output":
            result.stdout = json.dumps({"streams": [{"codec_name": "aac", "sample_rate": "48000",
                                                     "channels": 2}],
                                        "format": {"format_name": "wav", "duration": "2.0"}})
        return result
    runner.run = bad_run
    with pytest.raises(ValueError, match="MASTERING_OUTPUT_FORMAT_INVALID"):
        FFmpegLoudnormMasteringEngine(runner=runner, ffmpeg="ffmpeg", ffprobe="ffprobe").master(
            source, AudioMasteringConfig())
