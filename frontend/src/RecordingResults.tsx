import {useEffect,useRef,useState} from 'react';
import {fields} from './fields';
import {phaseNames,type Identity,type Recording,type Room} from './types';

function RecordingFile({recording:r,identity}:{recording:Recording;identity:Identity}){
  const [url,setUrl]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [wave,setWave]=useState<number[]>([]),[decodedDuration,setDecodedDuration]=useState<number|null>(null);
  const canvas=useRef<HTMLCanvasElement>(null);
  useEffect(()=>()=>{if(url)URL.revokeObjectURL(url);},[url]);
  useEffect(()=>{const c=canvas.current?.getContext('2d');if(!c)return;c.clearRect(0,0,600,80);c.strokeStyle='#107e76';c.beginPath();wave.forEach((v,i)=>{c.moveTo(i*600/wave.length,40-v*35);c.lineTo(i*600/wave.length,40+v*35);});c.stroke();},[wave]);
  const load=async()=>{
    setBusy(true);setError('');
    try{
      const response=await fetch(`/api/rooms/${identity.room_code}/recordings/${r.participant_id}/audio`,{headers:{Authorization:'Bearer '+identity.token}});
      if(!response.ok)throw new Error('音檔尚未封存，請回錄音者頁面補傳');
      const blob=await response.blob();setUrl(URL.createObjectURL(blob));
      // Playback stays available even if this browser cannot decode the format for a preview.
      if(blob.size>32*1024*1024){setError('大型音檔略過全檔波形解碼；仍可試聽或下載。');return;}
      const context=new AudioContext();
      try{
        const audio=await context.decodeAudioData(await blob.arrayBuffer());setDecodedDuration(audio.duration);
        const data=audio.getChannelData(0),step=Math.max(1,Math.ceil(data.length/300)),peaks=[];
        for(let i=0;i<data.length;i+=step){let peak=0;for(let j=i;j<Math.min(i+step,data.length);j++)peak=Math.max(peak,Math.abs(data[j]));peaks.push(peak);}
        setWave(peaks);
      }catch{setError('此瀏覽器無法解碼波形；請試聽或下載原始音檔至支援此格式的播放器。');}
      finally{await context.close();}
    }catch(e){setError((e as Error).message);}finally{setBusy(false);}
  };
  const extension=r.mime_type?.includes('mp4')?'m4a':r.mime_type?.includes('ogg')?'ogg':'webm';
  return <article className="card result-file" aria-busy={busy}>
    <h3>Recorder {r.source_label}</h3><p>{phaseNames[r.status]}{r.error?' · '+r.error:''}</p>
    <dl className="condition-details">
      <div><dt>原始格式</dt><dd>{r.mime_type||'尚未錄製'}</dd></div>
      <div><dt>音檔大小</dt><dd>{r.byte_size==null?'尚未封存':r.byte_size.toLocaleString()+' bytes'}</dd></div>
      <div><dt>本機錄製時長（單調時鐘）</dt><dd>{r.duration_ms==null?'未知／中斷':(r.duration_ms/1000).toFixed(3)+' 秒'}</dd></div>
      <div><dt>取樣率／聲道（裝置回報）</dt><dd>{r.sample_rate??'未知'} Hz／{r.channel_count??'未知'}</dd></div>
      <div><dt>已收到／預期分段</dt><dd>{r.received_chunks??0}／{r.expected_chunks??'尚未宣告'}</dd></div>
      <div><dt>上傳檢查</dt><dd>{r.byte_size&&r.missing_chunks===0?'上傳完整':r.missing_chunks==null?'待完成宣告':`缺少 ${r.missing_chunks} 段，請補傳`}</dd></div>
    </dl>
    <p className="session-id">Recording ID：{r.participant_recording_id??'—'}</p>
    {!url&&<button className="secondary-action" disabled={!r.byte_size||busy} onClick={()=>void load()}>{busy?'正在載入音訊…':'載入試聽與波形'}</button>}
    {url&&<><audio controls preload="metadata" src={url} aria-label={`Recorder ${r.source_label} 試聽`} onError={()=>setError('此瀏覽器無法播放原始格式，請下載後使用支援的播放器。')}/>
      {wave.length>0&&<canvas ref={canvas} className="wave-canvas" width={600} height={80} aria-label={`Recorder ${r.source_label} 原始音檔波形`}/>}
      {decodedDuration!==null&&<p>音檔解碼時長：{decodedDuration.toFixed(3)} 秒</p>}
      <a className="ghost-btn" href={url} download={`${identity.session_id}_${r.source_label}.${extension}`}>下載原始音檔</a></>}
    {error&&<p role="status">{error}</p>}
  </article>;
}

export function RecordingResults({room,identity}:{room:Room;identity:Identity}){
  const durations=room.recordings.map(r=>r.duration_ms).filter((v):v is number=>v!=null);
  const date=(ms:number|null)=>ms==null?'—':new Date(ms).toLocaleString();
  return <section><div className="card"><h2>錄音測試結果</h2>
    <p>Room Code：{identity.room_code} · {phaseNames[room.status]}</p><p className="session-id">Session ID：{room.id}</p>
    <p>伺服器開始：{date(room.started_at)}<br/>伺服器結束：{date(room.stopped_at)}</p>
    <dl className="condition-details">{fields.map(([key,label])=><div key={key}><dt>{label}</dt><dd>{room.conditions[key]??'—'}</dd></div>)}</dl>
    <p>三份錄製時長差異：{durations.length===3?((Math.max(...durations)-Math.min(...durations))/1000).toFixed(3)+' 秒':'尚未取得三份可靠時長'}</p>
    <p className="sync-note">獨立手機時鐘，未完成精確對齊。上傳完整只表示分段齊全；仍需逐檔試聽確認收音。</p>
    {room.participants.filter(p=>p.error).map(p=><p role="status" key={p.id}>Recorder {p.source_label}：{p.error}</p>)}
    </div><div className="result-grid">{room.recordings.map(r=><RecordingFile key={r.participant_id} recording={r} identity={identity}/>)}</div></section>;
}
