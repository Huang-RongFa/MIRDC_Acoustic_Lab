import {useEffect,useRef,useState} from 'react';
import {RecorderDevice} from './capture';
import type {Identity,Room} from './types';
import {staticHosting} from './config';
import {staticRoom} from './staticState';
import {api} from './api';
import {SyncReference} from './syncReference';
import {appendWave,type LiveWave} from './liveWave';

export function useRoom(identity:Identity|null){
  const [room,setRoom]=useState<Room|null>(staticHosting?staticRoom:null);
  const [connected,setConnected]=useState(false);
  const [message,setMessage]=useState('');
  const [waves,setWaves]=useState<Record<string,LiveWave>>({});
  const [mic,setMic]=useState(false);
  const device=useRef<RecorderDevice|null>(null);
  const socket=useRef<WebSocket|null>(null);
  const reference=useRef<SyncReference|null>(null);
  const clock=useRef({server:Date.now(),local:performance.now()});
  const refreshRoom=async()=>{
    if(!identity)throw new Error('尚未加入房間');
    const state=await api<Room>('/rooms/'+identity.room_code,identity);
    setRoom(old=>old?.room_id===state.room_id&&old.event_version<=state.event_version?state:old);
    return state;
  };
  const leaving=!!room?.participants.some(p=>p.leaving);
  useEffect(()=>{
    if(!leaving||!identity||staticHosting)return;
    const timer=setInterval(()=>void refreshRoom().catch(error=>setMessage(error.message)),1500);
    return()=>clearInterval(timer);
  },[leaving,identity]);
  const send=(data:object)=>{if(socket.current?.readyState===WebSocket.OPEN)socket.current.send(JSON.stringify(data));};
  useEffect(()=>{
    if(staticHosting)return;
    setRoom(null);setConnected(false);setWaves({});setMic(false);
    if(!identity)return;
    let closed=false, timer:ReturnType<typeof setTimeout>,lastMessage=performance.now();
    const recorder=new RecorderDevice(identity,send,setMessage);device.current=recorder;
    const signal=new SyncReference();reference.current=signal;
    let bestRtt=Infinity;
    let events=Promise.resolve();
    const connect=()=>{
      const ws=new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/api/rooms/${identity.room_code}/ws`);socket.current=ws;
      ws.onopen=()=>{recorder.room=null;bestRtt=Infinity;ws.send(JSON.stringify({type:'auth',token:identity.token}));send({type:'ping',client_ms:Date.now()});};
      ws.onmessage=event=>{
        lastMessage=performance.now();
        events=events.then(async()=>{
          if(closed||socket.current!==ws||ws.readyState!==WebSocket.OPEN)return;
          const m=JSON.parse(event.data);
          if(m.type==='state'){
            if(recorder.room&&recorder.room.event_version>m.state.event_version)return;
            const member=m.state.participants.find((p:{id:string;leaving?:boolean;connected:boolean})=>p.id===identity.participant_id);
            setConnected(!!member?.connected&&!member.leaving&&!m.state.closed_at);setRoom(old=>old&&old.room_id===m.state.room_id&&old.event_version>m.state.event_version?old:m.state);if(bestRtt===Infinity)clock.current={server:m.state.server_now,local:performance.now()};
            if(identity.is_host){
              if(m.state.status==='countdown')signal.schedule(m.state.id+'/'+m.state.starts_at,m.state.starts_at-1500-(clock.current.server+performance.now()-clock.current.local),setMessage);
              else if(!['preparing','recording'].includes(m.state.status))signal.clear();
            }
            const self=m.state.participants.find((p:{id:string})=>p.id===identity.participant_id);
            if(self?.leaving){recorder.personalStop=true;recorder.stop();}
            if(!recorder.room&&recorder.stream?.getAudioTracks().some(track=>track.readyState==='live')){recorder.reportSettings();send({type:'mic',mic:true});}
            await recorder.sync(m.state);
          }else if(m.type==='prepare'&&identity.source_label&&!recorder.personalStop){await recorder.prepare();}
          else if(m.type==='start'&&identity.source_label&&!recorder.personalStop){await recorder.start();recorder.confirmStart();}
          else if(m.type==='stop_personal'){recorder.personalStop=true;recorder.stop();}
          else if(m.type==='stop'){recorder.stop();}
          else if(m.type==='cancel'){await recorder.cancel();setMessage(m.reason);}
          else if(m.type==='preview'&&m.source_label!==identity.source_label){setWaves(old=>({...old,[m.source_label]:appendWave(old[m.source_label],{samples:m.samples,channels:m.channels,duration:m.duration,at:performance.now()})}));}
          else if(m.type==='pong'){
            const now=Date.now(),rtt=now-m.client_ms;
            if(rtt>=0&&(rtt<=bestRtt||performance.now()-clock.current.local>30000)){bestRtt=rtt;clock.current={server:m.server_ms+rtt/2,local:performance.now()};}
            if(recorder.pcm&&Number.isFinite(bestRtt))recorder.pcm.clock={...clock.current,uncertainty:bestRtt/2};
            send({type:'clock',client_sent_ms:m.client_ms,server_received_ms:m.server_ms,client_received_ms:now,performance_ms:performance.now()});
          }
        }).catch(error=>{setMessage(error.message);send({type:'error',message:error.message});});
      };
      ws.onclose=event=>{setConnected(false);if(closed)return;if(event.code===4410){localStorage.removeItem('cnc-current-room');const saved=JSON.parse(localStorage.getItem('cnc-identities')||'[]') as Identity[];localStorage.setItem('cnc-identities',JSON.stringify(saved.filter(i=>i.room_code!==identity.room_code)));location.replace(location.pathname);return;}setMessage(event.code===4409?'同一錄音者已在另一分頁連線':'連線中斷，正在重新連線；本機錄音與暫存持續進行');if(![4409,4400].includes(event.code))timer=setTimeout(connect,1500);};
      ws.onerror=()=>setMessage('無法連線至錄音伺服器');
    };
    connect();
    const heartbeat=setInterval(()=>{if(performance.now()-lastMessage>6000)setConnected(false);send({type:'ping',client_ms:Date.now()});},1500);
    const preview=setInterval(()=>{const frame=recorder.samples();if(frame){setWaves(old=>({...old,[identity.source_label]:appendWave(old[identity.source_label],{...frame,at:performance.now()})}));send({type:'preview',...frame});}setMic(!!recorder.stream?.getAudioTracks().some(t=>t.readyState==='live'));},250);
    const retry=setInterval(()=>void recorder.flush(),3000);
    const beforeUnload=(event:BeforeUnloadEvent)=>{if(recorder.recorder?.state==='recording'){event.preventDefault();event.returnValue='';}};
    window.addEventListener('beforeunload',beforeUnload);
    const visibility=()=>{if(document.visibilityState==='hidden')recorder.background();};
    document.addEventListener('visibilitychange',visibility);
    return()=>{closed=true;clearTimeout(timer);clearInterval(heartbeat);clearInterval(preview);clearInterval(retry);window.removeEventListener('beforeunload',beforeUnload);document.removeEventListener('visibilitychange',visibility);wsClose();recorder.dispose();signal.dispose();reference.current=null;device.current=null;};
    function wsClose(){socket.current?.close();}
  },[identity]);
  return {room,connected,message,setMessage,waves,mic,device,send,clock,refreshRoom,reference};
}
