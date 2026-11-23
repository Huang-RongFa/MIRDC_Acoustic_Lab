import {test,expect} from '@playwright/test';
import {referenceSignal} from '../src/syncReference';
import {detectMarkers,fitAlignment,analyzeSync,alignedWav,type SyncInput} from '../src/syncAnalysis';

const rate=48000,times=[1,1.23,1.61,8,8.23,8.61,14,14.23,14.61];
function recording(id:string,offset=0,scale=1,shiftMiddle=0):SyncInput{
  const data=new Float32Array(rate*18),signal=referenceSignal(rate);
  for(let i=0;i<data.length;i++)data[i]=0.001*Math.sin(i*0.719);
  for(let index=0;index<times.length;index++){
    const start=(offset+scale*times[index]+(index>=3&&index<=5?shiftMiddle:0))*rate;
    for(let i=Math.ceil(start);i<start+signal.length*scale;i++){
      const p=(i-start)/scale,j=Math.floor(p),f=p-j;
      data[i]+=0.5*((signal[j]??0)*(1-f)+(signal[j+1]??0)*f);
    }
  }
  return {id,audio:{getChannelData:()=>data,sampleRate:rate,numberOfChannels:1,length:data.length,duration:18} as unknown as AudioBuffer,captureServerMs:1000000,clockUncertaintyMs:3,interrupted:false};
}
test('measures offset and drift with held-out markers and exports equal WAV windows',async()=>{
  const a=recording('A'),b=recording('B',0.12,1.0003);
  const report=analyzeSync([a,b],1003000,1016000);
  expect(report.status).toBe('reference_pass');
  expect(report.absoluteAccuracy).toBe('unverified');
  expect(report.tracks[1].offsetMs).toBeCloseTo(120,0);
  expect(Math.abs(report.tracks[1].driftPpm-300)).toBeLessThan(15);
  expect(report.tracks[1].residualMs).toBeLessThan(0.3);
  const wa=await alignedWav(a,a,report).arrayBuffer(),wb=await alignedWav(b,a,report).arrayBuffer();
  expect(wa.byteLength).toBe(44+13*rate*2);expect(wb.byteLength).toBe(wa.byteLength);
  expect(new DataView(wa).getUint32(24,true)).toBe(rate);
  const samples=(bytes:ArrayBuffer)=>Float32Array.from(new Int16Array(bytes,44),n=>n/32768);
  const ma=detectMarkers(samples(wa),rate),mb=detectMarkers(samples(wb),rate);
  expect(ma.length).toBe(6);expect(mb.length).toBe(6);
  expect(Math.max(...ma.map((m,i)=>Math.abs(m.seconds-mb[i].seconds)))).toBeLessThan(0.001);
});
test('rejects silence and ordinary tone as a sync reference',()=>{
  expect(detectMarkers(new Float32Array(rate*2),rate)).toEqual([]);
  const tone=Float32Array.from({length:rate*2},(_,i)=>Math.sin(2*Math.PI*1500*i/rate));
  expect(detectMarkers(tone,rate)).toEqual([]);
  expect(()=>fitAlignment('B',[],[])).toThrow('參考音缺失');
});
test('held-out middle references expose nonlinear timing error',()=>{
  const report=analyzeSync([recording('A'),recording('B',0.12,1,0.008)],1003000,1016000);
  expect(report.status).toBe('failed');expect(report.tracks[1].residualMs).toBeGreaterThan(7);
});
test('refuses missing coverage, clock metadata, interrupted or single-device verification',()=>{
  const a=recording('A'),b=recording('B');
  expect(()=>analyzeSync([a,b],999000,1016000)).toThrow('缺少倒數期間');
  expect(()=>analyzeSync([a,{...b,captureServerMs:NaN}],1003000,1016000)).toThrow('校時');
  expect(()=>analyzeSync([a],1003000,1016000)).toThrow('兩位');
  expect(analyzeSync([a,{...b,interrupted:true}],1003000,1016000).status).toBe('failed');
});
