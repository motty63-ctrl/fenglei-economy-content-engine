import fs from 'node:fs';
import { pathToFileURL } from 'node:url';

const [puppeteerPath, browserPath, outputDirectory] = process.argv.slice(2);
const { default: puppeteer } = await import(pathToFileURL(puppeteerPath + '/lib/puppeteer/puppeteer-core.js').href);
const browser = await puppeteer.launch({
  executablePath: browserPath,
  headless: true,
  args: ['--no-sandbox', '--autoplay-policy=no-user-gesture-required'],
});
try {
  for (const scenario of [
    { name: 'matching', width: 320, height: 240, audio: true, captions: true, reverse: false },
    { name: 'divergent', width: 320, height: 240, audio: true, captions: true, reverse: true },
    { name: 'no-captions', width: 320, height: 240, audio: true, captions: false, reverse: false },
    { name: 'no-audio', width: 320, height: 240, audio: false, captions: true, reverse: false },
    { name: 'wrong-size', width: 160, height: 120, audio: true, captions: true, reverse: false },
  ]) {
    let written = false;
    for (let attempt = 0; attempt < 4 && !written; attempt++) {
      const page = await browser.newPage({ viewport: { width: 320, height: 240 } });
      try {
        const result = await page.evaluate(async ({ width, height, audio, captions, reverse }) => {
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const context = canvas.getContext('2d');
        const stream = canvas.captureStream(30);
        const videoTrack = stream.getVideoTracks()[0];
        const tracks = [videoTrack];
        let audioElement = null;
        if (audio) {
          const sampleRate = 48000;
          const sampleCount = sampleRate * 2;
          const wav = new ArrayBuffer(44 + sampleCount * 2);
          const view = new DataView(wav);
          const writeText = (offset, text) => [...text].forEach((character, index) => view.setUint8(offset + index, character.charCodeAt(0)));
          writeText(0, 'RIFF'); view.setUint32(4, wav.byteLength - 8, true); writeText(8, 'WAVE');
          writeText(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
          view.setUint16(22, 1, true); view.setUint32(24, sampleRate, true);
          view.setUint32(28, sampleRate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
          writeText(36, 'data'); view.setUint32(40, sampleCount * 2, true);
          for (let index = 0; index < sampleCount; index++) {
            view.setInt16(44 + index * 2, Math.round(Math.sin(index / sampleRate * Math.PI * 880) * 1200), true);
          }
          audioElement = document.createElement('audio');
          audioElement.preload = 'auto';
          audioElement.src = URL.createObjectURL(new Blob([wav], { type: 'audio/wav' }));
          await new Promise((resolve, reject) => {
            audioElement.onloadeddata = resolve;
            audioElement.onerror = () => reject(new Error('SYNTHETIC_WAV_LOAD_FAILED'));
          });
          audioElement.volume = 0.1;
          tracks.push(...audioElement.captureStream().getAudioTracks());
        }
        const mimeType = 'video/mp4;codecs="avc1.42E01E,mp4a.40.2"';
        if (!MediaRecorder.isTypeSupported(mimeType)) throw new Error('SYNTHETIC_MP4_MIME_UNSUPPORTED');
        const recorder = new MediaRecorder(new MediaStream(tracks), {
          mimeType, videoBitsPerSecond: 500000, audioBitsPerSecond: 64000,
        });
        const chunks = [];
        let recorderError = null;
        recorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
        recorder.onerror = event => { recorderError = event.error?.message ?? 'MEDIA_RECORDER_ERROR'; };
        recorder.start(100);
        const started = performance.now();
        const draw = () => {
          const firstHalf = performance.now() - started < 500;
          const index = firstHalf !== reverse ? 0 : 1;
          const palette = ['#173f5f', '#ed553b'];
          context.fillStyle = palette[index];
          context.fillRect(0, 0, width, height);
          context.fillStyle = '#ffffff';
          context.textAlign = 'center';
          context.font = `bold ${Math.max(14, Math.round(width * 0.075))}px sans-serif`;
          context.fillText(index === 0 ? 'SCENE ALPHA' : 'SCENE BETA', width / 2, height / 2);
          if (captions) {
            context.fillStyle = '#ffffff';
            context.fillRect(width * 0.08, height * 0.84, width * 0.84, height * 0.09);
            context.fillStyle = '#17202a';
            context.font = `bold ${Math.max(12, Math.round(width * 0.045))}px sans-serif`;
            context.fillText(firstHalf ? 'Caption Alpha' : 'Caption Beta', width / 2, height * 0.9);
          }
          if (performance.now() - started < 2050) requestAnimationFrame(draw);
        };
        draw();
        const mediaFinished = audio
          ? new Promise(resolve => { audioElement.onended = resolve; })
          : new Promise(resolve => setTimeout(resolve, 2100));
        const play = audio ? audioElement.play() : Promise.resolve();
        await play;
        await mediaFinished;
        await new Promise(resolve => {
          recorder.onstop = resolve;
          recorder.stop();
        });
        if (recorderError) throw new Error(recorderError);
        const blob = new Blob(chunks, { type: recorder.mimeType });
        const bytes = new Uint8Array(await blob.arrayBuffer());
        if (bytes.length === 0) throw new Error(`SYNTHETIC_MEDIA_EMPTY_${width}x${height}_audio_${audio}`);
        let binary = '';
        for (let offset = 0; offset < bytes.length; offset += 0x8000) {
          binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
        }
        return btoa(binary);
        }, scenario);
        const playback = await page.evaluate(async base64 => new Promise(resolve => {
          const video = document.createElement('video');
          video.preload = 'auto';
          video.onloadeddata = () => {
            let audioTrackCount = 0;
            try { audioTrackCount = video.captureStream().getAudioTracks().length; } catch {}
            resolve({ width: video.videoWidth, height: video.videoHeight, duration: video.duration, audioTrackCount });
          };
          video.onerror = () => resolve({ error: `MEDIA_ERROR_${video.error?.code ?? 'UNKNOWN'}` });
          video.src = `data:video/mp4;base64,${base64}`;
          video.load();
          setTimeout(() => resolve({ error: 'MEDIA_METADATA_TIMEOUT' }), 10000);
        }), result);
        if (playback.width === scenario.width && playback.height === scenario.height
            && Number.isFinite(playback.duration)
            && (scenario.audio ? playback.audioTrackCount > 0 : playback.audioTrackCount === 0)) {
          fs.writeFileSync(`${outputDirectory}/${scenario.name}.mp4`, Buffer.from(result, 'base64'));
          written = true;
        }
      } catch {
        written = false;
      } finally {
        await page.close();
      }
    }
    if (!written) throw new Error(`SYNTHETIC_MEDIA_GENERATION_FAILED_${scenario.name}`);
  }
  fs.writeFileSync(`${outputDirectory}/corrupt.mp4`, Buffer.concat([
    Buffer.from([0, 0, 0, 24]), Buffer.from('ftyp'), Buffer.from('isom'),
  ]));
} finally {
  await browser.close();
}
