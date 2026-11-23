import {useEffect,useMemo,useState} from 'react';
import {WavePlot} from './WavePlot';
import type {Identity,Room} from './types';

export function channelWav(audio:AudioBuffer,channel:number){
  const data=audio.getChannelData(channel),bytes=new ArrayBuffer(44+data.length*4),v=new DataView(bytes);
  const text=(o:number,s:string)=>{for(let i=0;i<s.length;i++)v.setUint8(o+i,s.charCodeAt(i));};
  text(0,'RIFF');v.setUint32(4,36+data.length*4,true);text(8,'WAVE');text(12,'fmt ');v.setUint32(16,16,true);v.setUint16(20,3,true);v.setUint16(22,1,true);v.setUint32(24,audio.sampleRate,true);v.setUint32(28,audio.sampleRate*4,true);v.setUint16(32,4,true);v.setUint16(34,32,true);text(36,'data');v.setUint32(40,data.length*4,true);data.forEach((s,i)=>v.setFloat32(44+i*4,s,true));
  return new Blob([bytes],{type:'audio/wav'});
}
export function channelFeatures(data:Float32Array,rate:number,start:number){
  const window=data.subarray(Math.round(start*rate),Math.round(start*rate)+1024),n=window.length;
  let energy=0,peak=0,best=0,bin=0;
  for(const x of window){energy+=x*x;peak=Math.max(peak,Math.abs(x));}
  // A bounded, windowed spectrum of the selected channel only; no channel fusion.
  for(let k=1;k<=Math.floor(n/2);k++){let re=0,im=0;for(let i=0;i<n;i++){const x=window[i]*(0.5-0.5*Math.cos(2*Math.PI*i/Math.max(1,n-1))),phase=2*Math.PI*k*i/n;re+=x*Math.cos(phase);im-=x*Math.sin(phase);}const power=re*re+im*im;if(power>best){best=power;bin=k;}}
  return {rms:Math.sqrt(energy/Math.max(1,n)),peak,frequency:n&&energy>1e-12?bin*rate/n:0,windowSeconds:n/rate};
}
export function ChannelInspector({audio,label}:{audio:AudioBuffer;label:string}){
  const [channel,setChannel]=useState(0),[start,setStart]=useState(0),[url,setUrl]=useState('');
  useEffect(()=>{setChannel(0);setStart(0);},[audio]);
  const selected=Math.min(channel,audio.numberOfChannels-1);
  useEffect(()=>{const value=URL.createObjectURL(channelWav(audio,selected));setUrl(value);return()=>URL.revokeObjectURL(value);},[audio,selected]);
  const wave=useMemo(()=>{const data=audio.getChannelData(selected),stride=Math.max(1,Math.ceil(data.length/300)),values=[];for(let i=0;i<data.length;i+=stride){let peak=0;for(let j=i;j<Math.min(i+stride,data.length);j++)peak=Math.max(peak,Math.abs(data[j]));values.push(peak);}return values;},[audio,selected]);
  const features=useMemo(()=>channelFeatures(audio.getChannelData(selected),audio.sampleRate,start),[audio,selected,start]);
  return <section aria-label={label+' 聲道檢視'}>
    <label>聲道選擇<select value={selected} onChange={e=>setChannel(Number(e.target.value))}>{Array.from({length:audio.numberOfChannels},(_,i)=><option value={i} key={i}>{audio.numberOfChannels===1?'Mono':i===0?'L（Left）':i===1?'R（Right）':'Channel '+(i+1)}</option>)}</select></label>
    <p>解碼實際聲道數：{audio.numberOfChannels} · 解碼分析取樣率：{audio.sampleRate} Hz</p>
    <audio controls src={url} aria-label={label+' 所選聲道試聽'}/>
    <WavePlot label={label+' 所選聲道波形'} samples={wave} duration={audio.duration} envelope/>
    <label>分析起點（秒）<input type="number" min={0} max={Math.max(0,audio.duration-1024/audio.sampleRate)} step="0.01" value={start} onChange={e=>setStart(Math.max(0,Math.min(Number(e.target.value)||0,Math.max(0,audio.duration-1024/audio.sampleRate))))}/></label>
    <p>所選聲道：RMS {features.rms.toFixed(2)} · Peak {features.peak.toFixed(2)} · 主頻 {features.frequency.toFixed(2)} Hz · 分析窗 {features.windowSeconds.toFixed(2)} 秒</p>
    <p>此為所選音軌的獨立瀏覽器分析，未校正同步，不覆寫原有分析結果。</p>
  </section>;
}

export function RecordingChannelAnalysis({room,identity}:{room:Room;identity:Identity}){
  const [track,setTrack]=useState(room.recordings[0]?.participant_id??''),[audio,setAudio]=useState<AudioBuffer|null>(null),[message,setMessage]=useState(''),[busy,setBusy]=useState(false);
  const load=async()=>{setBusy(true);setAudio(null);setMessage('');const context=new AudioContext();try{const response=await fetch(`/api/rooms/${identity.room_code}/recordings/${track}/audio?take_id=${room.id}`,{headers:{Authorization:'Bearer '+identity.token}});if(!response.ok)throw new Error('音檔尚未封存或無存取權限');const bytes=await response.arrayBuffer();if(bytes.byteLength>32*1024*1024)throw new Error('超過瀏覽器分析大小限制，請下載原始音檔');setAudio(await context.decodeAudioData(bytes));}catch(e){setMessage((e as Error).message);}finally{await context.close();setBusy(false);}};
  return <section className="card"><h2>獨立音軌／聲道分析</h2><label>錄音裝置<select value={track} disabled={busy} onChange={e=>{setTrack(e.target.value);setAudio(null);}}>{room.recordings.map(r=><option key={r.participant_id} value={r.participant_id}>{r.source_label} · {r.channel_count??'未知'} ch</option>)}</select></label><button className="secondary-action" disabled={busy||!track} onClick={()=>void load()}>載入聲道分析</button>{message&&<p role="status">{message}</p>}{audio&&<ChannelInspector audio={audio} label={'音軌 '+track}/>}</section>;
}
