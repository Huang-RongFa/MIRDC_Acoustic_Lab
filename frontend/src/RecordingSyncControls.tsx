import {useState} from 'react';
import {recordingSyncOptions,type RecordingSyncOptions} from './recordingSyncOptions';
import type {RecorderDevice} from './capture';
import type {Identity,CaptureSettings} from './types';

export function RecordingSyncControls({locked,device}:{identity:Identity;locked:boolean;device:RecorderDevice|null;status?:CaptureSettings|null}){
  const [options,setOptions]=useState(recordingSyncOptions),[message,setMessage]=useState(''),[busy,setBusy]=useState(false);
  const save=async(next:RecordingSyncOptions)=>{setOptions(next);setBusy(true);try{if(!device)throw new Error('尚未連線');await device.configure(next);setMessage('已套用；同步精度仍未驗證。');}catch(e){setMessage((e as Error).message);}finally{setBusy(false);}};
  return <div aria-label="本機收音設定">
    <label className="single-field">要求取樣率<select value={options.requestedSampleRate} disabled={locked||busy} onChange={e=>void save({...options,requestedSampleRate:Number(e.target.value) as 44100|48000})}><option value={44100}>44100 Hz</option><option value={48000}>48000 Hz</option></select></label>
    <label className="single-field">收音來源<select value={options.channelCount??1} disabled={locked||busy} onChange={e=>void save({...options,channelCount:Number(e.target.value) as 1|2})}><option value={1}>Mono（1 Channel）</option><option value={2}>Stereo（2 Channels）</option></select></label>
    {message&&<p role="status">{message}</p>}
  </div>;
}
