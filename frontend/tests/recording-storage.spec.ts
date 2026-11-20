import {expect,test} from '@playwright/test';

test('indexed reads preserve legacy chunks and committed local audio after reload',async({page})=>{
  await page.goto('/');
  const modulePath='/src/storage.ts';
  await page.evaluate(async path=>{
    // Write the pre-existing IndexedDB format first, as an older client would.
    const db=await new Promise<IDBDatabase>((resolve,reject)=>{
      const open=indexedDB.open('cnc-capture-v1',1);
      open.onupgradeneeded=()=>{
        open.result.createObjectStore('chunks',{keyPath:'key'});
        open.result.createObjectStore('captures',{keyPath:'key'});
      };
      open.onsuccess=()=>resolve(open.result);
      open.onerror=()=>reject(open.error);
    });
    const capture={key:'room/device',count:1,mime:'audio/webm',started:1,performance:1,done:false,interrupted:false};
    const chunk={key:capture.key+':0',capture:capture.key,index:0,blob:new Blob(['first']),checksum:'first',created:2,uploaded:true};
    await new Promise<void>((resolve,reject)=>{
      const tx=db.transaction(['captures','chunks'],'readwrite');
      tx.objectStore('captures').put(capture);
      tx.objectStore('chunks').put(chunk);
      tx.oncomplete=()=>resolve();
      tx.onabort=()=>reject(tx.error);
    });
    db.close();
    const {saveChunk}=await import(path);
    await saveChunk({...chunk,key:capture.key+':1',index:1,blob:new Blob(['tail']),checksum:'tail',created:3,uploaded:false},
      {...capture,count:2,done:true,stopped:4});
  },modulePath);
  await page.reload();
  const saved=await page.evaluate(async path=>{
    const {getCapture,getChunk}=await import(path);
    const capture=await getCapture('room/device');
    const first=await getChunk(capture.key,0);
    const tail=await getChunk(capture.key,1);
    return {count:capture.count,done:capture.done,first:await first.blob.text(),tail:await tail.blob.text(),
      uploaded:[first.uploaded,tail.uploaded],missing:await getChunk(capture.key,2)};
  },modulePath);
  expect(saved).toEqual({count:2,done:true,first:'first',tail:'tail',uploaded:[true,false],missing:undefined});
});
