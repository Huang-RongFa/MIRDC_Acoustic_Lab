import {RecordingWaveformImages} from './RecordingWaveformImages';
import {peakEnvelope,type Peaks} from './recordingWaveforms';
import {SyncResults} from './SyncResults';
import {useEffect,useState} from 'react';
import {fields} from './fields';
import {recorderNumber,phaseNames,type Identity,type Recording,type Room} from './types';

function RecordingFile({recording:r,identity}:{recording:Recording;identity:Identity}){
  const [url,setUrl]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [wave,setWave]=useState<{peaks:Peaks[];duration:number}|null>(null);
  const [retry,setRetry]=useState(0);
  const {room_code:roomCode,token}=identity;
  const {participant_id:participantId,byte_size:size}=r;
  const takeId=r.session_id??identity.session_id;
  useEffect(()=>{
    if(!size)return;
    const controller=new AbortController(),{signal}=controller;
    let objectUrl='';
    setUrl('');setWave(null);setBusy(true);setError('');
    const load=async()=>{
      try{
        const response=await fetch(`/api/rooms/${roomCode}/recordings/${participantId}/audio?take_id=${takeId}`,{signal,headers:{Authorization:'Bearer '+token}});
        if(!response.ok)throw new Error('音檔尚未封存，請回錄音者頁面補傳');
        const blob=await response.blob();
        signal.throwIfAborted();
        objectUrl=URL.createObjectURL(blob);setUrl(objectUrl);
        try{
          const context=new AudioContext();
          const audio=await (async()=>{
            try{return await context.decodeAudioData(await blob.arrayBuffer());}
            finally{await context.close();}
          })();
          if(audio.numberOfChannels>2){
            if(!signal.aborted)setError('此音檔超過兩個聲道，仍可試聽或下載原始音檔。');
            return;
          }
          const peaks=[];
          for(let c=0;c<audio.numberOfChannels;c++){
            peaks.push(await peakEnvelope(audio.getChannelData(c),signal));
          }
          signal.throwIfAborted();
          setWave({peaks,duration:audio.duration});
          if(r.channel_count===2&&audio.numberOfChannels===1)setError('封存音檔只解碼出一個聲道，目前顯示 Mono 波形。');
        }catch{
          if(!signal.aborted)setError('此瀏覽器無法解碼波形；仍可試聽或下載原始音檔。');
        }
      }catch(e){if(!signal.aborted)setError((e as Error).message);}
      finally{if(!signal.aborted)setBusy(false);}
    };
    void load();
    return()=>{controller.abort();if(objectUrl)URL.revokeObjectURL(objectUrl);};
  },[participantId,roomCode,takeId,token,size,retry,r.channel_count]);
  const extension=r.mime_type?.includes('mp4')?'m4a':r.mime_type?.includes('ogg')?'ogg':'webm';
  return <article className="card result-file" aria-busy={busy}>
    <h3>錄音者 {recorderNumber(r.source_label)}</h3><p>{phaseNames[r.status]}{r.error?' · '+r.error:''}</p>
    <dl className="condition-details">
      <div><dt>原始格式</dt><dd>{r.mime_type||'尚未錄製'}</dd></div>
      <div><dt>音檔大小</dt><dd>{r.byte_size==null?'尚未封存':r.byte_size.toLocaleString()+' 位元組'}</dd></div>
      <div><dt>本機錄製時長（單調時鐘）</dt><dd>{r.duration_ms==null?'未知／中斷':(r.duration_ms/1000).toFixed(3)+' 秒'}</dd></div>
      <div><dt>取樣率／聲道（裝置回報）</dt><dd>{r.sample_rate??'未知'} Hz／{r.channel_count??'未知'}</dd></div>
      <div><dt>已收到／預期分段</dt><dd>{r.received_chunks??0}／{r.expected_chunks??'尚未宣告'}</dd></div>
      <div><dt>上傳檢查</dt><dd>{r.byte_size&&r.missing_chunks===0?'上傳完整':r.missing_chunks==null?'待完成宣告':`缺少 ${r.missing_chunks} 段，請補傳`}</dd></div>
    </dl>
    {busy&&<p role="status">正在載入音訊與波形…</p>}
    {!!size&&!busy&&!wave&&<button className="secondary-action" onClick={()=>setRetry(n=>n+1)}>重新載入音訊與波形</button>}
    {url&&<><audio controls preload="metadata" src={url} aria-label={`錄音者 ${recorderNumber(r.source_label)} 試聽`} onError={()=>setError('此瀏覽器無法播放原始格式，請下載後使用支援的播放器。')}/>
      {wave&&<p>音檔解碼時長：{wave.duration.toFixed(3)} 秒</p>}
      <a className="ghost-btn" href={url} download={`${takeId}_${recorderNumber(r.source_label)}.${extension}`}>下載原始音檔</a></>}
    {error&&<p role="status">{error}</p>}
    {wave&&<RecordingWaveformImages {...wave}/>}
  </article>;
}

export function RecordingResults({room,identity}:{room:Room;identity:Identity}){
  const durations=room.recordings.map(r=>r.duration_ms).filter((v):v is number=>v!=null);
  const date=(ms:number|null)=>ms==null?'—':new Date(ms).toLocaleString();
  return <section><div className="card"><h2>錄音測試結果</h2>
    <p>Room Code：{identity.room_code} · {phaseNames[room.status]}</p><p className="session-id">Session ID：{room.id}</p>
    <p>伺服器開始：{date(room.started_at)}<br/>伺服器結束：{date(room.stopped_at)}</p>
    <dl className="condition-details">{fields.map(([key,label])=><div key={key}><dt>{label}</dt><dd>{room.conditions[key]??'—'}</dd></div>)}</dl>
    <p>各聲源錄製時長差異：{durations.length===room.required_recorder_count?((Math.max(...durations)-Math.min(...durations))/1000).toFixed(3)+' 秒':'尚未取得全體錄音時長'}</p>
    <p className="sync-note">獨立手機時鐘，未完成精確對齊。上傳完整只表示分段齊全；仍需逐檔試聽確認收音。</p>
    {room.participants.filter(p=>p.error).map(p=><p role="status" key={p.id}>錄音者 {recorderNumber(p.source_label)}：{p.error}</p>)}
    </div><SyncResults key={room.id} room={room} identity={identity}/><div className="result-grid">{room.recordings.map(r=><RecordingFile key={room.id+r.participant_id} recording={r} identity={identity}/>)}</div></section>;
}
