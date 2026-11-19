import {test,expect,type Browser,type Page} from '@playwright/test';

const conditions:Record<string,string>={machine_code:'CNC-01',machine_name:'測試機台',machine_model:'VMC',material:'AL6061',material_spec:'T6',workpiece_code:'W1',tool_type:'平銑刀',tool_material:'硬質合金',tool_diameter_mm:'10',tool_flutes:'4',tool_overhang_mm:'35',tool_setup:'ER32',spindle_rpm:'6000',feed_mm_min:'600',axial_depth_mm:'0.5',radial_width_mm:'2',process:'銑削',coolant:'乾式',toolpath:'平行',nc_program:'O001'};
async function phone(browser:Browser){const context=await browser.newContext({permissions:['microphone'],viewport:{width:390,height:844}});const page=await context.newPage();return {context,page};}
async function ready(page:Page){await page.getByRole('button',{name:'測試並授權麥克風'}).click();await expect(page.getByRole('button',{name:'我已就緒，等待主控',exact:true})).toBeEnabled();await page.getByRole('button',{name:'我已就緒，等待主控',exact:true}).click();}
async function recordedFor(page:Page,seconds:number,timeout:number){
  await expect.poll(async()=>{
    const text=await page.getByTestId('elapsed').innerText();
    return /^\d\d:\d\d:\d\d$/.test(text)?text.split(':').reduce((total,part)=>total*60+Number(part),0):0;
  },{timeout}).toBeGreaterThanOrEqual(seconds);
}
async function microphone(page:Page,channels:1|2,frequencies:(number|null)[]){
  await page.addInitScript(({channels,frequencies})=>{
    let previous:{graph:AudioContext;stream:MediaStream}|undefined;
    navigator.mediaDevices.getUserMedia=async()=>{
      if(previous){
        if(previous.stream.getTracks().some(track=>track.readyState!=='ended'))throw new Error('Previous microphone track was not stopped');
        await previous.graph.close();
      }
      const graph=new AudioContext();
      const merger=graph.createChannelMerger(channels);
      const destination=graph.createMediaStreamDestination();
      destination.channelCount=channels;
      for(const [channel,frequency] of frequencies.entries()){
        if(frequency===null)continue;
        const oscillator=graph.createOscillator();
        const gain=graph.createGain();
        oscillator.frequency.value=frequency;
        gain.gain.value=0.4;
        oscillator.connect(gain).connect(merger,0,channel);
        oscillator.start();
      }
      merger.connect(destination);
      await graph.resume();
      previous={graph,stream:destination.stream};
      return destination.stream;
    };
  },{channels,frequencies});
}
async function activeWave(page:Page,label:string){
  const wave=page.getByLabel(label+'即時音訊波形',{exact:true});
  await expect(wave).toBeVisible();
  await expect.poll(()=>wave.evaluate((canvas:HTMLCanvasElement)=>{
    const context=canvas.getContext('2d')!;
    // The preview stroke is teal. Count coloured pixels away from the centre line.
    const pixels=context.getImageData(0,32,canvas.width,6).data;
    for(let i=0;i<pixels.length;i+=4)if(pixels[i]<80&&pixels[i+1]>90&&pixels[i+2]>80&&pixels[i+3]>100)return true;
    return false;
  })).toBe(true);
}

