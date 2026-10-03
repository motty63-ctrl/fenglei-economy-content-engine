"""Browser-measured review composition driven by the renderer's requested time."""
from __future__ import annotations

import json
from typing import Literal


REVIEW_OVERLAYS = (
    '<div class="preview-label">PREVIEW · NOT FINAL</div>',
    '<div id="review-required">HUMAN REVIEW REQUIRED</div>',
)


def apply_presentation_mode(html: str, presentation_mode: Literal["review", "publication"] = "review") -> str:
    """Change only owner-defined review overlay nodes in a frozen composition."""
    if presentation_mode not in ("review", "publication"):
        raise ValueError("PRESENTATION_MODE_UNSUPPORTED")
    if presentation_mode == "review":
        return html
    for overlay in REVIEW_OVERLAYS:
        if html.count(overlay) != 1:
            raise ValueError("PUBLICATION_REVIEW_OVERLAY_STRUCTURE_INVALID")
    for overlay in REVIEW_OVERLAYS:
        html = html.replace(overlay, "", 1)
    return html


REVIEW_RENDER_SCRIPT = r"""(() => {
  const data = JSON.parse(document.getElementById('preview-data').textContent);
  const stage = document.getElementById('stage');
  const panel = document.getElementById('subtitle-layer');
  const text = document.getElementById('subtitle-text');
  const layout = data.layout;
  const scenes = data.scenes.map(row => ({...row, node:document.getElementById(row.scene_id)}));
  const measurements = new Map();
  let currentSeconds = 0;
  const rect = node => {
    const r = node.getBoundingClientRect(), root = stage.getBoundingClientRect();
    return {x:r.left-root.left, y:r.top-root.top, width:r.width, height:r.height};
  };
  const intersects = (a,b) => a.x < b.x+b.width && a.x+a.width > b.x && a.y < b.y+b.height && a.y+a.height > b.y;
  const safePosition = (height,width,rows) => {
    const gap=16, left=(layout.canvas_width-width)/2;
    const critical=rows.flatMap(s=>[...s.node.querySelectorAll('[data-object-id]')].map(rect));
    const footers=rows.flatMap(s=>[...s.node.querySelectorAll('[data-source-ids]')].map(rect));
    const floor=Math.min(layout.canvas_height-64, ...footers.map(r=>r.y-gap));
    const blockers=critical.filter(r=>r.x<left+width && r.x+r.width>left)
      .map(r=>({start:Math.max(96,r.y-gap),end:r.y+r.height+gap})).sort((a,b)=>a.start-b.start);
    const bands=[];
    let cursor=96;
    for(const r of blockers){if(r.start>cursor)bands.push({start:cursor,end:Math.min(r.start,floor)});cursor=Math.max(cursor,r.end);}
    if(cursor<floor)bands.push({start:cursor,end:floor});
    const band=bands.reverse().find(r=>r.end-r.start>=height);
    if(!band)return null;
    const preferred=layout.reserved_zone.y+layout.reserved_zone.height;
    const y=Math.max(band.start,Math.min(preferred,band.end)-height);
    const box={x:left,y,width,height};
    return {box,critical,footers};
  };
  const measure = cue => {
    const rows=scenes.filter(s=>cue.start_ms<s.end_ms&&cue.end_ms>s.start_ms);
    panel.style.display='block';panel.style.minHeight='0';
    text.textContent=cue.text;
    const maximum=Math.max(layout.minimum_font_size_px, cue.font_size_px);
    for(const font of [maximum, ...Array.from({length:Math.ceil((maximum-layout.minimum_font_size_px)/2)},(_,i)=>maximum-2*(i+1)).filter(f=>f>=layout.minimum_font_size_px)]) {
      for(const padding of [layout.horizontal_padding_px, Math.min(8,layout.horizontal_padding_px)]) {
        panel.style.fontSize=font+'px';panel.style.padding=layout.vertical_padding_px+'px '+padding+'px';
        panel.style.left='0px';panel.style.top='0px';
        const height=Math.ceil(panel.getBoundingClientRect().height),width=panel.getBoundingClientRect().width;
        const position=safePosition(height,width,rows);
        if(!position||height>layout.canvas_height*.18)continue;
        panel.style.left=position.box.x+'px';panel.style.top=position.box.y+'px';
        const range=document.createRange();range.selectNodeContents(text);
        const lineCount=new Set([...range.getClientRects()].map(r=>Math.round(r.top*10)/10)).size;
        const box=rect(panel),textBox=rect(text);
        const report={cue_id:cue.cue_id,text:cue.text,rendered_text:text.textContent,
          line_count:lineCount,font_size_px:font,font_family:getComputedStyle(text).fontFamily,
          panel:box,text_box:textBox,scroll_height:text.scrollHeight,client_height:text.clientHeight,
          overflow:text.scrollHeight>text.clientHeight+1||text.scrollWidth>text.clientWidth+1||textBox.height>box.height,
          safe_area_ok:box.x>=0&&box.x+box.width<=layout.canvas_width&&box.y>=96&&box.y+box.height<=layout.canvas_height-64,
          footer_collision:position.footers.some(r=>intersects(box,r)),
          critical_collision:position.critical.some(r=>intersects(box,r)),
          horizontal_padding_px:padding};
        if(report.overflow||!report.safe_area_ok||report.footer_collision||report.critical_collision)continue;
        measurements.set(cue.cue_id,report);return report;
      }
    }
    throw new Error('RENDER_SUBTITLE_NO_SAFE_SPACE');
  };
  const renderAt = seconds => {
    if(!Number.isFinite(seconds))throw new Error('RENDER_TIME_INVALID');
    currentSeconds=Math.max(0,Math.min(seconds,data.duration_ms/1000));
    const ms=currentSeconds*1000;
    const active=scenes.find((s,i)=>ms>=s.start_ms&&(ms<s.end_ms||(i===scenes.length-1&&ms<=s.end_ms)));
    for(const scene of scenes){
      const on=scene===active;scene.node.style.visibility=on?'visible':'hidden';scene.node.style.opacity=on?'1':'0';
      scene.node.classList.toggle('active',on);
      if(!on)continue;
      for(const cue of scene.motion){
        const node=[...scene.node.querySelectorAll('[data-object-id]')].find(n=>n.dataset.objectId===cue.object_id);
        if(node){const progress=Math.max(0,Math.min(1,(ms-scene.start_ms-cue.delay_ms)/Math.max(1,cue.duration_ms)));
          node.style.opacity=cue.effect==='hold'?'1':String(progress);}
      }
    }
    const cue=data.subtitles.find(c=>ms>=c.start_ms&&ms<c.end_ms);
    panel.style.display=cue?'block':'none';
    if(cue){const measured=measurements.get(cue.cue_id);if(!measured)throw new Error('RENDER_SUBTITLE_NOT_MEASURED');
      text.textContent=cue.text;panel.style.fontSize=measured.font_size_px+'px';
      panel.style.padding=layout.vertical_padding_px+'px '+measured.horizontal_padding_px+'px';
      panel.style.left=measured.panel.x+'px';panel.style.top=measured.panel.y+'px';}
    stage.dataset.renderTimeSeconds=String(currentSeconds);stage.dataset.activeScene=active?.scene_id||'';
  };
  window.fengleiRenderReadiness={settled:false,ready:false,error:null};
  window.fengleiSubtitleLayoutReport=[];
  // No browser playback or wall clock participates in scene/caption selection.
  const clock={vars:{paused:true},duration:()=>data.duration_ms/1000,totalDuration:()=>data.duration_ms/1000,
    pause(){return this;},play(){return this;},getChildren:()=>[],
    seek(t){if(t===undefined)return currentSeconds;renderAt(Number(t));return this;},
    time(t){if(t===undefined)return currentSeconds;return this.seek(t);},
    totalTime(t){if(t===undefined)return currentSeconds;return this.seek(t);}};
  document.fonts.ready.then(()=>{
    try{
      window.fengleiSubtitleLayoutReport=data.subtitles.map(measure);
      renderAt(0);
      window.__timelines=window.__timelines||{};
      window.__timelines['fenglei-review']=clock;
      // HyperFrames' frame-capture contract calls __hf.seek(frame / fps).
      // Expose it directly as well as the native timeline registry; no GSAP or
      // browser-media event is required to apply the requested composition time.
      window.__hf=window.__hf||{};
      window.__hf.duration=data.duration_ms/1000;
      window.__hf.seek=(t,options)=>{
        if(window.__playerReady&&typeof window.__player?.renderSeek==='function')
          window.__player.renderSeek(t,options);
        else clock.seek(t);
      };
      window.fengleiRenderReadiness={settled:true,ready:true,error:null};
      window.__renderReady=true;
    }catch(error){panel.style.display='none';window.fengleiRenderReadiness={settled:true,ready:false,error:error.message};}
  });
})();
"""


