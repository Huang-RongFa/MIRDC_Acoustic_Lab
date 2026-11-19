import {api,ApiError} from './api';
import {chunks,getCapture,getChunk,put,saveChunk,type Capture,type ChirpEvent} from './storage';
import {summarizeProcessing,processingLabel,type ProcessingReport} from './audioSettings';
import {playSyncChirp} from './syncChirp';
import type {Identity,Room} from './types';

export class RecorderDevice {
  stream:MediaStream|null=null;
  context:AudioContext|null=null;
  analyser:AnalyserNode|null=null;
  private rightAnalyser:AnalyserNode|null=null;
  private monoOutput:MediaStreamAudioDestinationNode|null=null;
  private authorizing=false;
  channelCount:1|2=1;
  private inputSettings:MediaTrackSettings|null=null;
  private inputCapabilities:MediaTrackCapabilities|null=null;
  recorder:MediaRecorder|null=null;
  private capture:Capture|null=null;
  private writes=Promise.resolve();
  private flushing:Promise<void>|null=null;
  private drainRequested=false;
  private retryTimer:ReturnType<typeof setTimeout>|undefined;
  private disposed=false;
  private uploadIndex=0;
  private inventoryNeeded=true;
  private failures=0;
  private interrupted=false;
  private startPending=false;
  private saving=false;
  private localError=false;
  private lastUpload:number|null=null;
  private httpStatus:number|null=null;
  private retries=0;
  private uploadState='等待錄音';
  private stoppedByHost=false;
  room:Room|null=null;
  /** getSettings() 實際回報的收音處理狀態；網頁的關閉要求不一定被瀏覽器採用。 */
  processing:ProcessingReport|null=null;
  /** 本機播放同步嗶聲的時間（僅主控手機會有），供分析交叉核對。 */
  chirps:ChirpEvent[]=[];
  key:string;
  constructor(public identity:Identity,private send:(data:object)=>void,private report:(message:string)=>void){this.key=identity.session_id+'/'+identity.participant_id;}

