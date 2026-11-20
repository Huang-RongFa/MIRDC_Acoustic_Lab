import {test,expect} from '@playwright/test';
import {pcmWav,type PcmMetadata,type PcmChunk} from '../src/pcmStorage';

test('PCM export rejects missing, duplicate and reordered sample ranges',()=>{
  const m={sample_count:4,chunk_count:2,actual_sample_rate:44100} as PcmMetadata;
  const chunk=(sequence:number,start:number)=>({sequence_number:sequence,sample_start:start,sample_count:2,actual_sample_rate:44100,samples:new Float32Array([.1,.2])}) as PcmChunk;
  expect(pcmWav(m,[chunk(0,0),chunk(1,2)]).size).toBe(60);
  expect(()=>pcmWav(m,[chunk(0,0)])).toThrow();
  expect(()=>pcmWav(m,[chunk(0,0),chunk(0,0)])).toThrow();
  expect(()=>pcmWav(m,[chunk(1,2),chunk(0,0)])).toThrow();
  expect(()=>pcmWav(m,[chunk(0,0),chunk(1,3)])).toThrow();
});

test('mixed-rate worklets preserve independent PCM, scheduled epoch and legacy uploads during network failure',async({page})=>{
  await page.context().grantPermissions(['microphone']);
  let offline=true;const uploads:string[]=[];
  await page.route('**/api/rooms/PCM001/recordings/**',async route=>{if(offline)await route.abort();else{uploads.push(route.request().url());await route.fulfill({json:{ok:true}});}});
  await page.goto('/');
  await page.evaluate(async()=>{
    const cp='/src/capture.ts',sp='/src/recordingSyncOptions.ts';
    const {RecorderDevice}=await import(cp),{saveRecordingSyncOptions}=await import(sp);
    const devices=[];
    for(const [i,rate] of [44100,48000].entries()){
      saveRecordingSyncOptions({multiDeviceSyncEnabled:true,requestedSampleRate:rate});
      const identity={session_id:'mixed',participant_id:'device'+i,room_code:'PCM001',source_label:i?'B':'A',token:'test',is_host:i===0};
      const device=new RecorderDevice(identity,()=>{},()=>{});
      await device.sync({id:'mixed',status:'waiting',recordings:[]});await device.authorize();await device.prepare();
      device.pcm.clock={server:Date.now(),local:performance.now(),uncertainty:2};devices.push(device);
    }
    const starts_at=Date.now()+700;
    for(const device of devices)await device.sync({id:'mixed',status:'countdown',starts_at,recordings:[]});
    await new Promise(r=>setTimeout(r,1000));
    for(const device of devices)await device.sync({id:'mixed',status:'recording',starts_at,started_at:starts_at,recordings:[]});
    await new Promise(r=>setTimeout(r,600));
    // Only one recorder stops locally; the other must keep capturing.
    devices[0].stop();await new Promise(r=>setTimeout(r,350));
    if(devices[1].recorder.state!=='recording')throw new Error('other device stopped');
    for(const device of devices)await device.sync({id:'mixed',status:'finalizing',starts_at,started_at:starts_at,recordings:[]});
    await Promise.all(devices.map(d=>d.pcm.stop()));
    (window as any).pcmTestDevices=devices;
  });
  offline=false;
  const result=await page.evaluate(async()=>{
    const sp='/src/pcmStorage.ts',legacy='/src/storage.ts';
    const {pcmHistory,loadPcm,pcmWav}=await import(sp),{getCapture,chunks}=await import(legacy);
    const devices=(window as any).pcmTestDevices,results=[];
    for(const device of devices){
      for(let i=0;i<30&&!(await getCapture(device.key))?.done;i++)await new Promise(r=>setTimeout(r,50));
      await device.flush();const raw=await getCapture(device.key),parts=await chunks(device.key);
      const [meta]=await pcmHistory('PCM001',device.identity.participant_id),saved=await loadPcm(meta.key);
      const wav=pcmWav(saved.metadata,saved.chunks),header=new DataView(await wav.arrayBuffer());
      const audio=await device.context.decodeAudioData(await new Blob(parts.map((p:any)=>p.blob),{type:raw.mime}).arrayBuffer());
      results.push({rate:meta.actual_sample_rate,headerRate:header.getUint32(24,true),complete:meta.complete,count:meta.sample_count,chunks:meta.chunk_count,start:meta.recording_started_at,scheduled:meta.scheduled_server_ms,status:meta.sync_status,legacyDone:raw.done,sealed:raw.sealed,duration:audio.duration,pcmDuration:meta.sample_count/meta.actual_sample_rate});
      device.dispose();
    }
    return results;
  });
  expect(result.map(r=>r.rate)).toEqual([44100,48000]);
  for(const r of result){expect(r.headerRate).toBe(r.rate);expect(r.complete).toBe(true);expect(r.count).toBeGreaterThan(10000);expect(r.chunks).toBeGreaterThan(1);expect(r.status).toBe('unverified');expect(r.legacyDone).toBe(true);expect(r.sealed).toBe(true);expect(r.duration).toBeGreaterThan(r.pcmDuration);expect(Math.abs(r.start-r.scheduled)).toBeLessThan(100);}
  expect(result[1].pcmDuration).toBeGreaterThan(result[0].pcmDuration+.2);
  expect(uploads.some(u=>u.includes('device0'))).toBe(true);expect(uploads.some(u=>u.includes('device1'))).toBe(true);
});

