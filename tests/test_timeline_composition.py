from __future__ import annotations

import hashlib
import json

import pytest

from fanglei.human_storyboard_recovery import canonical_json_sha256
from fanglei.human_visual_asset_recovery import HumanVisualAssetReviewV1
from fanglei.nikola_adapter import build_nikola_project
from fanglei.timeline import compile_approved_visual_timeline
from fanglei.v05_models import (
    AlignedSentence,
    AlignmentDocument,
    AudioMetadata,
    TimelineDocument,
)
from fanglei.v1b_models import SubtitleLayout, SubtitleRect


RUN_ID = "2026-09-29-001-synthetic-retail-run"
CASE_ID = "synthetic-retail-case"
AUDIO_BYTES = b"wav-fixture"
AUDIO_SHA = hashlib.sha256(AUDIO_BYTES).hexdigest()
HASHES = {
    "script.json": "1" * 64,
    "human_script_approval.json": "2" * 64,
    "audio/narration.wav": AUDIO_SHA,
    "audio/metadata.json": "3" * 64,
    "audio/review.json": "4" * 64,
    "alignment.json": "5" * 64,
    "subtitle_track.json": "6" * 64,
    "human_storyboard_candidate.json": "7" * 64,
    "human_storyboard_approval.json": "8" * 64,
    "angle_selection.json": "e" * 64,
    "facts.json": "f" * 64,
    "visual_asset_recovery_candidate_3.json": "9" * 64,
    "visual_assets_candidate_3": "b" * 64,
    "human_visual_asset_review_candidate_3.json": "c" * 64,
    "visual_beats.json": "d" * 64,
}


