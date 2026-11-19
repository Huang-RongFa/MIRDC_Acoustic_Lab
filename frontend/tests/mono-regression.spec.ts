import {expect,test} from '@playwright/test';

test('right-only stereo input reaches Mono after the capture context starts',async({page})=>{
  await page.goto('/');
  const result=await page.evaluate(async path=>{
    const {RecorderDevice}=await import(path);
    const input=new AudioContext();
    const merger=input.createChannelMerger(2);
    const destination=input.createMediaStreamDestination();
    const oscillator=input.createOscillator();
    oscillator.connect(merger,0,1);
    oscillator.start();
    merger.connect(destination);
    await input.resume();
    navigator.mediaDevices.getUserMedia=async()=>destination.stream;

    const resume=AudioContext.prototype.resume;
    let release!:()=>void;
    const gate=new Promise<void>(resolve=>{release=resolve;});
    let requested!:()=>void;
    const request=new Promise<void>(resolve=>{requested=resolve;});
    AudioContext.prototype.resume=function(){requested();return gate.then(()=>resume.call(this));};
    const device=new RecorderDevice({session_id:'mono-regression',participant_id:'test'},()=>{},()=>{});
    try{
      let ready=false;
      const authorization=device.authorize(1).then(()=>{ready=true;});
      await request;
      await new Promise(resolve=>setTimeout(resolve,40));
      const authorizedBeforeResume=ready;
      release();
      await authorization;
      await device.context.resume();
      await device.prepare();
      const recorder:MediaRecorder=device.recorder;
      const recorded=new Promise<Blob>(resolve=>{recorder.ondataavailable=event=>resolve(event.data);});
      recorder.start();
      await new Promise(resolve=>setTimeout(resolve,700));
      const peak=Math.max(...(device.samples()??[]).map(Math.abs));
      recorder.stop();
      const blob=await recorded;
      const audio=await input.decodeAudioData(await blob.arrayBuffer());
      const samples=audio.getChannelData(0);
      const rms=Math.sqrt(samples.reduce((power,sample)=>power+sample*sample,0)/samples.length);
      return {authorizedBeforeResume,peak,channels:audio.numberOfChannels,rms};
    }finally{
      AudioContext.prototype.resume=resume;
      device.dispose();
      await input.close();
    }
  },'/src/capture.ts');
  expect.soft(result.authorizedBeforeResume).toBe(false);
  expect.soft(result.peak).toBeGreaterThan(0.2);
  expect(result.channels).toBe(1);
  expect(result.rms).toBeGreaterThan(0.2);
});

test('resume rejection closes the input and never reports the microphone as ready',async({page})=>{
  await page.goto('/');
  const result=await page.evaluate(async path=>{
    const {RecorderDevice}=await import(path);
    const input=new AudioContext();
    const stream=input.createMediaStreamDestination().stream;
    const track=stream.getAudioTracks()[0];
    navigator.mediaDevices.getUserMedia=async()=>stream;
    const resume=AudioContext.prototype.resume;
    AudioContext.prototype.resume=()=>Promise.reject(new Error('resume denied by test'));
    const messages:{type:string;mic?:boolean}[]=[];
    const device=new RecorderDevice({session_id:'mono-regression',participant_id:'test'},(message:typeof messages[number])=>messages.push(message),()=>{});
    try{
      await device.authorize(1);
      return null;
    }catch(error){
      return {message:(error as Error).message,state:track.readyState,ready:device.microphoneReady,
        reportedReady:messages.some(message=>message.type==='mic'&&message.mic)};
    }finally{
      AudioContext.prototype.resume=resume;
      device.dispose();
      await input.close();
    }
  },'/src/capture.ts');
  expect(result).toEqual({message:'resume denied by test',state:'ended',ready:false,reportedReady:false});
});

test('native Mono uses its original stream and preserves an unknown sample rate',async({page})=>{
  await page.goto('/');
  const result=await page.evaluate(async path=>{
    const {RecorderDevice}=await import(path);
    const input=new AudioContext();
    const destination=input.createMediaStreamDestination();
    destination.channelCount=1;
    const track=destination.stream.getAudioTracks()[0];
    const settings=track.getSettings();
    track.getSettings=()=>({...settings,sampleRate:undefined});
    navigator.mediaDevices.getUserMedia=async()=>destination.stream;
    const messages:{type:string;sample_rate?:number|null;channel_count?:number|null}[]=[];
    const device=new RecorderDevice({session_id:'mono-regression',participant_id:'test'},(message:typeof messages[number])=>messages.push(message),()=>{});
    try{
      await device.authorize(1);
      await device.prepare();
      const prepared=messages.find(message=>message.type==='prepared');
      return {original:device.recorder.stream===destination.stream,channels:prepared?.channel_count,rate:prepared?.sample_rate};
    }finally{
      device.dispose();
      await input.close();
    }
  },'/src/capture.ts');
  expect(result).toEqual({original:true,channels:1,rate:null});
});
