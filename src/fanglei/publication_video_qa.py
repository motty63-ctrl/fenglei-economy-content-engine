"""Independent publication-media QA attempts and the human release-review gate."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from array import array
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from fanglei.artifacts import read_json, sha256_bytes
from fanglei.errors import ArtifactConflictError
from fanglei.final_render import ArtifactBinding, _path
from fanglei.final_video_qa import _ffprobe_metadata
from fanglei.human_storyboard_recovery import canonical_json_sha256
from fanglei.publication_package import PACKAGE_ARTIFACT, PACKAGE_DIRECTORY, validate_publication_renderer_package
from fanglei.publication_render import (
    AUTHORIZED_DIFFERENCES, MEDIA_ARTIFACT, RENDER_MANIFEST,
    REQUEST_ARTIFACT, PublicationVideoV1,
    publication_render_registry, validate_publication_render_request,
)
from fanglei.v05_models import TimelineDocument


QA_IMPLEMENTATION_VERSION = "publication-video-qa-implementation/1.0"
QA_IMPLEMENTATION_SOURCES = ("publication_video_qa.py", "publication_video_probe.mjs")
MINIMUM_OUTSIDE_MASK_SIMILARITY = 0.94
MAXIMUM_OVERLAY_REGION_SIMILARITY = 0.985
REQUIRED_PUBLICATION_CHECKS = (
    "media_exists", "container_decode", "full_video_decode", "full_audio_decode", "video_stream", "audio_stream",
    "video_dimensions", "frame_rate", "frame_count", "video_codec", "audio_codec", "duration",
    "scene_coverage", "subtitle_coverage", "subtitle_text_unchanged", "subtitle_timing",
    "audio_equivalence", "source_footer",
    "opening", "ending", "subtitle_geometry", "subtitle_clipping", "subtitle_overflow",
    "black_frame_regression", "overlay_absence",
    "final_publication_comparison",
)


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PublicationQACheckV1(_Contract):
    check_id: str = Field(min_length=1)
    status: Literal["pass", "fail"]
    blocking: bool
    summary: str = Field(min_length=1)
    evidence: dict[str, Any]


class PublicationQAImplementationSourceV1(_Contract):
    relative_source_path: str
    canonical_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PublicationQAImplementationIdentityV1(_Contract):
    implementation_contract_version: Literal["publication-video-qa-implementation/1.0"] = QA_IMPLEMENTATION_VERSION
    sources: list[PublicationQAImplementationSourceV1]
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def identity_is_canonical(self):
        if tuple(row.relative_source_path for row in self.sources) != QA_IMPLEMENTATION_SOURCES:
            raise ValueError("PUBLICATION_QA_IMPLEMENTATION_PARTICIPANTS_INVALID")
        body = {"implementation_contract_version": self.implementation_contract_version,
                "sources": [row.model_dump(mode="json") for row in self.sources]}
        expected = sha256_bytes(json.dumps(body, ensure_ascii=False, sort_keys=True,
                                           separators=(",", ":")).encode("utf-8"))
        if self.sha256 != expected:
            raise ValueError("PUBLICATION_QA_IMPLEMENTATION_IDENTITY_INVALID")
        return self


def publication_qa_implementation_identity(source_root: Path | None = None):
    root = Path(source_root) if source_root is not None else Path(__file__).parent
    sources = []
    for relative in QA_IMPLEMENTATION_SOURCES:
        raw = (root / relative).read_bytes()
        raw.decode("utf-8", errors="strict")
        normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        sources.append(PublicationQAImplementationSourceV1(
            relative_source_path=relative, canonical_source_sha256=sha256_bytes(normalized),
        ))
    body = {"implementation_contract_version": QA_IMPLEMENTATION_VERSION,
            "sources": [row.model_dump(mode="json") for row in sources]}
    digest = sha256_bytes(json.dumps(body, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8"))
    return PublicationQAImplementationIdentityV1(sources=sources, sha256=digest)


def _implementation_sha256():
    return publication_qa_implementation_identity().sha256


class PublicationVideoQAReportV1(_Contract):
    schema_version: Literal["publication-video-qa/1.0"] = "publication-video-qa/1.0"
    run_id: str
    case_id: str
    attempt_number: int = Field(ge=1)
    previous_qa: ArtifactBinding | None
    publication_media: ArtifactBinding
    publication_media_file: ArtifactBinding
    publication_render_request: ArtifactBinding
    publication_render_manifest: ArtifactBinding
    publication_package: ArtifactBinding
    source_final_candidate: ArtifactBinding
    source_final_media: ArtifactBinding
    source_human_final_approval: ArtifactBinding
    source_final_render_request: ArtifactBinding
    timeline: ArtifactBinding
    subtitle: ArtifactBinding
    audio: ArtifactBinding
    authorized_visual_differences: list[Literal["review_overlay_removal"]]
    implementation_version: Literal["publication-video-qa-implementation/1.0"] = QA_IMPLEMENTATION_VERSION
    implementation_identity: PublicationQAImplementationIdentityV1
    executed_at: datetime
    result: Literal["passed", "failed"]
    checks: list[PublicationQACheckV1]
    measurements: dict[str, Any]

    @field_validator("executed_at")
    @classmethod
    def timestamp_aware(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("PUBLICATION_QA_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
        return value

    @model_validator(mode="after")
    def result_matches_checks(self):
        identifiers = [check.check_id for check in self.checks]
        if (len(identifiers) != len(set(identifiers)) or set(identifiers) != set(REQUIRED_PUBLICATION_CHECKS)
            or any(not check.blocking for check in self.checks)):
            raise ValueError("PUBLICATION_QA_REQUIRED_CHECKS_INVALID")
        failed = any(check.blocking and check.status == "fail" for check in self.checks)
        if failed and self.result != "failed":
            raise ValueError("PUBLICATION_QA_BLOCKING_FAILURE_CANNOT_PASS")
        if self.result == "failed" and not failed:
            raise ValueError("PUBLICATION_QA_FAILURE_REQUIRES_BLOCKING_CHECK")
        if self.authorized_visual_differences != AUTHORIZED_DIFFERENCES:
            raise ValueError("PUBLICATION_QA_AUTHORIZED_DIFFERENCES_INVALID")
        if (self.attempt_number == 1) != (self.previous_qa is None):
            raise ValueError("PUBLICATION_QA_ATTEMPT_CHAIN_INVALID")
        return self


class HumanPublicationReviewEntryV1(_Contract):
    schema_version: Literal["human-publication-review-entry/1.0"] = "human-publication-review-entry/1.0"
    run_id: str
    case_id: str
    status: Literal["ready_for_human_publication_review"] = "ready_for_human_publication_review"
    publication_media_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    qa_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_path: str
    source_final_candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_final_media_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_human_final_approval_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class HumanPublicationReviewV1(_Contract):
    schema_version: Literal["human-publication-review/1.0"] = "human-publication-review/1.0"
    run_id: str
    case_id: str
    reviewer: str = Field(min_length=1)
    reviewed_at: datetime
    decision: Literal["approved_for_release", "changes_required"]
    rationale: str = Field(min_length=1)
    publication_media_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    publication_qa_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_final_candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_final_media_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_human_final_approval_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    release_target: str
    dependency_hashes: dict[str, str]

    @field_validator("reviewed_at")
    @classmethod
    def timestamp_aware(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("HUMAN_PUBLICATION_REVIEW_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
        return value

    @field_validator("reviewer", "rationale")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("HUMAN_PUBLICATION_REVIEW_TEXT_REQUIRED")
        return value


def publication_qa_registry(run_dir: Path, *, attempt: int | None = None):
    return publication_render_registry(Path(run_dir), qa_attempt=attempt)


def _binding(registry, name):
    return ArtifactBinding(path=name, sha256=registry.manifest.artifacts[name].content_hash)


def _latest_number(registry):
    names = [name for name in registry.manifest.artifacts
             if name == "publication_video_qa.json" or name.startswith("publication_video_qa_attempt_")]
    numbers = [int(name.removeprefix("publication_video_qa_attempt_").removesuffix(".json"))
               for name in names if name.startswith("publication_video_qa_attempt_")
               and name.removeprefix("publication_video_qa_attempt_").removesuffix(".json").isdigit()]
    if numbers and sorted(numbers) != list(range(2, max(numbers) + 1)):
        raise ArtifactConflictError("PUBLICATION_VIDEO_QA_ATTEMPT_CHAIN_INVALID")
    return max(numbers) if numbers else 1


def _qa_name(attempt):
    return "publication_video_qa.json" if attempt == 1 else f"publication_video_qa_attempt_{attempt}.json"


def _current_inputs(root: Path):
    request = validate_publication_render_request(root)
    package = validate_publication_renderer_package(root)
    registry = publication_qa_registry(root)
    for name in (MEDIA_ARTIFACT, request.output_path, RENDER_MANIFEST, REQUEST_ARTIFACT,
                 PACKAGE_ARTIFACT, PACKAGE_DIRECTORY, "final_video_candidate.json", "final.mp4",
                 "human_final_video_review.json", "final_render_request.json", package.timeline.path,
                 package.subtitle.path, package.audio.path):
        registry.validate(name)
    media = PublicationVideoV1.model_validate_json(_path(registry, MEDIA_ARTIFACT).read_text(encoding="utf-8"))
    if (media.path != request.output_path
        or media.media_sha256 != registry.manifest.artifacts[request.output_path].content_hash
        or media.file_size != _path(registry, request.output_path).stat().st_size
        or media.expected_technical_properties != {
            "container": "mp4", "width": request.render_configuration.width,
            "height": request.render_configuration.height, "fps": request.render_configuration.fps,
            "duration_ms": request.render_configuration.duration_ms,
            "frame_count": request.render_configuration.frame_count,
            "video_codec": request.render_configuration.video_codec,
            "audio_codec": request.render_configuration.audio_codec,
        }
        or media.source_publication_render_request_sha256 != registry.manifest.artifacts[REQUEST_ARTIFACT].content_hash
        or media.source_publication_package_sha256 != registry.manifest.artifacts[PACKAGE_ARTIFACT].content_hash
        or media.source_final_candidate_sha256 != registry.manifest.artifacts["final_video_candidate.json"].content_hash
        or media.source_final_media_sha256 != registry.manifest.artifacts["final.mp4"].content_hash
        or media.source_human_final_approval_sha256 != registry.manifest.artifacts["human_final_video_review.json"].content_hash):
        raise ValueError("PUBLICATION_MEDIA_BINDING_MISMATCH")
    return registry, request, package, media


def _timeline_samples(timeline: TimelineDocument, fps: int):
    duration = int(timeline.audio.get("duration_ms", 0))
    frame_ms = max(1, round(1000 / fps))
    rows = [{"sample_id": "opening", "time_ms": min(frame_ms, max(0, duration // 20))}]
    for index, scene in enumerate(timeline.scenes):
        rows.append({"sample_id": f"scene-interior-{scene.scene_id}", "time_ms": (scene.start_ms + scene.end_ms) // 2})
        if index + 1 < len(timeline.scenes):
            boundary = scene.end_ms
            rows.extend(({"sample_id": f"scene-boundary-{index+1}-left", "time_ms": max(0, boundary-frame_ms)},
                         {"sample_id": f"scene-boundary-{index+1}-right", "time_ms": min(duration-1, boundary+frame_ms)}))
    composition = timeline.composition
    for cue in composition.subtitle_cues if composition else []:
        rows.append({"sample_id": f"subtitle-{cue.cue_id}", "time_ms": (cue.start_ms+cue.end_ms)//2,
                     "subtitle_region": composition.subtitle_layout.reserved_zone.model_dump(mode="json")})
    rows.append({"sample_id": "ending", "time_ms": max(0, duration-frame_ms)})
    return rows


def _media_tools(node_path=None, ffmpeg_path=None, ffprobe_path=None):
    from fanglei.render_preflight import resolve_renderer_environment

    env = resolve_renderer_environment()
    node = node_path or env.node or os.environ.get("FENGLEI_RENDER_NODE")
    if not node:
        raise ValueError("PUBLICATION_QA_NODE_UNAVAILABLE")
    ffprobe = ffprobe_path or os.environ.get("HYPERFRAMES_FFPROBE_PATH") or os.environ.get("NIKOLA_FFPROBE_PATH") or env.ffprobe
    ffmpeg = ffmpeg_path or os.environ.get("HYPERFRAMES_FFMPEG_PATH") or os.environ.get("NIKOLA_FFMPEG_PATH") or env.ffmpeg
    root = Path(__file__).resolve().parents[2] / "tools/ffmpeg/node_modules"
    for package_name, current in (("ffprobe-static", ffprobe), ("@ffmpeg-installer/ffmpeg", ffmpeg)):
        if current:
            continue
        package = root / package_name
        if package.exists():
            result = subprocess.run([node, "-e", "console.log(require(process.argv[1]).path)", str(package)],
                                    check=False, capture_output=True, text=True, timeout=20)
            if result.returncode == 0:
                if package_name == "ffprobe-static": ffprobe = result.stdout.strip()
                else: ffmpeg = result.stdout.strip()
    for path in (ffmpeg, ffprobe):
        if not path or not Path(path).is_absolute() or not Path(path).is_file():
            raise ValueError("PUBLICATION_QA_MEDIA_TOOL_UNAVAILABLE")
    puppeteer = os.environ.get("FENGLEI_PUPPETEER_MODULE")
    browser = os.environ.get("FENGLEI_RENDER_BROWSER")
    if not puppeteer or not browser or not Path(puppeteer).exists() or not Path(browser).exists():
        raise ValueError("PUBLICATION_QA_BROWSER_TOOLCHAIN_UNAVAILABLE")
    return node, str(Path(puppeteer).resolve()), str(Path(browser).resolve()), Path(ffmpeg).resolve(), Path(ffprobe).resolve()


def _decode_track(ffmpeg: Path, media_path: Path, stream: str):
    result = subprocess.run([str(ffmpeg), "-v", "error", "-i", str(media_path), "-map", stream,
                             "-f", "null", "-"], check=False, capture_output=True,
                             text=True, encoding="utf-8", timeout=600)
    return {"passed": result.returncode == 0, "returncode": result.returncode,
            "stderr_tail": result.stderr[-500:]}


def _decode_pcm(ffmpeg: Path, media_path: Path, stream: str | None):
    command = [str(ffmpeg), "-v", "error", "-i", str(media_path)]
    if stream:
        command.extend(["-map", stream])
    command.extend(["-ac", "1", "-ar", "16000", "-f", "s16le", "-"])
    result = subprocess.run(command, check=False, capture_output=True, timeout=600)
    if result.returncode:
        raise ValueError("PUBLICATION_AUDIO_DECODE_FAILED: " + result.stderr[-500:].decode("utf-8", "replace"))
    samples = array("h")
    samples.frombytes(result.stdout)
    if sys.byteorder != "little":
        samples.byteswap()
    return samples


def _pcm_similarity(left: array, right: array, *, max_offset: int = 160):
    if len(left) < 160 or len(right) < 160:
        return None
    best = -1.0
    for offset in range(-max_offset, max_offset + 1, 40):
        a_start, b_start = max(0, offset), max(0, -offset)
        count = min(len(left) - a_start, len(right) - b_start)
        if count <= 0:
            continue
        # Sample deterministically to bound CPU on long-form narration.
        stride = max(1, count // 50000)
        av = [left[index] for index in range(a_start, a_start + count, stride)]
        bv = [right[index] for index in range(b_start, b_start + count, stride)]
        if not av or len(av) != len(bv):
            continue
        am, bm = sum(av) / len(av), sum(bv) / len(bv)
        numerator = sum((x-am)*(y-bm) for x, y in zip(av, bv))
        denominator = math.sqrt(sum((x-am)**2 for x in av) * sum((y-bm)**2 for y in bv))
        if denominator:
            best = max(best, numerator / denominator)
    return best if best >= -1 else None


def _measure_media(root, registry, request, package, media, *, node_path=None, ffmpeg_path=None, ffprobe_path=None):
    expected = request.render_configuration
    output_path = _path(registry, media.path)
    final_path = _path(registry, "final.mp4")
    timeline = TimelineDocument.model_validate(read_json(_path(registry, package.timeline.path)))
    tools = _media_tools(node_path, ffmpeg_path, ffprobe_path)
    node, puppeteer, browser, ffmpeg, ffprobe = tools
    publication_probe = _ffprobe_metadata(output_path, ffprobe)
    final_probe = _ffprobe_metadata(final_path, ffprobe)
    decode_video = _decode_track(ffmpeg, output_path, "0:v:0")
    decode_audio = _decode_track(ffmpeg, output_path, "0:a:0")
    decoded_audio = _decode_pcm(ffmpeg, output_path, "0:a:0")
    source_audio = _decode_pcm(ffmpeg, _path(registry, package.audio.path), None)
    audio_similarity = _pcm_similarity(source_audio, decoded_audio)
    final_request = read_json(_path(registry, "final_render_request.json"))
    source_html = _path(registry, f"{package.source_renderer_package.path}/{expected.entry}")
    publication_html = _path(registry, f"{PACKAGE_DIRECTORY}/{expected.entry}")
    temp_root = Path(tempfile.mkdtemp(prefix="fenglei-publication-qa-"))
    try:
        samples_path = temp_root / "samples.json"
        samples_path.write_text(json.dumps(_timeline_samples(timeline, expected.fps), ensure_ascii=False), encoding="utf-8")
        script = Path(__file__).with_name("publication_video_probe.mjs")
        proc = subprocess.run([node, str(script), puppeteer, browser, str(final_path), str(output_path),
                               str(source_html), str(samples_path), str(expected.width), str(expected.height)],
                              capture_output=True, text=True, encoding="utf-8", check=False, timeout=600)
        if proc.returncode:
            raise ValueError("PUBLICATION_BROWSER_PROBE_FAILED: " + proc.stderr[-800:])
        browser_probe = json.loads(proc.stdout)
    finally:
        import shutil
        shutil.rmtree(temp_root, ignore_errors=True)

    subtitle = read_json(_path(registry, package.subtitle.path))
    timeline_cues = [cue.model_dump(mode="json") for cue in timeline.composition.subtitle_cues]
    subtitle_cues = subtitle.get("cues", [])
    package_timeline = read_json(_path(registry, f"{PACKAGE_DIRECTORY}/data/timeline.json"))
    package_cues = package_timeline.get("composition", {}).get("subtitle_cues", [])
    texts = [cue.get("text") for cue in timeline_cues]
    text_match = texts == [cue.get("text") for cue in subtitle_cues] == [cue.get("text") for cue in package_cues]
    times_match = [(cue.get("start_ms"), cue.get("end_ms")) for cue in timeline_cues] == [(cue.get("start_ms"), cue.get("end_ms")) for cue in subtitle_cues] == [(cue.get("start_ms"), cue.get("end_ms")) for cue in package_cues]
    entry_source = source_html.read_text(encoding="utf-8")
    entry_pub = publication_html.read_text(encoding="utf-8")
    from fanglei.preview_composition import REVIEW_OVERLAYS
    source_overlay = all(entry_source.count(row) == 1 for row in REVIEW_OVERLAYS)
    publication_overlay_absent = all(row not in entry_pub for row in REVIEW_OVERLAYS)
    source_footer_nodes = re.findall(r"<[^>]*data-source-ids=(?:\"[^\"]*\"|'[^']*')[^>]*>", entry_source)
    publication_footer_nodes = re.findall(r"<[^>]*data-source-ids=(?:\"[^\"]*\"|'[^']*')[^>]*>", entry_pub)
    regions = browser_probe.get("regions", [])
    samples = browser_probe.get("samples", [])
    interior = [row for row in samples if row.get("sample_id", "").startswith("scene-interior-")]
    cue_samples = [row for row in samples if row.get("sample_id", "").startswith("subtitle-")]
    sample_valid = lambda row: not row.get("error") and all(
        isinstance(row.get(key), (int, float)) and math.isfinite(row[key]) for key in (
            "outside_mask_similarity", "overlay_region_similarity", "publication_average_luma"))
    expected_cues = bool(timeline_cues) and text_match
    layout = timeline.composition.subtitle_layout
    zone = layout.reserved_zone
    geometry_ok = (0 <= zone.x and 0 <= zone.y and zone.width > 0 and zone.height > 0
                   and zone.x + zone.width <= expected.width and zone.y + zone.height <= expected.height
                   and all(len(cue.lines) <= layout.maximum_lines for cue in timeline.composition.subtitle_cues))
    subtitle_pixels_match = bool(cue_samples) and all(
        sample_valid(row) and row.get("subtitle_region_similarity", -1) >= MINIMUM_OUTSIDE_MASK_SIMILARITY
        for row in cue_samples
    )
    no_overflow = all(len(cue.lines) <= layout.maximum_lines for cue in timeline.composition.subtitle_cues)
    browser_full = browser_probe.get("full_decode", {})
    publication_full = browser_full.get("publication", {})
    final_full = browser_full.get("final", {})
    publication_video = publication_probe.get("video") or {}
    publication_audio = publication_probe.get("audio") or {}
    final_video = final_probe.get("video") or {}
    close = lambda left, right, tolerance: isinstance(left, (int, float)) and abs(left-right) <= tolerance
    tolerance = max(0.2, 2 / expected.fps)
    checks = {
        "media_exists": output_path.is_file() and output_path.stat().st_size > 0,
        "container_decode": publication_probe.get("container") == "mp4"
                            and isinstance(publication_probe.get("container_duration_seconds"), (int, float)),
        "full_video_decode": decode_video["passed"] and publication_full.get("ended") is True and publication_full.get("decoded_frames", 0) > 0,
        "full_audio_decode": decode_audio["passed"] and publication_audio is not None,
        "video_stream": publication_video.get("handler") == "vide",
        "audio_stream": publication_audio.get("handler") == "soun" and browser_probe.get("publication", {}).get("audio_track_count", 0) > 0,
        "video_dimensions": publication_video.get("width") == expected.width and publication_video.get("height") == expected.height,
        "frame_rate": close(publication_video.get("fps"), expected.fps, 0.5),
        "frame_count": isinstance(publication_video.get("frame_count"), int) and abs(publication_video["frame_count"]-expected.frame_count) <= max(1, round(expected.frame_count*0.02)),
        "video_codec": str(publication_video.get("codec", "")).startswith(expected.video_codec),
        "audio_codec": publication_audio.get("codec") == expected.audio_codec,
        "duration": close(publication_probe.get("container_duration_seconds"), expected.duration_ms/1000, tolerance)
                    and close(publication_audio.get("duration_seconds"), expected.duration_ms/1000, tolerance),
        "scene_coverage": len(interior) == len(timeline.scenes) and all(sample_valid(row) and row["outside_mask_similarity"] >= MINIMUM_OUTSIDE_MASK_SIMILARITY for row in interior),
        "subtitle_coverage": expected_cues and len(cue_samples) == len(timeline_cues)
                             and all(sample_valid(row) and isinstance(row.get("subtitle_region_similarity"), (int, float))
                                     and row["subtitle_region_similarity"] >= MINIMUM_OUTSIDE_MASK_SIMILARITY for row in cue_samples),
        "subtitle_text_unchanged": text_match,
        "subtitle_timing": times_match and bool(timeline_cues),
        "audio_equivalence": (package.audio.sha256 == registry.manifest.artifacts[package.audio.path].content_hash
                              and final_request.get("inputs", {}).get("audio", {}).get("sha256") == package.audio.sha256
                              and close(publication_audio.get("duration_seconds"), timeline.audio.get("duration_ms", 0)/1000, tolerance)
                              and audio_similarity is not None and audio_similarity >= 0.90),
        "source_footer": bool(source_footer_nodes) and source_footer_nodes == publication_footer_nodes,
        "opening": any(row.get("sample_id") == "opening" and sample_valid(row) and row["publication_average_luma"] > 0.01 for row in samples),
        "ending": any(row.get("sample_id") == "ending" and sample_valid(row) and row["publication_average_luma"] > 0.01 for row in samples),
        "subtitle_geometry": geometry_ok,
        "subtitle_clipping": geometry_ok and subtitle_pixels_match,
        "subtitle_overflow": no_overflow and geometry_ok and text_match,
        "black_frame_regression": bool(samples) and all(
            sample_valid(row) and (row["final_average_luma"] <= 0.01 or row["publication_average_luma"] > 0.01)
            for row in samples),
        "overlay_absence": source_overlay and publication_overlay_absent and len(regions) == 2
                           and all(isinstance(row, dict) and row.get("width", 0) > 0 and row.get("height", 0) > 0 for row in regions)
                           and bool(samples) and all(sample_valid(row) and row["overlay_region_similarity"] <= MAXIMUM_OVERLAY_REGION_SIMILARITY for row in samples),
        "final_publication_comparison": final_video.get("width") == publication_video.get("width")
                           and final_video.get("height") == publication_video.get("height")
                           and close(final_probe.get("container_duration_seconds"), publication_probe.get("container_duration_seconds"), tolerance)
                           and bool(samples) and all(sample_valid(row) and row["outside_mask_similarity"] >= MINIMUM_OUTSIDE_MASK_SIMILARITY for row in samples),
    }
    return {
        "metadata": publication_probe, "final_metadata": final_probe,
        "full_decode": {"ffmpeg_video": decode_video, "ffmpeg_audio": decode_audio,
                        "browser_final": final_full, "browser_publication": publication_full},
        "comparison": {"checks": checks, "regions": regions, "samples": samples,
                       "audio_similarity": audio_similarity,
                       "minimum_outside_mask_similarity": MINIMUM_OUTSIDE_MASK_SIMILARITY,
                       "maximum_overlay_region_similarity": MAXIMUM_OVERLAY_REGION_SIMILARITY,
                       "subtitle_text_exact_match": text_match, "subtitle_timing_exact_match": times_match,
                       "authorized_differences": AUTHORIZED_DIFFERENCES},
        "tools": {"ffmpeg_sha256": sha256_bytes(ffmpeg.read_bytes()), "ffprobe_sha256": sha256_bytes(ffprobe.read_bytes())},
    }


def _check(identifier, passed, summary, evidence):
    return PublicationQACheckV1(check_id=identifier, status="pass" if passed else "fail",
                                blocking=True, summary=summary, evidence=evidence)


def _qa_bindings(registry, package):
    request = read_json(_path(registry, REQUEST_ARTIFACT))
    return {
        "publication_media": _binding(registry, MEDIA_ARTIFACT),
        "publication_media_file": _binding(registry, request["output_path"]),
        "publication_render_request": _binding(registry, REQUEST_ARTIFACT),
        "publication_render_manifest": _binding(registry, RENDER_MANIFEST),
        "publication_package": _binding(registry, PACKAGE_ARTIFACT),
        "source_final_candidate": _binding(registry, "final_video_candidate.json"),
        "source_final_media": _binding(registry, "final.mp4"),
        "source_human_final_approval": _binding(registry, "human_final_video_review.json"),
        "source_final_render_request": _binding(registry, "final_render_request.json"),
        "timeline": _binding(registry, package.timeline.path),
        "subtitle": _binding(registry, package.subtitle.path),
        "audio": _binding(registry, package.audio.path),
    }


def _attempt_matches(report, registry, package, number):
    if report.attempt_number != number:
        return False
    for field, binding in _qa_bindings(registry, package).items():
        if getattr(report, field) != binding:
            return False
    if number == 1:
        return report.previous_qa is None
    previous_name = _qa_name(number - 1)
    return (report.previous_qa is not None and report.previous_qa.path == previous_name
            and report.previous_qa.sha256 == registry.manifest.artifacts[previous_name].content_hash)


def _load_report(path: Path):
    return PublicationVideoQAReportV1.model_validate_json(path.read_text(encoding="utf-8"))


def run_publication_video_qa(
    run_dir: Path, *, reevaluate: bool = False, expected_previous_qa_sha256: str | None = None,
    node_path: str | Path | None = None, ffmpeg_path: str | Path | None = None,
    ffprobe_path: str | Path | None = None,
) -> Path:
    root = Path(run_dir).resolve()
    registry, request, package, media = _current_inputs(root)
    latest = _latest_number(registry)
    prior_name = _qa_name(latest)
    prior_state = registry.manifest.artifacts[prior_name]
    prior_path = _path(registry, prior_name)
    attempt, previous = 1, None
    if prior_state.status != "missing" or prior_path.exists():
        if not reevaluate:
            raise ArtifactConflictError("PUBLICATION_VIDEO_QA_ALREADY_EXISTS")
        registry.validate(prior_name)
        prior = _load_report(prior_path)
        if expected_previous_qa_sha256 != prior_state.content_hash:
            raise ArtifactConflictError("PUBLICATION_VIDEO_QA_EXPECTED_PREVIOUS_HASH_MISMATCH")
        if not _attempt_matches(prior, registry, package, latest):
            raise ArtifactConflictError("PUBLICATION_VIDEO_QA_PREVIOUS_BINDING_MISMATCH")
        if prior.result != "failed" and prior.implementation_identity.sha256 == _implementation_sha256():
            raise ArtifactConflictError("PUBLICATION_VIDEO_QA_ALREADY_EXISTS")
        if registry.manifest.artifacts["human_publication_review.json"].status != "missing":
            raise ArtifactConflictError("HUMAN_PUBLICATION_REVIEW_ALREADY_EXISTS")
        attempt = latest + 1
        previous = ArtifactBinding(path=prior_name, sha256=prior_state.content_hash)
        registry = publication_qa_registry(root, attempt=attempt)
        prior_path = _path(registry, _qa_name(attempt))
        if prior_path.exists():
            raise ArtifactConflictError("PUBLICATION_VIDEO_QA_ALREADY_EXISTS")
    elif reevaluate:
        raise ArtifactConflictError("PUBLICATION_VIDEO_QA_PREVIOUS_ATTEMPT_MISSING")

    implementation_identity = publication_qa_implementation_identity()
    try:
        measurements = _measure_media(root, registry, request, package, media,
                                       node_path=node_path, ffmpeg_path=ffmpeg_path, ffprobe_path=ffprobe_path)
        check_results = measurements.get("comparison", {}).get("checks", {})
    except Exception as error:
        measurements = {"error": str(error), "comparison": {"checks": {}}}
        check_results = {}
    checks = [_check(name, check_results.get(name) is True,
                     f"Publication QA {name.replace('_', ' ')} check.",
                     {"passed": check_results.get(name) is True,
                      "measurements": measurements.get("comparison", {}).get(name),
                      "execution_error": measurements.get("error")}) for name in REQUIRED_PUBLICATION_CHECKS]
    report = PublicationVideoQAReportV1(
        run_id=request.run_id, case_id=request.case_id, attempt_number=attempt,
        previous_qa=previous, **_qa_bindings(registry, package),
        authorized_visual_differences=AUTHORIZED_DIFFERENCES,
        implementation_identity=implementation_identity, executed_at=datetime.now(timezone.utc),
        result="failed" if any(check.status == "fail" for check in checks) else "passed",
        checks=checks, measurements=measurements,
    )
    current_registry, current_request, current_package, current_media = _current_inputs(root)
    if (current_request != request or current_package != package or current_media != media
        or implementation_identity.sha256 != _implementation_sha256()):
        raise ArtifactConflictError("PUBLICATION_QA_INPUT_CHANGED_DURING_RUN")
    if previous:
        current_registry.validate(previous.path)
        if current_registry.manifest.artifacts[previous.path].content_hash != previous.sha256:
            raise ArtifactConflictError("PUBLICATION_QA_PREVIOUS_CHANGED_DURING_RUN")
    current_registry = publication_qa_registry(root, attempt=attempt)
    target = _path(current_registry, _qa_name(attempt))
    if target.exists():
        raise ArtifactConflictError("PUBLICATION_VIDEO_QA_ALREADY_EXISTS")
    path = current_registry.write_json(_qa_name(attempt), report.model_dump(mode="json"), "publication_video_qa")
    current_registry.save_manifest()
    return path


def _current_report(registry, package, name, number):
    registry.validate(name)
    report = _load_report(_path(registry, name))
    if not _attempt_matches(report, registry, package, number):
        raise ValueError("PUBLICATION_QA_APPROVED_INPUT_BINDING_MISMATCH")
    return report


def derive_publication_video_qa_status(run_dir: Path) -> Literal["pending", "passed", "failed", "stale"]:
    try:
        registry, _request, package, _media = _current_inputs(Path(run_dir).resolve())
        number = _latest_number(registry)
        name = _qa_name(number)
        if registry.manifest.artifacts[name].status == "missing" and not _path(registry, name).exists():
            return "pending"
        report = _current_report(registry, package, name, number)
        return report.result
    except (ValueError, OSError, ArtifactConflictError, json.JSONDecodeError):
        return "stale"


def validate_human_publication_review_entry(run_dir: Path) -> HumanPublicationReviewEntryV1:
    root = Path(run_dir).resolve()
    registry, request, package, media = _current_inputs(root)
    from fanglei.final_video_qa import validate_existing_human_final_video_approval
    validate_existing_human_final_video_approval(root)
    number = _latest_number(registry)
    name = _qa_name(number)
    qa = _current_report(registry, package, name, number)
    if qa.result != "passed":
        raise ValueError("PUBLICATION_VIDEO_QA_NOT_PASSED")
    if qa.implementation_identity.sha256 != _implementation_sha256():
        raise ValueError("PUBLICATION_VIDEO_QA_IMPLEMENTATION_NOT_CURRENT")
    qa_sha = registry.manifest.artifacts[name].content_hash
    return HumanPublicationReviewEntryV1(
        run_id=request.run_id, case_id=request.case_id,
        publication_media_sha256=media.media_sha256, qa_sha256=qa_sha,
        request_sha256=registry.manifest.artifacts[REQUEST_ARTIFACT].content_hash,
        output_path=request.output_path,
        source_final_candidate_sha256=registry.manifest.artifacts["final_video_candidate.json"].content_hash,
        source_final_media_sha256=registry.manifest.artifacts["final.mp4"].content_hash,
        source_human_final_approval_sha256=registry.manifest.artifacts["human_final_video_review.json"].content_hash,
    )


def record_human_publication_review(
    run_dir: Path, *, reviewer: str, decision: Literal["approved_for_release", "changes_required"],
    rationale: str, expected_media_sha256: str, expected_qa_sha256: str,
) -> Path:
    entry = validate_human_publication_review_entry(run_dir)
    if (entry.publication_media_sha256 != expected_media_sha256 or entry.qa_sha256 != expected_qa_sha256):
        raise ValueError("HUMAN_PUBLICATION_REVIEW_EXPECTED_HASH_MISMATCH")
    registry = publication_qa_registry(Path(run_dir).resolve())
    target = _path(registry, "human_publication_review.json")
    if target.exists() or registry.manifest.artifacts["human_publication_review.json"].status != "missing":
        raise ArtifactConflictError("HUMAN_PUBLICATION_REVIEW_ALREADY_EXISTS")
    latest = _qa_name(_latest_number(registry))
    dependencies = {name: registry.manifest.artifacts[name].content_hash
                    for name in registry.graph["human_publication_review.json"][1]}
    review = HumanPublicationReviewV1(
        run_id=entry.run_id, case_id=entry.case_id, reviewer=reviewer,
        reviewed_at=datetime.now(timezone.utc), decision=decision, rationale=rationale,
        publication_media_sha256=entry.publication_media_sha256, publication_qa_sha256=entry.qa_sha256,
        source_final_candidate_sha256=entry.source_final_candidate_sha256,
        source_final_media_sha256=entry.source_final_media_sha256,
        source_human_final_approval_sha256=entry.source_human_final_approval_sha256,
        release_target=entry.output_path, dependency_hashes=dependencies,
    )
    path = registry.write_json("human_publication_review.json", review.model_dump(mode="json"), "human_publication_review")
    registry.save_manifest()
    return path
