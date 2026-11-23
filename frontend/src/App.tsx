import {WavePlot} from './WavePlot';
import type {LiveWave} from './liveWave';
import {useEffect,useRef,useState,type ReactNode,type FormEvent} from 'react';
import {api} from './api';
import {fields} from './fields';
import {useRoom} from './useRoom';
import {recorderNumber,phaseNames,type Conditions,type Identity,type Room} from './types';
import {staticHosting} from './config';
import {staticIdentity} from './staticState';
import {RecordingResults} from './RecordingResults';
import {RecordingSyncControls} from './RecordingSyncControls';
import {RecordingAnalysis} from './RecordingAnalysis';
import {channelColors} from './recordingWaveforms';
import {processingLabel} from './audioSettings';
import { alignmentLabel, hasActiveJob, jobLabel, type AnalysisJob } from './analysisStatus';

function identities():Identity[]{try{return JSON.parse(localStorage.getItem('cnc-identities')||'[]');}catch{return [];}}
function initialIdentity(){if(staticHosting)return staticIdentity;const all=identities(),code=new URLSearchParams(location.search).get('room');return all.find(i=>i.room_code===(code||localStorage.getItem('cnc-current-room')))||null;}
function Card({step,title,help,children,action,className=''}:{step?:string;title:string;help?:string;children:ReactNode;action?:ReactNode;className?:string}){return <section className={'card '+className}><div className="section-head">{step&&<div className="step">{step}</div>}<div className="head-title"><h2>{title}</h2>{help&&<p>{help}</p>}</div>{action&&<div className="section-action">{action}</div>}</div>{children}</section>;}
function LiveWaves({room,waves}:{room:Room;waves:Record<string,LiveWave>}){
  const recording=room.status==='recording';
  const [now,setNow]=useState(()=>performance.now());
  useEffect(()=>{
    if(!recording)return;
    let frame=0,last=-Infinity;
    const tick=(time:number)=>{
      if(time-last>=32){setNow(performance.now());last=time;}
      frame=requestAnimationFrame(tick);
    };
    frame=requestAnimationFrame(tick);
    return()=>cancelAnimationFrame(frame);
  },[recording]);
  return <div className="wave-tracks">{Array.from('ABCDE'.slice(0,room.required_recorder_count),(source,i)=>{
    const settings=room.participants.find(p=>p.source_label===source)?.capture_settings;
    const wave=recording?waves[source]:undefined;
    const stereo=settings?.channel_count===2||(!settings&&wave?.channelCount===2);
    const stereoUnavailable=settings?.requested_channel_count===2&&!stereo;
    const label='錄音者 '+recorderNumber(source)+' 波形';
    return <div className="wave-track" key={source}>
      <div className="wave-track-head"><strong>{label}</strong><span className="wave-state">{wave&&now-wave.at<1500?'即時訊號':'等待訊號'}</span></div>
      {stereoUnavailable?<p role="status">無法確認獨立的 Stereo 雙聲道，請選擇 Mono 後重新連接麥克風。</p>:stereo?
        ['CH 1 — Left Channel (L)','CH 2 — Right Channel (R)'].map((title,channel)=><div className="wave-track" key={title}>
          <strong>{title}</strong><WavePlot label={title} live={wave} now={now} channel={channel} color={channelColors[channel]}/>
        </div>):<WavePlot label={label} live={wave} now={now} channel={0} color={['#4a96bf','#25a399','#d4a163','#8065a3','#65763b'][i]}/>}
    </div>;
  })}</div>;
}
function ConditionFields({values,onChange}:{values:Conditions;onChange:(v:Conditions)=>void}){return <div className="dialog-form">{fields.filter(([key])=>!key.startsWith("machine_")).map(([key,label,type])=><label key={key}><span>{label}</span><input name={key} maxLength={200} type={type?'number':'text'} min={key==='tool_flutes'?1:key==='tool_diameter_mm'?0.000001:0} max={key==='tool_diameter_mm'?1000:type==='integer'?100:1000000} step={type==='integer'?1:'any'} value={values[key]??''} onChange={e=>onChange({...values,[key]:e.target.value===''?null:type?Number(e.target.value):e.target.value})}/></label>)}</div>;}

