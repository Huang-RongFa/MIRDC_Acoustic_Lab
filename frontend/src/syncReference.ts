import {recordingSyncOptions} from './recordingSyncOptions';
// A short, windowed chirp. Version this waveform together with the detector.
export const REFERENCE_VERSION='chirp-1';
export function referenceSignal(rate:number){
  const n=Math.round(rate*0.06),data=new Float32Array(n);
  for(let i=0;i<n;i++){
    const t=i/rate;
    data[i]=Math.sin(2*Math.PI*(900*t+3100*t*t/(2*0.06)))*Math.sin(Math.PI*i/(n-1))**2;
  }
  return data;
}

export class SyncReference {
  private silent=recordingSyncOptions().multiDeviceSyncEnabled;
  private context:AudioContext|null=null;
  private timer:ReturnType<typeof setTimeout>|undefined;
  private periodic:ReturnType<typeof setInterval>|undefined;
  private take='';
  private playing:Promise<void>|null=null;
  async enable(){
    if(this.silent)return;
    this.context??=new AudioContext();await this.context.resume();
    if(this.context.state!=='running')throw new Error('請開啟主控裝置音訊輸出，再開始錄音');
  }
  async play(){
    if(this.silent)return;
    if(this.playing)return this.playing;
    const ctx=this.context;
    if(!ctx||ctx.state!=='running')throw new Error('同步參考音未播放：主控音訊已暫停');
    const signal=referenceSignal(ctx.sampleRate),buffer=ctx.createBuffer(1,signal.length,ctx.sampleRate);
    buffer.copyToChannel(signal,0);
    const when=ctx.currentTime+0.05;
    for(const offset of [0,0.23,0.61]){
      const source=ctx.createBufferSource(),gain=ctx.createGain();
      source.buffer=buffer;gain.gain.value=0.35;source.connect(gain).connect(ctx.destination);
      source.start(when+offset);
    }
    this.playing=new Promise<void>(resolve=>setTimeout(resolve,850));
    try{await this.playing;}finally{this.playing=null;}
  }
  schedule(take:string,delay:number,report:(s:string)=>void){
    if(this.silent)return;
    if(this.take===take)return;
    this.clear();this.take=take;
    const play=()=>void this.play().catch(e=>report(e.message));
    this.timer=setTimeout(()=>{play();this.periodic=setInterval(play,10000);},Math.max(0,delay));
  }
  clear(){clearTimeout(this.timer);clearInterval(this.periodic);this.take='';}
  async finish(){this.clear();await this.playing;await this.play();}
  dispose(){this.clear();void this.context?.close();}
}
