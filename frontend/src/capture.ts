import {api} from './api';
import {chunks,getCapture,put,saveChunk,type Capture} from './storage';
import type {Identity,Room} from './types';
import {recordingSyncOptions,saveRecordingSyncOptions,type RecordingSyncOptions} from './recordingSyncOptions';
import {PcmCapture} from './pcmCapture';

export class RecorderDevice {
  syncOptions=recordingSyncOptions();
  pcm:PcmCapture|null=null;
  stream:MediaStream|null=null;
  context:AudioContext|null=null;
  analyser:AnalyserNode|null=null;
  recorder:MediaRecorder|null=null;
  private recordingDestination:MediaStreamAudioDestinationNode|null=null;
  private capture:Capture|null=null;
  private writes=Promise.resolve();
  private flushing=false;
  private stoppedByHost=false;
  room:Room|null=null;
  personalStop=false;
  key:string;
  constructor(public identity:Identity,private send:(data:object)=>void,private report:(message:string)=>void){this.key=identity.session_id+'/'+identity.participant_id;}

  async configure(options:RecordingSyncOptions){
    if(this.recorder?.state==='recording'||(this.room&&this.room.status!=='waiting'))throw new Error('錄音準備或錄音期間不可變更收音設定');
    this.send({type:'mic',mic:false});
    await this.pcm?.dispose();this.pcm=null;
    if(this.context)this.context.onstatechange=null;
    this.stream?.getTracks().forEach(t=>{t.onended=null;t.onmute=null;t.stop();});
    await this.context?.close();this.context=null;this.stream=null;this.recorder=null;
    this.syncOptions={...options,multiDeviceSyncEnabled:true};
    saveRecordingSyncOptions(this.syncOptions);
    await this.authorize();
  }
  reportSettings(){
    const settings=this.stream?.getAudioTracks()[0]?.getSettings();
    this.send({type:'capture_settings',requested_sample_rate:this.syncOptions.requestedSampleRate,requested_channel_count:this.syncOptions.channelCount??1,input_sample_rate:settings?.sampleRate??null,actual_sample_rate:this.context?.sampleRate??null,channel_count:this.pcm?(this.syncOptions.channelCount??1):null,support_status:this.pcm?'ready':'unavailable'});
  }

