"""Build the isolated V1.0a HyperFrames renderer project."""
from __future__ import annotations

import json
from html import escape
from pathlib import Path

from fanglei.artifacts import sha256_bytes
from fanglei.gdp_calibration_v1 import build_gdp_calibration_storyboard
from fanglei.visual_qa_v1 import run_minimal_visual_qa
from fanglei.visual_system_v1 import (
    StoryboardV1,
    VisualProgram,
    VisualProgramCompiler,
    build_default_registry,
)


def _json(value: object, *, indent: int | None = None) -> str:
    return json.dumps(value, ensure_ascii=False, indent=indent, separators=None if indent else (",", ":"))


def _scene_markup(storyboard: StoryboardV1, program: VisualProgram) -> tuple[str, list[dict]]:
    registry = build_default_registry()
    compiled_by_id = {scene.scene_id: scene for scene in program.scenes}
    markup: list[str] = []
    schedule: list[dict] = []
    for index, scene in enumerate(storyboard.scenes):
        compiled = compiled_by_id[scene.scene_id]
        is_last = index == len(storyboard.scenes) - 1
        visible_end_ms = (
            program.scenes[index + 1].start_ms if not is_last else program.duration_ms
        )
        hold_end_frame_exclusive = (
            program.scenes[index + 1].start_frame if not is_last else program.frame_count
        )
        revealed_object_ids: set[str] = set()
        scheduled_states: list[dict] = []
        for state in compiled.states:
            state_payload = state.model_dump(mode="json")
            actions: list[dict[str, str]] = []
            for object_id in state.target_object_ids:
                if object_id not in revealed_object_ids:
                    operation = "reveal"
                elif (
                    scene.primitive.type.value == "number_transform"
                    and state.change_type == "transform"
                ):
                    operation = "transform"
                else:
                    operation = "emphasize"
                actions.append({"object_id": object_id, "operation": operation})
                revealed_object_ids.add(object_id)
            state_payload["object_actions"] = actions
            scheduled_states.append(state_payload)
        component = registry.resolve(scene.primitive.type).render(scene, storyboard.theme)
        markup.append(
            f'<section id="{escape(scene.scene_id)}" class="visual-scene" '
            f'data-scene-id="{escape(scene.scene_id)}" '
            f'data-start-ms="{compiled.start_ms}" data-end-ms="{compiled.end_ms}" '
            f'data-hold-end-ms="{visible_end_ms}" '
            f'data-hold-end-frame-exclusive="{hold_end_frame_exclusive}" '
            f'data-terminal-visibility="{"hold" if is_last else "hide"}" '
            f'data-start-frame="{compiled.start_frame}" '
            f'data-end-frame-exclusive="{compiled.end_frame_exclusive}">{component}</section>'
        )
        schedule.append({
            "scene_id": scene.scene_id,
            "start_ms": compiled.start_ms,
            "end_ms": compiled.end_ms,
            "hold_end_ms": visible_end_ms,
            "hold_end_frame_exclusive": hold_end_frame_exclusive,
            "terminal_visibility": "hold" if is_last else "hide",
            "states": scheduled_states,
        })
    return "".join(markup), schedule


