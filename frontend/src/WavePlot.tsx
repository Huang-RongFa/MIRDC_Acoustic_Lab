import type {LiveWave} from './liveWave';
type Props={label:string;samples?:number[];duration?:number;color?:string;envelope?:boolean;live?:LiveWave;now?:number;channel?:number};

export function WavePlot({label,samples=[],duration,color='var(--green)',envelope=false,live,now,channel}:Props){
  const limit=1;
  const y=(value:number)=>50-48*value;
  const path=samples.length?samples.map((v,i)=>{
    const x=100*i/Math.max(1,samples.length-1);
    return envelope?`M${x} ${y(v)}V${y(-v)}`:`${i?'L':'M'}${x} ${y(v)}`;
  }).join(' '):'M0 50H100';
  const tick=(n:number)=>n.toFixed(2);
  const liveMode=now!=null;
  const visible=live?.points.filter(p=>p.at>=now!-10000&&p.at<=now!)??[];
  return <figure className="signal-plot" aria-label={label}>
    <figcaption>振幅（正規化）</figcaption>
    <div className="signal-grid"><div className="signal-scale"><span>{tick(limit)}</span><span>0.00</span><span>{tick(-limit)}</span></div>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label={label}>
        <path d="M0 2H100M0 50H100M0 98H100" stroke="#d5e0e2" vectorEffect="non-scaling-stroke"/>
        {liveMode?(channel==null?Array.from({length:live?.channelCount??1},(_,c)=>c):[channel]).map(c=><path key={c} data-channel={c===0?'L':'R'} d={visible.length&&c<(live?.channelCount??0)?visible.map((p,i)=>`${!i||p.gap?'M':'L'}${(p.at-now!+10000)/100} ${y(p.values[c])}`).join(' '):'M0 50H100'} stroke={channel!=null||c===0?color:'#bc7040'} fill="none" vectorEffect="non-scaling-stroke"/>):<path d={path} stroke={color} fill="none" vectorEffect="non-scaling-stroke"/>}
      </svg><div className="signal-time">{liveMode?[-10,-5,0].map(t=><span key={t}>{tick(t)}</span>):duration!=null&&[0,0.5,1].map(f=><span key={f}>{tick(f*duration)}</span>)}</div></div>
    <div className="signal-unit">{liveMode?'最近 10.00 秒（0.00 為現在）':'時間（s）'}{channel==null&&live?.channelCount===2&&<span> · <span style={{color}}>L</span>／<span style={{color:'#bc7040'}}>R</span></span>}</div>
  </figure>;
}
