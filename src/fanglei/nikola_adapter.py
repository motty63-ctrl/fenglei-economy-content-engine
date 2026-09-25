"""Deterministic translation from validated storyboard/timeline to a Nikola project."""
from __future__ import annotations

import json
import math
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


def _beat_one_dry_run_html(scene: dict, *, audio_path: str = "assets/narration.wav",
                           audio_track_index: int = 5) -> str:
    duration_seconds = (scene["end_ms"] - scene["start_ms"]) / 1000
    beat_id = (scene.get("beat_ids") or ["beat_001"])[0]
    object_markup: list[str] = []
    object_ids: list[str] = []
    for obj in scene["objects"]:
        object_id = escape(obj["object_id"], quote=True)
        object_ids.append(obj["object_id"])
        content = escape(obj.get("content") or "")
        placement = obj["placement"]
        delay = max(0, int(obj.get("appearance_order", 1)) - 1) * 0.45
        style = (
            f"left:{placement['x'] * 100:g}%;top:{placement['y'] * 100:g}%;"
            f"width:{placement['width'] * 100:g}%;height:{placement['height'] * 100:g}%;"
            f"animation-delay:{delay:g}s"
        )
        classes = "beat-object"
        if obj.get("emphasis") == "primary":
            classes += " primary"
        if obj.get("object_type") == "shape":
            object_markup.append(
                f'<svg id="{object_id}" class="{classes} shape" style="{style}" '
                'viewBox="0 0 100 100" role="img">'
                '<rect x="4" y="8" width="92" height="84" rx="12"/>'
                f'<text x="50" y="58" text-anchor="middle">{content}</text></svg>'
            )
        else:
            object_markup.append(
                f'<div id="{object_id}" class="{classes}" style="{style}">{content}</div>'
            )
    primitives = ",".join(scene["renderer_directives"].get("animation_primitives", []))
    required_ids = json.dumps(object_ids, ensure_ascii=False)
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=1080,height=1920">'
        '<style>'
        "@font-face{font-family:'Microsoft YaHei';src:local('Microsoft YaHei')}"
        "@font-face{font-family:'FangleiSans';src:local('Microsoft YaHei')}"
        '*{box-sizing:border-box}html,body{margin:0;width:1080px;height:1920px;overflow:hidden;'
        "background:#faf8f0;font-family:'Microsoft YaHei',sans-serif}"
        '#root{position:relative;width:1080px;height:1920px;overflow:hidden;background:#faf8f0}'
        '.beat-object{position:absolute;display:flex;align-items:center;justify-content:center;'
        'color:#20211d;font-size:58px;font-weight:700;opacity:0;transform:translateY(28px);'
        'animation:beatReveal .7s ease-out both}'
        '.shape rect{fill:#fff;stroke:#20211d;stroke-width:3}.shape text{font-family:'
        "'Microsoft YaHei',sans-serif;font-size:16px;font-weight:700;fill:#20211d}"
        '.primary{color:#d54b3d;font-size:110px;animation-name:beatReveal,beatPulse;'
        'animation-duration:.7s,.6s;animation-delay:.9s,1.6s;animation-iteration-count:1,2;'
        'animation-direction:normal,alternate}'
        '@keyframes beatReveal{to{opacity:1;transform:translateY(0)}}'
        '@keyframes beatPulse{to{transform:scale(1.12)}}'
        '</style></head><body>'
        f'<main id="root" data-composition-id="main" data-no-timeline data-beat-id="{escape(beat_id, quote=True)}" '
        f'data-animation-primitives="{escape(primitives, quote=True)}" data-start="0" '
        f'data-duration="{duration_seconds:g}" data-width="1080" data-height="1920">'
        + "".join(object_markup)
        + f'<audio id="{escape(beat_id, quote=True)}_narration" class="clip" data-start="0" '
        f'data-duration="{duration_seconds:g}" '
        f'data-track-index="{audio_track_index}" '
        f'src="{escape(audio_path, quote=True)}"></audio></main>'
        f'<script>const requiredIds={required_ids};const root=document.getElementById("root");'
        'root.dataset.animationStatus=requiredIds.every(id=>document.getElementById(id))?"ready":"invalid";'
        '</script></body></html>\n'
    )


def _frame_at_or_after(timestamp_ms: int, fps: int) -> int:
    return math.ceil(timestamp_ms * fps / 1000)


def _placement_key(obj: dict) -> str:
    return _canonical_json(obj["placement"])


