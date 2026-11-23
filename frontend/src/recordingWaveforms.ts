export const channelColors=['#007f89','#c15e24'] as const;
const bins=800;
export type Peaks={min:Float32Array;max:Float32Array};

export async function peakEnvelope(samples:Float32Array,signal:AbortSignal):Promise<Peaks>{
  const count=Math.min(bins,samples.length);
  const min=new Float32Array(count),max=new Float32Array(count);
  const batch=Math.max(1,Math.floor(count*262144/samples.length));
  for(let start=0;start<count;start+=batch){
    signal.throwIfAborted();
    for(let i=start;i<Math.min(start+batch,count);i++){
      const from=Math.floor(i*samples.length/count),to=Math.floor((i+1)*samples.length/count);
      let low=samples[from],high=low;
      for(let j=from+1;j<to;j++){low=Math.min(low,samples[j]);high=Math.max(high,samples[j]);}
      min[i]=low;max[i]=high;
    }
    if(start+batch<count)await new Promise(resolve=>setTimeout(resolve,0));
  }
  return {min,max};
}

export function drawWaveform(canvas:HTMLCanvasElement,title:string,duration:number,series:{peaks:Peaks;color:string}[]){
  const ctx=canvas.getContext('2d');
  if(!ctx)return;
  canvas.width=800;canvas.height=340;
  const left=124,right=756,top=92,bottom=250;
  const y=(v:number)=>top+(1-v)*(bottom-top)/2;
  ctx.fillStyle='#f8fbfb';ctx.fillRect(0,0,800,340);
  ctx.fillStyle='#243b41';ctx.font='bold 28px sans-serif';ctx.fillText(title,24,36);
  ctx.font='24px sans-serif';
  if(series.length===2){
    ['L (Left)','R (Right)'].forEach((label,i)=>{
      const x=124+i*156;
      ctx.fillStyle=series[i].color;ctx.fillRect(x,58,26,5);
      ctx.fillStyle='#243b41';ctx.fillText(label,x+34,68);
    });
  }
  ctx.textAlign='right';
  for(const value of [1,0,-1]){
    const py=y(value);
    ctx.strokeStyle='#b7cacc';ctx.beginPath();ctx.moveTo(left,py);ctx.lineTo(right,py);ctx.stroke();
    ctx.fillText(value.toFixed(1),left-10,py+7);
  }
  ctx.strokeStyle='#759397';ctx.beginPath();ctx.moveTo(left,top);ctx.lineTo(left,bottom);ctx.stroke();
  ctx.textAlign='center';
  for(const fraction of [0,.25,.5,.75,1])ctx.fillText((duration*fraction).toFixed(2),left+(right-left)*fraction,282);
  ctx.fillText('Time (s)',(left+right)/2,320);
  ctx.save();ctx.translate(38,(top+bottom)/2);ctx.rotate(-Math.PI/2);ctx.fillText('Amplitude',0,0);ctx.restore();
  ctx.save();ctx.beginPath();ctx.rect(left-1,top-1,right-left+2,bottom-top+2);ctx.clip();
  // Give the background trace a wider stroke so coincident peaks retain both colors.
  for(const {peaks,color} of [...series].reverse()){
    ctx.strokeStyle=color;ctx.lineWidth=series.length===2&&color===channelColors[1]?1.8:1;
    ctx.beginPath();
    for(let i=0;i<peaks.min.length;i++){
      const x=left+(i+.5)*(right-left)/peaks.min.length;
      const highest=y(peaks.max[i]),lowest=y(peaks.min[i]);
      ctx.moveTo(x,highest);ctx.lineTo(x,Math.max(highest+1,lowest));
    }
    ctx.stroke();
  }
  ctx.restore();
}