  async authorize(){
    if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder)throw new Error('此瀏覽器需 HTTPS 及 MediaRecorder 支援');
    if(this.stream?.getAudioTracks().some(t=>t.readyState==='live')){await this.context?.resume();this.reportSettings();this.send({type:'mic',mic:true});return;}
    if(this.context){this.context.onstatechange=null;await this.context.close();}
    try{
      this.stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:false,noiseSuppression:false,autoGainControl:false,sampleRate:{ideal:this.syncOptions.requestedSampleRate},channelCount:{exact:this.syncOptions.channelCount??1}}});
      const settings=this.stream.getAudioTracks()[0].getSettings();
      if(this.syncOptions.channelCount===2&&settings.channelCount!==2)throw new Error('Stereo 未獲得兩個獨立輸入通道，請選擇 Mono');
      if(this.syncOptions.multiDeviceSyncEnabled){
        try{this.context=new AudioContext({sampleRate:this.syncOptions.requestedSampleRate});}catch{this.context=new AudioContext();}
      }else this.context=new AudioContext();
      await this.context.resume();
      // Explicitly select the first input for Mono. Never upmix Mono to Stereo.
      this.recordingDestination=this.context.createMediaStreamDestination();
      this.recordingDestination.channelCount=this.syncOptions.channelCount??1;
      this.recordingDestination.channelCountMode='explicit';
      this.recordingDestination.channelInterpretation='discrete';
      const source=this.context.createMediaStreamSource(this.stream);
      if(this.syncOptions.channelCount===2)source.connect(this.recordingDestination);
      else{const splitter=this.context.createChannelSplitter(2);source.connect(splitter);splitter.connect(this.recordingDestination,0,0);}
      if(this.syncOptions.multiDeviceSyncEnabled){
        this.pcm=new PcmCapture(this.context,this.stream,this.identity,this.syncOptions,this.report);
        await this.pcm.prepare();
      }
      this.analyser=this.context.createAnalyser();this.analyser.fftSize=512;
      this.context.createMediaStreamSource(this.stream).connect(this.analyser);
      this.stream.getAudioTracks()[0].onended=()=>this.fail('麥克風已停止，錄音可能不完整');
      this.stream.getAudioTracks()[0].onmute=()=>this.background('麥克風被系統暫停，錄音可能中斷');
      this.context.onstatechange=()=>{if(this.context?.state!=='running')this.background('音訊處理被系統暫停，錄音可能中斷');};
      await navigator.storage?.persist?.();
      this.reportSettings();
      this.send({type:'mic',mic:true});
      this.report('麥克風已連接，連線正常時會自動就緒，等待主控者開始錄音');
    }catch(error){
      const name=(error as Error).name;
      this.stream?.getTracks().forEach(t=>t.stop());this.stream=null;
      if(this.context)this.context.onstatechange=null;
      await this.pcm?.dispose();this.pcm=null;await this.context?.close();this.context=null;
      this.reportSettings();
      const reason=name==='NotAllowedError'?'麥克風權限遭拒，請在網站設定開啟權限':this.syncOptions.channelCount===2?'裝置不支援或無法確認 Stereo 雙通道，請選擇 Mono 後重新連接':name==='NotFoundError'?'找不到麥克風裝置':'麥克風或 AudioWorklet 無法使用，請確認裝置及瀏覽器支援';
      this.fail(reason,name==='NotAllowedError'?'denied':undefined);throw new Error(reason);
    }
  }
  samples(){return this.pcm?.getPreview()??null;}
  private fail(message:string,permission?:string){if(this.capture&&!this.capture.done){this.capture.interrupted=true;void put('captures',this.capture).catch(()=>{});}this.send({type:'error',message,permission});this.report(message);}
  background(message='手機進入背景或鎖定，無法保證持續收音；此份錄音標記中斷，請回前景由主控停止'){if(this.recorder?.state==='recording')this.fail(message);}
  async prepare(){
    if(!this.stream?.getAudioTracks().some(t=>t.readyState==='live')||!this.context||this.context.state!=='running')throw new Error('請重新授權麥克風並保持此頁在前景');
    const mime=['audio/webm;codecs=opus','audio/mp4','audio/ogg;codecs=opus'].find(m=>MediaRecorder.isTypeSupported(m));
    if(!mime)throw new Error('瀏覽器沒有支援的錄音格式');
    if(await getCapture(this.key))throw new Error('此 Session 已有本機錄音，請建立新房間');
    if(!this.recordingDestination)throw new Error('錄音輸出尚未準備');
    this.recorder=new MediaRecorder(this.recordingDestination.stream,{mimeType:mime});
    const settings=this.stream.getAudioTracks()[0].getSettings();
    this.send({type:'prepared',mime_type:this.recorder.mimeType,sample_rate:this.context.sampleRate,channel_count:this.syncOptions.channelCount??1});
    if(this.syncOptions.multiDeviceSyncEnabled)this.report(`輸入取樣率：${settings.sampleRate??'未知'} Hz；PCM 處理率：${this.context.sampleRate} Hz；要求：${this.syncOptions.requestedSampleRate} Hz。echoCancellation=${settings.echoCancellation??'未知'}、noiseSuppression=${settings.noiseSuppression??'未知'}、autoGainControl=${settings.autoGainControl??'未知'}。同步精度未驗證。`);
  }
  async start(){
    if(this.recorder?.state==='recording')return;
    if(!this.recorder)throw new Error('未完成裝置準備，無法開始');
    this.stoppedByHost=false;
    this.capture={key:this.key,count:0,mime:this.recorder.mimeType,started:Date.now(),performance:performance.now(),done:false,interrupted:false};
    await put('captures',this.capture);
    if(this.pcm)try{await this.pcm.start(this.room?.id??this.identity.session_id,this.room?.starts_at??null);}catch(e){this.report('PCM 擴充啟動失敗，原始錄音繼續：'+(e as Error).message);}
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
      void this.pcm?.stop(!this.stoppedByHost||!!this.capture?.interrupted);
      const stopped=Date.now(),stoppedPerf=performance.now();
      this.writes=this.writes.then(async()=>{if(!this.capture)return;this.capture.done=true;this.capture.stopped=stopped;this.capture.duration=Math.max(0,stoppedPerf-this.capture.performance);if(!this.stoppedByHost)this.capture.interrupted=true;await put('captures',this.capture);void this.flush();});
    };
    this.recorder.onstart=()=>{
      this.capture!.started=Date.now();this.capture!.performance=performance.now();
      void put('captures',this.capture!).then(()=>{
        if(this.room?.status==='recording')this.confirmStart();
        this.report('本機收音中（含倒數預錄）；原始音訊保留供同步驗證');
      }).catch(error=>this.fail('無法保存開始資訊：'+error.message));
    };
    this.recorder.start(1000);
  }
  stop(){this.stoppedByHost=true;if(this.recorder?.state==='recording')this.recorder.stop();else void this.flush();}
  async cancel(){
    if(this.recorder?.state==='recording'){
      const recorder=this.recorder;
      await new Promise<void>(resolve=>{recorder.addEventListener('stop',()=>resolve(),{once:true});recorder.stop();});
    }
    await this.writes;
    await this.pcm?.stop(true);
  }
  confirmStart(){if(this.capture)this.send({type:'started',client_ms:this.capture.started,performance_ms:this.capture.performance});}
  async sync(room:Room){
    if(!this.identity.source_label)return;
    const baseKey=room.id+'/'+this.identity.participant_id;
    let nextKey=baseKey+(room.starts_at?'/'+room.starts_at:'');
    // Older clients stored raw audio under the base key; keep recovery available.
    if(nextKey!==baseKey&&!await getCapture(nextKey)&&await getCapture(baseKey))nextKey=baseKey;
    if(this.key!==nextKey){
      if(this.recorder?.state==='recording'){
        const recorder=this.recorder;
        await new Promise<void>(resolve=>{recorder.addEventListener('stop',()=>resolve(),{once:true});recorder.stop();});
      }
      await this.writes;
      this.key=nextKey;
      this.capture=null;
      // The prepared MediaRecorder is reused when the countdown assigns its key.
      if(room.status!=='countdown')this.recorder=null;
    }
    this.room=room;
    const saved=await getCapture(this.key);
    if(room.status==='countdown'&&!saved&&this.recorder){await this.start();return;}
    if(saved&&(room.started_at||['finalizing','interrupted'].includes(room.status))&&!room.recordings.find(r=>r.participant_id===this.identity.participant_id)?.actual_started_at){
      this.send({type:'started',client_ms:saved.started,performance_ms:saved.performance});
    }
    if(this.capture&&room.starts_at&&room.stopped_at&&room.stopped_at<room.starts_at)this.capture.interrupted=true;
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
    if(!this.room||!['recording','finalizing','interrupted','completed'].includes(this.room.status))return;
    this.flushing=true;
    const base=`/rooms/${this.identity.room_code}/recordings/${this.identity.participant_id}`;
    try{
      for(const chunk of await chunks(this.key)){
        if(chunk.uploaded)continue;
        const capture=await getCapture(this.key);
        await api(base+'/chunks/'+chunk.index+'?take_id='+this.key.split('/')[0],this.identity,{method:'PUT',headers:{'Content-Type':capture?.mime||chunk.blob.type,'X-Checksum':chunk.checksum,'X-Created-At':String(chunk.created)},body:chunk.blob});
        await put('chunks',{...chunk,uploaded:true});
      }
      const c=await getCapture(this.key);
      if(c?.done&&!c.sealed&&c.count&&this.room&&(this.personalStop||['finalizing','interrupted','completed'].includes(this.room.status))){
        await api(base+'/finish?take_id='+this.key.split('/')[0],this.identity,{method:'POST',body:JSON.stringify({chunk_count:c.count,client_ms:c.stopped,duration_ms:c.duration??null,interrupted:c.interrupted})});
        await put('captures',{...c,sealed:true});
        this.report(c.interrupted?'可用音訊已保存，但錄音曾中斷':'本機音訊已完整儲存');
      }
    }catch(error){this.report('待補傳：'+(error as Error).message);}finally{this.flushing=false;}
  }
  async downloadLocal(){const parts=await chunks(this.key);if(!parts.length)throw new Error('目前沒有已保存音訊');const mime=parts[0].blob.type;const url=URL.createObjectURL(new Blob(parts.map(c=>c.blob),{type:mime}));const a=document.createElement('a');a.href=url;a.download='local-'+this.identity.source_label+(mime.includes('mp4')?'.m4a':mime.includes('ogg')?'.ogg':'.webm');a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}
  dispose(){if(this.recorder?.state==='recording'){this.fail('離開錄音工作階段');this.recorder.stop();}this.stream?.getTracks().forEach(t=>{t.onended=null;t.onmute=null;t.stop();});if(this.context)this.context.onstatechange=null;if(this.pcm)void this.pcm.dispose().finally(()=>this.context?.close());else void this.context?.close();}
}
