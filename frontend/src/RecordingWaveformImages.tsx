import {useLayoutEffect,useRef,useState} from 'react';
import {channelColors,drawWaveform,type Peaks} from './recordingWaveforms';

const stereoCharts=[
  {title:'Stereo Combined Waveform',filename:'recording_stereo_combined.png',channels:[0,1]},
  {title:'Left Channel Waveform',filename:'recording_left_channel.png',channels:[0]},
  {title:'Right Channel Waveform',filename:'recording_right_channel.png',channels:[1]},
];
const monoCharts=[{title:'Mono Waveform',filename:'recording_mono.png',channels:[0]}];

function download(blob:Blob,filename:string){
  const url=URL.createObjectURL(blob);
  const link=document.createElement('a');
  link.href=url;link.download=filename;link.click();
  setTimeout(()=>URL.revokeObjectURL(url),10000);
}

function png(canvas:HTMLCanvasElement){
  return new Promise<Blob>((resolve,reject)=>canvas.toBlob(blob=>{
    if(blob)resolve(blob);
    else reject(new Error('無法輸出 PNG'));
  },'image/png'));
}

// PNG data is already compressed. Store it directly in a ZIP so a single download
// works in browsers that block multiple automatic file downloads.
async function zip(files:{filename:string;blob:Blob}[]){
  const local:BlobPart[]=[],directory:BlobPart[]=[];
  let offset=0,directorySize=0;
  for(const {filename,blob} of files){
    const name=new TextEncoder().encode(filename);
    const data=new Uint8Array(await blob.arrayBuffer());
    let crc=-1;
    for(const byte of data){
      crc^=byte;
      for(let bit=0;bit<8;bit++)crc=(crc>>>1)^((crc&1)?0xedb88320:0);
    }
    const header=new DataView(new ArrayBuffer(30));
    header.setUint32(0,0x04034b50,true);
    header.setUint16(4,20,true);
    header.setUint16(12,33,true); // DOS date 1980-01-01
    header.setUint32(14,~crc,true);
    header.setUint32(18,data.length,true);
    header.setUint32(22,data.length,true);
    header.setUint16(26,name.length,true);
    const entry=new DataView(new ArrayBuffer(46));
    entry.setUint32(0,0x02014b50,true);
    entry.setUint16(4,20,true);
    new Uint8Array(entry.buffer).set(new Uint8Array(header.buffer,4,26),6);
    entry.setUint32(42,offset,true);
    local.push(header.buffer,name,data);
    directory.push(entry.buffer,name);
    offset+=30+name.length+data.length;
    directorySize+=46+name.length;
  }
  const end=new DataView(new ArrayBuffer(22));
  end.setUint32(0,0x06054b50,true);
  end.setUint16(8,files.length,true);end.setUint16(10,files.length,true);
  end.setUint32(12,directorySize,true);end.setUint32(16,offset,true);
  return new Blob([...local,...directory,end.buffer],{type:'application/zip'});
}

export function RecordingWaveformImages({peaks,duration}:{peaks:Peaks[];duration:number}){
  const canvases=useRef<(HTMLCanvasElement|null)[]>([]);
  const [exporting,setExporting]=useState(false),[error,setError]=useState('');
  const charts=peaks.length===2?stereoCharts:monoCharts;
  useLayoutEffect(()=>{
    charts.forEach(({title,channels},i)=>drawWaveform(canvases.current[i]!,title,duration,
      channels.map(c=>({peaks:peaks[c],color:channelColors[c]}))));
  },[charts,duration,peaks]);

  const exportImages=async(index?:number)=>{
    setExporting(true);setError('');
    try{
      if(index!=null){download(await png(canvases.current[index]!),charts[index].filename);return;}
      const files=await Promise.all(charts.map(async({filename},i)=>({filename,blob:await png(canvases.current[i]!)})));
      download(await zip(files),'recording_waveforms.zip');
    }catch{setError('波形圖片下載失敗，請重試。');}
    finally{setExporting(false);}
  };
  return <div className="recording-waveform-images">
    {charts.length===3&&<button className="ghost-btn" type="button" disabled={exporting} onClick={()=>void exportImages()}>下載全部三張 PNG（ZIP）</button>}
    {charts.map(({title},i)=><figure key={title}>
      <canvas role="img" aria-label={title} ref={node=>{canvases.current[i]=node;}}/>
      <button className="ghost-btn" type="button" aria-label={`下載 ${title} PNG`} disabled={exporting} onClick={()=>void exportImages(i)}>下載 PNG</button>
    </figure>)}
    {error&&<p role="status">{error}</p>}
  </div>;
}
