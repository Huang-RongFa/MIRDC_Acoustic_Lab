import workletUrl from './pcmCapture.worklet.js?url';
import {savePcm,type PcmMetadata,type PcmChunk} from './pcmStorage';
import type {Identity} from './types';
import type {RecordingSyncOptions} from './recordingSyncOptions';

export class PcmCapture {
  private node:AudioWorkletNode|null=null;
  private source:MediaStreamAudioSourceNode|null=null;
  private writes=Promise.resolve();
  private metadata:PcmMetadata|null=null;
  private stopped:(()=>void)|null=null;
  private pending=0;
  private active=false;
  private failed=false;
  private stopPromise:Promise<void>|null=null;
  private previews:{channels:number[][];duration:number}[]=[];
  getPreview(){
    if(!this.previews.length)return null;
    const frames=this.previews.splice(0),channels=Array.from({length:this.options.channelCount??1},(_,c)=>frames.flatMap(f=>f.channels[c]));
    return {samples:channels[0],channels,duration:frames.reduce((sum,f)=>sum+f.duration,0)};
  }
  clock:{server:number;local:number;uncertainty:number}|null=null;
  constructor(private context:AudioContext,private stream:MediaStream,private identity:Identity,private options:RecordingSyncOptions,private report:(s:string)=>void){}
  async prepare(){
    if(this.node)return;
    await this.context.audioWorklet.addModule(workletUrl);
    this.node=new AudioWorkletNode(this.context,'cnc-pcm-capture',{numberOfInputs:1,numberOfOutputs:1,outputChannelCount:[1],channelCountMode:'max',channelInterpretation:'discrete',processorOptions:{channelCount:this.options.channelCount??1}});
    this.source=this.context.createMediaStreamSource(this.stream);this.source.connect(this.node);this.node.connect(this.context.destination);
    let ready:()=>void=()=>{},rejectReady:(e:Error)=>void=()=>{};
    const verified=new Promise<void>((resolve,reject)=>{ready=resolve;rejectReady=reject;});
    const timer=setTimeout(()=>rejectReady(new Error('無法確認 AudioWorklet 實際通道，請重新連接麥克風')),3000);
    this.node.port.onmessage=({data})=>{
      if(data.type==='input_ready'){clearTimeout(timer);ready();return;}
      if(data.type==='preview'){this.previews.push(data);if(this.previews.length>4)this.previews.shift();return;}
      if(data.type==='error'){clearTimeout(timer);rejectReady(new Error(data.message));this.fail(data.message);return;}
      if(!this.metadata)return;
      if(data.type==='stopped'){this.stopped?.();return;}
      if(data.type==='started'){
        this.metadata.start_context_time=data.context_time;this.metadata.context_frame=data.context_frame;
        // AudioContext time is mapped to the local monotonic clock at scheduling.
        this.metadata.recording_started_at=this.clock?this.clock.server+(data.context_time-this.context.currentTime)*1000+performance.now()-this.clock.local:undefined;
      }
      if(data.type==='chunk'&&!this.failed){
        if(data.sequence_number!==this.metadata.chunk_count||data.sample_start!==this.metadata.sample_count||data.actual_sample_rate!==this.context.sampleRate||data.channel_count!==this.metadata.channel_count){this.fail('PCM 樣本順序或通道數不一致');return;}
        if(++this.pending>128){this.fail('本機 PCM 寫入跟不上收音；原始錄音仍繼續');return;}
        this.metadata.sample_count+=data.sample_count;this.metadata.chunk_count++;
        const metadata={...this.metadata},chunk:PcmChunk={key:metadata.key+':'+data.sequence_number,capture:metadata.key,sequence_number:data.sequence_number,sample_start:data.sample_start,sample_count:data.sample_count,actual_sample_rate:data.actual_sample_rate,samples:data.samples};
        this.writes=this.writes.then(()=>savePcm(metadata,chunk)).catch(e=>this.fail('PCM 暫存失敗：'+e.message)).finally(()=>{this.pending--;});
      }
    };
    this.node.onprocessorerror=()=>{clearTimeout(timer);rejectReady(new Error('AudioWorklet 已停止'));this.fail('AudioWorklet 已停止；原始錄音仍繼續');};
    try{await verified;}finally{clearTimeout(timer);}
  }
  private fail(message:string){this.failed=true;if(this.metadata){this.metadata.sync_status='failed';this.metadata.error=message;}this.node?.port.postMessage({type:'stop'});this.report(message);}
  async start(session:string,scheduled:number|null){
    if(this.stopPromise)await this.stopPromise;
    if(this.active)return;
    await this.prepare();this.failed=false;this.stopPromise=null;
    const settings=this.stream.getAudioTracks()[0].getSettings();
    const clock=this.clock&&performance.now()-this.clock.local<30000?this.clock:null;
    const delay=scheduled!=null&&clock?(scheduled-clock.server-performance.now()+clock.local)/1000:0;
    this.metadata={key:session+'/'+this.identity.participant_id+'/'+crypto.randomUUID(),room_code:this.identity.room_code,session_id:session,device_id:this.identity.participant_id,requested_sample_rate:this.options.requestedSampleRate,actual_sample_rate:this.context.sampleRate,input_sample_rate:settings.sampleRate??null,sample_count:0,chunk_count:0,channel_count:this.options.channelCount??1,audio_format:'float32le',sync_status:'unverified',complete:false,scheduled_server_ms:scheduled,clock_uncertainty_ms:clock?.uncertainty??null,settings};
    await savePcm(this.metadata);this.active=true;
    this.node!.port.postMessage({type:'start',at:this.context.currentTime+Math.max(0,delay)});
    this.report(`PCM 附加錄音：${this.context.sampleRate} Hz；${clock?'依共同時間排程，精度未驗證':'缺少有效校時，未驗證同步'}。附加 PCM 僅保存在此瀏覽器，請匯出。`);
  }
  stop(interrupted=false):Promise<void>{
    if(this.stopPromise)return this.stopPromise;
    if(!this.active)return Promise.resolve();
    this.stopPromise=(async()=>{
      if(interrupted&&this.metadata){this.metadata.error='收音曾中斷';this.metadata.sync_status='failed';}
      await new Promise<void>(resolve=>{const timer=setTimeout(()=>{this.fail('PCM 停止確認逾時');resolve();},2000);this.stopped=()=>{clearTimeout(timer);resolve();};this.node?.port.postMessage({type:'stop'});});
      await this.writes;
      if(this.metadata){this.metadata.complete=!this.failed&&!interrupted&&this.metadata.sample_count>0;if(!this.metadata.sample_count){this.metadata.sync_status='failed';this.metadata.error='尚未取得 PCM 樣本';}await savePcm(this.metadata).catch(e=>this.report('PCM 完成資訊未保存：'+e.message));}
      this.active=false;this.stopped=null;
    })();return this.stopPromise;
  }
  async dispose(){await this.stop(true);this.source?.disconnect();this.node?.disconnect();this.node?.port.close();this.node=null;}
}
