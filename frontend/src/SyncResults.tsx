import {useEffect,useState} from 'react';
import {alignedWav,analyzeSync,type SyncInput,type SyncReport} from './syncAnalysis';
import {recorderNumber,type Identity,type Room} from './types';

export function SyncResults({room,identity}:{room:Room;identity:Identity}){
  const [busy,setBusy]=useState(false),[message,setMessage]=useState('尚未驗證');
  const [report,setReport]=useState<SyncReport|null>(null);
  const [downloads,setDownloads]=useState<{name:string;url:string}[]>([]);
  useEffect(()=>()=>downloads.forEach(d=>URL.revokeObjectURL(d.url)),[downloads]);
  const verify=async()=>{
    setBusy(true);setMessage('正在下載原始音訊、偵測參考音與驗證…');setReport(null);setDownloads([]);
    const context=new AudioContext({sampleRate:48000});
    try{
      const inputs:SyncInput[]=[],evidence:{id:string;sha256:string}[]=[];
      let decodedBytes=0;
      for(const r of room.recordings){
        if(r.capture_server_ms==null||r.clock_uncertainty_ms==null)throw new Error('缺少開始前後 30 秒內的有效校時資料；請重新錄製');
        if(!r.byte_size||r.byte_size>32*1024*1024)throw new Error('缺少封存音檔或單檔超過 32 MiB；請使用較短錄音驗證');
        const response=await fetch(`/api/rooms/${identity.room_code}/recordings/${r.participant_id}/audio?take_id=${room.id}`,{headers:{Authorization:'Bearer '+identity.token}});
        if(!response.ok)throw new Error('音訊下載失敗，請確認上傳完整後重試');
        const bytes=await response.arrayBuffer();
        const sha256=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),v=>v.toString(16).padStart(2,'0')).join('');
        const expected=response.headers.get('X-Checksum');
        if(!expected||sha256!==expected)throw new Error('原始音檔校驗失敗，請重新下載');
        const audio=await context.decodeAudioData(bytes);
        decodedBytes+=audio.length*audio.numberOfChannels*4;
        if(audio.duration>190||decodedBytes>256*1024*1024)throw new Error('此瀏覽器驗證支援 180 秒錄音及最多 256 MiB 解碼資料；請縮短錄音');
        inputs.push({id:r.source_label,audio,captureServerMs:r.capture_server_ms,clockUncertaintyMs:r.clock_uncertainty_ms,interrupted:r.interrupted});
        evidence.push({id:r.source_label,sha256});
      }
      if(room.starts_at==null||room.stopped_at==null)throw new Error('此批次沒有完整的共同起訖時間');
      const result=analyzeSync(inputs,room.starts_at,room.stopped_at);
      const files:{name:string;blob:Blob}[]=[];
      if(result.status==='reference_pass')for(const input of inputs)files.push({name:`${room.id}_${input.id}_aligned.wav`,blob:alignedWav(input,inputs[0],result)});
      files.push({name:`${room.id}_sync-report.json`,blob:new Blob([JSON.stringify({...result,takeId:room.id,generatedAt:new Date().toISOString(),sources:evidence,limitations:['Relative acoustic-reference alignment only; propagation delay is not removed.','Clock RTT is an estimate, not an absolute timing bound.','PCM WAV uses linear interpolation for drift correction; original audio is preserved.','Residuals apply to detected reference points, not a guarantee between points.']},null,2)],{type:'application/json'})});
      setDownloads(files.map(f=>({name:f.name,url:URL.createObjectURL(f.blob)})));setReport(result);setMessage(result.reason);
    }catch(e){setMessage('無法驗證：'+(e as Error).message);}finally{await context.close();setBusy(false);}
  };
  return <section className="card" aria-busy={busy}>
    <h2>同步裁切與驗證</h2>
    <p>倒數結束為共同零點，主控停止為共同終點。以第一位錄音者為參考，利用首尾參考點校正偏移與漂移，其餘參考點獨立檢查 1 ms 門檻。</p>
    <p>這是聲學參考音的相對對齊，包含喇叭到麥克風的傳播時間；絕對收音精度仍未驗證。校正檔不可用來判斷原始聲源到達時間差。</p>
    <button className="secondary-action" disabled={busy||!['completed','interrupted'].includes(room.status)||room.recordings.some(r=>!r.byte_size)} onClick={()=>void verify()}>{busy?'正在驗證…':'驗證同步並產生共同時間 WAV'}</button>
    <p role="status">{message}</p>
    {report&&<><p>驗證狀態：{report.status==='reference_pass'?'參考點殘差通過':'未通過'} · 絕對精度：未驗證</p><p>共同長度：{report.frames} 個取樣點／48,000 Hz · 網路半往返時間估計：{report.clockEstimateMs.toFixed(2)} ms（不是誤差上限）</p>
      {report.tracks.map(t=><div key={t.id}><h3>錄音者 {recorderNumber(t.id)}{t.id===report.referenceId?'（參考）':''}</h3><dl className="condition-details">
        <div><dt>相對原檔起點偏移</dt><dd>{t.offsetMs.toFixed(3)} ms</dd></div><div><dt>相對取樣漂移</dt><dd>{t.driftPpm.toFixed(2)} ppm</dd></div><div><dt>獨立參考點最大殘差</dt><dd>{t.id===report.referenceId?'基準，非獨立量測':t.residualMs.toFixed(3)+' ms'}</dd></div><div><dt>有效參考點</dt><dd>{t.markers.length}</dd></div>
      </dl></div>)}
      <p>報告保留所有參考音位置、配對分數及原檔 SHA-256；參考音仍存在音檔中。WAV 是裁切與漂移重取樣後的衍生檔，原始音檔不變。</p></>}
    <div className="button-row">{downloads.map(d=><a className="ghost-btn" key={d.name} href={d.url} download={d.name}>{d.name.endsWith('.json')?'下載驗證報告':'下載 '+d.name.split('_').at(-2)+' 同步 WAV'}</a>)}</div>
  </section>;
}