def _full_html(storyboard: StoryboardV1, program: VisualProgram) -> str:
    scene_markup, schedule = _scene_markup(storyboard, program)
    theme = storyboard.theme
    colors = theme.colors
    motion = theme.motion
    duration_seconds = program.duration_ms / 1000
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=1080,height=1920">'
        '<style>'
        "@font-face{font-family:'FangleiSans';src:local('Microsoft YaHei')}"
        "@font-face{font-family:'Microsoft YaHei';src:local('Microsoft YaHei')}"
        '*{box-sizing:border-box}html,body{margin:0;width:1080px;height:1920px;overflow:hidden;'
        f'background:{colors.canvas};font-family:FangleiSans,"Microsoft YaHei",sans-serif;color:{colors.ink_primary}}}'
        f'#root{{position:relative;width:1080px;height:1920px;overflow:hidden;background:{colors.canvas}}}'
        '.brand{position:absolute;z-index:40;left:96px;top:68px;font-size:28px;font-weight:700;'
        'letter-spacing:.18em;color:#6B665E}.brand-dot{color:#D94B3D}'
        '.visual-scene{position:absolute;inset:0;visibility:hidden;opacity:0}'
        '.visual-scene>section{position:absolute;left:96px;top:120px;width:888px;height:1360px}'
        '.hook-stage{display:grid;grid-template-columns:1fr 1fr;grid-template-rows:180px 410px 200px;'
        'column-gap:44px;align-content:center}.hook-object{opacity:0}.hook-object[data-semantic-role="topic"]{'
        'grid-column:1/3;text-align:center;font-size:58px;font-weight:700;align-self:end}'
        '.hook-object[data-semantic-role="numeric_value"]{display:flex;align-items:center;justify-content:center;'
        'font-size:120px;font-weight:800;background:#fff;border:4px solid #1E1E1E;border-radius:28px;'
        'box-shadow:0 18px 0 #E8E1D5}.hook-object[data-semantic-role="question"]{grid-column:1/3;'
        'text-align:center;font-size:64px;font-weight:800;color:#D94B3D;align-self:center}'
        '.comparison-grid{display:grid;grid-template-columns:1fr 1fr;grid-template-rows:150px 170px 300px 130px;'
        'gap:28px 44px;align-content:center}.comparison-item{opacity:0;display:flex;align-items:center;justify-content:center}'
        '.comparison-item[data-semantic-role="metric_context"]{grid-column:1/3;font-size:42px;font-weight:700}'
        '.comparison-item[data-semantic-role="source_badge"]{font-size:38px;font-weight:700;background:#E8E1D5;'
        'border-radius:999px;align-self:center;justify-self:center;padding:18px 36px}'
        '.comparison-item[data-semantic-role="numeric_value"]{font-size:108px;font-weight:800;background:#fff;'
        'border:4px solid #1E1E1E;border-radius:28px;box-shadow:0 16px 0 #E8E1D5}'
        '.comparison-item[data-semantic-role="comparison_relation"]{grid-column:1/3;font-size:48px;'
        'font-weight:800;color:#D94B3D}'
        '.number-transform{display:grid;grid-template-columns:1fr 150px 1fr;grid-template-rows:120px 340px 160px 150px;'
        'gap:32px;align-content:center}.transform-item{opacity:0;display:flex;align-items:center;justify-content:center}'
        '.transform-item[data-semantic-role="source_badge"]{font-size:30px;background:#E8E1D5;border-radius:999px;'
        'padding:12px 24px;justify-self:center}.transform-item[data-semantic-role="numeric_value"]{font-size:100px;'
        'font-weight:800;background:#fff;border:4px solid #1E1E1E;border-radius:28px;padding:38px 24px}'
        '.transform-item[data-object-id="world_bank_value"]{grid-column:1}.transform-item[data-object-id="bea_value"]{grid-column:3}'
        '.transform-item[data-semantic-role="transform_rule"]{grid-column:1/4;font-size:44px;font-weight:700;'
        'color:#E69A32}.transform-item[data-semantic-role="numeric_relation"]{grid-column:1/4;font-size:64px;'
        'font-weight:800;color:#D94B3D}'
        '.process-flow{display:grid;grid-template-columns:1fr 1fr;grid-template-rows:150px 280px 280px;'
        'gap:44px;align-content:center}.process-node{opacity:0;display:flex;align-items:center;justify-content:center}'
        '.process-node[data-semantic-role="numeric_value"]{font-size:54px;font-weight:800;background:#fff;border-radius:22px;'
        'border:3px solid #B9B2A7}.process-node[data-semantic-role="process_step"]{font-size:52px;font-weight:800;'
        'background:#fff;border:4px solid #1E1E1E;border-radius:28px;box-shadow:0 14px 0 #E8E1D5}'
        '.process-node[data-semantic-role="process_step"]::after{content:"✓";position:absolute;transform:translate(125px,-70px);'
        'font-size:38px;color:#3E8E68}'
        '.conclusion-lockup{display:grid;grid-template-columns:1fr 1fr;grid-template-rows:180px 260px 260px;'
        'gap:40px;align-content:center}.conclusion-object{opacity:0;display:flex;align-items:center;justify-content:center}'
        '.conclusion-object[data-semantic-role="numeric_value"]{font-size:64px;font-weight:800;background:#fff;'
        'border:3px solid #1E1E1E;border-radius:24px}.conclusion-object[data-semantic-role="conclusion"]{'
        'grid-column:1/3;font-size:66px;font-weight:800;color:#D94B3D}.conclusion-object[data-semantic-role="metaphor"]{'
        'grid-column:1/3;font-size:46px;font-weight:700;text-align:center;background:#fff;border-radius:28px;'
        'border:4px dashed #E69A32;padding:42px}'
        '.focus-ring{position:absolute;inset:180px 120px auto;width:840px;height:1000px;pointer-events:none;opacity:.12}'
        '</style></head><body>'
        f'<main id="root" data-composition-id="full" data-animation-status="ready" '
        'data-layout-status="ready" data-no-timeline '
        f'data-start="0" data-duration="{duration_seconds:g}" data-fps="{program.fps}" '
        f'data-frame-count="{program.frame_count}" data-width="1080" data-height="1920">'
        '<div class="brand"><span class="brand-dot">●</span> 风雷经济</div>'
        '<svg class="focus-ring" viewBox="0 0 840 1000" aria-hidden="true">'
        '<path d="M32 80 Q420 8 808 80" fill="none" stroke="#D94B3D" stroke-width="5" stroke-linecap="round"/>'
        '</svg>'
        + scene_markup
        + f'<audio id="full_narration" class="clip" data-start="0" data-duration="{duration_seconds:g}" '
        'data-track-index="5" data-volume="1" src="assets/narration.wav"></audio></main>'
        f'<script>const visualSchedule={_json(schedule)};const totalDuration={program.duration_ms};'
        'for(const item of visualSchedule){const scene=document.getElementById(item.scene_id);'
        'const start=item.start_ms/totalDuration;const end=item.hold_end_ms/totalDuration;'
        'const sceneKeyframes=[{visibility:"hidden",opacity:0,offset:0},'
        '{visibility:"hidden",opacity:0,offset:start},{visibility:"visible",opacity:1,offset:start}];'
        'if(item.terminal_visibility==="hold"){sceneKeyframes.push({visibility:"visible",opacity:1,offset:1});}'
        'else{sceneKeyframes.push({visibility:"visible",opacity:1,offset:end},'
        '{visibility:"hidden",opacity:0,offset:end},{visibility:"hidden",opacity:0,offset:1});}'
        'scene.animate(sceneKeyframes,'
        '{duration:totalDuration,fill:"both",easing:"linear"});'
        'for(const state of item.states){for(const action of state.object_actions){'
        'const object=[...scene.querySelectorAll("[data-object-id]")].find(node=>node.dataset.objectId===action.object_id);'
        'if(!object)continue;'
        'const at=state.at_ms/totalDuration;const reveal=Math.min((state.at_ms+' + str(motion.standard_ms) + ')/totalDuration,1);'
        'if(action.operation==="reveal"){object.animate([{opacity:0,transform:"translateY(32px) scale(.96)",offset:0},'
        '{opacity:0,transform:"translateY(32px) scale(.96)",offset:at},'
        '{opacity:1,transform:"translateY(0) scale(1)",offset:reveal},'
        '{opacity:1,transform:"translateY(0) scale(1)",offset:1}],'
        '{duration:totalDuration,fill:"both",easing:"linear"});}'
        'if(action.operation==="transform"&&state.meaningful_change){'
        'const transformed=Math.min((state.at_ms+' + str(motion.standard_ms) + ')/totalDuration,1);'
        'object.animate([{backgroundColor:"#FFFFFF",borderColor:"#1E1E1E",color:"#1E1E1E",offset:0},'
        '{backgroundColor:"#FFFFFF",borderColor:"#1E1E1E",color:"#1E1E1E",offset:at},'
        '{backgroundColor:"#FFF3DF",borderColor:"#E69A32",color:"#D94B3D",offset:transformed},'
        '{backgroundColor:"#FFF3DF",borderColor:"#E69A32",color:"#D94B3D",offset:1}],'
        '{duration:totalDuration,fill:"both",easing:"linear"});}'
        'if(action.operation==="emphasize"&&state.meaningful_change){object.animate('
        '[{transform:"scale(1)"},{transform:"scale(1.07)"},{transform:"scale(1)"}],'
        '{duration:' + str(motion.emphasis_ms) + ',delay:state.at_ms,fill:"both",easing:"ease-in-out"});}}}}'
        'const root=document.getElementById("root");'
        'root.dataset.animationStatus=visualSchedule.length===5?"ready":"invalid";'
        'const layoutOK=[...document.querySelectorAll("[data-semantic-object=true]")].every(node=>{'
        'const box=node.getBoundingClientRect();return box.left>=0&&box.top>=0&&box.right<=1080&&box.bottom<=1480;});'
        'root.dataset.layoutStatus=layoutOK?"ready":"overflow";'
        '</script></body></html>\n'
    )


