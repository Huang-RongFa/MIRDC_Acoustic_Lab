import {test,expect,type Browser,type Page} from '@playwright/test';

const conditions:Record<string,string>={machine_code:'CNC-01',machine_name:'測試機台',machine_model:'VMC',material:'AL6061',material_spec:'T6',workpiece_code:'W1',tool_type:'平銑刀',tool_material:'硬質合金',tool_diameter_mm:'10',tool_flutes:'4',tool_overhang_mm:'35',tool_setup:'ER32',spindle_rpm:'6000',feed_mm_min:'600',axial_depth_mm:'0.5',radial_width_mm:'2',process:'銑削',coolant:'乾式',toolpath:'平行',nc_program:'O001'};
async function phone(browser:Browser){const context=await browser.newContext({permissions:['microphone'],viewport:{width:390,height:844}});const page=await context.newPage();return {context,page};}
async function ready(page:Page){await page.getByRole('button',{name:'測試並授權麥克風'}).click();await expect(page.getByRole('button',{name:'我已就緒，等待主控',exact:true})).toBeEnabled();await page.getByRole('button',{name:'我已就緒，等待主控',exact:true}).click();}

test('three independent browser recordings, offline retransmit and restored history',async({browser})=>{
  const a=await phone(browser),b=await phone(browser),c=await phone(browser);
  try{
    await a.page.goto('/');await a.page.getByRole('button',{name:'建立新房間',exact:true}).click();
    await expect(a.page.getByText('伺服器已連線',{exact:true})).toBeVisible();
    const code=await a.page.locator('.room-identity strong').innerText();
    await a.page.getByRole('button',{name:'編輯加工條件'}).click();
    for(const [name,value] of Object.entries(conditions))await a.page.locator(`dialog input[name="${name}"]`).fill(value);
    await a.page.getByRole('button',{name:'儲存設定',exact:true}).click();
    for(const [person,source] of [[b,'B'],[c,'C']] as const){await person.page.goto('/?room='+code);await person.page.getByLabel('我的聲源位置').selectOption(source);await person.page.getByLabel('錄音人員',{exact:true}).fill('Recorder '+source);await person.page.getByRole('button',{name:'加入此錄音房間'}).click();await expect(person.page.getByText('伺服器已連線',{exact:true})).toBeVisible();}
    await ready(a.page);await ready(b.page);
    await expect(a.page.getByRole('button',{name:'開始統一錄音'})).toBeDisabled();
    await ready(c.page);await expect(a.page.getByRole('button',{name:'開始統一錄音'})).toBeEnabled();
    await a.page.screenshot({path:'../tmp/dashboard-mobile.png',fullPage:true});
    await a.page.getByRole('button',{name:'開始統一錄音'}).click();
    await expect(a.page.getByTestId('elapsed')).toHaveText('00:00:02',{timeout:12000});
    await b.context.setOffline(true);
    await expect(a.page.getByTestId('elapsed')).toHaveText('00:00:05',{timeout:8000});
    await a.page.getByRole('button',{name:'由主控者停止錄音'}).click();
    await expect(a.page.locator('.control-state')).toContainText('等待音訊封存');
    await b.context.setOffline(false);
    await expect(a.page.locator('.control-state')).toContainText('三聲源儲存完成',{timeout:30000});
    const files=await a.page.evaluate(async()=>{const identity=JSON.parse(localStorage.getItem('cnc-identities')!)[0];const headers={Authorization:'Bearer '+identity.token};const state=await (await fetch('/api/rooms/'+identity.room_code,{headers})).json();const context=new AudioContext();const results=[];for(const p of state.participants){const response=await fetch(`/api/rooms/${identity.room_code}/recordings/${p.id}/audio`,{headers});const bytes=await response.arrayBuffer();const size=bytes.byteLength;const audio=await context.decodeAudioData(bytes);results.push({source:p.source_label,size,duration:audio.duration,mime:response.headers.get('content-type')});}await context.close();return results;});
    expect(files.map(f=>f.source)).toEqual(['A','B','C']);for(const f of files){expect(f.size).toBeGreaterThan(1000);expect(f.duration).toBeGreaterThan(4);expect(f.mime).toContain('webm');}
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
