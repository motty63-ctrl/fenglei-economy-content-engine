"""Deterministic translation from validated storyboard/timeline to a Nikola project."""
from __future__ import annotations

import json
from html import escape

from fanglei.artifacts import sha256_bytes, sha256_text
from fanglei.v05_models import TimelineDocument


SUPPORTED_ANIMATION_DIRECTIVES = {
    "appear", "check", "connect", "connect_complete_flow", "count_in", "deemphasize",
    "digit_highlight", "draw", "fade_out", "final_hold", "focus", "highlight", "hold",
    "mask_digits", "merge", "move_focus_next", "pulse", "replace", "reveal",
    "reveal_sequence", "round", "scale_down",
}


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_nikola_project(storyboard: dict, timeline: TimelineDocument,
                         narration_audio: bytes) -> tuple[dict[str, str | bytes], dict]:
    gate = storyboard.get("quality_gate") or {}
    if gate.get("passed") is not True:
        raise ValueError("NIKOLA_STORYBOARD_INVALID")
    if not timeline.validation.passed:
        raise ValueError("NIKOLA_TIMELINE_INVALID")
    if sha256_bytes(narration_audio) != timeline.audio.get("sha256"):
        raise ValueError("NIKOLA_AUDIO_HASH_MISMATCH")
    time_by_scene = {row.scene_id: row for row in timeline.scenes}
    project_scenes: list[dict] = []
    factual_count = 0
    for scene in storyboard.get("scenes", []):
        timing = time_by_scene.get(scene["scene_id"])
        if timing is None:
            raise ValueError("NIKOLA_SCENE_TIMING_MISSING")
        objects = scene.get("objects", [])
        for obj in objects:
            if obj.get("factual"):
                factual_count += 1
                if not obj.get("sentence_ids") or not obj.get("claim_ids"):
                    raise ValueError("NIKOLA_FACT_PROVENANCE_MISSING")
        directives = scene["renderer_directives"]
        steps = directives.get("micro_animation_sequence", [])
        requested_actions = set(directives.get("animation_primitives", []))
        requested_actions.update(action for step in steps for action in step.get("actions", []))
        unsupported = requested_actions - SUPPORTED_ANIMATION_DIRECTIVES
        if unsupported:
            raise ValueError("ADAPTER_UNSUPPORTED_DIRECTIVE:" + ",".join(sorted(unsupported)))
        project_scenes.append({
            "scene_id": scene["scene_id"],
            "start_ms": timing.start_ms,
            "end_ms": timing.end_ms,
            "object_ids": [obj["object_id"] for obj in objects],
            "objects": objects,
            "persistent_objects": scene.get("persistent_objects", []),
            "inherited_objects": scene.get("inherited_objects", []),
            "introduced_objects": scene.get("introduced_objects", []),
            "removed_objects": scene.get("removed_objects", []),
            "transition_in": scene.get("transition_in"),
            "transition_out": scene.get("transition_out"),
            "animation_steps": [step["step_id"] for step in steps],
            "renderer_directives": scene["renderer_directives"],
        })
    storyboard_hash = sha256_text(_canonical_json(storyboard))
    timeline_payload = timeline.model_dump(mode="json")
    timeline_hash = sha256_text(_canonical_json(timeline_payload))
    project_manifest = {
        "schema_version": "5.0",
        "run_id": timeline.run_id,
        "route": storyboard["renderer_selection"]["primary_route"],
        "audio": {"path": "assets/narration.wav", **timeline.audio},
        "scenes": project_scenes,
    }
    manifest = {
        "schema_version": "5.0",
        "run_id": timeline.run_id,
        "adapter": {"name": "nikola-program-animation", "version": "0.5.0"},
        "inputs": {
            "storyboard": {"path": "storyboard.json", "sha256": storyboard_hash},
            "timeline": {"path": "timeline.json", "sha256": timeline_hash},
        },
        "canvas": {"width": 1080, "height": 1920, "fps": 30, "orientation": "portrait"},
        "audio": project_manifest["audio"],
        "renderer": {
            "route": storyboard["renderer_selection"]["primary_route"],
            "engine": "hyperframes",
            "full_render_requested": False,
        },
        "scene_mappings": [{
            "scene_id": row["scene_id"], "start_ms": row["start_ms"], "end_ms": row["end_ms"],
            "object_ids": row["object_ids"], "animation_steps": row["animation_steps"],
        } for row in project_scenes],
        "provenance": {
            "factual_object_count": factual_count,
            "all_factual_objects_traceable": True,
        },
    }
    project_json = json.dumps(project_manifest, ensure_ascii=False, indent=2) + "\n"
    visible_text = " · ".join(
        escape(obj["content"]) for scene in project_scenes for obj in scene["objects"]
        if obj.get("content")
    )
    files: dict[str, str | bytes] = {
        "project-manifest.json": project_json,
        "hyperframes.json": json.dumps({
            "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
            "registry": "https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry",
            "paths": {
                "blocks": "compositions",
                "components": "compositions/components",
                "assets": "assets",
            },
            "media": {"autoProxy": True},
        }, ensure_ascii=False, indent=2) + "\n",
        "data/storyboard.json": json.dumps(storyboard, ensure_ascii=False, indent=2) + "\n",
        "data/timeline.json": json.dumps(timeline_payload, ensure_ascii=False, indent=2) + "\n",
        "assets/narration.wav": narration_audio,
        "package.json": json.dumps({
            "name": "fanglei-nikola-render-project", "private": True, "type": "module",
            "scripts": {
                "compat": "node scripts/compatibility-check.mjs",
                "check": "npx --yes hyperframes@0.8.20 check",
                "preview": "npx --yes hyperframes@0.8.20 preview",
            },
        }, ensure_ascii=False, indent=2) + "\n",
        "index.html": (
            "<!doctype html><meta charset=\"utf-8\"><style>body{font-family:'Microsoft YaHei',sans-serif}"
            "#root{width:1080px;height:1920px;overflow:hidden}</style>"
            f"<main id=\"root\" data-composition-id=\"main\" data-start=\"0\" "
            f"data-duration=\"{timeline.audio['duration_ms'] / 1000:g}\" "
            f"data-width=\"1080\" data-height=\"1920\">{visible_text}</main>\n"
        ),
        "scripts/compatibility-check.mjs": (
            "import fs from 'node:fs';\n"
            "for (const p of ['project-manifest.json','hyperframes.json','data/storyboard.json','data/timeline.json','assets/narration.wav']) "
            "if (!fs.existsSync(p)) throw new Error(`missing ${p}`);\n"
            "JSON.parse(fs.readFileSync('project-manifest.json','utf8'));\n"
        ),
    }
    return files, manifest