def _beat_one_html(storyboard: StoryboardV1, program: VisualProgram) -> str:
    scene = storyboard.scenes[0]
    component = build_default_registry().resolve(scene.primitive.type).render(scene, storyboard.theme)
    duration = (program.scenes[0].end_ms - program.scenes[0].start_ms) / 1000
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"></head><body>'
        f'<main data-composition-id="main" data-no-timeline data-duration="{duration:g}" '
        'data-width="1080" data-height="1920">' + component + '</main></body></html>\n'
    )


def build_v1_renderer_project(storyboard: StoryboardV1, program: VisualProgram,
                              timeline: dict, narration_audio: bytes, *,
                              audio_sha256: str) -> tuple[dict[str, str | bytes], dict]:
    if int(timeline["audio"]["duration_ms"]) != program.duration_ms:
        raise ValueError("V1_TIMELINE_DURATION_MISMATCH")
    scene_ranges = [{
        "scene_id": scene.scene_id, "start_ms": scene.start_ms, "end_ms": scene.end_ms,
        "start_frame": scene.start_frame, "end_frame_exclusive": scene.end_frame_exclusive,
    } for scene in program.scenes]
    project_scenes = [{
        "scene_id": scene.scene_id,
        "renderer_directives": {"primitive_type": scene.primitive_type.value},
    } for scene in program.scenes]
    project_manifest = {
        "schema_version": "5.0", "visual_system_version": "1.0a",
        "run_id": program.run_id,
        "audio": {"path": "assets/narration.wav", "sha256": audio_sha256,
                  "duration_ms": program.duration_ms},
        "composition": {"entry": "index.html", "duration_ms": program.duration_ms,
                        "fps": program.fps, "frame_count": program.frame_count,
                        "scene_frame_ranges": scene_ranges},
        "scenes": project_scenes,
    }
    manifest = {
        "schema_version": "5.0", "visual_system_version": "1.0a", "run_id": program.run_id,
        "audio": project_manifest["audio"],
        "renderer": {
            "engine": "hyperframes", "full_composition_entry": "index.html",
            "compatibility_composition_entry": "compositions/beat-001.html",
            "duration_ms": program.duration_ms, "fps": program.fps,
            "frame_count": program.frame_count, "scene_frame_ranges": scene_ranges,
            "full_render_requested": False,
        },
        "provenance": {"all_factual_objects_traceable": True},
    }
    files: dict[str, str | bytes] = {
        "project-manifest.json": _json(project_manifest, indent=2) + "\n",
        "hyperframes.json": _json({
            "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
            "registry": "https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry",
            "paths": {"blocks": "compositions", "components": "compositions/components",
                      "assets": "assets"},
            "media": {"autoProxy": True},
        }, indent=2) + "\n",
        "data/storyboard.json": storyboard.model_dump_json(indent=2) + "\n",
        "data/storyboard-v1.json": storyboard.model_dump_json(indent=2) + "\n",
        "data/visual_program.json": program.model_dump_json(indent=2) + "\n",
        "data/timeline.json": _json(timeline, indent=2) + "\n",
        "assets/narration.wav": narration_audio,
        "index.html": _full_html(storyboard, program),
        "compositions/beat-001.html": _beat_one_html(storyboard, program),
        "package.json": _json({
            "name": "fanglei-v1a-calibration", "private": True, "type": "module",
            "scripts": {
                "compat": "node scripts/compatibility-check.mjs",
                "check": "npx --yes hyperframes@0.8.20 check",
                "preview": "npx --yes hyperframes@0.8.20 preview",
                "render:calibration": "npx --yes hyperframes@0.8.20 render .",
            },
        }, indent=2) + "\n",
        "scripts/compatibility-check.mjs": (
            "import fs from 'node:fs';\n"
            "for (const p of ['project-manifest.json','hyperframes.json','data/storyboard.json',"
            "'data/visual_program.json','data/timeline.json','assets/narration.wav','index.html']) "
            "if (!fs.existsSync(p)) throw new Error(`missing ${p}`);\n"
        ),
    }
    return files, manifest


