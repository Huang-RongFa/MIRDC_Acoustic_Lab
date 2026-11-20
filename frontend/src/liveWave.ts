export type LiveFrame={samples:number[];channels?:number[][];duration?:number;at:number};
export type WavePoint={at:number;values:number[];gap?:boolean};
export type LiveWave={points:WavePoint[];at:number;channelCount:number};
export function appendWave(previous:LiveWave|undefined,frame:LiveFrame):LiveWave{
  const channels=frame.channels??[frame.samples],duration=Math.min(1,Math.max(0,frame.duration??0.25))*1000,n=channels[0].length;
  const start=frame.at-duration;
  const retained=previous?.channelCount===channels.length?previous.points.filter(p=>p.at>=frame.at-10000&&p.at<start):[];
  const incoming=Array.from({length:n},(_,i)=>({at:start+(i+1)*duration/n,values:channels.map(c=>c[i]),gap:i===0&&!!retained.length&&start-retained[retained.length-1].at>100}));
  return {points:[...retained,...incoming],at:frame.at,channelCount:channels.length};
}