def _object_visibility(scene: dict) -> list[dict]:
    objects = scene["objects"]
    max_order = max((int(obj.get("appearance_order", 1)) for obj in objects), default=1)
    scene_duration = scene["end_ms"] - scene["start_ms"]
    starts = {
        order: scene["start_ms"] + round((order - 1) * scene_duration / max_order)
        for order in range(1, max_order + 1)
    }
    groups: dict[str, list[dict]] = {}
    for obj in objects:
        groups.setdefault(_placement_key(obj), []).append(obj)
    windows: dict[str, dict] = {}
    for placement_key, grouped in groups.items():
        ordered = sorted(grouped, key=lambda item: int(item.get("appearance_order", 1)))
        for index, obj in enumerate(ordered):
            start_ms = starts[int(obj.get("appearance_order", 1))]
            end_ms = (
                starts[int(ordered[index + 1].get("appearance_order", 1))]
                if index + 1 < len(ordered) else scene["end_ms"]
            )
            windows[obj["object_id"]] = {
                "object_id": obj["object_id"],
                "placement_key": placement_key,
                "start_ms": start_ms,
                "end_ms": end_ms,
            }
    return [windows[obj["object_id"]] for obj in objects]


def _full_composition_html(project_scenes: list[dict], duration_ms: int, fps: int) -> str:
    duration_seconds = duration_ms / 1000
    scene_markup: list[str] = []
    scene_schedule: list[dict[str, int | str]] = []
    for scene in project_scenes:
        object_markup: list[str] = []
        visibility_by_id = {
            window["object_id"]: window for window in scene["object_visibility"]
        }
        primitives = ",".join(scene["renderer_directives"].get("animation_primitives", []))
        steps = ",".join(scene["animation_steps"])
        for obj in scene["objects"]:
            dom_id = escape(f'{scene["scene_id"]}__{obj["object_id"]}', quote=True)
            object_id = escape(obj["object_id"], quote=True)
            content = escape(obj.get("content") or "")
            placement = obj["placement"]
            visibility = visibility_by_id[obj["object_id"]]
            style = (
                f"left:{placement['x'] * 100:g}%;top:{placement['y'] * 100:g}%;"
                f"width:{placement['width'] * 100:g}%;height:{placement['height'] * 100:g}%"
            )
            classes = "scene-object"
            if obj.get("emphasis") == "primary":
                classes += " primary"
            if obj.get("object_type") == "shape":
                object_markup.append(
                    f'<svg id="{dom_id}" data-object-id="{object_id}" '
                    f'data-visible-start-ms="{visibility["start_ms"]}" '
                    f'data-visible-end-ms="{visibility["end_ms"]}" class="{classes} shape" '
                    f'style="{style}" viewBox="0 0 100 100" role="img">'
                    '<rect x="4" y="8" width="92" height="84" rx="12"/>'
                    f'<text x="50" y="58" text-anchor="middle">{content}</text></svg>'
                )
            else:
                object_markup.append(
                    f'<div id="{dom_id}" data-object-id="{object_id}" '
                    f'data-visible-start-ms="{visibility["start_ms"]}" '
                    f'data-visible-end-ms="{visibility["end_ms"]}" class="{classes}" '
                    f'style="{style}">{content}</div>'
                )
        scene_markup.append(
            f'<section id="{escape(scene["scene_id"], quote=True)}" class="scene" '
            f'data-scene-id="{escape(scene["scene_id"], quote=True)}" '
            f'data-start-ms="{scene["start_ms"]}" data-end-ms="{scene["end_ms"]}" '
            f'data-start-frame="{scene["start_frame"]}" '
            f'data-end-frame-exclusive="{scene["end_frame_exclusive"]}" '
            f'data-animation-primitives="{escape(primitives, quote=True)}" '
            f'data-animation-steps="{escape(steps, quote=True)}">'
            + "".join(object_markup) + "</section>"
        )
        scene_schedule.append({
            "scene_id": scene["scene_id"],
            "start_ms": scene["start_ms"],
            "end_ms": scene["end_ms"],
        })
    schedule_json = json.dumps(scene_schedule, ensure_ascii=False, separators=(",", ":"))
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=1080,height=1920">'
        '<style>'
        "@font-face{font-family:'Microsoft YaHei';src:local('Microsoft YaHei')}"
        "@font-face{font-family:'FangleiSans';src:local('Microsoft YaHei')}"
        '*{box-sizing:border-box}html,body{margin:0;width:1080px;height:1920px;overflow:hidden;'
        "background:#faf8f0;font-family:'Microsoft YaHei',sans-serif}"
        '#root{position:relative;width:1080px;height:1920px;overflow:hidden;background:#faf8f0}'
        '.scene{position:absolute;inset:0;visibility:hidden;opacity:0;background:#faf8f0}'
        '.scene-object{position:absolute;display:flex;align-items:center;justify-content:center;'
        'color:#20211d;font-size:58px;font-weight:700;opacity:0;transform:translateY(28px)}'
        '.shape rect{fill:#fff;stroke:#20211d;stroke-width:3}.shape text{font-family:'
        "'Microsoft YaHei',sans-serif;font-size:16px;font-weight:700;fill:#20211d}"
        '.primary{color:#d54b3d;font-size:110px}'
        '</style></head><body>'
        f'<main id="root" data-composition-id="full" data-no-timeline data-start="0" '
        f'data-duration="{duration_seconds:g}" data-fps="{fps}" '
        f'data-frame-count="{_frame_at_or_after(duration_ms, fps)}" '
        'data-width="1080" data-height="1920">'
        + "".join(scene_markup)
        + f'<audio id="full_narration" class="clip" data-start="0" '
        f'data-duration="{duration_seconds:g}" data-track-index="5" data-volume="1" '
        'src="assets/narration.wav"></audio></main>'
        f'<script>const sceneSchedule={schedule_json};'
        'for(const item of sceneSchedule){const scene=document.getElementById(item.scene_id);'
        'scene.animate([{visibility:"hidden",opacity:0,offset:0},'
        '{visibility:"hidden",opacity:0,offset:item.start_ms/' + str(duration_ms) + '},'
        '{visibility:"visible",opacity:1,offset:item.start_ms/' + str(duration_ms) + '},'
        '{visibility:"visible",opacity:1,offset:item.end_ms/' + str(duration_ms) + '},'
        '{visibility:"hidden",opacity:0,offset:item.end_ms/' + str(duration_ms) + '},'
        '{visibility:"hidden",opacity:0,offset:1}],'
        '{duration:' + str(duration_ms) + ',fill:"both",easing:"linear"});'
        'for(const object of scene.querySelectorAll(".scene-object")){'
        'const start=Number(object.dataset.visibleStartMs);const end=Number(object.dataset.visibleEndMs);'
        'const revealEnd=Math.min(start+350,end);'
        'object.animate([{visibility:"hidden",opacity:0,transform:"translateY(28px)",offset:0},'
        '{visibility:"hidden",opacity:0,transform:"translateY(28px)",offset:start/' + str(duration_ms) + '},'
        '{visibility:"visible",opacity:1,transform:"translateY(0)",offset:revealEnd/' + str(duration_ms) + '},'
        '{visibility:"visible",opacity:1,transform:"translateY(0)",offset:end/' + str(duration_ms) + '},'
        '{visibility:"hidden",opacity:0,transform:"translateY(0)",offset:end/' + str(duration_ms) + '},'
        '{visibility:"hidden",opacity:0,transform:"translateY(0)",offset:1}],'
        '{duration:' + str(duration_ms) + ',fill:"both",easing:"linear"});}}'
        'document.getElementById("root").dataset.animationStatus='
        'sceneSchedule.length===' + str(len(scene_schedule)) + '?"ready":"invalid";'
        '</script></body></html>\n'
    )


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
    fps = 30
    duration_ms = int(timeline.audio["duration_ms"])
    frame_count = _frame_at_or_after(duration_ms, fps)
    scene_frame_ranges = []
    for scene in project_scenes:
        scene["start_frame"] = _frame_at_or_after(scene["start_ms"], fps)
        scene["end_frame_exclusive"] = _frame_at_or_after(scene["end_ms"], fps)
        scene["object_visibility"] = _object_visibility(scene)
        scene_frame_ranges.append({
            "scene_id": scene["scene_id"],
            "start_ms": scene["start_ms"],
            "end_ms": scene["end_ms"],
            "start_frame": scene["start_frame"],
            "end_frame_exclusive": scene["end_frame_exclusive"],
        })
    project_manifest = {
        "schema_version": "5.0",
        "run_id": timeline.run_id,
        "route": storyboard["renderer_selection"]["primary_route"],
        "audio": {"path": "assets/narration.wav", **timeline.audio},
        "composition": {
            "entry": "index.html",
            "duration_ms": duration_ms,
            "fps": fps,
            "frame_count": frame_count,
            "scene_frame_ranges": scene_frame_ranges,
        },
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
            "compatibility_composition_entry": "compositions/beat-001.html",
            "full_composition_entry": "index.html",
            "duration_ms": duration_ms,
            "fps": fps,
            "frame_count": frame_count,
            "scene_frame_ranges": scene_frame_ranges,
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
        "index.html": _full_composition_html(project_scenes, duration_ms, fps),
        "compositions/beat-001.html": _beat_one_dry_run_html(
            project_scenes[0], audio_path="assets/narration.wav", audio_track_index=6,
        ),
        "package.json": json.dumps({
            "name": "fanglei-nikola-render-project", "private": True, "type": "module",
            "scripts": {
                "compat": "node scripts/compatibility-check.mjs",
                "check": "npx --yes hyperframes@0.8.20 check",
                "preview": "npx --yes hyperframes@0.8.20 preview",
                "render:full": "npx --yes hyperframes@0.8.20 render .",
            },
        }, ensure_ascii=False, indent=2) + "\n",
        "scripts/compatibility-check.mjs": (
            "import fs from 'node:fs';\n"
            "for (const p of ['project-manifest.json','hyperframes.json','data/storyboard.json','data/timeline.json','assets/narration.wav','index.html','compositions/beat-001.html']) "
            "if (!fs.existsSync(p)) throw new Error(`missing ${p}`);\n"
            "JSON.parse(fs.readFileSync('project-manifest.json','utf8'));\n"
        ),
    }
    return files, manifest
