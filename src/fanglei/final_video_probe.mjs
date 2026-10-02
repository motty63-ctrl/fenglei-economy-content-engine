import fs from 'node:fs';
import { pathToFileURL } from 'node:url';

const [puppeteerPath, browserPath, finalPath, previewPath, samplesPath, widthArg, heightArg] = process.argv.slice(2);
const sourceWidth = Number(widthArg);
const sourceHeight = Number(heightArg);
const { default: puppeteer } = await import(pathToFileURL(puppeteerPath + '/lib/puppeteer/puppeteer-core.js').href);
const finalBytes = fs.readFileSync(finalPath);
const previewBytes = fs.readFileSync(previewPath);
const samples = JSON.parse(fs.readFileSync(samplesPath, 'utf8'));
const asDataUrl = bytes => `data:video/mp4;base64,${bytes.toString('base64')}`;
const browser = await puppeteer.launch({
  executablePath: browserPath,
  headless: true,
  args: ['--no-sandbox', '--autoplay-policy=no-user-gesture-required'],
});
try {
  const page = await browser.newPage({ viewport: { width: 640, height: 640 } });
  const result = await page.evaluate(async ({ finalUrl, previewUrl, requestedSamples, sourceWidth, sourceHeight }) => {
    const load = url => new Promise(resolve => {
      const video = document.createElement('video');
      video.preload = 'auto';
      video.playsInline = true;
      video.volume = 0;
      let settled = false;
      const finish = data => { if (!settled) { settled = true; resolve({ video, ...data }); } };
      video.onloadeddata = () => finish({ error: null });
      video.onerror = () => finish({ error: `MEDIA_ERROR_${video.error?.code ?? 'UNKNOWN'}` });
      video.src = url;
      video.load();
      setTimeout(() => finish({ error: 'MEDIA_METADATA_TIMEOUT' }), 20000);
    });
    const final = await load(finalUrl);
    const preview = await load(previewUrl);
    const metadata = item => {
      const video = item.video;
      let stream;
      try { stream = video.captureStream(); } catch { stream = null; }
      return {
        error: item.error,
        width: video.videoWidth || 0,
        height: video.videoHeight || 0,
        duration_seconds: Number.isFinite(video.duration) ? video.duration : null,
        ready_state: video.readyState,
        audio_track_count: stream?.getAudioTracks().length ?? 0,
        audio_track_settings: stream?.getAudioTracks().map(track => track.getSettings()) ?? [],
      };
    };
    const finalMetadata = metadata(final);
    const previewMetadata = metadata(preview);
    let fullDecode = { ended: false, error: final.error, decoded_frames: 0, dropped_frames: 0 };
    if (!final.error && final.video.readyState >= 2) {
      const video = final.video;
      try {
        video.muted = false;
        video.playbackRate = 1;
        video.currentTime = 0;
        const ended = new Promise((resolve, reject) => {
          const timeout = setTimeout(() => reject(new Error('FULL_PLAYBACK_TIMEOUT')), Math.max(30000, video.duration * 3000));
          video.onended = () => { clearTimeout(timeout); resolve(); };
          video.onerror = () => { clearTimeout(timeout); reject(new Error(`MEDIA_ERROR_${video.error?.code ?? 'UNKNOWN'}`)); };
        });
        await video.play();
        await ended;
        const quality = video.getVideoPlaybackQuality?.();
        fullDecode = {
          ended: true, error: null,
          decoded_frames: quality?.totalVideoFrames ?? video.webkitDecodedFrameCount ?? 0,
          dropped_frames: quality?.droppedVideoFrames ?? video.webkitDroppedFrameCount ?? 0,
        };
      } catch (error) {
        fullDecode = { ...fullDecode, error: String(error?.message ?? error) };
      }
    }
    const canvas = document.createElement('canvas');
    canvas.width = 320;
    canvas.height = Math.max(1, Math.round(canvas.width * sourceHeight / sourceWidth));
    const context = canvas.getContext('2d', { willReadFrequently: true });
    const seek = async (video, timeMs, duration) => {
      const seconds = Math.max(0, Math.min(timeMs / 1000, duration - 0.02));
      await new Promise((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error('FRAME_SEEK_TIMEOUT')), 10000);
        const done = () => { clearTimeout(timeout); resolve(); };
        video.addEventListener('seeked', done, { once: true });
        video.currentTime = seconds;
        if (Math.abs(video.currentTime - seconds) < 0.001 && !video.seeking) done();
      });
      await new Promise(resolve => setTimeout(resolve, 30));
      context.clearRect(0, 0, canvas.width, canvas.height);
      context.drawImage(video, 0, 0, canvas.width, canvas.height);
      return context.getImageData(0, 0, canvas.width, canvas.height);
    };
    const similarity = (a, b, rect = null) => {
      const x0 = rect ? Math.max(0, Math.round(rect.x / sourceWidth * canvas.width)) : 0;
      const y0 = rect ? Math.max(0, Math.round(rect.y / sourceHeight * canvas.height)) : 0;
      const x1 = rect ? Math.min(canvas.width, Math.round((rect.x + rect.width) / sourceWidth * canvas.width)) : canvas.width;
      const y1 = rect ? Math.min(canvas.height, Math.round((rect.y + rect.height) / sourceHeight * canvas.height)) : canvas.height;
      if (x1 <= x0 || y1 <= y0) return null;
      let delta = 0;
      let count = 0;
      for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) {
        const i = (y * canvas.width + x) * 4;
        delta += Math.abs(a.data[i] - b.data[i]) + Math.abs(a.data[i + 1] - b.data[i + 1]) + Math.abs(a.data[i + 2] - b.data[i + 2]);
        count += 3;
      }
      return count ? 1 - delta / (count * 255) : null;
    };
    const rows = [];
    if (!final.error && !preview.error && finalMetadata.duration_seconds && previewMetadata.duration_seconds) {
      for (const sample of requestedSamples) {
        try {
          const a = await seek(final.video, sample.time_ms, finalMetadata.duration_seconds);
          const b = await seek(preview.video, sample.time_ms, previewMetadata.duration_seconds);
          rows.push({
            sample_id: sample.sample_id,
            time_ms: sample.time_ms,
            full_frame_similarity: similarity(a, b),
            subtitle_region_similarity: sample.subtitle_region ? similarity(a, b, sample.subtitle_region) : null,
            final_average_luma: (() => {
              let sum = 0;
              for (let i = 0; i < a.data.length; i += 4) sum += (0.2126 * a.data[i] + 0.7152 * a.data[i + 1] + 0.0722 * a.data[i + 2]) / 255;
              return sum / (a.data.length / 4);
            })(),
          });
        } catch (error) {
          rows.push({ sample_id: sample.sample_id, time_ms: sample.time_ms, error: String(error?.message ?? error) });
        }
      }
    }
    return { final: finalMetadata, preview: previewMetadata, full_decode: fullDecode, samples: rows };
  }, {
    finalUrl: asDataUrl(finalBytes), previewUrl: asDataUrl(previewBytes), requestedSamples: samples,
    sourceWidth, sourceHeight,
  });
  process.stdout.write(JSON.stringify(result));
} finally {
  await browser.close();
}
