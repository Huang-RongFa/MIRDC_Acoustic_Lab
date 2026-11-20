import {api} from './api';
import {chunks,getCapture,put,saveChunk,type Capture,type ChirpEvent} from './storage';
import {summarizeProcessing,processingLabel,type ProcessingReport} from './audioSettings';
import {playSyncChirp} from './syncChirp';
import type {Identity,Room} from './types';

export class RecorderDevice {
  stream:MediaStream|null=null;
  context:AudioContext|null=null;
  analyser:AnalyserNode|null=null;
  recorder:MediaRecorder|null=null;
  private capture:Capture|null=null;
  private writes=Promise.resolve();
  private flushing=false;
  private stoppedByHost=false;
  room:Room|null=null;
  /** getSettings() 實際回報的收音處理狀態；網頁的關閉要求不一定被瀏覽器採用。 */
  processing:ProcessingReport|null=null;
  /** 本機播放同步嗶聲的時間（僅主控手機會有），供分析交叉核對。 */
  chirps:ChirpEvent[]=[];
  key:string;
  constructor(public identity:Identity,private send:(data:object)=>void,private report:(message:string)=>void){this.key=identity.session_id+'/'+identity.participant_id;}

  async authorize(){
    if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder)throw new Error('此瀏覽器需 HTTPS 及 MediaRecorder 支援');
    if(this.stream?.getAudioTracks().some(t=>t.readyState==='live'))return;
    try{
      this.stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:false,noiseSuppression:false,autoGainControl:false},video:false});
      this.processing=summarizeProcessing(this.stream.getAudioTracks()[0].getSettings());
      this.context=new AudioContext();await this.context.resume();
      this.analyser=this.context.createAnalyser();this.analyser.fftSize=512;
      this.context.createMediaStreamSource(this.stream).connect(this.analyser);
      this.stream.getAudioTracks()[0].onended=()=>this.fail('麥克風已停止，錄音可能不完整');
      this.stream.getAudioTracks()[0].onmute=()=>this.background('麥克風被系統暫停，錄音可能中斷');
      this.context.onstatechange=()=>{if(this.context?.state!=='running')this.background('音訊處理被系統暫停，錄音可能中斷');};
      await navigator.storage?.persist?.();
      this.send({type:'mic',mic:true});
      this.report(this.processing?.raw===true?'麥克風已授權（原始收音）；確認波形後按下準備完成':'麥克風已授權，但'+processingLabel(this.processing)+'；可繼續錄音，分析時會標記');
    }catch(error){this.fail('麥克風無法使用：'+(error as Error).message);throw error;}
  }
  samples(){if(!this.analyser)return null;const values=new Float32Array(this.analyser.fftSize);this.analyser.getFloatTimeDomainData(values);return Array.from(values.filter((_,i)=>i%4===0),v=>Math.max(-1,Math.min(1,v)));}
  private fail(message:string){if(this.capture&&!this.capture.done){this.capture.interrupted=true;void put('captures',this.capture).catch(()=>{});}this.send({type:'error',message});this.report(message);}
  background(message='手機進入背景或鎖定，無法保證持續收音；此份錄音標記中斷，請回前景由主控停止'){if(this.recorder?.state==='recording')this.fail(message);}
  async prepare(){
    if(!this.stream?.getAudioTracks().some(t=>t.readyState==='live')||!this.context||this.context.state!=='running')throw new Error('請重新授權麥克風並保持此頁在前景');
    const mime=['audio/webm;codecs=opus','audio/mp4','audio/ogg;codecs=opus'].find(m=>MediaRecorder.isTypeSupported(m));
    if(!mime)throw new Error('瀏覽器沒有支援的錄音格式');
    if(await getCapture(this.key))throw new Error('此 Session 已有本機錄音，請建立新房間');
    this.recorder=new MediaRecorder(this.stream,{mimeType:mime});
    const settings=this.stream.getAudioTracks()[0].getSettings();
    this.processing=summarizeProcessing(settings);
    // processing 為附加欄位：現行後端只讀 mime_type/sample_rate/channel_count，其餘忽略（向下相容）。
    this.send({type:'prepared',mime_type:this.recorder.mimeType,sample_rate:settings.sampleRate??this.context.sampleRate,channel_count:settings.channelCount??null,
      processing:{echo_cancellation:this.processing.echoCancellation,noise_suppression:this.processing.noiseSuppression,auto_gain_control:this.processing.autoGainControl,latency:this.processing.latency}});
  }
  async start(){
    if(this.recorder?.state==='recording')return;
    if(!this.recorder)throw new Error('未完成裝置準備，無法開始');
    this.stoppedByHost=false;
    this.chirps=[];
    this.capture={key:this.key,count:0,mime:this.recorder.mimeType,started:Date.now(),performance:performance.now(),done:false,interrupted:false,processing:this.processing,chirps:[]};
    await put('captures',this.capture);
    this.recorder.ondataavailable=event=>{
      if(!event.data.size)return;
      const created=Date.now();
      this.writes=this.writes.then(async()=>{
        // Backgrounded browsers can deliver a very large blob. Split bytes, not codecs;
        // ordered concatenation still reconstructs the exact original container.
        for(let offset=0;offset<event.data.size;offset+=4*1024*1024){
          const c=this.capture!,blob=event.data.slice(offset,offset+4*1024*1024,c.mime);
          const checksum=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',await blob.arrayBuffer())),v=>v.toString(16).padStart(2,'0')).join('');
          const index=c.count;
          const next={...c,count:index+1};
          await saveChunk({key:this.key+':'+index,capture:this.key,index,blob,checksum,created,uploaded:false},next);
          // A visibility/track error may arrive while IndexedDB is writing.
          next.interrupted ||= this.capture!.interrupted;
          this.capture=next;
        }
        void this.flush();
      }).catch(error=>{this.fail('本機暫存失敗：'+error.message);if(this.recorder?.state==='recording')this.recorder.stop();});
    };
    this.recorder.onerror=()=>this.fail('瀏覽器錄音裝置錯誤');
    this.recorder.onstop=()=>{
      const stopped=Date.now(),stoppedPerf=performance.now();
      this.writes=this.writes.then(async()=>{if(!this.capture)return;this.capture.done=true;this.capture.stopped=stopped;this.capture.duration=Math.max(0,stoppedPerf-this.capture.performance);if(!this.stoppedByHost)this.capture.interrupted=true;await put('captures',this.capture);void this.flush();});
    };
    this.recorder.onstart=()=>{
      this.capture!.started=Date.now();this.capture!.performance=performance.now();
      void put('captures',this.capture!).then(()=>{
        this.send({type:'started',client_ms:this.capture!.started,performance_ms:this.capture!.performance});
        this.report('本機錄音中；音訊每秒分段暫存與上傳');
      }).catch(error=>this.fail('無法保存開始資訊：'+error.message));
    };
    this.recorder.start(1000);
  }
  /** 主控手機播放同步嗶聲；錄音中會把播放時間存進本機 capture（IndexedDB）。 */
  async playChirp(){
    if(!this.context||this.context.state!=='running')throw new Error('請先授權麥克風並保持此頁在前景，才能播放同步嗶聲');
    const contextAt=playSyncChirp(this.context);
    const event:ChirpEvent={epoch_ms:Date.now()+(contextAt-this.context.currentTime)*1000,performance_ms:performance.now()+(contextAt-this.context.currentTime)*1000,context_s:contextAt};
    this.chirps=[...this.chirps,event];
    // 排進同一條寫入鏈，並在執行當下取 this.capture：分段寫入會以新物件取代 capture，提早抓的參考會遺失紀錄。
    this.writes=this.writes.then(async()=>{
      const c=this.capture;if(!c||c.done)return;
      c.chirps=[...(c.chirps??[]),event];await put('captures',c);
    }).catch(error=>this.report('同步嗶聲時間未能存入本機：'+(error as Error).message));
    return event;
  }
  /** 本機收音設定與時間紀錄（JSON），與音檔一起交給 analysis/。不含憑證。 */
  async downloadMeta(){
    const saved=await getCapture(this.key);
    const meta={schema:'cnc-capture-meta/1',room_code:this.identity.room_code,session_id:this.identity.session_id,source_label:this.identity.source_label,
      mime:saved?.mime??this.recorder?.mimeType??null,started_epoch_ms:saved?.started??null,started_performance_ms:saved?.performance??null,
      stopped_epoch_ms:saved?.stopped??null,duration_ms:saved?.duration??null,interrupted:saved?.interrupted??null,chunk_count:saved?.count??0,
      processing:saved?.processing??this.processing,chirps:saved?.chirps??this.chirps,context_sample_rate:this.context?.sampleRate??null,user_agent:navigator.userAgent};
    const url=URL.createObjectURL(new Blob([JSON.stringify(meta,null,2)],{type:'application/json'}));
    const a=document.createElement('a');a.href=url;a.download=`${this.identity.session_id||'local'}_${this.identity.source_label}.meta.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);
    return meta;
  }
  stop(){this.stoppedByHost=true;if(this.recorder?.state==='recording')this.recorder.stop();else void this.flush();}
  async sync(room:Room){
    this.room=room;
    const saved=await getCapture(this.key);
    if(saved&&room.started_at&&!room.recordings.find(r=>r.participant_id===this.identity.participant_id)?.actual_started_at){
      this.send({type:'started',client_ms:saved.started,performance_ms:saved.performance});
    }
    if(this.recorder?.state==='recording'){
      if(['finalizing','interrupted','completed'].includes(room.status))this.stop();
    }else if(saved&&!saved.done&&!this.capture){
      saved.done=true;saved.interrupted=true;saved.stopped=Date.now();await put('captures',saved);this.fail('頁面重新載入造成錄音中斷；已保存的分段可以補傳');
    }else if(room.status==='recording'&&!saved){
      this.fail('此裝置未持續錄音，不能在中途冒充完整聲源');
    }
    void this.flush();
  }
  async flush(){
    if(this.flushing)return;
    this.flushing=true;
    const base=`/rooms/${this.identity.room_code}/recordings/${this.identity.participant_id}`;
    try{
      for(const chunk of await chunks(this.key)){
        if(chunk.uploaded)continue;
        const capture=await getCapture(this.key);
        await api(base+'/chunks/'+chunk.index,this.identity,{method:'PUT',headers:{'Content-Type':capture?.mime||chunk.blob.type,'X-Checksum':chunk.checksum,'X-Created-At':String(chunk.created)},body:chunk.blob});
        await put('chunks',{...chunk,uploaded:true});
      }
      const c=await getCapture(this.key);
      if(c?.done&&!c.sealed&&c.count&&this.room&&['finalizing','interrupted','completed'].includes(this.room.status)){
        await api(base+'/finish',this.identity,{method:'POST',body:JSON.stringify({chunk_count:c.count,client_ms:c.stopped,duration_ms:c.duration??null,interrupted:c.interrupted})});
        await put('captures',{...c,sealed:true});
        this.report(c.interrupted?'可用音訊已保存，但錄音曾中斷':'本機音訊已完整儲存');
      }
    }catch(error){this.report('待補傳：'+(error as Error).message);}finally{this.flushing=false;}
  }
  async downloadLocal(){const parts=await chunks(this.key);if(!parts.length)throw new Error('目前沒有已保存音訊');const mime=parts[0].blob.type;const url=URL.createObjectURL(new Blob(parts.map(c=>c.blob),{type:mime}));const a=document.createElement('a');a.href=url;a.download='local-'+this.identity.source_label+(mime.includes('mp4')?'.m4a':mime.includes('ogg')?'.ogg':'.webm');a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}
  dispose(){if(this.recorder?.state==='recording'){this.fail('離開錄音工作階段');this.recorder.stop();}this.stream?.getTracks().forEach(t=>{t.onended=null;t.onmute=null;t.stop();});if(this.context)this.context.onstatechange=null;void this.context?.close();}
}