def _inputs():
    audio = AudioMetadata(
        sample_rate_hz=24000, duration_ms=2000, sha256=AUDIO_SHA,
        provider="synthetic", voice_id="offline-fixture",
    )
    alignment = AlignmentDocument(
        run_id=RUN_ID, audio_sha256=AUDIO_SHA, audio_duration_ms=2000,
        provider="fixture", method="sentence_boundaries", sentences=[
            AlignedSentence(sentence_id="sentence_001", start_ms=0, end_ms=1000,
                            confidence=1, timing_source="deterministic_fake"),
            AlignedSentence(sentence_id="sentence_002", start_ms=1000, end_ms=2000,
                            confidence=1, timing_source="deterministic_fake"),
        ], coverage_ratio=1, confidence=1,
    )
    storyboard = {
        "schema_version": "5.0", "run_id": RUN_ID, "script_id": "script_synthetic",
        "total_estimated_duration_seconds": 2,
        "renderer_selection": {"primary_route": "program_animation"},
        "quality_gate": {"passed": True},
        "scenes": [
            {"scene_id": "scene_open", "order": 1, "beat_ids": ["beat_001"],
             "sentence_ids": ["sentence_001"], "objects": [{
                 "object_id": "opening_label", "object_type": "text", "content": "Retail sales",
                 "factual": False, "claim_ids": [], "sentence_ids": ["sentence_001"],
                 "appearance_order": 1, "emphasis": "primary",
                 "placement": {"x": .1, "y": .2, "width": .8, "height": .2},
             }], "renderer_directives": {"animation_primitives": [], "micro_animation_sequence": []}},
            {"scene_id": "scene_change", "order": 2, "beat_ids": ["beat_002"],
             "sentence_ids": ["sentence_002"], "objects": [{
                 "object_id": "retail_value", "object_type": "number", "content": "+120 points",
                 "factual": True, "claim_ids": ["claim_retail"], "sentence_ids": ["sentence_002"],
                 "appearance_order": 1, "emphasis": "primary",
                 "placement": {"x": .1, "y": .3, "width": .8, "height": .2},
             }], "renderer_directives": {"animation_primitives": [], "micro_animation_sequence": []}},
        ],
    }
    beats = {"beats": [
        {"beat_id": "beat_001", "sentence_ids": ["sentence_001"]},
        {"beat_id": "beat_002", "sentence_ids": ["sentence_002"]},
    ]}
    svg_by_name = {
        "scene_001.svg": b'<svg xmlns="http://www.w3.org/2000/svg"><g data-object-id="opening_label"/></svg>',
        "scene_002.svg": b'<svg xmlns="http://www.w3.org/2000/svg"><g data-object-id="retail_value"/></svg>',
    }
    storyboard_sha = canonical_json_sha256(storyboard)
    manifest = {
        "schema_version": "visual-assets/1.1", "run_id": RUN_ID, "case_id": CASE_ID,
        "candidate_id": 3, "candidate_storyboard_sha256": storyboard_sha,
        "scene_count": 2, "review_status": "pending_human_visual_review",
        "scenes": [
            {"scene_id": "scene_open", "order": 1, "start_ms": 0, "end_ms": 1000,
             "asset_path": "scene_001.svg", "asset_sha256": hashlib.sha256(svg_by_name["scene_001.svg"]).hexdigest(),
             "sentence_ids": ["sentence_001"], "claim_ids": [],
             "objects": [{"object_id": "opening_label", "sentence_ids": ["sentence_001"], "claim_ids": []}]},
            {"scene_id": "scene_change", "order": 2, "start_ms": 1000, "end_ms": 2000,
             "asset_path": "scene_002.svg", "asset_sha256": hashlib.sha256(svg_by_name["scene_002.svg"]).hexdigest(),
             "sentence_ids": ["sentence_002"], "claim_ids": ["claim_retail"],
             "objects": [{"object_id": "retail_value", "sentence_ids": ["sentence_002"], "claim_ids": ["claim_retail"]}]},
        ],
    }
    subtitle_track = {
        "schema_version": "subtitle_track.v1", "run_id": RUN_ID, "script_id": "script_synthetic",
        "timing_source": "approved_sentence_alignment",
        "source": {"script_path": "script.json", "script_sha256": HASHES["script.json"],
                   "alignment_path": "alignment.json", "alignment_sha256": HASHES["alignment.json"],
                   "alignment_audio_sha256": AUDIO_SHA},
        "layout": {"canvas_width": 1080, "canvas_height": 1920,
                   "reserved_zone": {"x": 96, "y": 1480, "width": 888, "height": 260},
                   "maximum_lines": 2, "default_font_size_px": 52,
                   "minimum_font_size_px": 40, "line_height": 1.28,
                   "horizontal_padding_px": 36, "vertical_padding_px": 24},
        "cues": [
            {"cue_id": "cue_001", "sentence_id": "sentence_001", "text": "Retail sales report.",
             "start_ms": 0, "end_ms": 1000, "font_size_px": 52,
             "lines": [{"line_id": "line_01", "text": "Retail sales report.", "start_char": 0, "end_char": 20}],
             "emphasis_spans": []},
            {"cue_id": "cue_002", "sentence_id": "sentence_002", "text": "The measured change was 120 points.",
             "start_ms": 1000, "end_ms": 2000, "font_size_px": 52,
             "lines": [{"line_id": "line_01", "text": "The measured change was 120 points.", "start_char": 0, "end_char": 35}],
             "emphasis_spans": []},
        ],
        "validation": {"passed": True, "sentence_coverage": 1,
                        "text_exact_match": True, "timing_exact_match": True, "issues": []},
    }
    visual_review = HumanVisualAssetReviewV1.model_validate({
        "schema_version": "human-visual-asset-review/1.0", "candidate_id": 3,
        "decision": "approved_for_timeline", "run_id": RUN_ID, "case_id": CASE_ID,
        "reviewer": "reviewer", "reviewed_at": "2026-09-29T10:00:00+08:00",
        "reason_code": "APPROVED_FOR_TIMELINE", "rationale": "Approved for timeline composition.",
        "findings": ["Approved candidate 3."], "storyboard_sha256": storyboard_sha,
        "storyboard_artifact_sha256": HASHES["human_storyboard_candidate.json"],
        "storyboard_approval_sha256": HASHES["human_storyboard_approval.json"],
        "visual_bundle_sha256": HASHES["visual_assets_candidate_3"],
        "dependency_hashes": {
            "human_storyboard_candidate.json": HASHES["human_storyboard_candidate.json"],
            "human_storyboard_approval.json": HASHES["human_storyboard_approval.json"],
            "visual_assets_candidate_3": HASHES["visual_assets_candidate_3"],
            "angle_selection.json": HASHES["angle_selection.json"],
            "facts.json": HASHES["facts.json"],
            "script.json": HASHES["script.json"],
            "human_script_approval.json": HASHES["human_script_approval.json"],
            "audio/narration.wav": HASHES["audio/narration.wav"],
            "audio/review.json": HASHES["audio/review.json"],
            "alignment.json": HASHES["alignment.json"],
            "subtitle_track.json": HASHES["subtitle_track.json"],
        },
    })
    return audio, alignment, storyboard, beats, manifest, svg_by_name, subtitle_track, visual_review