test('core PCM enabled by default and incomplete PCM survives reload',async({page})=>{
  await page.goto('/');
  const initial=await page.evaluate(async()=>{const p='/src/recordingSyncOptions.ts';return (await import(p)).recordingSyncOptions();});
  expect(initial.multiDeviceSyncEnabled).toBe(true);
  await page.evaluate(async()=>{
    const p='/src/pcmStorage.ts';const {savePcm}=await import(p);
    const metadata={key:'recovery',room_code:'PCM001',session_id:'take1',device_id:'device0',actual_sample_rate:44100,sample_count:2,chunk_count:1,complete:false,sync_status:'unverified'};
    await savePcm(metadata,{key:'recovery:0',capture:'recovery',sequence_number:0,sample_start:0,sample_count:2,actual_sample_rate:44100,samples:new Float32Array([.1,.2])});
    try{await savePcm({...metadata,sample_count:4},{key:'recovery:0',capture:'recovery',sequence_number:0,sample_start:0,sample_count:2,actual_sample_rate:44100,samples:new Float32Array([.1,.2])});throw new Error('duplicate accepted');}catch(e){if((e as Error).message==='duplicate accepted')throw e;}
  });
  await page.reload();
  const saved=await page.evaluate(async()=>{const p='/src/pcmStorage.ts';const {loadPcm,pcmWav}=await import(p),{metadata,chunks}=await loadPcm('recovery');return {metadata,size:pcmWav(metadata,chunks).size,chunks:chunks.length};});
  expect(saved.metadata.complete).toBe(false);expect(saved.metadata.sample_count).toBe(2);expect(saved.chunks).toBe(1);expect(saved.size).toBe(52);
});

test('recorder card settings have no optional sync switch',async({page})=>{
  await page.goto('/');await page.setViewportSize({width:390,height:844});
  await page.evaluate(async()=>{
    const component='/src/RecordingSyncControls.tsx',react='/node_modules/.vite/deps/react.js',dom='/node_modules/.vite/deps/react-dom_client.js';
    const [{RecordingSyncControls},{default:React},{default:ReactDOM}]=await Promise.all([import(component),import(react),import(dom)]);
    const container=document.createElement('div');container.className='card';document.body.replaceChildren(container);
    ReactDOM.createRoot(container).render(React.createElement(RecordingSyncControls,{identity:{room_code:'PCM001',participant_id:'device0'},locked:false,device:{configure:async()=>{}}}));
  });
  await expect(page.getByRole('checkbox')).toHaveCount(0);
  await expect(page.locator('details')).toHaveCount(0);
  await expect(page.getByLabel('要求取樣率')).toHaveValue('48000');
  await page.getByLabel('要求取樣率').selectOption('44100');
  await page.getByLabel('收音來源').selectOption('2');
  await expect(page.getByRole('status')).toContainText('已套用');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:'../tmp/stereo-recording-controls.png',fullPage:true});
});
