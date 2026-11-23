import {REFERENCE_VERSION} from './syncReference';

export type Marker={seconds:number;score:number};
export type SyncInput={id:string;audio:AudioBuffer;captureServerMs:number;clockUncertaintyMs:number;interrupted:boolean};
export type Alignment={id:string;offsetMs:number;driftPpm:number;residualMs:number;markers:Marker[];scale:number;intercept:number};
export type SyncReport={version:string;status:'reference_pass'|'failed';reason:string;thresholdMs:number;sampleRate:number;startServerMs:number;stopServerMs:number;referenceId:string;clockEstimateMs:number;absoluteAccuracy:'unverified';frames:number;tracks:Alignment[]};

// Quadrature matched filter: tolerate speaker phase response, but require the
// entire swept-frequency signature, not just a loud impulse or a tonal peak.
export function detectMarkers(data:Float32Array,rate:number):Marker[]{
  const stride=Math.max(1,Math.floor(rate/12000)),sr=rate/stride;
  const x=Float32Array.from({length:Math.floor(data.length/stride)},(_,i)=>data[i*stride]);
  const n=Math.round(sr*0.06),sin=new Float32Array(n),cos=new Float32Array(n);
  let templateEnergy=0;
  for(let j=0;j<n;j++){
    const t=j/sr,w=Math.sin(Math.PI*j/(n-1))**2,p=2*Math.PI*(900*t+3100*t*t/(2*0.06));
    sin[j]=Math.sin(p)*w;cos[j]=Math.cos(p)*w;templateEnergy+=sin[j]**2;
  }
  const energy=new Float64Array(x.length+1);
  for(let i=0;i<x.length;i++)energy[i+1]=energy[i]+x[i]**2;
  const score=(i:number)=>{
    const e=energy[i+n]-energy[i];if(e<1e-8)return 0;
    let a=0,b=0;for(let j=0;j<n;j++){a+=x[i+j]*sin[j];b+=x[i+j]*cos[j];}
    return Math.min(1,Math.hypot(a,b)/Math.sqrt(e*templateEnergy));
  };
  const candidates:Marker[]=[],hop=Math.max(1,Math.round(sr*0.00025));
  for(let i=0;i+n<x.length;i+=hop){
    if(score(i)<0.65)continue;
    let best=i,value=0;
    for(let k=Math.max(0,i-hop);k<Math.min(x.length-n,i+hop*2);k++){const v=score(k);if(v>value){value=v;best=k;}}
    candidates.push({seconds:best/sr,score:value});i=best+Math.round(sr*0.1);
  }
  const markers:Marker[]=[];
  for(let i=0;i+2<candidates.length;i++){
    const [a,b,c]=candidates.slice(i,i+3);
    if(Math.abs(b.seconds-a.seconds-0.23)<0.004&&Math.abs(c.seconds-a.seconds-0.61)<0.004){markers.push(a,b,c);i+=2;}
  }
  return markers;
}

export function fitAlignment(id:string,reference:Marker[],markers:Marker[]):Alignment{
  if(markers.length!==reference.length||markers.length<6)throw new Error('參考音缺失或數量不同；至少需要首尾兩組參考音');
  const last=markers.length-1,span=reference[last].seconds-reference[0].seconds;
  if(span<5)throw new Error('參考音間隔不足 5 秒，無法估測漂移');
  const scale=(markers[last].seconds-markers[0].seconds)/span;
  const intercept=markers[0].seconds-scale*reference[0].seconds;
  // Only endpoints fit the model. All remaining points are held out.
  const residualMs=Math.max(...markers.slice(1,-1).map((m,i)=>Math.abs((m.seconds-intercept)/scale-reference[i+1].seconds)*1000));
  if(!Number.isFinite(scale)||Math.abs(scale-1)>0.002)throw new Error('取樣漂移超過 2000 ppm 或參考音配對錯誤');
  return {id,offsetMs:intercept*1000,driftPpm:(scale-1)*1e6,residualMs,markers,scale,intercept};
}

