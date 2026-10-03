import {pathToFileURL} from 'node:url';
const [modulePath, browserPath, runtimePath, entry, output, auditAll] = process.argv.slice(2);
const {default: puppeteer} = await import(pathToFileURL(modulePath + '/lib/puppeteer/puppeteer-core.js').href);
const browser = await puppeteer.launch({executablePath: browserPath, headless: true, args: ['--no-sandbox']});
try {
  const page = await browser.newPage();
  const warnings=[];
  page.on('console', msg => {if(['warning','error'].includes(msg.type()))warnings.push(msg.text());});
  await page.setViewport({width:1080,height:1920,deviceScaleFactor:1});
  await page.setRequestInterception(true);
  page.on('request', request => /^(file:|data:|blob:)/.test(request.url()) ? request.continue() : request.abort());
  await page.goto(pathToFileURL(entry).href);
  await page.evaluate(() => document.fonts.ready);
  await page.waitForFunction(() => window.fengleiRenderReadiness?.settled ?? document.readyState === 'complete');
  const result = await page.evaluate(() => ({
    layout_ready: !!window.fengleiRenderReadiness?.ready,
    layout_error: window.fengleiRenderReadiness?.error ?? null,
    layout: window.fengleiSubtitleLayoutReport ?? [],
    native_time_ready: !!window.__timelines?.['fenglei-review'],
    samples: [], same_frame_after_audio_seek: false,
  }));
  if (result.layout_ready && result.native_time_ready) {
    await page.addScriptTag({path: runtimePath});
    await page.waitForFunction(() => window.__playerReady && window.__renderReady);
    const schedule = await page.evaluate(() => JSON.parse(document.getElementById('preview-data').textContent));
    const samples = auditAll ? schedule.scenes.map(s=>({label:s.scene_id,time:(s.start_ms+s.end_ms)/2000}))
      : [...'ABC'].map((letter,i)=>({label:letter,time:i*2+.5}));
    for (const sample of samples) {
      await page.evaluate(t => window.__hf.seek(t, {suppressEvents:true}), sample.time);
      result.samples.push(await page.evaluate(() => {
        const node = [...document.querySelectorAll('.visual-scene')].find(n => getComputedStyle(n).visibility === 'visible');
        return {scene_id:node?.dataset.sceneId,visible_object_count:[...node.querySelectorAll('[data-object-id]')].filter(n=>Number(getComputedStyle(n).opacity)>0).length};
      }));
      result.samples.at(-1).time=sample.time;
      await page.screenshot({path:output + '/sample-' + sample.label + '.png'});
      const capturedScene = await page.evaluate(() => document.getElementById('stage').dataset.activeScene);
      if(capturedScene !== result.samples.at(-1).scene_id)throw new Error('RENDER_SCENE_CHANGED_DURING_CAPTURE');
    }
    await page.evaluate(() => window.__hf.seek(.5, {suppressEvents:true}));
    const first = await page.screenshot();
    await page.evaluate(() => {document.getElementById('narration').currentTime=5;window.__hf.seek(.5,{suppressEvents:true});});
    result.same_frame_after_audio_seek = Buffer.from(first).equals(Buffer.from(await page.screenshot()));
    if(auditAll){
      result.boundaries=[];result.cue_frames=[];
      const session=await page.createCDPSession();
      await session.send('DOM.enable');await session.send('CSS.enable');
      const {root}=await session.send('DOM.getDocument');
      const {nodeId}=await session.send('DOM.querySelector',{nodeId:root.nodeId,selector:'#subtitle-text'});
      for(const cue of schedule.subtitles){
        const time=(cue.start_ms+cue.end_ms)/2000;
        await page.evaluate(t=>window.__hf.seek(t,{suppressEvents:true}),time);
        const fonts=await session.send('CSS.getPlatformFontsForNode',{nodeId});
        const visible=await page.evaluate(()=>({text:document.getElementById('subtitle-text').textContent,
          scene_id:document.getElementById('stage').dataset.activeScene}));
        result.cue_frames.push({cue_id:cue.cue_id,time,...visible,fonts:fonts.fonts});
        await page.screenshot({path:output+'/subtitle-'+cue.cue_id+'.png'});
      }
      for(const scene of schedule.scenes.slice(1))for(const side of [-1,1]){
        const time=scene.start_ms/1000+side*2/30;
        await page.evaluate(t=>window.__hf.seek(t,{suppressEvents:true}),time);
        result.boundaries.push({time,scene_id:await page.evaluate(()=>document.getElementById('stage').dataset.activeScene)});
        await page.screenshot({path:output+'/boundary-'+scene.scene_id+'-'+(side<0?'before':'after')+'.png'});
      }
    }
  }
  result.warnings=warnings;
  process.stdout.write(JSON.stringify(result));
} finally {await browser.close();}
