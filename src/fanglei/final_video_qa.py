"""Immutable final-candidate media QA and the gated human review owner."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from fanglei.artifacts import read_json, sha256_bytes
from fanglei.errors import ArtifactConflictError
from fanglei.final_render import (
    ArtifactBinding, FinalVideoCandidateV1, _path, _registry,
    validate_final_render_request,
)
from fanglei.v05_models import TimelineDocument


QA_OWNER_VERSION = "1.1"
MINIMUM_FRAME_SIMILARITY = 0.94


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class FinalVideoQACheckV1(_Contract):
    check_id: str = Field(min_length=1)
    status: Literal["pass", "fail", "caution"]
    blocking: bool
    summary: str = Field(min_length=1)
    evidence: dict[str, Any]


class FinalVideoQAReportV1(_Contract):
    schema_version: Literal["final-video-qa/1.0"] = "final-video-qa/1.0"
    run_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    media: ArtifactBinding
    candidate: ArtifactBinding
    request: ArtifactBinding
    human_preview_approval: ArtifactBinding
    preview: ArtifactBinding
    timeline: ArtifactBinding
    qa_owner_version: Literal["1.0"] = "1.0"
    executed_at: datetime
    result: Literal["passed", "failed"]
    checks: list[FinalVideoQACheckV1]
    measurements: dict[str, Any]

    @field_validator("executed_at")
    @classmethod
    def timezone_aware(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("FINAL_VIDEO_QA_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
        return value

    @model_validator(mode="after")
    def result_matches_checks(self):
        blocking_failure = any(check.blocking and check.status == "fail" for check in self.checks)
        if blocking_failure and self.result != "failed":
            raise ValueError("blocking QA failure cannot be labeled passed")
        if self.result == "failed" and not blocking_failure:
            raise ValueError("failed QA requires a blocking failure")
        return self


class FinalVideoQAReportV2(FinalVideoQAReportV1):
    """A new immutable evaluation, linked to the prior attempt when superseding."""
    schema_version: Literal["final-video-qa/1.1"] = "final-video-qa/1.1"
    qa_owner_version: Literal["1.1"] = QA_OWNER_VERSION
    attempt_number: int = Field(ge=1)
    previous_qa: ArtifactBinding | None
    implementation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def previous_attempt_required(self):
        if (self.attempt_number == 1) != (self.previous_qa is None):
            raise ValueError("FINAL_VIDEO_QA_ATTEMPT_CHAIN_INVALID")
        return self


def _implementation_sha256():
    root = Path(__file__).parent
    return sha256_bytes(b"\0".join((root / name).read_bytes() for name in (
        "final_video_qa.py", "final_video_probe.mjs",
    )))


def _qa_report(path):
    raw = read_json(path)
    if raw.get("schema_version") == "final-video-qa/1.0":
        return FinalVideoQAReportV1.model_validate_json(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") == "final-video-qa/1.1":
        return FinalVideoQAReportV2.model_validate_json(path.read_text(encoding="utf-8"))
    raise ValueError("FINAL_VIDEO_QA_VERSION_UNSUPPORTED")


def _qa_name(number):
    return "final_video_qa.json" if number == 1 else f"final_video_qa_attempt_{number}.json"


def _latest_qa_number(registry):
    numbers = [1]
    for name in registry.graph:
        if name.startswith("final_video_qa_attempt_"):
            numbers.append(int(name.removeprefix("final_video_qa_attempt_").removesuffix(".json")))
    return max(numbers)


def _ffprobe_json_metadata(raw):
    """Validate the ffprobe JSON boundary; never infer absent technical properties."""
    def positive(value, integer=False):
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise ValueError("FFPROBE_PROPERTY_INVALID")
        try:
            result = int(value) if integer else float(value)
        except (ValueError, TypeError, OverflowError) as error:
            raise ValueError("FFPROBE_PROPERTY_INVALID") from error
        if not math.isfinite(result) or result <= 0 or (integer and str(result) != str(value)):
            raise ValueError("FFPROBE_PROPERTY_INVALID")
        return result
    if not isinstance(raw, dict) or not isinstance(raw.get("streams"), list) or not isinstance(raw.get("format"), dict):
        raise ValueError("FFPROBE_JSON_INVALID")
    if "mp4" not in raw["format"].get("format_name", "").split(","):
        raise ValueError("FFPROBE_CONTAINER_INVALID")
    if not all(isinstance(row, dict) for row in raw["streams"]):
        raise ValueError("FFPROBE_STREAM_INVALID")
    tracks = {}
    for kind, handler in (("video", "vide"), ("audio", "soun")):
        rows = [row for row in raw["streams"] if row.get("codec_type") == kind]
        if len(rows) > 1:
            raise ValueError("FFPROBE_AMBIGUOUS_STREAMS")
        if not rows:
            tracks[kind] = None
            continue
        row = rows[0]
        if not isinstance(row.get("codec_name"), str) or not row["codec_name"]:
            raise ValueError("FFPROBE_CODEC_INVALID")
        track = {"handler": handler, "codec": row["codec_name"],
                 "duration_seconds": positive(row.get("duration"))}
        if kind == "video":
            try:
                numerator, denominator = row["avg_frame_rate"].split("/")
                fps = positive(numerator) / positive(denominator)
            except (KeyError, AttributeError, ValueError) as error:
                raise ValueError("FFPROBE_FRAME_RATE_INVALID") from error
            track.update(width=positive(row.get("width"), True), height=positive(row.get("height"), True),
                         fps=fps, frame_count=positive(row.get("nb_read_frames", row.get("nb_frames")), True))
        else:
            track.update(sample_rate=positive(row.get("sample_rate"), True), channels=positive(row.get("channels"), True))
        tracks[kind] = track
    return {"container": "mp4", "container_duration_seconds": positive(raw["format"].get("duration")),
            **tracks, "track_count": len(raw["streams"])}


def _ffprobe_metadata(media_path, executable):
    try:
        result = subprocess.run([str(executable), "-v", "error", "-count_frames", "-show_format", "-show_streams",
                                 "-of", "json", str(media_path)], capture_output=True, text=True,
                                encoding="utf-8", check=False, timeout=180)
        if result.returncode:
            raise ValueError("FFPROBE_FAILED: " + result.stderr[-500:])
        return _ffprobe_json_metadata(json.loads(result.stdout))
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        raise ValueError("FFPROBE_FAILED: " + str(error)) from error


def _ffprobe_tool(node, configured=None):
    path = configured or os.environ.get("FENGLEI_FFPROBE") or os.environ.get("HYPERFRAMES_FFPROBE_PATH")
    if not path:
        # Resolve the repository-local dependency through its own exported path.
        module = Path(__file__).resolve().parents[2] / "tools/ffmpeg/node_modules/ffprobe-static"
        result = subprocess.run([node, "-e", "console.log(require(process.argv[1]).path)", str(module)],
                                capture_output=True, text=True, check=False, timeout=20)
        if result.returncode == 0:
            path = result.stdout.strip()
    if not path or not Path(path).is_absolute() or not Path(path).is_file():
        raise ValueError("FINAL_VIDEO_QA_FFPROBE_UNAVAILABLE")
    return Path(path).resolve()


class HumanFinalVideoReviewEntryV1(_Contract):
    schema_version: Literal["human-final-video-review-entry/1.0"] = "human-final-video-review-entry/1.0"
    run_id: str
    case_id: str
    candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    qa_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["ready_for_human_review"] = "ready_for_human_review"


class HumanFinalVideoReviewV1(_Contract):
    schema_version: Literal["human-final-video-review/1.0"] = "human-final-video-review/1.0"
    run_id: str
    case_id: str
    candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    qa_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewer: str = Field(min_length=1)
    decision: Literal["approved", "changes_required"]
    reviewed_at: datetime
    rationale: str = Field(min_length=1)

    @field_validator("reviewer", "rationale")
    @classmethod
    def nonempty_text(cls, value):
        if not value.strip():
            raise ValueError("FINAL_VIDEO_REVIEW_TEXT_REQUIRED")
        return value

    @field_validator("reviewed_at")
    @classmethod
    def timezone_aware(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("FINAL_VIDEO_REVIEW_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
        return value


def _box_rows(data: bytes, start: int, end: int):
    if not 0 <= start <= end <= len(data):
        raise ValueError("MP4_BOX_SCOPE_INVALID")
    rows = []
    cursor = start
    while cursor + 8 <= end:
        size = int.from_bytes(data[cursor:cursor + 4], "big")
        kind = data[cursor + 4:cursor + 8]
        header = 8
        if size == 1:
            if cursor + 16 > end:
                raise ValueError("MP4_BOX_TRUNCATED")
            size = int.from_bytes(data[cursor + 8:cursor + 16], "big")
            header = 16
        elif size == 0:
            size = end - cursor
        if size < header or cursor + size > end:
            raise ValueError("MP4_BOX_SIZE_INVALID")
        rows.append((kind, cursor, cursor + header, cursor + size))
        cursor += size
    if cursor != end:
        raise ValueError("MP4_BOX_TRAILING_BYTES")
    return rows


def _children(data: bytes, parent, skip=None):
    kind, _start, payload, end = parent
    if skip is None:
        # FullBox and sample-entry prefixes are structured fields, not boxes.
        skip = {b"meta": 4, b"stsd": 8, b"avc1": 78, b"mp4a": 28}.get(kind, 0)
    rows = _box_rows(data, payload + skip, end)
    if kind == b"stsd" and len(rows) != int.from_bytes(data[payload + 4:payload + 8], "big"):
        raise ValueError("MP4_SAMPLE_ENTRY_COUNT_INVALID")
    return rows


def _find(rows, kind):
    return next((row for row in rows if row[0] == kind), None)


def _mp4_metadata(data: bytes) -> dict[str, Any]:
    if len(data) < 16 or data[4:8] != b"ftyp":
        raise ValueError("MP4_CONTAINER_INVALID")
    top = _box_rows(data, 0, len(data))
    moov = _find(top, b"moov")
    if moov is None:
        raise ValueError("MP4_MOOV_MISSING")
    moov_children = _children(data, moov)
    # Validate metadata containers without descending into opaque leaf payloads.
    for udta in (row for row in moov_children if row[0] == b"udta"):
        for meta in (row for row in _children(data, udta) if row[0] == b"meta"):
            _children(data, meta)
    mvhd = _find(moov_children, b"mvhd")
    if mvhd is None:
        raise ValueError("MP4_MVHD_MISSING")
    version = data[mvhd[2]]
    timescale_offset = mvhd[2] + (20 if version == 1 else 12)
    duration_offset = timescale_offset + 4
    movie_timescale = int.from_bytes(data[timescale_offset:timescale_offset + 4], "big")
    if movie_timescale <= 0:
        raise ValueError("MP4_MOVIE_TIMESCALE_INVALID")
    duration_width = 8 if version == 1 else 4
    movie_duration = int.from_bytes(data[duration_offset:duration_offset + duration_width], "big")
    tracks = []
    tracks_by_id = {}
    trex_durations = {}
    for trak in (row for row in moov_children if row[0] == b"trak"):
        trak_children = _children(data, trak)
        tkhd, mdia = _find(trak_children, b"tkhd"), _find(trak_children, b"mdia")
        if tkhd is None or mdia is None:
            continue
        tkhd_version = data[tkhd[2]]
        track_id_offset = tkhd[2] + (20 if tkhd_version == 1 else 12)
        track_id = int.from_bytes(data[track_id_offset:track_id_offset + 4], "big")
        mdia_children = _children(data, mdia)
        hdlr, mdhd, minf = (_find(mdia_children, key) for key in (b"hdlr", b"mdhd", b"minf"))
        if hdlr is None or mdhd is None or minf is None:
            continue
        handler = data[hdlr[2] + 8:hdlr[2] + 12].decode("ascii", "replace")
        mdhd_version = data[mdhd[2]]
        media_timescale_offset = mdhd[2] + (20 if mdhd_version == 1 else 12)
        media_duration_offset = media_timescale_offset + 4
        media_timescale = int.from_bytes(data[media_timescale_offset:media_timescale_offset + 4], "big")
        if media_timescale <= 0:
            raise ValueError("MP4_MEDIA_TIMESCALE_INVALID")
        media_width = 8 if mdhd_version == 1 else 4
        media_duration = int.from_bytes(data[media_duration_offset:media_duration_offset + media_width], "big")
        minf_children = _children(data, minf)
        stbl = _find(minf_children, b"stbl")
        sample_entry = None
        stts = None
        if stbl:
            stbl_children = _children(data, stbl)
            stsd, stts = _find(stbl_children, b"stsd"), _find(stbl_children, b"stts")
            if stsd:
                entries = _children(data, stsd, skip=8)
                sample_entry = entries[0] if entries else None
        track = {
            "track_id": track_id,
            "handler": handler, "timescale": media_timescale,
            "duration_seconds": media_duration / media_timescale if media_timescale else None,
            "sample_entry": sample_entry[0].decode("ascii", "replace") if sample_entry else None,
        }
        sample_count = 0
        sample_ticks = 0
        if sample_entry and handler == "vide":
            track["width"] = int.from_bytes(data[sample_entry[2] + 24:sample_entry[2] + 26], "big")
            track["height"] = int.from_bytes(data[sample_entry[2] + 26:sample_entry[2] + 28], "big")
            entry_children = _children(data, sample_entry, skip=78)
            avcc = _find(entry_children, b"avcC")
            if avcc and avcc[3] - avcc[2] >= 12:
                track["codec"] = "h264"
                track["codec_profile"] = "avc1." + data[avcc[2] + 1:avcc[2] + 4].hex()
            else:
                track["codec"] = track["sample_entry"]
        elif sample_entry and handler == "soun":
            track["channels"] = int.from_bytes(data[sample_entry[2] + 16:sample_entry[2] + 18], "big")
            track["sample_rate"] = int.from_bytes(data[sample_entry[2] + 24:sample_entry[2] + 28], "big") >> 16
            track["codec"] = "aac" if sample_entry[0] == b"mp4a" else track["sample_entry"]
            _children(data, sample_entry)
        if stts:
            payload, end = stts[2], stts[3]
            if end - payload < 8:
                raise ValueError("MP4_STTS_TRUNCATED")
            entry_count = int.from_bytes(data[payload + 4:payload + 8], "big")
            if payload + 8 + entry_count * 8 != end:
                raise ValueError("MP4_STTS_ENTRY_COUNT_INVALID")
            for cursor in range(payload + 8, end, 8):
                count = int.from_bytes(data[cursor:cursor + 4], "big")
                delta = int.from_bytes(data[cursor + 4:cursor + 8], "big")
                if not count or not delta:
                    raise ValueError("MP4_STTS_TIMING_INVALID")
                sample_count += count
                sample_ticks += count * delta
        track["sample_count"] = sample_count
        track["sample_ticks"] = sample_ticks
        tracks.append(track)
        tracks_by_id[track_id] = track
    mvex = _find(moov_children, b"mvex")
    if mvex is not None:
        for trex in (row for row in _children(data, mvex) if row[0] == b"trex"):
            payload = trex[2]
            tid = int.from_bytes(data[payload + 4:payload + 8], "big")
            trex_durations[tid] = int.from_bytes(data[payload + 12:payload + 16], "big")
    fragment_stats = {track_id: [0, 0] for track_id in tracks_by_id}
    for moof in (row for row in top if row[0] == b"moof"):
        for traf in (row for row in _children(data, moof) if row[0] == b"traf"):
            traf_children = _children(data, traf)
            tfhd = _find(traf_children, b"tfhd")
            if tfhd is None:
                continue
            payload = tfhd[2]
            flags = int.from_bytes(data[payload:payload + 4], "big") & 0xFFFFFF
            tid = int.from_bytes(data[payload + 4:payload + 8], "big")
            cursor = payload + 8
            if flags & 0x000001:
                cursor += 8
            if flags & 0x000002:
                cursor += 4
            default_duration = trex_durations.get(tid, 0)
            if flags & 0x000008:
                default_duration = int.from_bytes(data[cursor:cursor + 4], "big")
                cursor += 4
            if flags & 0x000010:
                cursor += 4
            if flags & 0x000020:
                cursor += 4
            if tid not in fragment_stats:
                continue
            for trun in (row for row in traf_children if row[0] == b"trun"):
                run_payload = trun[2]
                run_flags = int.from_bytes(data[run_payload:run_payload + 4], "big") & 0xFFFFFF
                count = int.from_bytes(data[run_payload + 4:run_payload + 8], "big")
                run_cursor = run_payload + 8
                if run_flags & 0x000001:
                    run_cursor += 4
                if run_flags & 0x000004:
                    run_cursor += 4
                total_duration = 0
                for _ in range(count):
                    sample_duration = default_duration
                    if run_flags & 0x000100:
                        sample_duration = int.from_bytes(data[run_cursor:run_cursor + 4], "big")
                        run_cursor += 4
                    if run_flags & 0x000200:
                        run_cursor += 4
                    if run_flags & 0x000400:
                        run_cursor += 4
                    if run_flags & 0x000800:
                        run_cursor += 4
                    total_duration += sample_duration
                fragment_stats[tid][0] += count
                fragment_stats[tid][1] += total_duration
    for track in tracks:
        tid = track["track_id"]
        fragment_count, fragment_ticks = fragment_stats[tid]
        sample_count, sample_ticks = track.pop("sample_count"), track.pop("sample_ticks")
        if fragment_count:
            sample_count, sample_ticks = fragment_count, fragment_ticks
        if sample_count:
            track["sample_count"] = sample_count
            track["duration_seconds"] = sample_ticks / track["timescale"] if sample_ticks else track["duration_seconds"]
            if track["handler"] == "vide":
                track["frame_count"] = sample_count
                track["fps"] = sample_count * track["timescale"] / sample_ticks if sample_ticks else None
    for track in tracks:
        track.pop("track_id", None)
    video = next((row for row in tracks if row["handler"] == "vide"), None)
    audio = next((row for row in tracks if row["handler"] == "soun"), None)
    if video is None:
        raise ValueError("MP4_VIDEO_TRACK_MISSING")
    return {
        "container": "mp4", "container_duration_seconds": movie_duration / movie_timescale,
        "video": video, "audio": audio, "track_count": len(tracks),
    }


def _sample_plan(timeline: TimelineDocument, width: int, height: int, fps: int):
    rows = []
    composition = timeline.composition
    if composition is None:
        return rows
    region = composition.subtitle_layout.reserved_zone.model_dump(mode="json")
    duration_ms = int(timeline.audio.get("duration_ms", 0))
    frame_ms = max(1, round(1000 / fps))
    add = lambda sample_id, time_ms, subtitle_region=None: rows.append({
        "sample_id": sample_id, "time_ms": max(0, min(duration_ms - 1, round(time_ms))),
        **({"subtitle_region": subtitle_region} if subtitle_region else {}),
    })
    add("opening", min(frame_ms, duration_ms / 20))
    scenes = timeline.scenes
    for index, scene in enumerate(scenes):
        add(f"scene-interior-{index + 1}", (scene.start_ms + scene.end_ms) / 2)
        if index + 1 < len(scenes):
            boundary = scene.end_ms
            add(f"scene-boundary-{index + 1}-left", boundary - frame_ms)
            add(f"scene-boundary-{index + 1}-right", boundary + frame_ms)
    for index, cue in enumerate(composition.subtitle_cues):
        add(f"subtitle-cue-{index + 1}", (cue.start_ms + cue.end_ms) / 2, region)
    add("ending", max(0, duration_ms - frame_ms))
    return rows


def _check(check_id, passed, summary, evidence, *, blocking=True):
    return FinalVideoQACheckV1(
        check_id=check_id, status="pass" if passed else "fail", blocking=blocking,
        summary=summary, evidence=evidence,
    )


def _registry_candidate(run_dir: Path):
    candidate_registry = _registry(run_dir)
    candidate_registry.validate("final_video_candidate.json")
    candidate = FinalVideoCandidateV1.model_validate(candidate_registry.read_json("final_video_candidate.json"))
    request = validate_final_render_request(run_dir)
    candidate_state = candidate_registry.manifest.artifacts["final_video_candidate.json"]
    media_state = candidate_registry.manifest.artifacts["final.mp4"]
    request_state = candidate_registry.manifest.artifacts["final_render_request.json"]
    if candidate.run_id != request.run_id or candidate.case_id != request.case_id:
        raise ArtifactConflictError("FINAL_VIDEO_CANDIDATE_IDENTITY_MISMATCH")
    if candidate.media.sha256 != media_state.content_hash or candidate.media.path != "final.mp4":
        raise ArtifactConflictError("FINAL_VIDEO_CANDIDATE_MEDIA_BINDING_INVALID")
    if candidate.request.sha256 != request_state.content_hash or candidate.provenance != request:
        raise ArtifactConflictError("FINAL_VIDEO_CANDIDATE_REQUEST_BINDING_INVALID")
    render_manifest = candidate_registry.manifest.artifacts["render_manifest_final.json"]
    if candidate.render_manifest.path != "render_manifest_final.json" or candidate.render_manifest.sha256 != render_manifest.content_hash:
        raise ArtifactConflictError("FINAL_VIDEO_CANDIDATE_RENDER_MANIFEST_BINDING_INVALID")
    return candidate_registry, candidate, request, candidate_state.content_hash


def _qa_inputs_match(qa, registry, candidate, request, candidate_sha):
    manifest = registry.manifest
    expected = (
        qa.run_id == candidate.run_id == request.run_id == manifest.run_id
        and qa.case_id == candidate.case_id == request.case_id
        and qa.media.path == candidate.media.path
        and qa.media.sha256 == manifest.artifacts[candidate.media.path].content_hash
        and qa.candidate.path == "final_video_candidate.json"
        and qa.candidate.sha256 == candidate_sha
        and qa.request.path == "final_render_request.json"
        and qa.request.sha256 == manifest.artifacts["final_render_request.json"].content_hash
        and qa.human_preview_approval == request.human_preview_approval
        and qa.preview == request.preview
        and qa.timeline == request.timeline
    )
    return expected and all(
        binding.sha256 == manifest.artifacts[binding.path].content_hash
        for binding in (qa.human_preview_approval, qa.preview, qa.timeline)
    )


def _current_qa(registry, name):
    qa = _qa_report(_path(registry, name))
    if isinstance(qa, FinalVideoQAReportV2):
        number = _latest_qa_number(registry)
        if qa.attempt_number != number:
            raise ValueError("FINAL_VIDEO_QA_ATTEMPT_CHAIN_INVALID")
        if qa.implementation_sha256 != _implementation_sha256():
            raise ValueError("FINAL_VIDEO_QA_IMPLEMENTATION_STALE")
        if number > 1:
            expected_path = _qa_name(number - 1)
            if qa.previous_qa.path != expected_path or qa.previous_qa.sha256 != registry.manifest.artifacts[expected_path].content_hash:
                raise ValueError("FINAL_VIDEO_QA_ATTEMPT_CHAIN_INVALID")
    elif _latest_qa_number(registry) != 1:
        raise ValueError("FINAL_VIDEO_QA_ATTEMPT_CHAIN_INVALID")
    return qa


def _node_tools(node_path=None, puppeteer_module=None, browser_path=None):
    node = node_path or os.environ.get("FENGLEI_RENDER_NODE")
    puppeteer = puppeteer_module or os.environ.get("FENGLEI_PUPPETEER_MODULE")
    browser = browser_path or os.environ.get("FENGLEI_RENDER_BROWSER")
    if not all((node, puppeteer, browser)) or not all(Path(value).exists() for value in (node, puppeteer, browser)):
        raise ValueError("FINAL_VIDEO_QA_TOOLCHAIN_UNAVAILABLE")
    return str(node), str(puppeteer), str(browser)


def run_final_video_qa(
    run_dir: Path, *, node_path: str | Path | None = None,
    puppeteer_module: str | Path | None = None, browser_path: str | Path | None = None,
    ffprobe_path: str | Path | None = None, reevaluate: bool = False,
    expected_previous_qa_sha256: str | None = None,
) -> Path:
    """Write one immutable evaluation; explicit re-evaluation preserves failed history."""
    run_dir = Path(run_dir).resolve()
    registry, candidate, request, candidate_sha = _registry_candidate(run_dir)
    registry.validate("final.mp4")
    registry.validate(f"human_preview_review_candidate_{request.preview_candidate_id}.json")
    registry.validate("final_render_request.json")
    number = _latest_qa_number(registry)
    name = _qa_name(number)
    qa_state = registry.manifest.artifacts[name]
    qa_path = _path(registry, name)
    previous = None
    if qa_state.status != "missing" or qa_path.exists():
        if not reevaluate:
            raise ArtifactConflictError("FINAL_VIDEO_QA_ALREADY_EXISTS")
        registry.validate(name)
        old = _qa_report(qa_path)
        if expected_previous_qa_sha256 != qa_state.content_hash:
            raise ArtifactConflictError("FINAL_VIDEO_QA_EXPECTED_PREVIOUS_HASH_MISMATCH")
        if not _qa_inputs_match(old, registry, candidate, request, candidate_sha):
            raise ArtifactConflictError("FINAL_VIDEO_QA_PREVIOUS_INPUT_BINDING_MISMATCH")
        if old.result != "failed" or (isinstance(old, FinalVideoQAReportV2)
                                     and old.implementation_sha256 == _implementation_sha256()):
            raise ArtifactConflictError("FINAL_VIDEO_QA_ALREADY_EXISTS")
        if registry.manifest.artifacts["human_final_video_review.json"].status != "missing":
            raise ArtifactConflictError("FINAL_VIDEO_QA_HUMAN_REVIEW_ALREADY_EXISTS")
        previous = ArtifactBinding(path=name, sha256=qa_state.content_hash)
        number += 1
        name = _qa_name(number)
        registry = _registry(run_dir, qa_attempt=number)
        if _path(registry, name).exists():
            raise ArtifactConflictError("FINAL_VIDEO_QA_ALREADY_EXISTS")
    elif reevaluate:
        raise ArtifactConflictError("FINAL_VIDEO_QA_PREVIOUS_ATTEMPT_MISSING")
    media_path = _path(registry, candidate.media.path)
    preview_path = _path(registry, request.preview.path)
    timeline_path = _path(registry, request.timeline.path)
    timeline = TimelineDocument.model_validate(read_json(timeline_path))
    expected_width = request.render_configuration.width
    expected_height = request.render_configuration.height
    samples = _sample_plan(
        timeline, expected_width, expected_height, request.render_configuration.fps,
    )
    node, puppeteer, browser = _node_tools(node_path, puppeteer_module, browser_path)
    ffprobe = _ffprobe_tool(node, ffprobe_path)
    implementation_sha = _implementation_sha256()
    with tempfile.TemporaryDirectory(prefix="fanglei-final-video-qa-") as temporary:
        sample_path = Path(temporary) / "samples.json"
        sample_path.write_text(json.dumps(samples, ensure_ascii=False), encoding="utf-8")
        script = Path(__file__).with_name("final_video_probe.mjs")
        timeout = max(90, int(request.render_configuration.duration_ms / 1000 * 3 + 60))
        try:
            proc = subprocess.run(
                [node, str(script), puppeteer, browser, str(media_path), str(preview_path), str(sample_path),
                 str(expected_width), str(expected_height)],
                check=False, capture_output=True, text=True, encoding="utf-8", timeout=timeout,
            )
            if proc.returncode:
                raise ValueError("FINAL_VIDEO_QA_BROWSER_PROBE_FAILED: " + proc.stderr[-1000:])
            probe = json.loads(proc.stdout)
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
            raise ValueError(f"FINAL_VIDEO_QA_BROWSER_PROBE_FAILED: {error}") from error
    media_bytes = media_path.read_bytes()
    expected_duration_ms = request.render_configuration.duration_ms
    tolerance_seconds = max(0.20, 2 / request.render_configuration.fps)
    final_probe = probe.get("final", {})
    preview_probe = probe.get("preview", {})
    full_decode = probe.get("full_decode", {})
    try:
        final_mp4 = _ffprobe_metadata(media_path, ffprobe)
    except (ValueError, IndexError, OverflowError) as error:
        final_mp4 = None
        mp4_error = str(error)
    else:
        mp4_error = None
    preview_bytes = preview_path.read_bytes()
    try:
        preview_mp4 = _ffprobe_metadata(preview_path, ffprobe)
    except (ValueError, IndexError, OverflowError) as error:
        preview_mp4 = None
        preview_mp4_error = str(error)
    else:
        preview_mp4_error = None
    samples_by_id = {row.get("sample_id"): row for row in probe.get("samples", [])}
    interior_ids = [f"scene-interior-{index + 1}" for index in range(len(timeline.scenes))]
    cue_ids = [f"subtitle-cue-{index + 1}" for index in range(len(timeline.composition.subtitle_cues))]
    boundary_ids = [row["sample_id"] for row in samples if row["sample_id"].startswith("scene-boundary-")]
    threshold = MINIMUM_FRAME_SIMILARITY
    interior = [samples_by_id.get(key, {}) for key in interior_ids]
    cue_rows = [samples_by_id.get(key, {}) for key in cue_ids]
    boundary = [samples_by_id.get(key, {}) for key in boundary_ids]
    final_duration = final_mp4["container_duration_seconds"] if final_mp4 else final_probe.get("duration_seconds")
    audio_track = final_mp4.get("audio") if final_mp4 else None
    video_track = final_mp4.get("video") if final_mp4 else None
    cue_texts = [cue.text for cue in timeline.composition.subtitle_cues]
    subtitle_track = read_json(_path(registry, request.subtitle.path))
    registered_texts = [cue.get("text") for cue in subtitle_track.get("cues", [])]
    packaged_timeline = read_json(_path(registry, f"{request.source_renderer_package.path}/data/timeline.json"))
    package_subtitles = packaged_timeline.get("composition", {}).get("subtitle_cues", [])
    package_texts = [cue.get("text") for cue in package_subtitles]
    layout = timeline.composition.subtitle_layout
    reserved = layout.reserved_zone
    layout_valid = (
        reserved.x >= 0 and reserved.y >= 0 and reserved.width > 0 and reserved.height > 0
        and reserved.x + reserved.width <= expected_width
        and reserved.y + reserved.height <= expected_height
        and all(len(cue.lines) <= layout.maximum_lines for cue in timeline.composition.subtitle_cues)
    )
    checks = [
        _check("media_exists", len(media_bytes) > 0, "Registered candidate media is non-empty.", {"size_bytes": len(media_bytes)}),
        _check("full_media_decode", bool(full_decode.get("ended")) and not full_decode.get("error") and full_decode.get("decoded_frames", 0) > 0,
               "Chromium decoded the complete final video playback.", full_decode),
        _check("video_stream", bool(final_mp4 and video_track), "MP4 contains a video track.", {"video_track": video_track, "error": mp4_error}),
        _check("audio_stream", bool(final_mp4 and audio_track and final_probe.get("audio_track_count", 0) > 0),
               "MP4 contains an audio track exposed by the media decoder.", {"audio_track": audio_track, "browser_audio_tracks": final_probe.get("audio_track_count", 0)}),
        _check("video_dimensions", bool(video_track and video_track.get("width") == expected_width and video_track.get("height") == expected_height),
               "Encoded dimensions match the approved render configuration.", {"actual": {"width": video_track.get("width") if video_track else None, "height": video_track.get("height") if video_track else None}, "expected": {"width": expected_width, "height": expected_height}}),
        _check("frame_rate", bool(video_track and video_track.get("fps") is not None and abs(video_track["fps"] - request.render_configuration.fps) <= 0.5),
               "Encoded sample timing matches the approved frame rate.", {"actual_fps": video_track.get("fps") if video_track else None, "expected_fps": request.render_configuration.fps}),
        _check("frame_count", bool(video_track and video_track.get("frame_count", 0) > 0 and abs(video_track["frame_count"] - request.render_configuration.frame_count) <= max(1, round(request.render_configuration.frame_count * 0.02))),
               "Encoded frame count is within the approved render tolerance.", {"actual": video_track.get("frame_count") if video_track else None, "expected": request.render_configuration.frame_count}),
        _check("video_codec", bool(video_track and video_track.get("codec", "").startswith(request.render_configuration.video_codec)),
               "Encoded video codec matches the approved profile.", {"actual": video_track.get("codec") if video_track else None, "expected": request.render_configuration.video_codec}),
        _check("audio_codec", bool(audio_track and audio_track.get("codec") == request.render_configuration.audio_codec),
               "Encoded audio codec matches the approved profile.", {"actual": audio_track.get("codec") if audio_track else None, "expected": request.render_configuration.audio_codec}),
        _check("audio_properties", bool(audio_track and audio_track.get("sample_rate", 0) > 0 and audio_track.get("channels", 0) > 0),
               "Audio sample rate and channel count are present.", {"sample_rate": audio_track.get("sample_rate") if audio_track else None, "channels": audio_track.get("channels") if audio_track else None}),
        _check("container_duration", bool(final_mp4 and final_duration is not None and abs(final_duration - expected_duration_ms / 1000) <= tolerance_seconds),
               "Container duration matches the approved render within frame tolerance.", {"actual_seconds": final_duration, "expected_seconds": expected_duration_ms / 1000, "tolerance_seconds": tolerance_seconds}),
        _check("audio_duration", bool(audio_track and audio_track.get("duration_seconds") is not None and abs(audio_track["duration_seconds"] - expected_duration_ms / 1000) <= tolerance_seconds),
               "Audio track duration matches the approved timeline within tolerance.", {"actual_seconds": audio_track.get("duration_seconds") if audio_track else None, "expected_seconds": expected_duration_ms / 1000, "tolerance_seconds": tolerance_seconds}),
        _check("scene_coverage", len(interior) == len(timeline.scenes) and all(row.get("full_frame_similarity") is not None and row["full_frame_similarity"] >= threshold for row in interior),
               "Each Timeline scene has an actual interior frame matching the approved Preview.", {"scene_ids": [scene.scene_id for scene in timeline.scenes], "samples": interior, "minimum_similarity": threshold}),
        _check("subtitle_coverage", bool(cue_texts) and cue_texts == registered_texts == package_texts and len(cue_rows) == len(cue_texts) and all(row.get("subtitle_region_similarity") is not None and row["subtitle_region_similarity"] >= threshold for row in cue_rows),
               "All exact Timeline subtitle texts are present in canonical and packaged metadata and their rendered regions match the approved Preview.", {"cue_count": len(cue_texts), "display_texts_match": cue_texts == registered_texts == package_texts, "samples": cue_rows, "minimum_similarity": threshold}),
        _check("subtitle_layout", layout_valid, "Subtitle geometry stays inside the canvas and respects the line limit.", {"reserved_zone": reserved.model_dump(mode="json"), "maximum_lines": layout.maximum_lines, "line_counts": [len(cue.lines) for cue in timeline.composition.subtitle_cues]}),
        _check("scene_boundary_regressions", len(boundary) == len(boundary_ids) and all(row.get("full_frame_similarity") is not None and row["full_frame_similarity"] >= threshold for row in boundary),
               "Frames on both sides of each scene boundary match the approved Preview.", {"samples": boundary, "minimum_similarity": threshold}),
        _check("opening_completeness", bool(samples_by_id.get("opening", {}).get("full_frame_similarity", 0) >= threshold and samples_by_id.get("opening", {}).get("final_average_luma", 0) > 0.015),
               "The opening frame matches the approved Preview and is not accidentally blank.", samples_by_id.get("opening", {})),
        _check("ending_completeness", bool(samples_by_id.get("ending", {}).get("full_frame_similarity", 0) >= threshold and samples_by_id.get("ending", {}).get("final_average_luma", 0) > 0.015),
               "The ending frame matches the approved Preview and is not accidentally blank.", samples_by_id.get("ending", {})),
        _check("preview_final_comparison", bool(preview_mp4 and final_mp4 and preview_mp4["video"].get("width") == video_track.get("width") and preview_mp4["video"].get("height") == video_track.get("height") and abs(preview_mp4["video"].get("fps", 0) - (video_track.get("fps") or 0)) <= 0.5 and abs(preview_mp4["container_duration_seconds"] - final_mp4["container_duration_seconds"]) <= tolerance_seconds and all(row.get("full_frame_similarity", 0) >= threshold for row in interior)),
               "Final media preserves approved Preview geometry, timing, and sampled scene content.", {"preview": preview_mp4, "final": final_mp4, "samples": interior, "preview_error": preview_mp4_error}),
    ]
    if final_probe.get("error") or preview_probe.get("error"):
        checks.append(_check("browser_media_load", False, "Browser could not load a media candidate.", {"final": final_probe.get("error"), "preview": preview_probe.get("error")}))
    else:
        checks.append(_check("browser_media_load", True, "Browser loaded both media candidates.", {"final": final_probe, "preview": preview_probe}))
    report = FinalVideoQAReportV2(
        attempt_number=number, previous_qa=previous, implementation_sha256=implementation_sha,
        run_id=candidate.run_id, case_id=candidate.case_id,
        media=ArtifactBinding(path="final.mp4", sha256=registry.manifest.artifacts["final.mp4"].content_hash),
        candidate=ArtifactBinding(path="final_video_candidate.json", sha256=candidate_sha),
        request=ArtifactBinding(path="final_render_request.json", sha256=registry.manifest.artifacts["final_render_request.json"].content_hash),
        human_preview_approval=request.human_preview_approval,
        preview=request.preview, timeline=request.timeline,
        executed_at=datetime.now(timezone.utc),
        result="failed" if any(check.blocking and check.status == "fail" for check in checks) else "passed",
        checks=checks,
        measurements={"final": final_mp4, "preview": preview_mp4, "full_decode": full_decode,
                      "sample_count": len(samples), "media_bytes": len(media_bytes),
                      "property_probe": {"tool": "ffprobe", "executable_sha256": sha256_bytes(ffprobe.read_bytes())}},
    )
    current_registry, current_candidate, current_request, current_candidate_sha = _registry_candidate(run_dir)
    current_registry.validate("final.mp4")
    review_name = f"human_preview_review_candidate_{current_request.preview_candidate_id}.json"
    current_registry.validate(review_name)
    current_registry.validate("final_render_request.json")
    current_bindings = {
        "final.mp4": current_registry.manifest.artifacts["final.mp4"].content_hash,
        "final_video_candidate.json": current_candidate_sha,
        "final_render_request.json": current_registry.manifest.artifacts["final_render_request.json"].content_hash,
        review_name: current_registry.manifest.artifacts[review_name].content_hash,
        current_request.preview.path: current_registry.manifest.artifacts[current_request.preview.path].content_hash,
        current_request.timeline.path: current_registry.manifest.artifacts[current_request.timeline.path].content_hash,
    }
    expected_bindings = {
        "final.mp4": report.media.sha256,
        "final_video_candidate.json": report.candidate.sha256,
        "final_render_request.json": report.request.sha256,
        review_name: report.human_preview_approval.sha256,
        current_request.preview.path: report.preview.sha256,
        current_request.timeline.path: report.timeline.sha256,
    }
    if (current_candidate != candidate or current_request != request or current_bindings != expected_bindings
            or implementation_sha != _implementation_sha256()):
        raise ArtifactConflictError("FINAL_VIDEO_QA_INPUT_CHANGED_DURING_RUN")
    if previous:
        current_registry.validate(previous.path)
        if current_registry.manifest.artifacts[previous.path].content_hash != previous.sha256:
            raise ArtifactConflictError("FINAL_VIDEO_QA_PREVIOUS_CHANGED_DURING_RUN")
    current_registry = _registry(run_dir, qa_attempt=number)
    if _path(current_registry, name).exists():
        raise ArtifactConflictError("FINAL_VIDEO_QA_ALREADY_EXISTS")
    path = current_registry.write_json(name, report.model_dump(mode="json"), "final_video_qa")
    current_registry.save_manifest()
    return path


def derive_final_video_qa_status(run_dir: Path) -> Literal["pending", "passed", "failed", "stale"]:
    registry = _registry(Path(run_dir))
    name = _qa_name(_latest_qa_number(registry))
    state = registry.manifest.artifacts[name]
    if state.status == "missing" and not (registry.run_dir / name).exists():
        return "pending"
    try:
        registry.validate(name)
        candidate_registry, candidate, request, candidate_sha = _registry_candidate(registry.run_dir)
        qa = _current_qa(registry, name)
    except (ArtifactConflictError, ValueError):
        return "stale"
    if not _qa_inputs_match(qa, candidate_registry, candidate, request, candidate_sha):
        return "stale"
    return qa.result


def validate_human_final_video_review_entry(run_dir: Path) -> HumanFinalVideoReviewEntryV1:
    registry, candidate, request, candidate_sha = _registry_candidate(Path(run_dir).resolve())
    name = _qa_name(_latest_qa_number(registry))
    registry.validate(name)
    qa_state = registry.manifest.artifacts[name]
    qa = _current_qa(registry, name)
    if qa.result != "passed":
        raise ValueError("FINAL_VIDEO_QA_NOT_PASSED")
    if not _qa_inputs_match(qa, registry, candidate, request, candidate_sha):
        raise ValueError("FINAL_VIDEO_QA_APPROVED_INPUT_BINDING_MISMATCH")
    return HumanFinalVideoReviewEntryV1(
        run_id=candidate.run_id, case_id=candidate.case_id, candidate_sha256=candidate_sha,
        qa_sha256=qa_state.content_hash,
        request_sha256=registry.manifest.artifacts["final_render_request.json"].content_hash,
    )


def record_human_final_video_review(
    run_dir: Path, *, reviewer: str, decision: Literal["approved", "changes_required"],
    rationale: str, expected_candidate_sha256: str, expected_qa_sha256: str,
) -> Path:
    entry = validate_human_final_video_review_entry(run_dir)
    if entry.candidate_sha256 != expected_candidate_sha256 or entry.qa_sha256 != expected_qa_sha256:
        raise ValueError("HUMAN_FINAL_VIDEO_REVIEW_EXPECTED_HASH_MISMATCH")
    review = HumanFinalVideoReviewV1(
        run_id=entry.run_id, case_id=entry.case_id, candidate_sha256=entry.candidate_sha256,
        qa_sha256=entry.qa_sha256, request_sha256=entry.request_sha256,
        reviewer=reviewer, decision=decision, reviewed_at=datetime.now(timezone.utc), rationale=rationale,
    )
    registry = _registry(Path(run_dir).resolve())
    review_path = _path(registry, "human_final_video_review.json")
    if review_path.exists() or registry.manifest.artifacts["human_final_video_review.json"].status != "missing":
        raise ArtifactConflictError("HUMAN_FINAL_VIDEO_REVIEW_ALREADY_EXISTS")
    path = registry.write_json("human_final_video_review.json", review.model_dump(mode="json"), "human_final_video_review")
    registry.save_manifest()
    return path