def _compose(changes=None):
    (audio, alignment, storyboard, beats, visual_manifest, svg_by_name,
     subtitles, visual_review) = _inputs()
    kwargs = {
        "storyboard": storyboard,
        "visual_beats": beats,
        "audio": audio,
        "visual_bundle_manifest": visual_manifest,
        "visual_bundle_sha256": HASHES["visual_assets_candidate_3"],
        "visual_review": visual_review,
        "visual_review_sha256": HASHES["human_visual_asset_review_candidate_3.json"],
        "subtitle_track": subtitles,
        "subtitle_sha256": HASHES["subtitle_track.json"],
        "dependency_hashes": HASHES,
        "asset_bytes": svg_by_name,
        "storyboard_artifact_sha256": HASHES["human_storyboard_candidate.json"],
        "storyboard_approval_sha256": HASHES["human_storyboard_approval.json"],
        "script_sha256": HASHES["script.json"],
        "script_approval_sha256": HASHES["human_script_approval.json"],
        "audio_review_sha256": HASHES["audio/review.json"],
    }
    kwargs.update(changes or {})
    return compile_approved_visual_timeline(alignment, **kwargs)


def test_approved_visual_timeline_binds_assets_audio_subtitles_and_review() -> None:
    timeline = _compose()

    assert timeline.schema_version == "5.1"
    assert timeline.audio["duration_ms"] == 2000
    assert timeline.composition.visual_bundle_sha256 == HASHES["visual_assets_candidate_3"]
    assert timeline.composition.visual_review_sha256 == HASHES["human_visual_asset_review_candidate_3.json"]
    assert [scene.scene_id for scene in timeline.composition.scene_visuals] == ["scene_open", "scene_change"]
    assert [scene.asset_sha256 for scene in timeline.composition.scene_visuals] == [
        timeline.composition.scene_visuals[0].asset_sha256,
        timeline.composition.scene_visuals[1].asset_sha256,
    ]
    assert len(timeline.composition.subtitle_cues) == 2
    assert timeline.composition.subtitle_cues[1].text == "The measured change was 120 points."
    assert timeline.composition.scene_visuals[1].motion[0].effect == "fade_in"
    assert timeline.composition.timing_quality == "estimated"
    assert [row.asset_sha256 for row in timeline.composition.scene_visuals] == [
        hashlib.sha256(payload).hexdigest() for payload in _inputs()[5].values()
    ]


def test_approved_visual_timeline_fails_closed_on_changed_bundle_identity() -> None:
    _, _, _, _, _, _, _, visual_review = _inputs()
    visual_review = visual_review.model_copy(update={"visual_bundle_sha256": "f" * 64})
    with pytest.raises(ValueError, match="TIMELINE_VISUAL_APPROVAL_BINDING_INVALID"):
        _compose({"visual_review": visual_review})


def test_approved_visual_timeline_fails_closed_on_stale_review_dependency() -> None:
    _, _, _, _, _, _, _, visual_review = _inputs()
    stale_dependencies = dict(visual_review.dependency_hashes)
    stale_dependencies["visual_assets_candidate_3"] = "f" * 64
    visual_review = visual_review.model_copy(update={"dependency_hashes": stale_dependencies})
    with pytest.raises(ValueError, match="TIMELINE_VISUAL_APPROVAL_DEPENDENCIES_STALE"):
        _compose({"visual_review": visual_review})


