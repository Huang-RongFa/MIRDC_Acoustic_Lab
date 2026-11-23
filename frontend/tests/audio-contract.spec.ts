// 只需 Vite dev server（npm run dev），不需後端。Chrome 假麥克風＋OfflineAudioContext。
// 驗證：(1) 網頁的收音限制條件在 Chrome 確實生效、預設則是開啟；(2) 同步嗶聲經 Web Audio 輸出後與規格一致。
// 執行：npm run dev（另一終端）→ npx playwright test tests/audio-contract.spec.ts
import {test,expect} from '@playwright/test';

// 以變數路徑動態匯入 Vite 提供的原始模組，避免 tsc 解析瀏覽器端路徑
const SETTINGS='/src/audioSettings.ts',CHIRP='/src/syncChirp.ts';

test('Chrome 套用關閉回音消除／降噪／自動增益，並如實回報',async({page})=>{
  await page.goto('/');
  const result=await page.evaluate(async(path)=>{
    const m=await import(path);
    const ask=async(audio:MediaTrackConstraints|boolean)=>{const s=await navigator.mediaDevices.getUserMedia({audio});const r=m.summarizeProcessing(s.getAudioTracks()[0].getSettings());s.getTracks().forEach(t=>t.stop());return r;};
    return {requested:await ask({echoCancellation:false,noiseSuppression:false,autoGainControl:false}),browserDefault:await ask(true)};
  },SETTINGS);
  expect(result.requested.raw).toBe(true);
  expect(result.requested.echoCancellation).toBe(false);
  // 對照：不指定時 Chrome 預設開啟處理——說明「必須明確關閉並記錄 getSettings」的理由
  expect(result.browserDefault.raw).toBe(false);
});

test('同步嗶聲經 OfflineAudioContext 輸出與 chirpSamples 一致',async({page})=>{
  await page.goto('/');
  const out=await page.evaluate(async(path)=>{
    const c=await import(path);
    const sr=48000,ctx=new OfflineAudioContext(1,sr*3,sr);
    const ref:Float32Array=c.chirpSamples(sr),buffer=ctx.createBuffer(1,ref.length,sr);buffer.getChannelData(0).set(ref);
    const src=ctx.createBufferSource();src.buffer=buffer;src.connect(ctx.destination);src.start(1.0);
    const rendered=(await ctx.startRendering()).getChannelData(0);
    let maxErr=0;for(let i=0;i<ref.length;i++)maxErr=Math.max(maxErr,Math.abs(rendered[sr+i]-ref[i]));
    let before=0;for(let i=0;i<sr;i++)before=Math.max(before,Math.abs(rendered[i]));
    const live=new AudioContext();const at:number=c.playSyncChirp(live);await live.close();   // 真實 AudioContext 只排程、不報錯
    return {maxErr,before,at,len:ref.length};
  },CHIRP);
  expect(out.len).toBe(24000);
  expect(out.maxErr).toBeLessThan(1e-6);
  expect(out.before).toBe(0);
  expect(out.at).toBeGreaterThan(0);
});
