export type Chunk={key:string;capture:string;index:number;blob:Blob;checksum:string;created:number;uploaded:boolean};
export type Capture={key:string;count:number;mime:string;started:number;performance:number;done:boolean;interrupted:boolean;stopped?:number;duration?:number;sealed?:boolean};
let connection:Promise<IDBDatabase>;
function database(){
  return connection??=new Promise((resolve,reject)=>{
    const request=indexedDB.open('cnc-capture-v1',1);
    request.onupgradeneeded=()=>{request.result.createObjectStore('chunks',{keyPath:'key'});request.result.createObjectStore('captures',{keyPath:'key'});};
    request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);
  });
}
export async function put(store:string,value:Chunk|Capture){
  const db=await database();
  return new Promise<void>((resolve,reject)=>{const tx=db.transaction(store,'readwrite');tx.objectStore(store).put(value);tx.oncomplete=()=>resolve();tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error);});
}
export async function getCapture(key:string):Promise<Capture|undefined>{
  const db=await database();return new Promise((resolve,reject)=>{const r=db.transaction('captures').objectStore('captures').get(key);r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});
}
export async function chunks(key:string):Promise<Chunk[]>{
  const db=await database();return new Promise((resolve,reject)=>{const r=db.transaction('chunks').objectStore('chunks').getAll(IDBKeyRange.bound(key+':',key+':\uffff'));r.onsuccess=()=>resolve((r.result as Chunk[]).sort((a,b)=>a.index-b.index));r.onerror=()=>reject(r.error);});
}
export async function saveChunk(chunk:Chunk,capture:Capture){
  const db=await database();return new Promise<void>((resolve,reject)=>{const tx=db.transaction(['chunks','captures'],'readwrite');tx.objectStore('chunks').put(chunk);tx.objectStore('captures').put(capture);tx.oncomplete=()=>resolve();tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error);});
}
