// Only sample capture runs here. Storage, checksums and export run on the main thread.
class PcmCapture extends AudioWorkletProcessor {
  constructor(options){
    super();this.active=false;this.offset=0;this.sequence=0;this.used=0;
    this.channels=options.processorOptions?.channelCount===2?2:1;
    this.verified=false;
    this.buffer=new Float32Array(4096*this.channels);this.startAt=Infinity;
    this.preview=Array.from({length:this.channels},()=>[]);this.peaks=new Array(this.channels).fill(0);this.previewFrames=0;this.binFrames=0;
    this.port.onmessage=({data})=>{
      if(data.type==='start'){this.offset=0;this.sequence=0;this.used=0;this.startAt=data.at;this.active=true;}
      if(data.type==='stop'){this.flush();this.active=false;this.port.postMessage({type:'stopped',sample_count:this.offset});}
    };
  }
  flush(){
    if(!this.used)return;
    const samples=this.buffer.slice(0,this.used*this.channels);
    this.port.postMessage({type:'chunk',sequence_number:this.sequence++,sample_start:this.offset,sample_count:this.used,channel_count:this.channels,actual_sample_rate:sampleRate,samples},[samples.buffer]);
    this.offset+=this.used;this.used=0;
  }
  process(inputs){
    const channels=inputs[0];
    if(!channels?.length)return true;
    if(channels.length<this.channels){this.active=false;this.port.postMessage({type:'error',message:'裝置未提供兩個獨立通道，請改用 Mono'});return false;}
    if(!this.verified){this.verified=true;this.port.postMessage({type:'input_ready',channel_count:channels.length});}
    for(let i=0;i<channels[0].length;i++){
      for(let c=0;c<this.channels;c++)if(Math.abs(channels[c][i])>Math.abs(this.peaks[c]))this.peaks[c]=channels[c][i];
      this.binFrames++;this.previewFrames++;
      if(this.binFrames>=Math.round(sampleRate/100)){
        for(let c=0;c<this.channels;c++){this.preview[c].push(this.peaks[c]);this.peaks[c]=0;}
        this.binFrames=0;
      }
      if(this.preview[0].length>=25){
        this.port.postMessage({type:'preview',channels:this.preview,duration:this.previewFrames/sampleRate});
        this.preview=Array.from({length:this.channels},()=>[]);this.previewFrames=0;
      }
      if(!this.active)continue;
      if(currentTime+i/sampleRate<this.startAt)continue;
      if(this.offset===0&&this.used===0)this.port.postMessage({type:'started',context_time:currentTime+i/sampleRate,context_frame:currentFrame+i});
      for(let c=0;c<this.channels;c++)this.buffer[this.used*this.channels+c]=channels[c][i];
      this.used++;
      if(this.used===4096)this.flush();
    }
    return true;
  }
}
registerProcessor('cnc-pcm-capture',PcmCapture);