export function App(){
  const [identity,setIdentity]=useState<Identity|null>(initialIdentity);
  const [page,setPage]=useState('record');
  const [name,setName]=useState('');const [code,setCode]=useState(new URLSearchParams(location.search).get('room')||'');const [recordAsHost,setRecordAsHost]=useState(false);const [takes,setTakes]=useState<{id:string;created_at:string}[]>([]);const [count,setCount]=useState(3);const [machines,setMachines]=useState<{machine_id:string;machine_code:string;machine_name:string;machine_type?:string;machine_model?:string}[]>([]);
  const {room:serverRoom,connected,message,setMessage,waves,mic,device,clock,refreshRoom,reference}=useRoom(identity);
  const [previewConditions,setPreviewConditions]=useState<Conditions>({});
  const [editorMessage,setEditorMessage]=useState('');
  const room=staticHosting&&serverRoom?{...serverRoom,conditions:previewConditions}:serverRoom;
  const [now,setNow]=useState(performance.now());const [busy,setBusy]=useState(false);
  const kickDialog=useRef<HTMLDialogElement>(null);
  const [kickTarget,setKickTarget]=useState<{id:string;name:string}|null>(null);
  const [kickError,setKickError]=useState('');
  const [draft,setDraft]=useState<Conditions>({});const dialog=useRef<HTMLDialogElement>(null);
  const [history,setHistory]=useState<Room|null>(null);const [historyIdentity,setHistoryIdentity]=useState<Identity|null>(null);
  const [catalog,setCatalog]=useState<{id:string;kind:string;name:string;values:Conditions}[]>([]);
  const [settingsStep,setSettingsStep]=useState<'machine'|'conditions'>('machine');const [machineSettings,setMachineSettings]=useState<Conditions>({});
  const settingsDialog=useRef<HTMLDialogElement>(null);const [settingsMessage,setSettingsMessage]=useState('');const [selectedPreset,setSelectedPreset]=useState('');const [itemName,setItemName]=useState('');const [settings,setSettings]=useState<Conditions>({});
  const [analysis,setAnalysis]=useState<{result?:unknown}[]>([]);const [jobs,setJobs]=useState<AnalysisJob[]>([]);
  useEffect(()=>{const timer=setInterval(()=>setNow(performance.now()),250);return()=>clearInterval(timer);},[]);
  const act=async(action:()=>Promise<unknown>)=>{setBusy(true);try{await action();}catch(e){setMessage((e as Error).message);}finally{setBusy(false);}};
  const removeParticipant=(id:string,name:string)=>act(async()=>{
    if(!identity)return;
    setKickError('');
    setMessage(`正在移除錄音者 ${name}…`);
    try{
      await api('/rooms/'+identity.room_code+'/participants/'+id,identity,{method:'DELETE'});
      const state=await refreshRoom();
      const member=state.participants.find(p=>p.id===id);
      if(member?.leaving)setMessage(`已要求錄音者 ${name} 退出，正在等待音訊保存（最多約 30 秒）`);
      else if(member)throw new Error(`尚未移除錄音者 ${name}，請重試`);
      else setMessage(`已移除錄音者 ${name}`);
      kickDialog.current?.close();
    }catch(error){
      const detail=error instanceof Error&&error.name==='AbortError'?'移除請求逾時，請重試':(error as Error).message;
      setKickError(detail);
      throw new Error(detail);
    }
  });
  const adopt=(value:Identity)=>{const all=identities().filter(i=>i.room_code!==value.room_code);localStorage.setItem('cnc-identities',JSON.stringify([...all,value]));localStorage.setItem('cnc-current-room',value.room_code);setHistory(null);setHistoryIdentity(null);setCatalog([]);setSettings({});setItemName('');setIdentity(value);setCode(value.room_code);setPage('record');};
  const create=()=>act(async()=>adopt(await api<Identity>('/rooms',null,{method:'POST',body:JSON.stringify({name:name||'主控者',required_recorder_count:count,record_as_host:recordAsHost})})));
  const join=(e:FormEvent)=>{e.preventDefault();const normalized=code.trim().toUpperCase();const saved=identities().find(i=>i.room_code===normalized);void act(async()=>{if(saved){await api('/rooms/'+normalized,saved);adopt(saved);}else adopt(await api<Identity>(`/rooms/${normalized}/join`,null,{method:'POST',body:JSON.stringify({name})}));});};
  const confirmReady=()=>act(async()=>{
    if(!identity||!connected)throw new Error('尚未連線，請等待重新連線後再確認');
    const recorder=device.current;
    if(!recorder?.stream?.getAudioTracks().some(track=>track.readyState==='live'&&track.enabled&&!track.muted)||recorder.context?.state!=='running')throw new Error('麥克風尚未正常收音，請先重新連接麥克風');
    await api('/rooms/'+identity.room_code+'/ready',identity,{method:'POST'});
    const state=await api<Room>('/rooms/'+identity.room_code,identity);
    const self=state.participants.find(person=>person.id===identity.participant_id);
    if(!self?.ready||!self.connected||!self.mic)throw new Error(self?.error||'後端尚未確認就緒，請重新連接麥克風後再試');
    setMessage('已確認就緒；全員就緒且加工條件設定完成後，主控者即可開始錄音');
  });
  const invitation=()=>{const url=new URL(location.pathname,location.origin);url.searchParams.set('room',identity!.room_code);return url.href;};
  const serverNow=clock.current.server+now-clock.current.local;
  const seconds=room?.started_at?Math.max(0,Math.floor(((room.stopped_at??serverNow)-room.started_at)/1000)):0;
  const elapsed=[Math.floor(seconds/3600),Math.floor(seconds/60)%60,seconds%60].map(n=>String(n).padStart(2,'0')).join(':');
  const time=room?.status==='countdown'?`倒數 ${Math.max(0,Math.ceil(((room.starts_at??serverNow)-serverNow)/1000))}`:elapsed;
  const current=room?.participants.find(p=>p.id===identity?.participant_id);
  const active=!!room&&['preparing','countdown','recording'].includes(room.status);
  const download=async(who:Identity,pid:string)=>{const response=await fetch(`/api/rooms/${who.room_code}/recordings/${pid}/audio?take_id=${history?.id??who.session_id}`,{headers:{Authorization:'Bearer '+who.token}});if(!response.ok)throw new Error('音檔尚未完整封存');const blob=await response.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`${history?.id??who.session_id}_${pid}.${blob.type.includes('mp4')?'m4a':blob.type.includes('ogg')?'ogg':'webm'}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);};
  function openConditions(){
    if(!room||!identity)return;
    setDraft({...room.conditions});
    setEditorMessage('');
    setMachines([]);
    dialog.current?.showModal();
    if(!staticHosting)void act(async()=>{
      try{
        await loadCatalog();
      }catch(error){setEditorMessage('無法載入機台清單：'+(error as Error).message);}
    });
  }
  function saveConditions(event:FormEvent){
    event.preventDefault();
    if(staticHosting){
      setPreviewConditions({...draft,machine_code:String(draft.machine_code??'').trim()});
      dialog.current?.close();
      return;
    }
    if(!identity)return;
    void act(async()=>{
      try{
        await api('/rooms/'+identity.room_code+'/conditions',identity,{method:'PUT',body:JSON.stringify(draft)});
        dialog.current?.close();
      }catch(error){setEditorMessage((error as Error).message);}
    });
  }
  const loadCatalog=async()=>{if(identity){const [items,registry]=await Promise.all([api<{items:typeof catalog}>(`/rooms/${identity.room_code}/catalog`,identity),api<{items:typeof machines}>('/machines',identity)]);setCatalog(items.items);setMachines(registry.items);}};
  const presetValues=(values:Conditions):Conditions=>Object.fromEntries(Object.entries(values).filter(([key])=>!key.startsWith('machine_')));
  function openSettings(){
    setSettingsStep('machine');setMachineSettings(Object.fromEntries(Object.entries(room?.conditions??{}).filter(([key])=>key.startsWith('machine_'))));setSettingsMessage('');setSelectedPreset('');setItemName('');setSettings({});settingsDialog.current?.showModal();
    if(!staticHosting&&identity)void act(async()=>{try{await loadCatalog();}catch(error){setSettingsMessage((error as Error).message);}});
  }
  function saveMachine(event:FormEvent){
    event.preventDefault();if(!identity)return;
    const code=String(machineSettings.machine_code??'').trim(),name=String(machineSettings.machine_name??'').trim();
    if(!code||!name){setSettingsMessage('請填寫機台編號與名稱');return;}
    void act(async()=>{try{
      const values={...machineSettings,machine_code:code,machine_name:name};
      if(!staticHosting){
        await api(`/rooms/${identity.room_code}/catalog`,identity,{method:'PUT',body:JSON.stringify({kind:'machines',name,values})});
        const registry=await api<{items:typeof machines}>('/machines',identity);setMachines(registry.items);
        const saved=registry.items.find(machine=>machine.machine_code===code);if(!saved)throw new Error('機台未出現在可用清單，請確認機台是否停用');
        setMachineSettings({...values,...saved});
      }else setMachineSettings(values);
      setSettingsMessage(staticHosting?'機台僅保存於本頁預覽。':'機台已保存至資料庫');setSettingsStep('conditions');
    }catch(error){setSettingsMessage((error as Error).message);}});
  }
  function savePreset(event:FormEvent){
    event.preventDefault();if(!identity)return;
    const name=itemName.trim();if(!name){setSettingsMessage('請輸入設定名稱');return;}
    void act(async()=>{try{
      const values={...presetValues(settings),...machineSettings};
      if(staticHosting){setCatalog(items=>[...items.filter(item=>item.kind!=='presets'||item.name!==name),{id:catalog.find(item=>item.kind==='presets'&&item.name===name)?.id||crypto.randomUUID(),kind:'presets',name,values}]);}
      else{await api(`/rooms/${identity.room_code}/catalog`,identity,{method:'PUT',body:JSON.stringify({kind:'presets',name,values})});setCatalog((await api<{items:typeof catalog}>(`/rooms/${identity.room_code}/catalog`,identity)).items);}
      setSelectedPreset('');setItemName(name);setSettingsMessage(staticHosting?'已儲存至本頁預覽，重新整理後清除。':'加工條件已儲存；相同名稱會更新原設定。');
    }catch(error){setSettingsMessage((error as Error).message);}});
  }
  function applyPreset(){
    if(!room||!identity||room.status!=='waiting')return;
    setDraft({...machineSettings,...presetValues(settings)});
    setEditorMessage('');settingsDialog.current?.close();dialog.current?.showModal();
    if(!staticHosting)void act(async()=>{try{await loadCatalog();}catch(error){setEditorMessage((error as Error).message);}});
  }
    const loadAnalysis=async()=>{if(!identity)return;const data=await api<{results:{result?:unknown}[];jobs?:AnalysisJob[]}>(`/rooms/${identity.room_code}/analysis`,identity);setAnalysis(data.results);setJobs(data.jobs??[]);};
  useEffect(()=>{if(page!=='analysis'||!identity||!hasActiveJob(jobs))return;const timer=setInterval(()=>{void loadAnalysis().catch(()=>undefined);},15000);return()=>clearInterval(timer);},[page,identity,jobs]);
  const navigate=(next:string)=>{setPage(next);if(next==='analysis'&&identity&&!staticHosting)void act(loadAnalysis);};
  return <><header className="topbar"><div className="topbar-inner"><div className="brandmark"><svg width="23" height="23" viewBox="0 0 24 24" aria-hidden="true"><path d="M1 13h4l3-8 5 15 3-10 3 3h4" stroke="currentColor" strokeWidth="2" fill="none"/></svg></div><div className="brandtext"><strong>CNC Acoustic Lab</strong><small>多人協作錄音</small></div>    {(identity||identities().length>0)&&<nav className="workspace-nav" aria-label="主要導覽">{[['record','錄音'],['results','錄音結果'],['analysis','錄音分析']].filter(([key])=>key!=='analysis'||identity).map(([key,label])=><button key={key} aria-current={page===key?'page':undefined} className={page===key?'active':''} onClick={()=>navigate(key)}>{label}</button>)}</nav>}
<div className="right-head">{identity&&!staticHosting&&<button className="ghost-btn" disabled={active||room?.status==="finalizing"} onClick={()=>{setIdentity(null);localStorage.removeItem('cnc-current-room');setPage('record');setMessage('可建立新房間或加入另一個房間；歷史憑證仍保留在此瀏覽器。');}}>建立／加入另一個房間</button>}{!identity&&<button className="ghost-btn" onClick={()=>navigate("record")}>建立／加入房間</button>}<span className={'status-badge '+(connected?'ok':'pending')}>{connected?'伺服器已連線':'尚未連線'}</span></div></div></header><main className="shell">    {message&&<div className="notice" role="status">{message}<button aria-label="關閉訊息" onClick={()=>setMessage('')}>×</button></div>}
    {!identity&&page==='record'&&<div className="main-grid"><Card step="01" title="建立錄音房間" help="錄音者加入時依序取得聲源位置。"><label className="single-field"><span>你的名稱</span><input value={name} onChange={e=>setName(e.target.value)} maxLength={80}/></label><label>錄音人數<select value={count} onChange={e=>setCount(Number(e.target.value))}>{[1,2,3,4,5].map(n=><option key={n}>{n}</option>)}</select></label><label><input type="checkbox" checked={recordAsHost} onChange={e=>setRecordAsHost(e.target.checked)}/>此裝置也參與錄音</label><button className="main-action" disabled={busy} onClick={create}>建立新房間</button></Card><Card step="02" title="加入錄音房間" help="輸入主控者提供的房間代碼。"><form onSubmit={join}><div className="form-pair"><label><span>房間代碼</span><input required value={code} onChange={e=>setCode(e.target.value)} maxLength={6} autoCapitalize="characters" autoCorrect="off"/></label><label><span>錄音人員</span><input required value={name} onChange={e=>setName(e.target.value)} maxLength={80}/></label></div><button className="secondary-action" disabled={busy}>加入此錄音房間</button></form></Card></div>}
    {identity&&!room&&<Card title="正在取得房間狀態"><p>等待伺服器連線，請確認後端已啟動。</p></Card>}
    {room&&identity&&page==='record'&&<div className="main-grid"><div className="main-column"><Card step="01" title="錄音房間" help="將邀請連結提供給錄音者。"><div className="room-identity"><div><small>房間代碼</small><strong>{identity.room_code}</strong></div><button className="ghost-btn" onClick={()=>void act(async()=>{await navigator.clipboard.writeText(invitation());setMessage('已複製邀請連結');})}>複製邀請連結 ↗</button></div><div className="button-row"><button className="ghost-btn" onClick={()=>void act(async()=>{await navigator.clipboard.writeText(identity.room_code);setMessage("已複製 房間代碼");})}>複製 房間代碼</button><button className="ghost-btn" onClick={()=>void act(async()=>{if(navigator.share)await navigator.share({title:"CNC Acoustic Lab",url:invitation()});else{await navigator.clipboard.writeText(invitation());setMessage("已複製邀請連結");}})}>分享邀請</button>{identity.is_host&&<button className="ghost-btn" disabled={busy||!!room.closed_at} onClick={()=>{if(confirm("確定停止錄音並關閉房間？"))void act(()=>api(`/rooms/${identity.room_code}/close`,identity,{method:"POST"}));}}>{room.closed_at?"房間已關閉":"關閉房間"}</button>}</div><p className="room-help">{room.closed_at?"房間已關閉":phaseNames[room.status]} · {current?.source_label?"錄音者 "+recorderNumber(current.source_label):"主控台"}{identity.is_host?'／主控者':''}</p></Card>
    <Card step="02" title="錄音者連線狀態" help="全員就緒，主控者才能啟動錄音。">{identity.is_host&&<label>錄音人數<select disabled={room.status!=="waiting"||busy} value={room.required_recorder_count} onChange={e=>void act(()=>api("/rooms/"+identity.room_code+"/config",identity,{method:"PATCH",body:JSON.stringify({required_recorder_count:Number(e.target.value)})}))}>{[1,2,3,4,5].map(n=><option key={n}>{n}</option>)}</select></label>}<div className="ready-overview"><div><strong><span>{room.ready_count}</span><span className="muted-num">/ {room.required_recorder_count}</span></strong><span>位錄音者已就緒</span></div></div><div className="progress"><div style={{width:room.ready_count/room.required_recorder_count*100+'%'}}/></div><div className="participant-list">{'ABCDE'.slice(0,room.required_recorder_count).split('').map(s=>{const p=room.participants.find(p=>p.source_label===s);return <div className="person" key={s}><span className={'person-icon '+s.toLowerCase()}>{recorderNumber(s)}</span><div className="person-core"><strong>{p?.name||'等待加入'}{p?.is_host?' · 主控者':''}</strong><small>{p?.error||(p?.connected?(p.recording_active?'錄音中':'已連線'):'未連線')} · {p?.microphone_permission==='denied'?'麥克風權限遭拒':p?.mic?'麥克風有效':'麥克風未啟用'}</small>{p&&p.id!==identity.participant_id&&<small>輸入 {p.capture_settings?.input_sample_rate??"—"} Hz · PCM {p.capture_settings?.actual_sample_rate??"—"} Hz · {p.capture_settings?.channel_count??"—"} ch · {p.capture_settings?.support_status==="ready"?"裝置已準備":"待確認裝置支援"}（由該錄音者設定）</small>}{p?.id===identity.participant_id&&<RecordingSyncControls identity={identity} device={device.current} status={p.capture_settings} locked={!connected||busy||room.status!=="waiting"||!!room.closed_at||!!p.leaving}/>}{p?.id===identity.participant_id&&<div className="button-row"><button type="button" className="ghost-btn" disabled={staticHosting||!connected||busy||room.status!=='waiting'||!!room.closed_at||p.leaving} onClick={()=>void act(async()=>{if(!device.current)throw new Error('麥克風尚未準備好，請稍後再試');await device.current.authorize();})}>{mic?'重新連接麥克風':'連接麥克風'}</button><button type="button" className="ghost-btn" disabled={staticHosting||!connected||busy||room.status!=='waiting'||!!room.closed_at||p.leaving} onClick={()=>void confirmReady()}>確認就緒</button></div>}</div><span className={'person-status '+(p?.ready?'ok':'waiting')}>{p?.leaving?'退出中':p?.error?'裝置錯誤':p?.recording_active&&p.connected?'錄音中':p?.ready&&p.connected?'已就緒':'未就緒'}</span>{p&&identity.is_host&&!p.is_host&&<button className="kick" title="強制退出" aria-label={`強制退出 ${p.name}`} disabled={busy||p.leaving} type="button" onClick={()=>{setKickTarget({id:p.id,name:p.name});setKickError('');kickDialog.current?.showModal();}}><svg viewBox="0 0 24 24" width="18" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M3 6h18M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7m4-7v7"/></svg></button>}</div>;})}</div><div className="tip-info">連線成功不代表已能錄音；請先確認各支手機的麥克風權限與收音位置。</div></Card>
    <Card step="03" title="本次加工條件" help="全體錄音者共用同一組加工參數。" action={identity.is_host&&<button type="button" className="ghost-btn" onClick={openSettings}>設定管理</button>}><div className="setup-rows">{[['machine_code','機台'],['material','加工材料'],['tool_type','刀具'],['tool_setup','裝夾']].map(([k,l])=><div key={k}><span>{l}</span><b>{room.conditions[k]??'未設定'}</b></div>)}</div><div className="stats-grid">{[['spindle_rpm','主軸轉速','RPM'],['feed_mm_min','進給速度','mm/min'],['axial_depth_mm','軸向切深','mm']].map(([k,l,u])=><div key={k}><small>{l}</small><strong>{room.conditions[k]??'—'}</strong><em>{u}</em></div>)}</div><button className="secondary-action" disabled={!identity.is_host||room.status!=='waiting'} onClick={openConditions}>編輯加工條件</button></Card></div>
    <div className="side-column"><Card step="04" title="主控錄音台" help="各支手機共同接收開始／停止指令，錄音不限時。"><div className={'control-state '+(room.status==='recording'?'recording':'')}><span className="state-led"/>{phaseNames[room.status]}</div><div className="clock-panel"><small>已錄製時間</small><div className="clock" data-testid="elapsed">{time}</div><p>以後端工作階段時間為依據</p></div><button className="main-action" disabled={!identity.is_host||!connected||busy||room.ready_count!==room.required_recorder_count||!!room.closed_at||room.status!=='waiting'||!room.conditions.machine_id} title={room.conditions.machine_id?undefined:"請先選擇機台"} onClick={()=>void act(async()=>{if(!reference.current)throw new Error('同步參考音尚未準備');await reference.current.enable();await api(`/rooms/${identity.room_code}/start`,identity,{method:'POST'});})}>開始統一錄音</button>{identity.is_host&&["completed","interrupted"].includes(room.status)&&<button className="secondary-action" onClick={()=>void act(()=>api("/rooms/"+identity.room_code+"/next",identity,{method:"POST"}))}>準備下一次錄音</button>}{['preparing','countdown','recording'].includes(room.status)&&<button className="stop-action" disabled={!identity.is_host||!connected||busy} onClick={()=>void act(async()=>{if(room.status==='recording'){try{await reference.current?.finish();}catch(e){setMessage((e as Error).message+'；仍會停止並保存原始錄音');}}await api(`/rooms/${identity.room_code}/stop`,identity,{method:'POST'});})}>由主控者停止錄音</button>}<p className="sync-note">各裝置獨立錄音，由主控統一開始／停止；共同時間僅用於排程，不代表取樣點級同步。原始音檔及 PCM 分別保存，不在加工量測期間自動播放校正音。</p></Card>
    <Card step="05" title="錄音波形" help="來自各支手機的真實音訊預覽。" className="wave-card"><LiveWaves room={room} waves={waves}/><p className="wave-disclaimer">預覽不等於正式音訊；原始分段各自保存，沒有收到訊號時顯示平線。</p><div className="upload-list">{room.recordings.map(r=><div className="upload-item" key={r.participant_id}><span>{recorderNumber(r.source_label)}</span><div><strong>聲源 {recorderNumber(r.source_label)} · 手機音訊</strong><small>{r.error||r.mime_type||'尚未錄製'}</small></div><em>{phaseNames[r.status]}</em></div>)}</div></Card></div></div>}
    {page==='record'&&identity&&device.current?.stream&&<div className="chart-actions"><span>{processingLabel(device.current.processing)}</span>{identity.is_host&&<button onClick={()=>void act(async()=>{await device.current?.playChirp();})}>播放同步嗶聲</button>}<button onClick={()=>void act(async()=>{await device.current?.downloadMeta();})}>下載收音設定</button></div>}
    {page==='results'&&<Card title="實驗紀錄" help="僅列出此瀏覽器持有存取權的房間；資料從後端讀取。"><div className="history-list">{history&&<button className="ghost-btn" onClick={()=>{setHistory(null);setHistoryIdentity(null);}}>返回目前錄音</button>}{identities().map(i=><button className="ghost-btn" key={i.session_id} onClick={()=>void act(async()=>{setHistory(await api<Room>('/rooms/'+i.room_code,i));setHistoryIdentity(i);setTakes((await api<{items:typeof takes}>('/rooms/'+i.room_code+'/takes',i)).items);})}>{i.room_code} · {i.session_id.slice(0,8)}</button>)}</div>{history&&historyIdentity&&<><label>錄音批次<select value={history.id} onChange={e=>void act(async()=>setHistory(await api<Room>("/rooms/"+historyIdentity.room_code+"?take_id="+e.target.value,historyIdentity)))}>{takes.map(t=><option key={t.id} value={t.id}>{new Date(t.created_at).toLocaleString()} · {t.id.slice(0,8)}</option>)}</select></label><h3>{phaseNames[history.status]}</h3><p className="session-id">Session ID：{history.id}</p><dl className="condition-details">{fields.map(([key,label])=><div key={key}><dt>{label}</dt><dd>{history.conditions[key]??'—'}</dd></div>)}</dl>{history.recordings.map(r=><div className="history-record" key={r.participant_id}><span>聲源 {recorderNumber(r.source_label)}：{phaseNames[r.status]} {r.error}</span><button className="ghost-btn" disabled={!['stored','interrupted'].includes(r.status)} onClick={()=>void act(()=>download(historyIdentity,r.participant_id))}>下載原始音檔</button></div>)}</>}</Card>}
    {page==='results'&&!staticHosting&&(history||room)&&(historyIdentity||identity)&&<RecordingResults key={(history??room)!.id} room={(history??room)!} identity={(historyIdentity??identity)!}/>}
    {page==='analysis'&&<Card title="分析結果" help="只顯示後端已保存的分析資料；未運行分析時不產生模擬圖表。">{jobs.map(job=>{const l=jobLabel(job);return <p key={job.id} className={'job-status '+l.tone} data-testid="analysis-job">{l.text}</p>;})}{analysis.length?analysis.map((item,i)=>{const a=alignmentLabel(item.result);return <div key={i}>{a&&<p className={'job-status '+a.tone} data-testid="alignment-verdict">{a.text}</p>}<pre>{JSON.stringify(item,null,2)}</pre></div>;}):<div className="empty-state"><h3>尚無正式分析結果</h3><p>FFT、RMS、濾波、三聲源融合及模型判定需由後續分析程序產生。三手機尚未完成樣本對齊，不能假設已同步。</p></div>}</Card>}
    {page==='analysis'&&<RecordingAnalysis key={identity?.room_code||'offline'} room={room} identity={identity}/>}
    <footer><span>© CNC Acoustic Lab · Research Capture</span><span>三手機獨立錄音 · HTTPS 麥克風授權</span></footer>
  </main><dialog ref={kickDialog} className="dialog" aria-labelledby="kick-title" aria-describedby="kick-description" onCancel={e=>{if(busy)e.preventDefault();}}>
    <h2 id="kick-title">移除錄音者</h2>
    <p id="kick-description">確定將「{kickTarget?.name}」移出房間？該錄音者的房間存取權限將失效。</p>
    {kickError&&<p role="alert">{kickError}</p>}
    {busy&&<p role="status">正在移除，請稍候…</p>}
    <div className="dialog-actions"><button type="button" disabled={busy} onClick={()=>kickDialog.current?.close()}>取消</button><button type="button" className="primary-small" disabled={busy||!kickTarget} onClick={()=>{if(kickTarget)void removeParticipant(kickTarget.id,kickTarget.name);}}>{busy?'移除中…':'確認移除'}</button></div>
  </dialog><dialog ref={dialog} className="dialog conditions-dialog"><form onSubmit={saveConditions}><div className="dialog-title"><div><h2>本次加工條件</h2><p>開始後鎖定；不包含正常、異常或磨耗判定。</p></div><button className="icon-btn" type="button" aria-label="關閉加工條件" onClick={()=>dialog.current?.close()}>×</button></div>{staticHosting&&<p>加工條件僅套用到本頁預覽。</p>}
    <label>機台 <strong style={{color:"red"}}>*</strong><input name="machine_code" required maxLength={200} pattern={'.*\\S.*'} placeholder="輸入機台編號或名稱" value={draft.machine_code??''} onChange={e=>setDraft({...(!staticHosting&&draft.machine_id?{}:draft),machine_code:e.target.value,machine_id:null})}/></label>
    {!staticHosting&&machines.length>0&&<label>從已登錄機台選擇<select value={draft.machine_id??""} onChange={e=>{const machine=machines.find(m=>m.machine_id===e.target.value);const defaults=catalog.find(item=>item.kind==="machines"&&item.values.machine_code===machine?.machine_code);setDraft({...defaults?.values,machine_id:machine?.machine_id??null,machine_code:machine?.machine_code??""});}}><option value="">手動輸入</option>{machines.map(m=><option key={m.machine_id} value={m.machine_id}>{m.machine_code} · {m.machine_name}</option>)}</select></label>}
    {<label>套用已儲存的加工參數<select value="" onChange={e=>{const item=catalog.find(i=>i.id===e.target.value);if(item)setDraft({...Object.fromEntries(Object.entries(draft).filter(([key])=>key.startsWith('machine_'))),...presetValues(item.values)});}}><option value="">選擇參數組合</option>{catalog.filter(i=>i.kind==='presets').map(i=><option key={i.id} value={i.id}>{i.name}</option>)}</select></label>}
    {editorMessage&&<p role="alert">{editorMessage}</p>}<ConditionFields values={draft} onChange={setDraft}/><div className="dialog-actions"><button type="button" onClick={()=>dialog.current?.close()}>取消</button><button className="primary-small" disabled={busy}>{staticHosting?'套用預覽':'儲存設定'}</button></div></form></dialog><dialog ref={settingsDialog} className="dialog conditions-dialog" aria-labelledby="settings-title"><form onSubmit={settingsStep==='machine'?saveMachine:savePreset}>
    <div className="dialog-title"><div><h2 id="settings-title">設定管理</h2><p>{settingsStep==='machine'?'步驟 1／2：機台設定':'步驟 2／2：加工條件'}</p></div><button className="icon-btn" type="button" aria-label="關閉設定管理" onClick={()=>settingsDialog.current?.close()}>×</button></div>
    {settingsStep==='machine'?<>
    <label>選取已儲存機台<select value={machineSettings.machine_id??''} disabled={busy} onChange={e=>{const machine=machines.find(item=>item.machine_id===e.target.value);setMachineSettings(machine?{...machine}:{});setSettingsMessage('');}}><option value="">新增機台</option>{machines.map(machine=><option key={machine.machine_id} value={machine.machine_id}>{machine.machine_code} · {machine.machine_name}</option>)}</select></label>
    <div className="dialog-form">{[['machine_code','機台編號'],['machine_name','機台名稱'],['machine_type','機台類型'],['machine_model','機台型號']].map(([key,label])=><label key={key}>{label}<input required={key==='machine_code'||key==='machine_name'} maxLength={200} value={machineSettings[key]??''} onChange={e=>setMachineSettings({...machineSettings,[key]:e.target.value||null,...(key==='machine_code'?{machine_id:null}:{})})}/></label>)}</div>
    </>:<>
    <p>機台：{machineSettings.machine_code} · {machineSettings.machine_name}</p>
    <label>選取自訂加工條件<select value={selectedPreset} disabled={busy} onChange={e=>{const item=catalog.find(item=>item.id===e.target.value);setSelectedPreset(e.target.value);setItemName(item?.name??'');setSettings(item?presetValues(item.values):{});setSettingsMessage('');}}><option value="">新增加工條件</option>{catalog.filter(item=>item.kind==='presets'&&(!item.values.machine_id||item.values.machine_id===machineSettings.machine_id)).map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
    <label>設定名稱<input required maxLength={200} value={itemName} onChange={e=>setItemName(e.target.value)}/></label>
    <ConditionFields values={settings} onChange={setSettings}/></>}
    {settingsMessage&&<p role="status">{settingsMessage}</p>}
    <div className="dialog-actions"><button type="button" onClick={()=>settingsDialog.current?.close()}>關閉</button>{settingsStep==='machine'?<button className="primary-small" disabled={busy}>儲存機台並下一步</button>:<><button type="button" disabled={busy} onClick={()=>{setSettingsStep('machine');setSettingsMessage('');}}>上一步：機台設定</button><button className="primary-small" disabled={busy}>儲存加工條件</button><button type="button" disabled={busy||!itemName.trim()||room?.status!=='waiting'} onClick={applyPreset}>套用本次設定</button></>}</div>
  </form></dialog></>;
}
