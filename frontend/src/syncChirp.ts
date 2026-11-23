// 三手機同步嗶聲。參數必須與 analysis/sync_chirp.py 的 CHIRP_* 常數一致；
// 改一邊就改另一邊，並重跑 tests-unit/syncChirp.test.ts 與 analysis/tests/test_synthetic.py。
export const CHIRP_F0_HZ=1500;
export const CHIRP_F1_HZ=7500;
export const CHIRP_DURATION_S=0.5;
export const CHIRP_FADE_S=0.010;
export const CHIRP_AMPLITUDE=0.8;

/** 線性掃頻 F0→F1，頭尾餘弦漸變；與 Python chirp_template(sr) 逐點相同（浮點誤差內）。 */
export function chirpSamples(sampleRate:number):Float32Array{
  const n=Math.round(sampleRate*CHIRP_DURATION_S),out=new Float32Array(n);
  const k=(CHIRP_F1_HZ-CHIRP_F0_HZ)/CHIRP_DURATION_S,fade=Math.round(sampleRate*CHIRP_FADE_S);
  for(let i=0;i<n;i++){
    const t=i/sampleRate;
    let v=CHIRP_AMPLITUDE*Math.sin(2*Math.PI*(CHIRP_F0_HZ*t+0.5*k*t*t));
    if(i<fade)v*=0.5-0.5*Math.cos(Math.PI*i/fade);
    else if(i>=n-fade)v*=0.5-0.5*Math.cos(Math.PI*(n-1-i)/fade);
    out[i]=v;
  }
  return out;
}

/** 在既有 AudioContext 播放一次嗶聲，回傳排定的開始時間（AudioContext 秒）。 */
export function playSyncChirp(context:BaseAudioContext):number{
  const data=chirpSamples(context.sampleRate);
  const buffer=context.createBuffer(1,data.length,context.sampleRate);
  buffer.getChannelData(0).set(data);
  const source=context.createBufferSource();
  source.buffer=buffer;source.connect(context.destination);
  const at=context.currentTime+0.05;
  source.start(at);
  return at;
}
