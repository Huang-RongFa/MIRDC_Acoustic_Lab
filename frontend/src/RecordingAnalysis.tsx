import {useEffect,useRef,useState} from 'react';
import {api} from './api';
import type {Identity,Room} from './types';
import {staticHosting} from './config';
import './analysis.css';

type Track={track_id:string;device_name:string;channel_label:string;original_sample_rate:number;duration_seconds:number;analysis_status:string;error?:string;spectrogram_url:string|null;mfcc_url:string|null};
type Analysis={session_name:string;created_at:string;status:string;recording_status:string;duration_seconds?:number;completed_device_count?:number;analyzable_track_count?:number;tracks:Track[];source_errors?:{device_id:string;device_name:string;error:string}[];error?:string};
const statuses:Record<string,string>={not_started:'尚無分析資料',queued:'分析排隊中',running:'分析中',completed:'分析完成',partial:'部分音軌分析完成',failed:'分析失敗'};
const number=(value:number|undefined)=>value===undefined?'—':value.toLocaleString('zh-TW',{maximumFractionDigits:2});

function Chart({track,kind,identity}:{track:Track;kind:'spectrogram'|'mfcc';identity:Identity}){
  const [url,setUrl]=useState(''),[error,setError]=useState('');
  const dialog=useRef<HTMLDialogElement>(null);
  const path=track[kind+'_url' as 'spectrogram_url'|'mfcc_url'];
  useEffect(()=>{
    setUrl('');setError('');
    if(!path)return;
    const controller=new AbortController();let objectUrl='';
    void fetch(path,{signal:controller.signal,headers:{Authorization:'Bearer '+identity.token}}).then(async response=>{
      if(!response.ok)throw new Error('圖表讀取失敗，請重新整理或確認房間權限');
      const blob=await response.blob();if(controller.signal.aborted)return;
      objectUrl=URL.createObjectURL(blob);setUrl(objectUrl);
    }).catch(e=>{if(!controller.signal.aborted)setError((e as Error).message);});
    return()=>{controller.abort();if(objectUrl)URL.revokeObjectURL(objectUrl);};
  },[path,identity.token]);
  const title=`${track.device_name}｜${track.channel_label}`;
  const chartName=kind==='spectrogram'?'Spectrogram':'MFCC';
  return <article className="analysis-chart">
    <h3>{title}</h3><p>{number(track.original_sample_rate)} Hz · {number(track.duration_seconds)} 秒</p>
    {url?<button className="chart-image" onClick={()=>dialog.current?.showModal()} aria-label={`放大 ${title} ${chartName}`}><img src={url} width="960" height="480" alt={`${title} ${chartName}；X 軸時間（秒），Y 軸${kind==='spectrogram'?'頻率（Hz）':'係數 C0～C19'}`}/></button>:<div className="chart-placeholder" role="status">{error||track.error||(path?'圖表載入中':'尚無分析資料')}</div>}
    <div className="chart-actions"><button className="ghost-btn" disabled={!url} onClick={()=>dialog.current?.showModal()}>放大</button>{url&&<a className="ghost-btn" href={url} download={`${track.device_name}-${track.channel_label}-${chartName}.png`}>下載 PNG</a>}</div>
    <dialog ref={dialog} className="analysis-dialog" aria-label={`${title} ${chartName}`}><div className="chart-actions"><strong>{title} · {chartName}</strong><button className="ghost-btn" onClick={()=>dialog.current?.close()}>關閉</button></div>{url&&<img src={url} alt={`${title} ${chartName} 放大圖`}/>}</dialog>
  </article>;
}