export function analyzeSync(inputs:SyncInput[],startServerMs:number,stopServerMs:number):SyncReport{
  if(inputs.length<2)throw new Error('至少需要兩位錄音者才能驗證相對同步');
  if(!Number.isFinite(startServerMs)||!Number.isFinite(stopServerMs)||stopServerMs<=startServerMs)throw new Error('缺少有效的共同錄音起訖時間');
  if(inputs.some(t=>!Number.isFinite(t.captureServerMs)||!Number.isFinite(t.clockUncertaintyMs)||t.clockUncertaintyMs<0))throw new Error('缺少有效校時資訊');
  const first=inputs[0],rate=48000,start=(startServerMs-first.captureServerMs)/1000,end=(stopServerMs-first.captureServerMs)/1000;
  const markers=inputs.map(t=>detectMarkers(t.audio.getChannelData(0),t.audio.sampleRate));
  const tracks=inputs.map((t,i)=>fitAlignment(t.id,markers[0],markers[i]));
  if(markers[0][0].seconds>=start||markers[0].at(-1)!.seconds<end-2)throw new Error('缺少倒數期間或停止前的參考音，無法驗證共同音段');
  if(markers[0].some((m,i)=>i>0&&m.seconds-markers[0][i-1].seconds>12))throw new Error('中段參考音間隔超過 12 秒，無法驗證整段漂移');
  const frames=Math.round((end-start)*rate);
  if(frames<=0||frames>rate*180)throw new Error('瀏覽器同步驗證目前支援 180 秒以內的錄音');
  for(let i=0;i<inputs.length;i++){
    const t=tracks[i],audio=inputs[i].audio;
    if(t.intercept+t.scale*start<0||t.intercept+t.scale*(start+(frames-1)/rate)>(audio.length-1)/audio.sampleRate)throw new Error('至少一個聲源未涵蓋共同時間範圍；不補零或冒充完整音段');
  }
  const interrupted=inputs.some(t=>t.interrupted),pass=!interrupted&&tracks.every(t=>t.residualMs<=1);
  return {version:REFERENCE_VERSION,status:pass?'reference_pass':'failed',reason:interrupted?'錄音曾中斷':pass?'獨立參考點殘差不超過 1 ms；只驗證參考音相對對齊，不代表絕對零誤差':'獨立參考點殘差超過 1 ms',thresholdMs:1,sampleRate:rate,startServerMs,stopServerMs,referenceId:first.id,clockEstimateMs:Math.max(...inputs.map(t=>t.clockUncertaintyMs)),absoluteAccuracy:'unverified',frames,tracks};
}

// Derived PCM WAV, preserving every channel. Raw uploads are never rewritten.
export function alignedWav(input:SyncInput,reference:SyncInput,report:SyncReport):Blob{
  const fit=report.tracks.find(t=>t.id===input.id)!;
  const channels=input.audio.numberOfChannels,frames=report.frames,rate=report.sampleRate;
  const bytes=new ArrayBuffer(44+frames*channels*2),view=new DataView(bytes);
  const text=(offset:number,s:string)=>{for(let i=0;i<s.length;i++)view.setUint8(offset+i,s.charCodeAt(i));};
  text(0,'RIFF');view.setUint32(4,bytes.byteLength-8,true);text(8,'WAVE');text(12,'fmt ');view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,channels,true);view.setUint32(24,rate,true);view.setUint32(28,rate*channels*2,true);view.setUint16(32,channels*2,true);view.setUint16(34,16,true);text(36,'data');view.setUint32(40,bytes.byteLength-44,true);
  const start=(report.startServerMs-reference.captureServerMs)/1000;
  for(let c=0;c<channels;c++){
    const data=input.audio.getChannelData(c);
    for(let i=0;i<frames;i++){
      const p=(fit.intercept+fit.scale*(start+i/rate))*input.audio.sampleRate,j=Math.floor(p),f=p-j;
      const value=Math.max(-1,Math.min(1,data[j]*(1-f)+data[Math.min(j+1,data.length-1)]*f));
      view.setInt16(44+(i*channels+c)*2,Math.round(value*(value<0?32768:32767)),true);
    }
  }
  return new Blob([bytes],{type:'audio/wav'});
}