def test_approved_visual_timeline_rejects_asset_hash_and_scene_timing_mismatch() -> None:
    _, _, _, _, manifest, assets, _, _ = _inputs()
    assets["scene_001.svg"] = b"<svg/>changed"
    with pytest.raises(ValueError, match="TIMELINE_VISUAL_ASSET_HASH_MISMATCH"):
        _compose({"asset_bytes": assets})

    manifest["scenes"][0]["end_ms"] = 999
    with pytest.raises(ValueError, match="TIMELINE_SCENE_RANGE_MISMATCH"):
        _compose({"visual_bundle_manifest": manifest})


def test_approved_visual_timeline_rejects_subtitle_that_does_not_match_alignment() -> None:
    _, _, _, _, _, _, subtitles, _ = _inputs()
    subtitles["cues"][0]["end_ms"] = 900
    with pytest.raises(ValueError, match="TIMELINE_SUBTITLE_ALIGNMENT_MISMATCH"):
        _compose({"subtitle_track": subtitles})


def test_review_preview_uses_exact_approved_svg_and_subtitle_copy_and_is_not_final() -> None:
    (audio, alignment, storyboard, beats, visual_manifest, svg_by_name,
     subtitles, _) = _inputs()
    timeline = _compose()
    files, manifest = build_nikola_project(
        storyboard, timeline, AUDIO_BYTES, visual_asset_files=svg_by_name,
    )

    preview = files["review-preview.html"]
    assert "PREVIEW" in preview and "NOT FINAL" in preview and "HUMAN REVIEW REQUIRED" in preview
    assert "The measured change was 120 points." in preview
    assert "2026" not in preview or "Retail sales" in preview
    assert files["assets/visual/scene_001.svg"] == svg_by_name["scene_001.svg"]
    assert manifest["renderer"]["preview_only"] is True
    assert manifest["renderer"]["full_render_requested"] is False
    assert manifest["renderer"]["preview_review_status"] == "pending_human_preview_review"
    assert "transform:scale(var(--preview-scale,1))" in preview
    assert 'data-final="false"' in preview
    assert not any(name.endswith("final.mp4") for name in files)


def test_review_preview_uses_compact_adaptive_subtitle_layout() -> None:
    _, _, storyboard, _, _, svg_by_name, _, _ = _inputs()
    timeline = _compose()
    layout = SubtitleLayout(
        reserved_zone=SubtitleRect(x=48, y=1724, width=984, height=120),
        default_font_size_px=48, minimum_font_size_px=40, line_height=1.08,
        horizontal_padding_px=14, vertical_padding_px=8,
    )
    composition = timeline.composition.model_copy(update={"subtitle_layout": layout})
    timeline = timeline.model_copy(update={"composition": composition})

    files, _ = build_nikola_project(
        storyboard, timeline, AUDIO_BYTES, visual_asset_files=svg_by_name,
    )
    preview = files["review-preview.html"]

    assert "height:auto;" in preview
    assert "width:max-content;max-width:984px" in preview
    assert "padding:8px 14px" in preview
    assert "line-height:1.08" in preview
    assert "rgba(247,242,232,.88)" in preview
    assert "minHeight" in preview
    assert 'data-final="false"' in preview


def test_review_preview_requires_the_exact_approved_asset_set() -> None:
    _, _, storyboard, _, _, svg_by_name, _, _ = _inputs()
    timeline = _compose()
    with pytest.raises(ValueError, match="REVIEW_PREVIEW_APPROVED_VISUAL_ASSETS_REQUIRED"):
        build_nikola_project(storyboard, timeline, AUDIO_BYTES)
    with pytest.raises(ValueError, match="REVIEW_PREVIEW_ASSET_SET_MISMATCH"):
        build_nikola_project(
            storyboard, timeline, AUDIO_BYTES,
            visual_asset_files={"scene_001.svg": svg_by_name["scene_001.svg"]},
        )
