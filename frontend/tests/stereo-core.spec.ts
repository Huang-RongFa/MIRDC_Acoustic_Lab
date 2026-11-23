import {test,expect} from '@playwright/test';
import {appendWave} from '../src/liveWave';
import {peakEnvelope} from '../src/recordingWaveforms';

test('waveform bins retain signed peaks and cover the whole recording',async()=>{
  const data=new Float32Array(16001).fill(.25);
  data[1]=-.75;
  data[16000]=1;
  const peaks=await peakEnvelope(data,new AbortController().signal);
  expect(peaks.min).toHaveLength(800);
  expect([peaks.min[0],peaks.max[0]]).toEqual([-.75,.25]);
  expect([peaks.min[799],peaks.max[799]]).toEqual([.25,1]);
});

test('rolling preview retains ten seconds and channel independence without scaling PCM',()=>{
  let wave;
  for(let i=1;i<=60;i++)wave=appendWave(wave,{samples:[.123456,-.8],channels:[[.123456,-.8],[.6,-.234567]],duration:.25,at:i*250});
  expect(wave!.points[0].at).toBeGreaterThanOrEqual(5000);
  expect(wave!.points.at(-1)!.at).toBe(15000);
  expect(wave!.points.at(-1)!.values).toEqual([-.8,-.234567]);
  expect(wave!.channelCount).toBe(2);
});

test('workspace navigation follows authenticated room state, leave and connection loss',async({page})=>{
  const identity={room_code:'NAV001',participant_id:'host',session_id:'take',source_label:'A',token:'test',is_host:true};
  const state={id:'take',room_id:'room',room_code:'NAV001',event_version:1,status:'waiting',conditions:{},required_recorder_count:3,ready_count:0,recordings:[],participants:[{id:'host',source_label:'A',name:'host',is_host:true,connected:true,mic:false,ready:false,error:null}],server_now:Date.now()};
  let connected=true;let socket:any;
  await page.route('**/api/rooms',r=>r.fulfill({json:identity}));
  await page.routeWebSocket('**/api/rooms/NAV001/ws',ws=>{socket=ws;ws.onMessage(m=>{if(connected&&JSON.parse(String(m)).type==='auth')ws.send(JSON.stringify({type:'state',state}));});});
  await page.goto('/');await expect(page.locator('.workspace-nav')).toHaveCount(0);
  await page.getByRole('button',{name:'建立新房間',exact:true}).click();await expect(page.locator('.workspace-nav')).toBeVisible();
  await expect(page.locator('.workspace-nav button')).toHaveText(['錄音','錄音結果','錄音分析']);
  await page.getByRole('button',{name:'建立／加入另一個房間'}).click();await expect(page.locator('.workspace-nav')).toHaveCount(0);
  await page.getByRole('button',{name:'建立新房間',exact:true}).click();await expect(page.locator('.workspace-nav')).toBeVisible();
  connected=false;socket.close({code:1000,reason:'test disconnect'});await expect(page.locator('.workspace-nav')).toHaveCount(0);
});

