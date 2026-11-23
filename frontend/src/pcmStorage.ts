export type PcmMetadata={key:string;room_code:string;session_id:string;device_id:string;requested_sample_rate:number;actual_sample_rate:number;input_sample_rate:number|null;sample_count:number;chunk_count:number;channel_count:1|2;audio_format:'float32le';sync_status:'unverified'|'failed';complete:boolean;scheduled_server_ms:number|null;recording_started_at?:number;context_frame?:number;start_context_time?:number;clock_uncertainty_ms:number|null;error?:string;settings:MediaTrackSettings};
export type PcmChunk={key:string;capture:string;sequence_number:number;sample_start:number;sample_count:number;actual_sample_rate:number;samples:Float32Array};
let connection:Promise<IDBDatabase>;
function database(){return connection??=new Promise((resolve,reject)=>{const r=indexedDB.open('cnc-sync-pcm-v1',1);r.onupgradeneeded=()=>{r.result.createObjectStore('metadata',{keyPath:'key'});const chunks=r.result.createObjectStore('chunks',{keyPath:'key'});chunks.createIndex('capture','capture');};r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});}
export async function savePcm(metadata:PcmMetadata,chunk?:PcmChunk){
  const db=await database();return new Promise<void>((resolve,reject)=>{const tx=db.transaction(['metadata','chunks'],'readwrite');tx.objectStore('metadata').put(metadata);if(chunk)tx.objectStore('chunks').add(chunk);tx.oncomplete=()=>resolve();tx.onabort=()=>reject(tx.error??new Error('PCM transaction aborted'));});
}
export async function loadPcm(key:string){
  const db=await database();return new Promise<{metadata:PcmMetadata;chunks:PcmChunk[]}>((resolve,reject)=>{const tx=db.transaction(['metadata','chunks']);const m=tx.objectStore('metadata').get(key),c=tx.objectStore('chunks').index('capture').getAll(key);tx.oncomplete=()=>resolve({metadata:m.result,chunks:(c.result as PcmChunk[]).sort((a,b)=>a.sequence_number-b.sequence_number)});tx.onerror=()=>reject(tx.error);});
}
export async function pcmHistory(room:string,device:string){
  const db=await database();return new Promise<PcmMetadata[]>((resolve,reject)=>{const r=db.transaction('metadata').objectStore('metadata').getAll();r.onsuccess=()=>resolve((r.result as PcmMetadata[]).filter(m=>m.room_code===room&&m.device_id===device));r.onerror=()=>reject(r.error);});
}
export function pcmWav(metadata:PcmMetadata,chunks:PcmChunk[]){
  const channels=metadata.channel_count??1;
  let count=0;
  chunks.forEach((c,i)=>{if(c.sequence_number!==i||c.sample_start!==count||c.samples.length!==c.sample_count*channels||c.actual_sample_rate!==metadata.actual_sample_rate)throw new Error('PCM 區塊遺失或順序錯誤');count+=c.sample_count;});
  if(count!==metadata.sample_count||chunks.length!==metadata.chunk_count||!count)throw new Error('PCM 樣本數不完整');
  if(count*channels*4>0xffffffff-36)throw new Error('PCM 超過 WAV 大小限制，保留本機區塊');
  const header=new ArrayBuffer(44),v=new DataView(header);const text=(o:number,s:string)=>{for(let i=0;i<s.length;i++)v.setUint8(o+i,s.charCodeAt(i));};
  text(0,'RIFF');v.setUint32(4,36+count*channels*4,true);text(8,'WAVE');text(12,'fmt ');v.setUint32(16,16,true);v.setUint16(20,3,true);v.setUint16(22,channels,true);v.setUint32(24,metadata.actual_sample_rate,true);v.setUint32(28,metadata.actual_sample_rate*channels*4,true);v.setUint16(32,channels*4,true);v.setUint16(34,32,true);text(36,'data');v.setUint32(40,count*channels*4,true);
  const parts:BlobPart[]=[header];
  for(const chunk of chunks){const bytes=new ArrayBuffer(chunk.samples.length*4),view=new DataView(bytes);chunk.samples.forEach((s,i)=>view.setFloat32(i*4,s,true));parts.push(bytes);}
  return new Blob(parts,{type:'audio/wav'});
}