def materialize_gdp_v1a(run_dir: Path) -> dict:
    """Materialize downstream-only V1.0a artifacts; never render or touch final.mp4."""
    legacy_storyboard = json.loads((run_dir / "storyboard.json").read_text(encoding="utf-8"))
    timeline = json.loads((run_dir / "timeline.json").read_text(encoding="utf-8"))
    script = json.loads((run_dir / "script.json").read_text(encoding="utf-8"))
    narration_audio = (run_dir / "audio" / "narration.wav").read_bytes()
    audio_sha = sha256_bytes(narration_audio)
    if audio_sha != timeline.get("audio", {}).get("sha256"):
        raise ValueError("V1_AUDIO_HASH_MISMATCH")
    storyboard = build_gdp_calibration_storyboard(
        legacy_storyboard, run_id=timeline["run_id"] if "run_id" in timeline else "gdp-run",
        script_id=script["script_id"],
    )
    program = VisualProgramCompiler(build_default_registry()).compile(storyboard, timeline)
    qa = run_minimal_visual_qa(program, storyboard, timeline=timeline)
    if not qa.passed:
        codes = ",".join(issue.code for issue in qa.issues if issue.severity == "error")
        raise ValueError("V1_STRUCTURAL_QA_FAILED:" + codes)
    files, manifest = build_v1_renderer_project(
        storyboard, program, timeline, narration_audio, audio_sha256=audio_sha,
    )
    project_dir = run_dir / "renderer_project_v1a"
    for relative, value in files.items():
        target = project_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(value, bytes):
            target.write_bytes(value)
        else:
            target.write_text(value, encoding="utf-8")
    (run_dir / "storyboard-v1a.json").write_text(
        storyboard.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    (run_dir / "visual_program.json").write_text(
        program.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    (run_dir / "visual_qa_v1a.json").write_text(
        qa.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    (run_dir / "render_manifest_v1a.json").write_text(
        _json(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return {"storyboard": storyboard, "program": program, "qa": qa, "manifest": manifest}