test('real two-channel signal survives worklet, WAV and MediaRecorder; unsupported Stereo fails',async({page})=>{
  await page.route('**/api/rooms/STEREO/recordings/**',r=>r.fulfill({json:{ok:true}}));
  await page.goto('/');
  const result=await page.evaluate(async()=>{
    const capture='/src/capture.ts',storage='/src/pcmStorage.ts',legacy='/src/storage.ts',options='/src/recordingSyncOptions.ts';
    const {RecorderDevice}=await import(capture),{pcmHistory,loadPcm,pcmWav}=await import(storage),{chunks,getCapture}=await import(legacy),{saveRecordingSyncOptions}=await import(options);
    const source=new AudioContext({sampleRate:48000});await source.resume();
    const dest=source.createMediaStreamDestination(),merger=source.createChannelMerger(2);dest.channelCount=2;merger.connect(dest);
    const oscillators=[440,880].map((frequency,index)=>{const osc=source.createOscillator(),gain=source.createGain();osc.frequency.value=frequency;gain.gain.value=index ? 0.2 : 0.1;osc.connect(gain);gain.connect(merger,0,index);osc.start();return osc;});
    const settings=dest.stream.getAudioTracks()[0].getSettings();
    if(settings.channelCount!==2)throw new Error('Synthetic source did not expose stereo');
    navigator.mediaDevices.getUserMedia=async()=>dest.stream;
    saveRecordingSyncOptions({multiDeviceSyncEnabled:true,requestedSampleRate:48000,channelCount:2});
    const events:any[]=[];
    const device=new RecorderDevice({room_code:'STEREO',session_id:'take',participant_id:'two',source_label:'A'},(e:any)=>events.push(e),()=>{});
    await device.sync({id:'take',status:'waiting',recordings:[]});await device.authorize();await device.prepare();
    const starts_at=Date.now()+100;device.pcm.clock={server:Date.now(),local:performance.now(),uncertainty:1};
    await device.sync({id:'take',status:'countdown',starts_at,recordings:[]});await new Promise(r=>setTimeout(r,1300));
    await device.sync({id:'take',status:'recording',starts_at,started_at:starts_at,recordings:[]});
    let locked=false;try{await device.configure({multiDeviceSyncEnabled:true,requestedSampleRate:44100,channelCount:1});}catch{locked=true;}
    await device.sync({id:'take',status:'finalizing',starts_at,started_at:starts_at,recordings:[]});await device.pcm.stop();
    for(let i=0;i<30&&!(await getCapture(device.key))?.done;i++)await new Promise(r=>setTimeout(r,50));
    const [meta]=await pcmHistory('STEREO','two'),saved=await loadPcm(meta.key),wav=await pcmWav(meta,saved.chunks).arrayBuffer(),view=new DataView(wav);
    const raw=await chunks(device.key),decoder=new AudioContext({sampleRate:48000}),pcm=await decoder.decodeAudioData(wav.slice(0)),encoded=await decoder.decodeAudioData(await new Blob(raw.map((r:any)=>r.blob),{type:raw[0].blob.type}).arrayBuffer());
    const frequency=(audio:AudioBuffer,c:number)=>{const x=audio.getChannelData(c),crossings:number[]=[];const begin=Math.floor(audio.sampleRate*.3),end=Math.min(x.length,begin+Math.floor(audio.sampleRate*.5));for(let i=begin+1;i<end;i++)if(x[i-1]<0&&x[i]>=0)crossings.push(i-1-x[i-1]/(x[i]-x[i-1]));const periods=crossings.slice(1).map((v,i)=>v-crossings[i]).sort((a,b)=>a-b);return audio.sampleRate/periods[Math.floor(periods.length/2)];};
    const answer={settings,locked,channels:meta.channel_count,frames:meta.sample_count,bytes:view.getUint32(40,true),wavChannels:view.getUint16(22,true),pcm:[frequency(pcm,0),frequency(pcm,1)],encodedChannels:encoded.numberOfChannels,encoded:[frequency(encoded,0),frequency(encoded,1)],prepared:events.find(e=>e.type==='prepared').channel_count};
    device.dispose();oscillators.forEach(o=>o.stop());await source.close();await decoder.close();
    const mono=new AudioContext(),destination=mono.createMediaStreamDestination();destination.channelCount=1;navigator.mediaDevices.getUserMedia=async()=>destination.stream;
    const unsupported=new RecorderDevice({room_code:'STEREO',session_id:'next',participant_id:'mono',source_label:'B'},()=>{},()=>{});let error='';try{await unsupported.authorize();}catch(e){error=(e as Error).message;}unsupported.dispose();await mono.close();
    return {...answer,error};
  });
  expect(result.locked).toBe(true);expect(result.channels).toBe(2);expect(result.wavChannels).toBe(2);expect(result.prepared).toBe(2);expect(result.encodedChannels).toBe(2);expect(result.bytes).toBe(result.frames*2*4);
  for(const frequencies of [result.pcm,result.encoded]){expect(frequencies[0]).toBeCloseTo(440,-1);expect(frequencies[1]).toBeCloseTo(880,-1);}
  expect(result.error).toContain('Mono');
});

test('fixed waveform axes and L/R selectors show only two decimal display values',async({page})=>{
  await page.goto('/');
  await page.evaluate(async()=>{
    const paths=['/src/WavePlot.tsx','/src/ChannelInspector.tsx','/node_modules/.vite/deps/react.js','/node_modules/.vite/deps/react-dom_client.js'];
    const [{WavePlot},{ChannelInspector},{default:React},{default:ReactDOM}]=await Promise.all(paths.map(p=>import(p)));
    const audio=new AudioBuffer({numberOfChannels:2,length:48000,sampleRate:48000});for(let i=0;i<audio.length;i++){audio.getChannelData(0)[i]=.1*Math.sin(2*Math.PI*440*i/48000);audio.getChannelData(1)[i]=.4*Math.sin(2*Math.PI*880*i/48000);}
    ReactDOM.createRoot(document.getElementById('root')!).render(React.createElement('div',null,React.createElement(WavePlot,{label:'live',now:10000,live:{channelCount:2,at:10000,points:[{at:1000,values:[.123456,.987654]},{at:10000,values:[.1,.2]}]}}),React.createElement(ChannelInspector,{audio,label:'stereo'})));
  });
  const plot=page.getByRole('figure',{name:'live',exact:true});
  await expect(plot.locator('.signal-scale')).toHaveText('1.000.00-1.00');
  await expect(plot.locator('.signal-time')).toHaveText('-10.00-5.000.00');
  await expect(plot.locator('path[data-channel]')).toHaveCount(2);
  await page.getByLabel('聲道選擇').selectOption('1');await expect(page.getByText(/所選聲道：RMS/)).toContainText('RMS 0.28');
  await page.getByLabel('聲道選擇').selectOption('0');await expect(page.getByText(/所選聲道：RMS/)).toContainText('RMS 0.07');
  await page.screenshot({path:'../tmp/stereo-wave-analysis.png',fullPage:true});
});
