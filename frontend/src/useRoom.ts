import {useEffect,useRef,useState} from 'react';
import {RecorderDevice} from './capture';
import type {Identity,Room} from './types';
import {staticHosting} from './config';
import {staticRoom} from './staticState';

export function useRoom(identity:Identity|null){
  const [room,setRoom]=useState<Room|null>(staticHosting?staticRoom:null);
  const [connected,setConnected]=useState(false);
  const [message,setMessage]=useState('');
  const [waves,setWaves]=useState<Record<string,{samples:number[];at:number}>>({});
  const [mic,setMic]=useState(false);
  const device=useRef<RecorderDevice|null>(null);
  const socket=useRef<WebSocket|null>(null);
  const clock=useRef({server:Date.now(),local:performance.now()});
  const send=(data:object)=>{if(socket.current?.readyState===WebSocket.OPEN)socket.current.send(JSON.stringify(data));};
  useEffect(()=>{
    if(staticHosting)return;
    setRoom(null);setConnected(false);setWaves({});setMic(false);
    if(!identity)return;
    let closed=false, timer:ReturnType<typeof setTimeout>;
    const recorder=new RecorderDevice(identity,send,setMessage);device.current=recorder;
    let events=Promise.resolve();
    const connect=()=>{
      const ws=new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/api/rooms/${identity.room_code}/ws`);socket.current=ws;
      ws.onopen=()=>ws.send(JSON.stringify({type:'auth',token:identity.token}));
      ws.onmessage=event=>{
        events=events.then(async()=>{
          const m=JSON.parse(event.data);
          if(m.type==='state'){
            setConnected(true);setRoom(m.state);clock.current={server:m.state.server_now,local:performance.now()};
            await recorder.sync(m.state);
          }else if(m.type==='prepare'){await recorder.prepare();}
          else if(m.type==='start'){await recorder.start();}
          else if(m.type==='stop'){recorder.stop();}
          else if(m.type==='cancel'){setMessage(m.reason);}
          else if(m.type==='preview'){setWaves(old=>({...old,[m.source_label]:{samples:m.samples,at:performance.now()}}));}
          else if(m.type==='pong'){
            const now=Date.now();clock.current={server:m.server_ms+(now-m.client_ms)/2,local:performance.now()};
            send({type:'clock',client_sent_ms:m.client_ms,server_received_ms:m.server_ms,client_received_ms:now,performance_ms:performance.now()});
          }
        }).catch(error=>{setMessage(error.message);send({type:'error',message:error.message});});
      };
      ws.onclose=event=>{setConnected(false);if(closed)return;setMessage(event.code===4409?'同一錄音者已在另一分頁連線':'連線中斷，正在重新連線；本機錄音與暫存持續進行');if(![4409,4400].includes(event.code))timer=setTimeout(connect,1500);};
      ws.onerror=()=>setMessage('無法連線至錄音伺服器');
    };
    connect();
    const heartbeat=setInterval(()=>send({type:'ping',client_ms:Date.now()}),5000);
    const preview=setInterval(()=>{const samples=recorder.samples();if(samples){setWaves(old=>({...old,local:{samples,at:performance.now()}}));send({type:'preview',samples});}setMic(!!recorder.stream?.getAudioTracks().some(t=>t.readyState==='live'));},250);
    const retry=setInterval(()=>void recorder.flush(),3000);
    const beforeUnload=(event:BeforeUnloadEvent)=>{if(recorder.recorder?.state==='recording'){event.preventDefault();event.returnValue='';}};
    window.addEventListener('beforeunload',beforeUnload);
    const visibility=()=>{if(document.visibilityState==='hidden')recorder.background();};
    document.addEventListener('visibilitychange',visibility);
    return()=>{closed=true;clearTimeout(timer);clearInterval(heartbeat);clearInterval(preview);clearInterval(retry);window.removeEventListener('beforeunload',beforeUnload);document.removeEventListener('visibilitychange',visibility);wsClose();recorder.dispose();device.current=null;};
    function wsClose(){socket.current?.close();}
  },[identity]);
  return {room,connected,message,setMessage,waves,mic,device,send,clock};
}