export function RecordingAnalysis({identity,room}:{identity:Identity|null;room:Room|null}){
  const [takes,setTakes]=useState<{id:string;created_at:string}[]>([]),[selected,setSelected]=useState(room?.id||'');
  const [data,setData]=useState<Analysis|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const [start,setStart]=useState('0'),[end,setEnd]=useState('');
  const [range,setRange]=useState({start_seconds:0,end_seconds:null as number|null});
  const [trackFilter,setTrackFilter]=useState('all');
  useEffect(()=>{if(!identity||staticHosting)return;let alive=true;
    void api<{items:typeof takes}>(`/rooms/${identity.room_code}/takes`,identity).then(value=>{if(alive){setTakes(value.items);setSelected(current=>value.items.some(t=>t.id===current)?current:room?.id||value.items[0]?.id||'');}}).catch(e=>{if(alive)setError((e as Error).message);});
    return()=>{alive=false;};
  },[identity?.room_code,room?.id,room?.status]);
  useEffect(()=>{setData(null);setError('');setTrackFilter('all');if(!identity||!selected||staticHosting)return;
    let alive=true;const controller=new AbortController();let timer:ReturnType<typeof setTimeout>;
    const poll=async()=>{try{
      const query=new URLSearchParams({start_seconds:String(range.start_seconds)});if(range.end_seconds!==null)query.set('end_seconds',String(range.end_seconds));
      const result=await api<Analysis>(`/v1/sessions/${selected}/analysis?${query}`,identity,{signal:controller.signal});
      if(alive){setData(result);setError('');}
    }catch(e){if(alive)setError((e as Error).message);}finally{if(alive)timer=setTimeout(()=>void poll(),2000);}};
    void poll();return()=>{alive=false;controller.abort();clearTimeout(timer);};
  },[identity?.token,selected,range]);
  async function analyze(){if(!identity)return;setBusy(true);setError('');try{
    const next={start_seconds:Number(start),end_seconds:end===''?null:Number(end)};
    if(!Number.isFinite(next.start_seconds)||next.start_seconds<0||(next.end_seconds!==null&&(!Number.isFinite(next.end_seconds)||next.end_seconds<=next.start_seconds)))throw new Error('請輸入有效時間區間，結束時間必須大於開始時間');
    await api(`/v1/sessions/${selected}/analysis`,identity,{method:'POST',body:JSON.stringify(next)});setRange(next);
  }catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  const tracks=(data?.tracks||[]).filter(track=>trackFilter==='all'||track.track_id===trackFilter);
  return <div className="analysis-page">
    <section className="card"><div className="section-head"><div className="head-title"><h2>錄音分析</h2><p>各聲道錄音起點為 0 秒；未進行跨裝置樣本級同步校正。</p></div></div>
      <label className="analysis-session">錄音批次 Session<select value={selected} disabled={!takes.length} onChange={e=>{setSelected(e.target.value);setRange({start_seconds:0,end_seconds:null});setStart('0');setEnd('');}}>{!takes.length&&<option value="">尚無錄音批次</option>}{takes.map(t=><option key={t.id} value={t.id}>Session {t.id.slice(0,8)} · {new Date(t.created_at).toLocaleString('zh-TW')}</option>)}</select></label>
      <dl className="analysis-summary"><div><dt>Session 名稱</dt><dd>{data?.session_name||'—'}</dd></div><div><dt>錄音日期</dt><dd>{data?.created_at?new Date(data.created_at).toLocaleString('zh-TW'):'—'}</dd></div><div><dt>錄音時長</dt><dd>{number(data?.duration_seconds)} 秒</dd></div><div><dt>完成裝置</dt><dd>{number(data?.completed_device_count)}</dd></div><div><dt>可分析音軌</dt><dd>{number(data?.analyzable_track_count)}</dd></div></dl>
      <form className="analysis-controls" onSubmit={e=>{e.preventDefault();void analyze();}}><label>開始（秒）<input type="number" min="0" step="any" required value={start} onChange={e=>setStart(e.target.value)}/></label><label>結束（秒，空白為整段）<input type="number" min="0" step="any" value={end} onChange={e=>setEnd(e.target.value)}/></label><button className="ghost-btn" type="submit" disabled={busy||!identity?.is_host||!selected||['waiting','preparing','countdown','recording'].includes(data?.recording_status||'waiting')}>{busy?'送出中':'套用時間並分析'}</button><label>顯示音軌<select value={trackFilter} onChange={e=>setTrackFilter(e.target.value)}><option value="all">顯示全部音軌</option>{data?.tracks.map(track=><option key={track.track_id} value={track.track_id}>{track.device_name}｜{track.channel_label}</option>)}</select></label></form>
      <p role="status">{staticHosting?'尚未連接分析服務':statuses[data?.status||'not_started']}{data?.status==='completed'?' · 分析取樣率 44,100 Hz':''}</p>
      {error&&<p role="alert">{error}</p>}{data?.error&&<p role="alert">{data.error}</p>}{data?.source_errors?.map(source=><p className="analysis-error" key={source.device_id}>{source.device_name}：{source.error}</p>)}
    </section>
    {(['spectrogram','mfcc'] as const).map(kind=><section className="card" key={kind}><div className="section-head"><div className="head-title"><h2>{kind==='spectrogram'?'時頻圖比較 Spectrogram':'梅爾頻率倒譜係數比較 MFCC'}</h2><p>{kind==='spectrogram'?'0～22,050 Hz · 共用固定 dBFS 色階（非校正音壓）':'C0～C19 · 全部聲道共用同一批次色階'}</p></div></div>{tracks.length&&identity?<div className="analysis-grid">{tracks.map(track=><Chart key={track.track_id} track={track} kind={kind} identity={identity}/>)}</div>:<div className="empty-state">{statuses[data?.status||'not_started']} · 完成音檔封存後自動分析</div>}</section>)}
  </div>;
}