for(const duration of [30,300])test(`three browser recordings, ${duration}s with independent Stereo and offline retransmit`,async({browser})=>{
  test.setTimeout((duration+180)*1000);
  const a=await phone(browser),b=await phone(browser),c=await phone(browser);
  try{
    await Promise.all([microphone(a.page,1,[330]),microphone(b.page,2,[null,660]),microphone(c.page,2,[440,880])]);
    await a.page.goto('/');await a.page.getByRole('button',{name:'建立新房間',exact:true}).click();
    await expect(a.page.getByText('伺服器已連線',{exact:true})).toBeVisible();
    const code=await a.page.locator('.room-identity strong').innerText();
    await a.page.getByRole('button',{name:'編輯加工條件'}).click();
    for(const [name,value] of Object.entries(conditions))await a.page.locator(`dialog input[name="${name}"]`).fill(value);
    await a.page.getByRole('button',{name:'儲存設定',exact:true}).click();
    for(const [person,source] of [[b,'B'],[c,'C']] as const){await person.page.goto('/?room='+code);await person.page.getByLabel('我的聲源位置').selectOption(source);await person.page.getByLabel('錄音人員',{exact:true}).fill('Recorder '+source);await person.page.getByRole('button',{name:'加入此錄音房間'}).click();await expect(person.page.getByText('伺服器已連線',{exact:true})).toBeVisible();}
    await ready(a.page);await ready(b.page);
    await activeWave(a.page,'本機實際波形');
    await activeWave(b.page,'本機實際波形');
    await b.page.getByLabel('錄音聲道').selectOption('2');
    await ready(b.page);
    await activeWave(b.page,'CH 2 · Right Channel');
    await b.page.getByLabel('錄音聲道').selectOption('1');
    await ready(b.page);
    await expect(b.page.getByText('CH 2 · Right Channel',{exact:true})).toHaveCount(0);
    await activeWave(b.page,'本機實際波形');
    await c.page.getByLabel('錄音聲道').selectOption('2');
    await expect(a.page.getByRole('button',{name:'開始統一錄音'})).toBeDisabled();
    await ready(c.page);await expect(a.page.getByRole('button',{name:'開始統一錄音'})).toBeEnabled();
    await activeWave(c.page,'CH 1 · Left Channel');
    await activeWave(c.page,'CH 2 · Right Channel');
    await a.page.screenshot({path:'../tmp/dashboard-mobile.png',fullPage:true});
    await a.page.getByRole('button',{name:'開始統一錄音'}).click();
    await recordedFor(a.page,4,15000);
    await expect(b.page.getByLabel('錄音聲道')).toBeDisabled();
    await c.context.setOffline(true);
    await new Promise(resolve=>setTimeout(resolve,10000));
    await c.context.setOffline(false);
    await recordedFor(a.page,duration,duration*1000);
    // Hold a PUT across stop for 32s. The device must still save the final chunk.
    let release!:()=>void;
    let entered!:()=>void;
    const hold=new Promise<void>(resolve=>{release=resolve;});
    const intercepted=new Promise<void>(resolve=>{entered=resolve;});
    await c.page.route('**/chunks/*',async route=>{entered();await hold;await route.continue();});
    await intercepted;
    await a.page.getByRole('button',{name:'由主控者停止錄音'}).click();
    await expect(a.page.locator('.control-state')).toContainText('等待音訊封存');
    if(duration===30)await new Promise(resolve=>setTimeout(resolve,32000));
    await expect(a.page.locator('.control-state')).toContainText('等待音訊封存');
    release();
    await expect(a.page.locator('.control-state')).toContainText('三聲源儲存完成',{timeout:30000});
    const local=await Promise.all([a,b,c].map(({page})=>page.evaluate(async path=>{
      const {getCapture,chunks}=await import(path);
      const identity=JSON.parse(localStorage.getItem('cnc-identities')!)[0];
      const key=identity.session_id+'/'+identity.participant_id;
      const capture=await getCapture(key);
      const saved=await chunks(key);
      return {sealed:capture?.sealed,count:capture?.count,uploaded:saved.every((chunk:{uploaded:boolean;index:number},index:number)=>chunk.uploaded&&chunk.index===index),total:saved.length};
    },'/src/storage.ts')));
    for(const device of local){
      expect(device.sealed).toBe(true);
      expect(device.uploaded).toBe(true);
      expect(device.total).toBe(device.count);
    }
    const files=await test.step('download and decode each sealed audio file',()=>a.page.evaluate(async()=>{
      const identity=JSON.parse(localStorage.getItem('cnc-identities')!)[0];
      const headers={Authorization:'Bearer '+identity.token};
      const state=await (await fetch('/api/rooms/'+identity.room_code,{headers})).json();
      const context=new AudioContext();
      const results=[];
      for(const p of state.recordings){
        const response=await fetch(`/api/rooms/${identity.room_code}/recordings/${p.participant_id}/audio`,{headers});
        const bytes=await response.arrayBuffer();
        const size=bytes.byteLength;
        const audio=await context.decodeAudioData(bytes);
        const channels=[];
        for(let channel=0;channel<audio.numberOfChannels;channel++){
          const samples=audio.getChannelData(channel);
          const window=Math.floor(audio.sampleRate/10);
          let minimumRms=1,maximumStep=0,minCrossings=Infinity,maxCrossings=0;
          for(let offset=window;offset+2*window<samples.length;offset+=window){
            let power=0,crossings=0;
            for(let i=offset;i<offset+window;i++){
              power+=samples[i]**2;
              maximumStep=Math.max(maximumStep,Math.abs(samples[i]-samples[i-1]));
              if(samples[i]>=0&&samples[i-1]<0)crossings++;
            }
            minimumRms=Math.min(minimumRms,Math.sqrt(power/window));
            minCrossings=Math.min(minCrossings,crossings);
            maxCrossings=Math.max(maxCrossings,crossings);
          }
          channels.push({samples:samples.length,minimumRms,maximumStep,minCrossings,maxCrossings});
        }
        results.push({source:p.source_label,size,duration:audio.duration,recorded:p.duration_ms/1000,
          expected:p.expected_chunks,received:p.received_chunks,channelCount:audio.numberOfChannels,channels,mime:response.headers.get('content-type')});
      }
      await context.close();
      return results;
    }));
    await test.info().attach('decoded-audio',{body:JSON.stringify(files,null,2),contentType:'application/json'});
    expect(files.map(f=>f.source)).toEqual(['A','B','C']);
    for(const f of files){
      expect(f.size).toBeGreaterThan(1000);
      expect(f.duration).toBeGreaterThan(duration-0.5);
      expect(Math.abs(f.recorded-f.duration)).toBeLessThan(0.75);
      expect(f.expected).toBe(f.received);
      expect(f.mime).toContain('webm');
      expect(f.channelCount).toBe(f.source==='C'?2:1);
    }
    expect(files[2].channels[0].samples).toBe(files[2].channels[1].samples);
    for(const [file,frequencies] of [[0,[33]],[1,[66]],[2,[44,88]]] as const){
      for(const [channel,expected] of frequencies.entries()){
        const decoded=files[file].channels[channel];
        expect(decoded.minimumRms).toBeGreaterThan(0.08);
        expect(decoded.maximumStep).toBeLessThan(0.15);
        expect(decoded.minCrossings).toBeGreaterThanOrEqual(expected-3);
        expect(decoded.maxCrossings).toBeLessThanOrEqual(expected+3);
      }
    }
    await expect(a.page.getByRole('button',{name:'錄音測試結果',exact:true})).toBeVisible();
    await a.page.getByRole('button',{name:'錄音測試結果',exact:true}).click();
    await expect(a.page.getByRole('heading',{name:'錄音測試結果',exact:true})).toBeVisible();
    await expect(a.page.getByText('上傳完整', {exact:true})).toHaveCount(3);
    for(const source of ['A','B','C'])await a.page.locator('article').filter({has:a.page.getByRole('heading',{name:'Recorder '+source,exact:true})}).getByRole('button',{name:'載入試聽與波形'}).click();
    await expect(a.page.locator('audio')).toHaveCount(3);
    await expect(a.page.locator('canvas[aria-label$="原始音檔波形"]')).toHaveCount(3,{timeout:15000});
    await expect.poll(()=>a.page.locator('audio').evaluateAll(elements=>elements.every(el=>(el as HTMLAudioElement).readyState>=2))).toBe(true);
    await a.page.locator('audio').first().evaluate(async el=>{await (el as HTMLAudioElement).play();});
    await expect.poll(()=>a.page.locator('audio').first().evaluate(el=>(el as HTMLAudioElement).currentTime)).toBeGreaterThan(0);
    await a.page.screenshot({path:'../tmp/results-mobile.png',fullPage:true});
    await a.page.reload();await expect(a.page.locator('.control-state')).toContainText('三聲源儲存完成');
    await a.page.getByRole('button',{name:'實驗紀錄',exact:true}).click();await a.page.getByRole('button',{name:new RegExp(code+' ·')}).click();await expect(a.page.getByRole('button',{name:'下載原始音檔'})).toHaveCount(3);
    // 三聲源封存完成時，migration 004 的 trigger 排入地端分析；網頁只顯示佇列狀態，不產生結果
    await a.page.getByRole('button',{name:'分析結果',exact:true}).click();
    await expect(a.page.getByTestId('analysis-job')).toHaveText(/等待地端分析/);
    await expect(a.page.getByTestId('alignment-verdict')).toHaveCount(0);
    expect(await a.page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  }finally{await a.context.close();await b.context.close();await c.context.close();}
});