  async authorize(channels:1|2=1){
    if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder)throw new Error('此瀏覽器需 HTTPS 及 MediaRecorder 支援');
    if(this.disposed||this.authorizing||this.startPending||(this.recorder&&this.recorder.state!=='inactive')||
      (this.room&&this.room.status!=='waiting'))throw new Error('目前無法切換錄音聲道');
    this.authorizing=true;
    try{
      if(this.stream?.getAudioTracks().some(t=>t.readyState==='live')&&this.channelCount===channels&&this.context){
        await this.resumePreview();
        this.recordingStream();
        this.send({type:'mic',mic:true});
        return;
      }
      this.send({type:'mic',mic:false});
      this.releaseInput();
      this.stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:channels===2?{exact:2}:{ideal:1},echoCancellation:false,noiseSuppression:false,autoGainControl:false},video:false});
      if(this.disposed)throw new Error('已離開錄音工作階段');
      const track=this.stream.getAudioTracks()[0];
      this.inputSettings=track.getSettings();
      this.inputCapabilities=track.getCapabilities?.()??null;
      const inputChannels=this.inputSettings.channelCount;
      if(channels===2&&inputChannels!==2)throw new Error('瀏覽器未確認雙聲道輸入，請使用支援 Stereo 的裝置或選擇 Mono');
      if(!inputChannels)throw new Error('瀏覽器未回報麥克風聲道數，無法確認錄音聲道');
      this.processing=summarizeProcessing(this.inputSettings);
      const context=this.context=new AudioContext();
      this.analyser=context.createAnalyser();this.analyser.fftSize=512;
      const source=context.createMediaStreamSource(this.stream);
      if(channels===2){
        const splitter=context.createChannelSplitter(2);
        this.rightAnalyser=context.createAnalyser();
        this.rightAnalyser.fftSize=512;
        source.connect(splitter);
        splitter.connect(this.analyser,0);
        splitter.connect(this.rightAnalyser,1);
      }else if(inputChannels>1){
        // The speaker downmix averages stereo L/R. The meter and encoder receive the same mono bus.
        const mono=context.createGain();
        mono.channelCount=1;
        mono.channelCountMode='explicit';
        mono.channelInterpretation='speakers';
        this.monoOutput=context.createMediaStreamDestination();
        this.monoOutput.channelCount=1;
        source.connect(mono);
        mono.connect(this.analyser);
        mono.connect(this.monoOutput);
        context.onstatechange=()=>{
          if(context.state!=='running'&&this.recorder?.state==='recording')this.fail('單聲道擷取的音訊處理暫停');
        };
      }else source.connect(this.analyser);
      await this.resumePreview();
      if(this.disposed||track.readyState!=='live')throw new Error('麥克風已停止，請重新授權');
      this.channelCount=channels;
      this.recordingStream();
      track.onended=()=>{
        if(!this.saving&&!this.capture?.done)this.fail('麥克風已停止，錄音可能不完整');
      };
      track.onmute=()=>{if(this.recorder?.state==='recording')this.fail('麥克風被系統暫停，錄音可能中斷');};
      track.onunmute=()=>{if(this.recorder?.state==='recording')this.report('麥克風已恢復收音');};
      void navigator.storage?.persist?.().catch(()=>{});
      this.send({type:'mic',mic:true});
      this.report(this.processing?.raw===true?'麥克風已授權（原始收音）；確認波形後按下準備完成':'麥克風已授權，但'+processingLabel(this.processing)+'；可繼續錄音，分析時會標記');
    }catch(error){
      this.releaseInput();
      if(!this.disposed)this.fail('麥克風無法使用：'+(error as Error).message);
      throw error;
    }finally{
      this.authorizing=false;
    }
  }
  async resumePreview(){
    const context=this.context;
    if(!context)return;
    let timer:ReturnType<typeof setTimeout>|undefined;
    try{
      await Promise.race([context.resume(),new Promise<never>((_,reject)=>{
        timer=setTimeout(()=>reject(new Error('音訊處理啟動逾時，請點選重新授權')),5000);
      })]);
      if(context.state!=='running')throw new Error('音訊處理未啟動，請點選重新授權');
    }finally{clearTimeout(timer);}
  }
  private releaseInput(){
    for(const track of [...(this.stream?.getTracks()??[]),...(this.monoOutput?.stream.getTracks()??[])]){
      track.onended=track.onmute=track.onunmute=null;
      track.stop();
    }
    const context=this.context;
    this.stream=this.context=this.analyser=this.rightAnalyser=this.monoOutput=null;
    this.recorder=null;
    this.inputSettings=this.inputCapabilities=this.processing=null;
    if(context){
      context.onstatechange=null;
      void context.close().catch(()=>{});
    }
  }
  private recordingStream(){
    const input=this.stream?.getAudioTracks()[0];
    const stream=this.monoOutput?.stream??this.stream;
    const output=stream?.getAudioTracks()[0];
    if(!stream||input?.readyState!=='live'||output?.readyState!=='live')throw new Error('請重新授權麥克風並保持此頁在前景');
    if(input.getSettings().channelCount!==this.inputSettings?.channelCount||output.getSettings().channelCount!==this.channelCount)
      throw new Error('無法確認錄音聲道，請重新授權麥克風');
    if(this.monoOutput&&this.context?.state!=='running')throw new Error('請回前景重新啟用單聲道擷取');
    return stream;
  }
  samples(analyser=this.analyser){
    if(this.authorizing||!analyser||this.context?.state!=='running')return null;
    const values=new Float32Array(analyser.fftSize);
    analyser.getFloatTimeDomainData(values);
    return Array.from({length:values.length/4},(_,i)=>Math.max(-1,Math.min(1,values[i*4])));
  }
  get microphoneReady(){return !this.authorizing&&!!this.stream?.getAudioTracks().some(track=>track.readyState==='live');}
  rightSamples(){return this.rightAnalyser?this.samples(this.rightAnalyser):null;}
  private fail(message:string){
    if(this.capture&&!this.capture.done&&!this.interrupted){
      this.interrupted=true;
      this.writes=this.writes.then(async()=>{
        if(this.capture){this.capture.interrupted=true;await put('captures',this.capture);}
      }).catch(()=>{this.localError=true;});
    }
    this.send({type:'error',message});this.report(message);
  }
  background(){if(this.recorder?.state==='recording')this.report('手機進入背景或鎖定，請回前景確認錄音狀態');}
  async prepare(){
    const mime=['audio/webm;codecs=opus','audio/mp4','audio/ogg;codecs=opus'].find(m=>MediaRecorder.isTypeSupported(m));
    if(!mime)throw new Error('瀏覽器沒有支援的錄音格式');
    if(await getCapture(this.key))throw new Error('此 Session 已有本機錄音，請建立新房間');
    if(this.authorizing)throw new Error('麥克風仍在重新授權，請稍後再開始');
    const recordingStream=this.recordingStream();
    const input=this.stream!.getAudioTracks()[0].getSettings();
    this.recorder=new MediaRecorder(recordingStream,{mimeType:mime});
    const settings=recordingStream.getAudioTracks()[0].getSettings();
    this.processing=summarizeProcessing(input);
    // processing 為附加欄位：現行後端只讀 mime_type/sample_rate/channel_count，其餘忽略（向下相容）。
    this.send({type:'prepared',mime_type:this.recorder.mimeType,sample_rate:settings.sampleRate??null,channel_count:settings.channelCount??null,
      processing:{echo_cancellation:this.processing.echoCancellation,noise_suppression:this.processing.noiseSuppression,auto_gain_control:this.processing.autoGainControl,latency:this.processing.latency}});
  }
  async start(){
    if(this.startPending||this.capture||this.recorder?.state==='recording')return;
    if(!this.recorder)throw new Error('未完成裝置準備，無法開始');
    this.recordingStream();
    this.stoppedByHost=false;
    this.chirps=[];
    this.capture={key:this.key,count:0,mime:this.recorder.mimeType,started:Date.now(),performance:performance.now(),done:false,interrupted:false,processing:this.processing,chirps:[]};
    await put('captures',this.capture);
    this.startPending=true;
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
          next.interrupted ||= this.interrupted;
          this.capture=next;
        }
        void this.flush();
      }).catch(error=>{this.localError=true;this.fail('本機暫存失敗：'+error.message);if(this.recorder?.state!=='inactive')this.recorder?.stop();});
    };
    this.recorder.onerror=()=>this.fail('瀏覽器錄音裝置錯誤');
    this.recorder.onpause=()=>this.fail('瀏覽器錄音已暫停，音訊可能不完整');
    this.recorder.onresume=()=>this.report('瀏覽器錄音已恢復');
    this.recorder.onstop=()=>{
      const stopped=Date.now(),stoppedPerf=performance.now();
      this.saving=true;
      this.writes=this.writes.then(async()=>{
        if(!this.capture)return;
        const saved={...this.capture,done:true,stopped,duration:Math.max(0,stoppedPerf-this.capture.performance),
          interrupted:this.interrupted||!this.stoppedByHost||!this.capture.count};
        await put('captures',saved);
        this.capture=saved;
        this.saving=false;
        if(!saved.count)this.fail('錄音停止時沒有可保存的音訊');
        void this.flush();
      }).catch(error=>{this.saving=false;this.localError=true;this.fail('無法保存停止資訊：'+error.message);});
    };
    this.recorder.onstart=()=>{
      this.startPending=false;
      this.capture!.started=Date.now();this.capture!.performance=performance.now();
      this.writes=this.writes.then(async()=>{
        await put('captures',this.capture!);
        this.send({type:'started',client_ms:this.capture!.started,performance_ms:this.capture!.performance});
        this.report('本機錄音中；音訊每秒分段暫存與上傳');
      }).catch(error=>{this.localError=true;this.fail('無法保存開始資訊：'+error.message);});
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
  stop(){
    if(this.recorder&&this.recorder.state!=='inactive'){
      this.stoppedByHost=true;
      this.saving=true;
      this.recorder.stop();
    }else void this.flush();
  }
  async sync(room:Room){
    this.room=room;
    const saved=await getCapture(this.key);
    if(saved&&room.started_at&&!room.recordings.find(r=>r.participant_id===this.identity.participant_id)?.actual_started_at){
      this.send({type:'started',client_ms:saved.started,performance_ms:saved.performance});
    }
    if(this.recorder&&this.recorder.state!=='inactive'){
      if(['finalizing','interrupted','completed'].includes(room.status))this.stop();
    }else if(saved&&!saved.done&&!this.capture){
      saved.done=true;saved.interrupted=true;saved.stopped=Date.now();await put('captures',saved);this.capture=saved;
      this.report('頁面重新載入造成錄音中斷；已保存的分段可以補傳');
    }else if(saved&&!this.capture){
      this.capture=saved;
    }else if(room.status==='recording'&&!saved){
      this.fail('此裝置未持續錄音，不能在中途冒充完整聲源');
    }
    void this.flush();
  }
  flush(force=false):Promise<void>{
    if(force){clearTimeout(this.retryTimer);this.retryTimer=undefined;this.inventoryNeeded=true;}
    this.drainRequested=true;
    if(this.disposed||this.retryTimer)return this.flushing??Promise.resolve();
    return this.flushing??=this.drain().finally(()=>{this.flushing=null;if(this.drainRequested&&!this.retryTimer&&!this.disposed)void this.flush();});
  }
  private async drain(){
    const base=`/rooms/${this.identity.room_code}/recordings/${this.identity.participant_id}`;
    try{
      while(this.drainRequested&&!this.disposed){
        this.drainRequested=false;
        const c=await getCapture(this.key);
        if(!c)continue;
        if(c.sealed){this.uploadIndex=c.count;this.uploadState=c.interrupted?'錄音異常中斷；已保存可用音訊':'錄音儲存完成';continue;}
        if(!c.count||!this.room?.recordings.find(r=>r.participant_id===this.identity.participant_id)?.actual_started_at)continue;
        const inventory=this.inventoryNeeded
          ? await api<{chunks:{chunk_index:number;checksum:string}[]}>(base+'/chunks',this.identity,{},120000)
          : null;
        const received=new Map(inventory?.chunks.map(chunk=>[chunk.chunk_index,chunk.checksum]));
        this.inventoryNeeded=false;
        this.uploadState='本機已保存，正在上傳';
        while(this.uploadIndex<c.count&&!this.disposed){
          const chunk=await getChunk(this.key,this.uploadIndex);
          if(!chunk)throw new Error('本機缺少音訊分段 '+this.uploadIndex);
          if(received.has(chunk.index)&&received.get(chunk.index)!==chunk.checksum)throw new ApiError('伺服器與本機分段校驗值不符',422);
          if(!received.has(chunk.index)){
            await api(base+'/chunks/'+chunk.index,this.identity,{method:'PUT',headers:{'Content-Type':c.mime,'X-Checksum':chunk.checksum,'X-Created-At':String(chunk.created)},body:chunk.blob},120000);
          }
          if(!chunk.uploaded)await put('chunks',{...chunk,uploaded:true});
          this.uploadIndex++;
          this.lastUpload=Date.now();
          this.failures=0;
        }
        if(!this.disposed&&c.done&&this.uploadIndex===c.count&&['finalizing','interrupted','completed'].includes(this.room.status)){
          this.uploadState='上傳完成，正在驗證';
          const result=await api<{interrupted:boolean}>(base+'/finish',this.identity,{method:'POST',body:JSON.stringify({chunk_count:c.count,client_ms:c.stopped,duration_ms:c.duration??null,interrupted:c.interrupted})},120000);
          const sealed={...c,sealed:true,interrupted:result.interrupted||c.interrupted};
          await put('captures',sealed);
          this.capture=sealed;
          this.uploadState=sealed.interrupted?'錄音異常中斷；已保存可用音訊':'錄音儲存完成';
          this.report(this.uploadState);
        }
      }
    }catch(error){
      const status=error instanceof ApiError?error.status:null;
      this.httpStatus=status;
      this.inventoryNeeded=true;
      const retryable=status===null||[408,409,425,429].includes(status)||status>=500;
      this.uploadState=retryable?'等待補傳':'儲存驗證錯誤';
      this.report(this.uploadState+'：'+(error as Error).message+'。請保留網站儲存資料。');
      if(retryable&&!this.disposed){
        if(status===409)this.uploadIndex=0;
        this.retryTimer=setTimeout(()=>{this.retryTimer=undefined;this.retries++;void this.flush();},Math.min(60000,1000*2**Math.min(this.failures++,6)));
      }else this.drainRequested=false;
    }
  }
  diagnostics(){
    const count=this.capture?.count??this.uploadIndex;
    return {count,uploaded:this.uploadIndex,pending:Math.max(0,count-this.uploadIndex),retries:this.retries,
      httpStatus:this.httpStatus,lastUpload:this.lastUpload,interrupted:this.interrupted||!!this.capture?.interrupted,
      recorder:this.recorder?.state??'inactive',context:this.context?.state??'未啟動',channels:this.inputSettings?.channelCount,
      recordedChannels:this.monoOutput?1:this.inputSettings?.channelCount,sampleRate:this.inputSettings?.sampleRate,
      capability:this.inputCapabilities?.channelCount,mime:this.capture?.mime??this.recorder?.mimeType,
      captureState:this.localError?'本機儲存錯誤':this.saving?'停止收音，正在保存':this.recorder?.state==='recording'?'錄音中':this.capture?.done?(this.capture.interrupted?'錄音異常中斷':'本機已保存'):'等待錄音',
      uploadState:this.uploadState};
  }
  async downloadLocal(){const parts=await chunks(this.key);if(!parts.length)throw new Error('目前沒有已保存音訊');const mime=parts[0].blob.type;const url=URL.createObjectURL(new Blob(parts.map(c=>c.blob),{type:mime}));const a=document.createElement('a');a.href=url;a.download='local-'+this.identity.source_label+(mime.includes('mp4')?'.m4a':mime.includes('ogg')?'.ogg':'.webm');a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}
  dispose(){this.disposed=true;clearTimeout(this.retryTimer);if(this.recorder&&this.recorder.state!=='inactive'){this.fail('離開錄音工作階段');this.recorder.stop();}this.releaseInput();}
}