def review_composition_html(scene_markup: list[str], data: dict, layout: dict, timing_status: str,
                           *, presentation_mode: Literal["review", "publication"] = "review") -> str:
    """Use one canvas/timebase; measure full canonical text after browser fonts resolve."""
    width,height=layout["canvas_width"],layout["canvas_height"]
    payload=json.dumps({**data,"layout":layout},ensure_ascii=False,separators=(",", ":")).replace("</","<\\/")
    html = (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width={width},height={height}"><title>Local Review Preview</title><style>'
        '*{box-sizing:border-box}html,body{margin:0;padding:0;background:#171717;'
        "font-family:system-ui,'Noto Sans CJK SC','PingFang SC','Hiragino Sans GB',sans-serif}"
        f'#stage{{position:relative;width:{width}px;height:{height}px;overflow:hidden;background:#F7F2E8}}'
        '#canvas{position:absolute;inset:0;width:100%;height:100%;transform-origin:top left;'
        'transform:scale(var(--preview-scale,1))}#canvas svg{width:100%;height:100%;display:block}'
        '.visual-scene{position:absolute;inset:0;visibility:hidden;opacity:0}'
        '.preview-label{position:absolute;z-index:20;left:24px;top:24px;padding:12px 18px;background:#8d2118;'
        'color:#fff;font-weight:800;font-size:24px}#review-required{position:absolute;z-index:20;right:20px;'
        'top:24px;padding:10px 14px;background:#20211d;color:#fff;font-weight:700;font-size:18px}'
        '#subtitle-layer{position:absolute;z-index:30;width:max-content;'
        f'max-width:{layout["reserved_zone"]["width"]}px;height:auto;min-height:0;'
        f'padding:{layout["vertical_padding_px"]}px {layout["horizontal_padding_px"]}px;'
        f'line-height:{layout["line_height"]};'
        'display:none;text-align:center;background:rgba(247,242,232,.88);color:#1E1E1E;border-radius:18px;'
        'font-weight:700;overflow:visible}#subtitle-text{display:block;line-height:normal;white-space:pre-wrap;overflow-wrap:anywhere}'
        'audio,#status{display:none}</style></head><body>'
        f'<main id="stage" data-composition-id="fenglei-review" data-width="{width}" data-height="{height}" '
        f'data-duration="{data["duration_ms"]/1000:g}" data-fps="30" data-preview="true" data-final="false"><div id="canvas">'
        + ''.join(scene_markup)
        + '<div class="preview-label">PREVIEW · NOT FINAL</div><div id="review-required">HUMAN REVIEW REQUIRED</div>'
        + '<div id="subtitle-layer"><span id="subtitle-text"></span></div>'
        + f'<audio id="narration" preload="auto" data-start="0" data-duration="{data["duration_ms"]/1000:g}" '
        + 'data-track-index="1" src="assets/narration.wav"></audio></div></main>'
        + f'<div id="status">{timing_status}</div><script type="application/json" id="preview-data">{payload}</script>'
        + '<script>'+REVIEW_RENDER_SCRIPT+'</script></body></html>\n'
    )
    return apply_presentation_mode(html, presentation_mode)
