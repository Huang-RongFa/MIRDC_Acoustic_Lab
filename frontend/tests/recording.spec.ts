import {test,expect,type Browser,type Page} from '@playwright/test';

const conditions:Record<string,string>={machine_code:'CNC-01',machine_name:'測試機台',machine_model:'VMC',material:'AL6061',material_spec:'T6',workpiece_code:'W1',tool_type:'平銑刀',tool_material:'硬質合金',tool_diameter_mm:'10',tool_flutes:'4',tool_overhang_mm:'35',tool_setup:'ER32',spindle_rpm:'6000',feed_mm_min:'600',axial_depth_mm:'0.5',radial_width_mm:'2',process:'銑削',coolant:'乾式',toolpath:'平行',nc_program:'O001'};
async function phone(browser:Browser){const context=await browser.newContext({permissions:['microphone'],viewport:{width:390,height:844}});const page=await context.newPage();return {context,page};}
async function ready(page:Page){await page.getByRole('button',{name:'測試並授權麥克風'}).click();await expect(page.getByRole('button',{name:'我已就緒，等待主控',exact:true})).toBeEnabled();await page.getByRole('button',{name:'我已就緒，等待主控',exact:true}).click();}

for(const duration of [30,300])test(`three browser recordings, ${duration}s with independent Stereo and offline retransmit`,async({browser})=>{
  test.setTimeout((duration+90)*1000);
  const a=await phone(browser),b=await phone(browser),c=await phone(browser);
  try{
    await b.page.addInitScript(()=>{
      navigator.mediaDevices.getUserMedia=async constraints=>{
        const requested=typeof constraints?.audio==='object'?constraints.audio.channelCount:undefined;
        if(typeof requested!=='object'||requested.exact!==2)
          throw new Error('Stereo was not requested');
        const graph=new AudioContext();
        const merger=graph.createChannelMerger(2);
        const destination=graph.createMediaStreamDestination();
        for (const [channel,frequency] of [440,880].entries()){
          const oscillator=graph.createOscillator();
          oscillator.frequency.value=frequency;
          const gain=graph.createGain();
          gain.gain.value=0.2;
          oscillator.connect(gain).connect(merger,0,channel);
          oscillator.start();
        }
        merger.connect(destination);
        await graph.resume();
        return destination.stream;
      };
    });
    await a.page.goto('/');await a.page.getByRole('button',{name:'建立新房間',exact:true}).click();
    await expect(a.page.getByText('伺服器已連線',{exact:true})).toBeVisible();
    const code=await a.page.locator('.room-identity strong').innerText();
    await a.page.getByRole('button',{name:'編輯加工條件'}).click();
    for(const [name,value] of Object.entries(conditions))await a.page.locator(`dialog input[name="${name}"]`).fill(value);
    await a.page.getByRole('button',{name:'儲存設定',exact:true}).click();
    for(const [person,source] of [[b,'B'],[c,'C']] as const){await person.page.goto('/?room='+code);await person.page.getByLabel('我的聲源位置').selectOption(source);await person.page.getByLabel('錄音人員',{exact:true}).fill('Recorder '+source);await person.page.getByRole('button',{name:'加入此錄音房間'}).click();await expect(person.page.getByText('伺服器已連線',{exact:true})).toBeVisible();}
    await b.page.getByLabel('錄音聲道').selectOption('2');
    await ready(a.page);await ready(b.page);
    await expect(b.page.getByText('CH 2 · Right Channel',{exact:true})).toBeVisible();
    await expect(a.page.getByRole('button',{name:'開始統一錄音'})).toBeDisabled();
    await ready(c.page);await expect(a.page.getByRole('button',{name:'開始統一錄音'})).toBeEnabled();
    await a.page.screenshot({path:'../tmp/dashboard-mobile.png',fullPage:true});
    await a.page.getByRole('button',{name:'開始統一錄音'}).click();
    await expect(a.page.getByTestId('elapsed')).toHaveText('00:00:04',{timeout:15000});
    await b.context.setOffline(true);
    await expect(a.page.getByTestId('elapsed')).toHaveText('00:00:14',{timeout:15000});
    await b.context.setOffline(false);
    const finishTime=duration===30?'00:00:30':'00:05:00';
    await expect(a.page.getByTestId('elapsed')).toHaveText(finishTime,{timeout:duration*1000});
    // Hold a PUT across stop for 32s. The device must still save the final chunk.
    let release!:()=>void;
    let entered!:()=>void;
    const hold=new Promise<void>(resolve=>{release=resolve;});
    const intercepted=new Promise<void>(resolve=>{entered=resolve;});
    await b.page.route('**/chunks/*',async route=>{entered();await hold;await route.continue();});
    await intercepted;
    await a.page.getByRole('button',{name:'由主控者停止錄音'}).click();
    await expect(a.page.locator('.control-state')).toContainText('等待音訊封存');
    if(duration===30)await new Promise(resolve=>setTimeout(resolve,32000));
    await expect(a.page.locator('.control-state')).toContainText('等待音訊封存');
    release();
    await expect(a.page.locator('.control-state')).toContainText('三聲源儲存完成',{timeout:30000});
    const files=await a.page.evaluate(async()=>{
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
        if(p.source_label==='B')for(let channel=0;channel<audio.numberOfChannels;channel++){
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
    });
    await test.info().attach('decoded-audio',{body:JSON.stringify(files,null,2),contentType:'application/json'});
    expect(files.map(f=>f.source)).toEqual(['A','B','C']);
    for(const f of files){
      expect(f.size).toBeGreaterThan(1000);
      expect(f.duration).toBeGreaterThan(duration-0.5);
      expect(Math.abs(f.recorded-f.duration)).toBeLessThan(0.75);
      expect(f.expected).toBe(f.received);
      expect(f.mime).toContain('webm');
      expect(f.channelCount).toBe(f.source==='B'?2:1);
    }
    const stereo=files[1].channels;
    expect(stereo[0].samples).toBe(stereo[1].samples);
    for(const [channel,expected] of [44,88].entries()){
      expect(stereo[channel].minimumRms).toBeGreaterThan(0.08);
      expect(stereo[channel].maximumStep).toBeLessThan(0.15);
      expect(stereo[channel].minCrossings).toBeGreaterThanOrEqual(expected-3);
      expect(stereo[channel].maxCrossings).toBeLessThanOrEqual(expected+3);
    }
    await expect(a.page.getByRole('button',{name:'錄音測試結果',exact:true})).toBeVisible();
    await a.page.getByRole('button',{name:'錄音測試結果',exact:true}).click();
    await expect(a.page.getByRole('heading',{name:'錄音測試結果',exact:true})).toBeVisible();
    await expect(a.page.getByText('上傳完整', {exact:true})).toHaveCount(3);
    for(const source of ['A','B','C'])await a.page.locator('article').filter({has:a.page.getByRole('heading',{name:'Recorder '+source,exact:true})}).getByRole('button',{name:'載入試聽與波形'}).click();
    await expect(a.page.locator('audio')).toHaveCount(3);
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
