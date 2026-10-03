import fs from 'node:fs';
import { pathToFileURL } from 'node:url';

const [puppeteerPath, browserPath, finalPath, publicationPath, sourceHtml, samplesPath, widthArg, heightArg] = process.argv.slice(2);
const width = Number(widthArg), height = Number(heightArg);
const { default: puppeteer } = await import(pathToFileURL(puppeteerPath + '/lib/puppeteer/puppeteer-core.js').href);
const finalBytes = fs.readFileSync(finalPath), publicationBytes = fs.readFileSync(publicationPath);
const requestedSamples = JSON.parse(fs.readFileSync(samplesPath, 'utf8'));
const browser = await puppeteer.launch({executablePath: browserPath, headless:true,
  args:['--no-sandbox','--autoplay-policy=no-user-gesture-required']});
try {
  const page = await browser.newPage({viewport:{width:640,height:640}});
  let html = fs.readFileSync(sourceHtml, 'utf8').replace(/<script\b[\s\S]*?<\/script>/gi, '');
  await page.setContent(html, {waitUntil:'domcontentloaded'});
  const regions = await page.evaluate(() => {
    const stage = document.querySelector('#stage');
    if (!stage) return [];
    const root = stage.getBoundingClientRect();
    return ['.preview-label', '#review-required'].map(selector => {
      const node = document.querySelector(selector);
      if (!node) return null;
      const r = node.getBoundingClientRect();
      return {selector, x:r.left-root.left, y:r.top-root.top, width:r.width, height:r.height};
    });
  });
  const inPage = await browser.newPage({viewport:{width:640,height:640}});
  const result = await inPage.evaluate(async ({finalUrl, publicationUrl, samples, width, height, regions}) => {
    const load = url => new Promise(resolve => {
      const video=document.createElement('video'); video.preload='auto'; video.playsInline=true; video.volume=0;
      let done=false; const finish=data=>{if(!done){done=true;resolve({video,...data});}};
      video.onloadeddata=()=>finish({error:null}); video.onerror=()=>finish({error:`MEDIA_ERROR_${video.error?.code??'UNKNOWN'}`});
      video.src=url; video.load(); setTimeout(()=>finish({error:'MEDIA_TIMEOUT'}),20000);
    });
    const a=await load(finalUrl), b=await load(publicationUrl);
    const metadata=x=>({error:x.error,width:x.video.videoWidth,height:x.video.videoHeight,
      duration_seconds:Number.isFinite(x.video.duration)?x.video.duration:null,
      audio_track_count:(()=>{try{return x.video.captureStream().getAudioTracks().length;}catch{return 0;}})()});
    const fullDecode=async x=>{
      if(x.error||!x.video.duration)return {ended:false,error:x.error||'NO_DURATION',decoded_frames:0};
      try {
        const video=x.video; video.playbackRate=1; video.currentTime=0;
        const ended=new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('FULL_DECODE_TIMEOUT')),Math.max(30000,video.duration*3000));
          video.onended=()=>{clearTimeout(timer);resolve();}; video.onerror=()=>{clearTimeout(timer);reject(new Error('MEDIA_DECODE_ERROR'));};});
        await video.play(); await ended; const q=video.getVideoPlaybackQuality?.();
        return {ended:true,error:null,decoded_frames:q?.totalVideoFrames??video.webkitDecodedFrameCount??0};
      } catch(error){return {ended:false,error:String(error?.message??error),decoded_frames:0};}
    };
    const decodeA=await fullDecode(a), decodeB=await fullDecode(b);
    const canvas=document.createElement('canvas'); canvas.width=320; canvas.height=Math.max(1,Math.round(320*height/width));
    const ctx=canvas.getContext('2d',{willReadFrequently:true});
    const seek=async(v,time,duration)=>{
      const seconds=Math.max(0,Math.min(time/1000,duration-.02));
      await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('SEEK_TIMEOUT')),10000);
        const end=()=>{clearTimeout(timer);resolve();}; v.addEventListener('seeked',end,{once:true}); v.currentTime=seconds;
        if(Math.abs(v.currentTime-seconds)<.001&&!v.seeking)end();});
      await new Promise(resolve=>setTimeout(resolve,30)); ctx.clearRect(0,0,canvas.width,canvas.height);
      ctx.drawImage(v,0,0,canvas.width,canvas.height); return ctx.getImageData(0,0,canvas.width,canvas.height);
    };
    const compare=(left,right,maskMode)=>{
      const rectangles=regions.filter(Boolean).map(r=>({x0:Math.max(0,Math.floor(r.x/width*canvas.width)),
        y0:Math.max(0,Math.floor(r.y/height*canvas.height)),x1:Math.min(canvas.width,Math.ceil((r.x+r.width)/width*canvas.width)),
        y1:Math.min(canvas.height,Math.ceil((r.y+r.height)/height*canvas.height))}));
      let error=0,count=0;
      for(let y=0;y<canvas.height;y++)for(let x=0;x<canvas.width;x++){
        const inside=rectangles.some(r=>x>=r.x0&&x<r.x1&&y>=r.y0&&y<r.y1);
        if(maskMode==='outside'&&inside)continue; if(maskMode==='inside'&&!inside)continue;
        const i=(y*canvas.width+x)*4; for(let c=0;c<3;c++){error+=Math.abs(left.data[i+c]-right.data[i+c]);count++;}
      }
      return count?1-error/(count*255):null;
    };
    const compareRect=(left,right,rect)=>{
      const x0=Math.max(0,Math.floor(rect.x/width*canvas.width));
      const y0=Math.max(0,Math.floor(rect.y/height*canvas.height));
      const x1=Math.min(canvas.width,Math.ceil((rect.x+rect.width)/width*canvas.width));
      const y1=Math.min(canvas.height,Math.ceil((rect.y+rect.height)/height*canvas.height));
      let error=0,count=0;
      for(let y=y0;y<y1;y++)for(let x=x0;x<x1;x++){const i=(y*canvas.width+x)*4;
        for(let c=0;c<3;c++){error+=Math.abs(left.data[i+c]-right.data[i+c]);count++;}}
      return count?1-error/(count*255):null;
    };
    const rows=[];
    if(!a.error&&!b.error&&a.video.duration&&b.video.duration)for(const sample of samples){
      try { const left=await seek(a.video,sample.time_ms,a.video.duration),right=await seek(b.video,sample.time_ms,b.video.duration);
        const lumaOf=data=>{let total=0;for(let i=0;i<data.data.length;i+=4)total+=(.2126*data.data[i]+.7152*data.data[i+1]+.0722*data.data[i+2])/255;return total/(data.data.length/4);};
        rows.push({sample_id:sample.sample_id,time_ms:sample.time_ms,
          full_frame_similarity:compare(left,right,'all'),outside_mask_similarity:compare(left,right,'outside'),
          overlay_region_similarity:compare(left,right,'inside'),
          subtitle_region_similarity:sample.subtitle_region?compareRect(left,right,sample.subtitle_region):null,
          final_average_luma:lumaOf(left),publication_average_luma:lumaOf(right)});
      } catch(error){rows.push({sample_id:sample.sample_id,error:String(error?.message??error)});}
    }
    return {final:metadata(a),publication:metadata(b),full_decode:{final:decodeA,publication:decodeB},regions,samples:rows};
  }, {finalUrl:`data:video/mp4;base64,${finalBytes.toString('base64')}`,
    publicationUrl:`data:video/mp4;base64,${publicationBytes.toString('base64')}`,
    samples:requestedSamples,width,height,regions});
  process.stdout.write(JSON.stringify(result));
} finally { await browser.close(); }
