"""Replaceable audio-mastering engine and FFmpeg loudnorm adapter."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Protocol, Sequence

from fanglei.security import safe_error_message
from fanglei.v1b_models import AudioMasteringConfig


@dataclass(frozen=True)
class EngineMasteringResult:
    audio_bytes: bytes
    engine: str
    method: str
    input_integrated_lufs: float
    input_true_peak_dbtp: float
    output_integrated_lufs: float
    output_true_peak_dbtp: float
    output_codec: str
    output_format: str
    output_sample_rate_hz: int
    output_channels: int


class AudioMasteringEngine(Protocol):
    name: str

    def master(self, source_path: Path, config: AudioMasteringConfig) -> EngineMasteringResult: ...


class SubprocessRunner:
    def run(self, argv: Sequence[str], *, phase: str):
        del phase
        return subprocess.run(list(argv), capture_output=True, text=True, check=False)


def _loudnorm_json(stderr: str) -> dict[str, str]:
    candidates = re.findall(r"\{[^{}]+\}", stderr, flags=re.DOTALL)
    for candidate in reversed(candidates):
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if "input_i" in value and "input_tp" in value:
            return value
    raise ValueError("MASTERING_MEASUREMENT_PARSE_FAILED")


class FFmpegLoudnormMasteringEngine:
    name = "ffmpeg_loudnorm"

    def __init__(self, *, runner=None, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe"):
        self.runner = runner or SubprocessRunner()
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe

    def _run(self, argv: list[str], phase: str):
        result = self.runner.run(argv, phase=phase)
        if result.returncode != 0:
            raise ValueError(f"MASTERING_{phase.upper()}_FAILED:{safe_error_message(result.stderr)}")
        return result

    def _measure(self, path: Path, config: AudioMasteringConfig, phase: str) -> dict[str, str]:
        peak_target = config.maximum_true_peak_dbtp - config.true_peak_headroom_db
        filter_value = (
            f"loudnorm=I={config.target_integrated_lufs}:TP={peak_target:g}:"
            "LRA=11:print_format=json"
        )
        result = self._run([
            self.ffmpeg, "-hide_banner", "-nostats", "-i", str(path),
            "-af", filter_value, "-f", "null", "NUL",
        ], phase)
        return _loudnorm_json(result.stderr)

    def master(self, source_path: Path, config: AudioMasteringConfig) -> EngineMasteringResult:
        measured = self._measure(source_path, config, "measure_input")
        peak_target = config.maximum_true_peak_dbtp - config.true_peak_headroom_db
        applied = (
            f"loudnorm=I={config.target_integrated_lufs}:TP={peak_target:g}:LRA=11:"
            f"measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:"
            f"measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}:"
            f"offset={measured['target_offset']}:linear=true:print_format=summary"
        )
        with tempfile.TemporaryDirectory(prefix="fanglei-mastering-") as temp:
            output = Path(temp) / "mastered.wav"
            self._run([
                self.ffmpeg, "-y", "-hide_banner", "-nostats", "-i", str(source_path),
                "-af", applied, "-ar", str(config.sample_rate_hz), "-ac", str(config.channels),
                "-c:a", config.output_codec, str(output),
            ], "normalize")
            verified = self._measure(output, config, "measure_output")
            probe_result = self._run([
                self.ffprobe, "-v", "error", "-show_streams", "-show_format",
                "-of", "json", str(output),
            ], "probe_output")
            try:
                probe = json.loads(probe_result.stdout)
                stream = next(item for item in probe["streams"] if item.get("codec_type", "audio") == "audio")
                codec = str(stream["codec_name"])
                sample_rate = int(stream["sample_rate"])
                channels = int(stream["channels"])
                format_name = str(probe["format"]["format_name"])
            except (KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError) as error:
                raise ValueError("MASTERING_OUTPUT_PROBE_INVALID") from error
            if (codec != config.output_codec or sample_rate != config.sample_rate_hz
                    or channels != config.channels or "wav" not in format_name):
                raise ValueError("MASTERING_OUTPUT_FORMAT_INVALID")
            audio_bytes = output.read_bytes()
        return EngineMasteringResult(
            audio_bytes=audio_bytes, engine=self.name, method="ebu_r128_two_pass",
            input_integrated_lufs=float(measured["input_i"]),
            input_true_peak_dbtp=float(measured["input_tp"]),
            output_integrated_lufs=float(verified["input_i"]),
            output_true_peak_dbtp=float(verified["input_tp"]),
            output_codec=codec, output_format="wav", output_sample_rate_hz=sample_rate,
            output_channels=channels,
        )
