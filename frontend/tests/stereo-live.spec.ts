import {test,expect,type Download} from '@playwright/test';

async function downloadBytes(download:Download){
  const stream=await download.createReadStream();
  const chunks:Uint8Array[]=[];
  for await(const chunk of stream)chunks.push(new Uint8Array(chunk));
  return new Uint8Array(await new Blob(chunks.map(chunk=>Uint8Array.from(chunk))).arrayBuffer());
}

test('one master controls three browser recorders with 1/2/1 channels and exports stereo waveforms',async({browser},testInfo)=>{
  const contexts=[];
  try{
    const hostContext=await browser.newContext();contexts.push(hostContext);const host=await hostContext.newPage();await host.goto('/');
    await expect(host.locator('.workspace-nav')).toHaveCount(0);await host.getByRole('button',{name:'建立新房間',exact:true}).click();await expect(host.locator('.workspace-nav')).toBeVisible();
    const code=await host.locator('.room-identity strong').innerText();
    await host.evaluate(async()=>{
      const identity=JSON.parse(localStorage.getItem('cnc-identities')!)[0],headers={'Authorization':'Bearer '+identity.token,'Content-Type':'application/json'},name='stereo-ui-'+crypto.randomUUID();
      const saved=await fetch('/api/rooms/'+identity.room_code+'/catalog',{method:'PUT',headers,body:JSON.stringify({kind:'machines',name,values:{machine_code:name}})});if(!saved.ok)throw new Error(await saved.text());
      const machines=await (await fetch('/api/machines',{headers})).json(),machine=machines.items.find((m:any)=>m.machine_code===name);
      const assigned=await fetch('/api/rooms/'+identity.room_code+'/conditions',{method:'PUT',headers,body:JSON.stringify({machine_id:machine.machine_id})});if(!assigned.ok)throw new Error(await assigned.text());
    });
    const pages=[];
    for(let i=0;i<3;i++){
      const context=await browser.newContext({permissions:['microphone'],viewport:{width:390,height:844}});contexts.push(context);const page=await context.newPage();pages.push(page);
      await page.goto('/?room='+code);await page.getByLabel('錄音人員',{exact:true}).fill('Recorder '+(i+1));await page.getByRole('button',{name:'加入此錄音房間'}).click();await expect(page.locator('.workspace-nav')).toBeVisible();
      if(i===1){
        await page.evaluate(()=>{
          navigator.mediaDevices.getUserMedia=async(constraints)=>{
            const count=(constraints?.audio as MediaTrackConstraints)?.channelCount as ConstrainULongRange;
            const channels=count?.exact===2?2:1,context=new AudioContext({sampleRate:44100});await context.resume();
            const dest=context.createMediaStreamDestination(),merger=context.createChannelMerger(channels);dest.channelCount=channels;merger.connect(dest);
            for(let c=0;c<channels;c++){const osc=context.createOscillator(),gain=context.createGain();osc.frequency.value=c?880:440;gain.gain.value=c ? 0.2 : 0.1;osc.connect(gain);gain.connect(merger,0,c);osc.start();}
            return dest.stream;
          };
        });
        await page.getByLabel('要求取樣率').selectOption('44100');await expect(page.getByRole('status').filter({hasText:'已套用'})).toBeVisible();
        await page.getByLabel('收音來源').selectOption('2');
      }else await page.getByRole('button',{name:'連接麥克風',exact:true}).click();
      await page.getByRole('button',{name:'確認就緒',exact:true}).click();
      await expect(page.locator('.person-status.ok')).toHaveCount(i+1);
    }
    await expect(host.getByRole('button',{name:'開始統一錄音'})).toBeEnabled();await host.getByRole('button',{name:'開始統一錄音'}).click();await expect(host.locator('.control-state')).toContainText('錄音進行中',{timeout:15000});
    for(const page of pages){await expect(page.getByLabel('要求取樣率')).toBeDisabled();await expect(page.getByLabel('收音來源')).toBeDisabled();}
    for(const viewer of [host,pages[1]]){
      const left=viewer.getByRole('figure',{name:'CH 1 — Left Channel (L)'});
      const right=viewer.getByRole('figure',{name:'CH 2 — Right Channel (R)'});
      await expect(left.locator('.signal-time')).toHaveText('-10.00-5.000.00');
      await expect(right.locator('.signal-time')).toHaveText('-10.00-5.000.00');
      await expect.poll(()=>viewer.evaluate(()=>{
        const left=document.querySelector('path[data-channel="L"][stroke="#007f89"]')?.getAttribute('d');
        const right=document.querySelector('path[data-channel="R"]')?.getAttribute('d');
        return !!left&&!!right&&left!=='M0 50H100'&&right!=='M0 50H100'&&left!==right;
      })).toBe(true);
      await expect(viewer.locator('.wave-tracks figure')).toHaveCount(4);
    }
    await host.waitForTimeout(1500);await host.getByRole('button',{name:'由主控者停止錄音'}).click();await expect(host.locator('.control-state')).toContainText('錄音儲存完成',{timeout:30000});
    const channels=await host.evaluate(async()=>{
      const identity=JSON.parse(localStorage.getItem('cnc-identities')!)[0],headers={'Authorization':'Bearer '+identity.token},state=await (await fetch('/api/rooms/'+identity.room_code,{headers})).json(),context=new AudioContext(),result=[];
      for(const r of state.recordings){const bytes=await (await fetch(`/api/rooms/${identity.room_code}/recordings/${r.participant_id}/audio?take_id=${state.id}`,{headers})).arrayBuffer(),audio=await context.decodeAudioData(bytes);result.push({stored:r.channel_count,decoded:audio.numberOfChannels,rate:r.sample_rate,duration:audio.duration});}
      await context.close();return result;
    });
    expect(channels.map(c=>c.stored)).toEqual([1,2,1]);expect(channels.map(c=>c.decoded)).toEqual([1,2,1]);expect(channels.every(c=>c.duration>1)).toBe(true);
    await host.getByRole('button',{name:'錄音結果',exact:true}).click();
    const stereo=host.locator('.result-file').nth(1);
    const titles=['Stereo Combined Waveform','Left Channel Waveform','Right Channel Waveform'];
    const filenames=['recording_stereo_combined.png','recording_left_channel.png','recording_right_channel.png'];
    await expect(stereo.locator('canvas')).toHaveCount(3);
    expect(await stereo.locator('canvas').evaluateAll(nodes=>nodes.map(node=>node.getAttribute('aria-label')))).toEqual(titles);
    const combinedColors=await stereo.locator('canvas').first().evaluate(canvas=>{
      const pixels=(canvas as HTMLCanvasElement).getContext('2d')!.getImageData(124,93,632,156).data;
      let cyan=false,orange=false;
      for(let i=0;i<pixels.length;i+=4){
        if(pixels[i+1]-pixels[i]>30)cyan=true;
        if(pixels[i]-pixels[i+1]>30)orange=true;
      }
      return {cyan,orange};
    });
    expect(combinedColors).toEqual({cyan:true,orange:true});
    await expect(host.getByRole('img',{name:'Mono Waveform'})).toHaveCount(2);
    await expect(host.getByLabel('聲道選擇')).toHaveCount(0);
    await expect(host.getByText(/Recording ID/)).toHaveCount(0);
    const pngs=[];
    for(const [i,title] of titles.entries()){
      const [download]=await Promise.all([host.waitForEvent('download'),stereo.getByRole('button',{name:`下載 ${title} PNG`}).click()]);
      expect(download.suggestedFilename()).toBe(filenames[i]);
      const bytes=await downloadBytes(download);
      expect(Array.from(bytes.subarray(0,8))).toEqual([137,80,78,71,13,10,26,10]);
      pngs.push(bytes);
    }
    expect(pngs[1]).not.toEqual(pngs[2]);
    const [all]=await Promise.all([host.waitForEvent('download'),stereo.getByRole('button',{name:'下載全部三張 PNG（ZIP）'}).click()]);
    const zip=await downloadBytes(all),headers=new DataView(zip.buffer);
    expect(all.suggestedFilename()).toBe('recording_waveforms.zip');
    let offset=0;
    for(const [i,filename] of filenames.entries()){
      expect(headers.getUint32(offset,true)).toBe(0x04034b50);
      const nameEnd=offset+30+headers.getUint16(offset+26,true),dataEnd=nameEnd+headers.getUint32(offset+18,true);
      expect(new TextDecoder().decode(zip.subarray(offset+30,nameEnd))).toBe(filename);
      expect(zip.subarray(nameEnd,dataEnd)).toEqual(pngs[i]);
      offset=dataEnd;
    }
    expect(headers.getUint32(offset,true)).toBe(0x02014b50);
    expect(headers.getUint32(zip.length-22,true)).toBe(0x06054b50);
    expect(headers.getUint32(zip.length-6,true)).toBe(offset);
    await stereo.screenshot({path:testInfo.outputPath('stereo-results-desktop.png')});
    await host.setViewportSize({width:390,height:844});
    expect(await stereo.evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
    await stereo.screenshot({path:testInfo.outputPath('stereo-results-mobile.png')});
    await host.getByRole('button',{name:'錄音分析',exact:true}).click();
    await expect(host.locator('.chart-image img')).toHaveCount(8,{timeout:60000});
    const charts=host.locator('.analysis-grid').first();
    await expect(charts.locator('h3')).toHaveText([/Mono/,/Left/,/Right/,/Mono/]);
    const options=await host.getByLabel('顯示音軌').locator('option').allTextContents();
    await host.getByLabel('顯示音軌').selectOption({label:options[3]});
    await expect(host.locator('.analysis-chart')).toHaveCount(2);
    await expect(host.locator('.analysis-chart h3')).toHaveText([/Right/,/Right/]);
    await pages[1].screenshot({path:'../tmp/stereo-live-recorder.png',fullPage:true});
  }finally{for(const context of contexts)await context.close();}
});
