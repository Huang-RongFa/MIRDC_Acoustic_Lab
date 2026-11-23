import {test,expect} from '@playwright/test';

test('real MediaRecorder preserves preroll, confirms it once active, and uploads complete raw audio',async({page})=>{
  await page.context().grantPermissions(['microphone']);
  await page.route('**/api/rooms/SYNC01/recordings/**',route=>route.fulfill({json:{ok:true}}));
  await page.goto('/');
  const result=await page.evaluate(async()=>{
    const path='/src/capture.ts',storagePath='/src/storage.ts';
    const {RecorderDevice}=await import(path),{getCapture,chunks}=await import(storagePath);
    const events:Record<string,unknown>[]=[],messages:string[]=[];
    const identity={session_id:'take-sync',participant_id:'p1',room_code:'SYNC01',source_label:'A',token:'test',is_host:true};
    const device=new RecorderDevice(identity,(e:Record<string,unknown>)=>events.push(e),(s:string)=>messages.push(s));
    const room={id:'take-sync',status:'waiting',starts_at:null,started_at:null,recordings:[],participants:[]};
    await device.sync(room);await device.authorize();await device.prepare();
    const startsAt=Date.now()+3000;
    await device.sync({...room,status:'countdown',starts_at:startsAt});
    await new Promise(resolve=>setTimeout(resolve,3300));
    const preroll=await getCapture(device.key),before=events.filter(e=>e.type==='started').length;
    await device.sync({...room,status:'recording',starts_at:startsAt,started_at:startsAt});
    await new Promise(resolve=>setTimeout(resolve,1200));
    await device.sync({...room,status:'finalizing',starts_at:startsAt,started_at:startsAt});
    let saved=await getCapture(device.key);
    for(let i=0;i<50&&!saved?.done;i++){await new Promise(resolve=>setTimeout(resolve,50));saved=await getCapture(device.key);}
    const parts=await chunks(device.key),context=new AudioContext();
    const audio=await context.decodeAudioData(await new Blob(parts.map((p:{blob:Blob})=>p.blob),{type:saved.mime}).arrayBuffer());
    await context.close();device.dispose();
    return {before,started:events.filter(e=>e.type==='started').length,preMs:startsAt-preroll.started,duration:audio.duration,done:saved.done,interrupted:saved.interrupted,messages};
  });
  expect(result.before).toBe(0);expect(result.started).toBeGreaterThan(0);
  expect(result.preMs).toBeGreaterThan(2500);expect(result.duration).toBeGreaterThan(4);
  expect(result.done).toBe(true);expect(result.interrupted).toBe(false);
});

test('cancelled countdown retains its raw capture and allows a fresh countdown',async({page})=>{
  await page.context().grantPermissions(['microphone']);await page.goto('/');
  const result=await page.evaluate(async()=>{
    const path='/src/capture.ts',storagePath='/src/storage.ts';
    const {RecorderDevice}=await import(path),{getCapture}=await import(storagePath);
    const device=new RecorderDevice({session_id:'cancel-take',participant_id:'p',room_code:'SYNC01',source_label:'A'},()=>{},()=>{});
    const room={id:'cancel-take',status:'waiting',starts_at:null,started_at:null,recordings:[]};
    await device.sync(room);await device.authorize();await device.prepare();
    await device.sync({...room,status:'countdown',starts_at:Date.now()+3000});
    await new Promise(resolve=>setTimeout(resolve,300));const oldKey=device.key;
    await device.cancel();await device.sync(room);
    await device.prepare();await device.sync({...room,status:'countdown',starts_at:Date.now()+3000});
    await new Promise(resolve=>setTimeout(resolve,300));
    const active=device.recorder.state,newKey=device.key,old=await getCapture(oldKey);
    await device.cancel();device.dispose();return {active,oldKey,newKey,done:old.done,interrupted:old.interrupted};
  });
  expect(result.active).toBe('recording');expect(result.newKey).not.toBe(result.oldKey);
  expect(result.done).toBe(true);expect(result.interrupted).toBe(true);
});

test('core recording does not automatically emit calibration sounds',async({page})=>{
  await page.goto('/');
  const silent=await page.evaluate(async()=>{const p='/src/syncReference.ts';const {SyncReference}=await import(p);const player=new SyncReference();await player.enable();await player.play();const result=player.context===null;player.dispose();return result;});
  expect(silent).toBe(true);
});

test('host stop during countdown acknowledges and preserves interrupted preroll',async({page})=>{
  await page.context().grantPermissions(['microphone']);
  await page.route('**/api/rooms/SYNC01/recordings/**',route=>route.fulfill({json:{ok:true}}));
  await page.goto('/');
  const result=await page.evaluate(async()=>{
    const path='/src/capture.ts',storagePath='/src/storage.ts';
    const {RecorderDevice}=await import(path),{getCapture}=await import(storagePath);
    const events:{type:string}[]=[];
    const device=new RecorderDevice({session_id:'early-stop',participant_id:'p',room_code:'SYNC01',source_label:'A'},(e:{type:string})=>events.push(e),()=>{});
    const room={id:'early-stop',status:'waiting',starts_at:null,started_at:null,recordings:[]};
    await device.sync(room);await device.authorize();await device.prepare();
    const starts_at=Date.now()+3000;
    await device.sync({...room,status:'countdown',starts_at});await new Promise(resolve=>setTimeout(resolve,200));
    await device.sync({...room,status:'finalizing',starts_at,stopped_at:Date.now()});
    let saved=await getCapture(device.key);
    for(let i=0;i<50&&!saved.done;i++){await new Promise(resolve=>setTimeout(resolve,50));saved=await getCapture(device.key);}
    device.dispose();return {started:events.some(e=>e.type==='started'),done:saved.done,interrupted:saved.interrupted};
  });
  expect(result).toEqual({started:true,done:true,interrupted:true});
});
