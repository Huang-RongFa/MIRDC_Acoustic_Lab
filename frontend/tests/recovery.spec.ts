import {test,expect} from '@playwright/test';

test('microphone denial is reported without becoming ready',async({browser})=>{
  const context=await browser.newContext({permissions:[],viewport:{width:360,height:800}});
  const page=await context.newPage();
  await page.addInitScript(()=>{navigator.mediaDevices.getUserMedia=async()=>{throw new DOMException('Permission denied','NotAllowedError');};});
  try{await page.goto('/');await page.getByRole('button',{name:'建立新房間',exact:true}).click();await expect(page.getByText('伺服器已連線',{exact:true})).toBeVisible();await page.getByRole('button',{name:'測試並授權麥克風'}).click();await expect(page.getByRole('status')).toContainText('Permission denied');await expect(page.getByRole('button',{name:'我已就緒，等待主控',exact:true})).toBeDisabled();await expect(page.locator('.person-status').first()).toHaveText('裝置錯誤');expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);}finally{await context.close();}
});

for(const failure of ['refresh','host-background','host-close'])test(failure+' during capture cannot claim uninterrupted recording',async({browser})=>{
  const contexts=await Promise.all([0,1,2].map(()=>browser.newContext({permissions:['microphone']})));
  const pages=await Promise.all(contexts.map(c=>c.newPage()));
  try{
    await pages[0].goto('/');
    const state=await pages[0].evaluate(async()=>{
      const host=await (await fetch('/api/rooms',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'A'})})).json();
      const participants=[host];for(const source_label of ['B','C'])participants.push(await (await fetch(`/api/rooms/${host.room_code}/join`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:source_label,source_label})})).json());
      const values={machine_code:'CNC',machine_name:'VMC',machine_model:'V1',material:'AL',material_spec:'T6',workpiece_code:'W1',tool_type:'mill',tool_material:'carbide',tool_diameter_mm:10,tool_flutes:4,tool_overhang_mm:35,tool_setup:'ER32',spindle_rpm:6000,feed_mm_min:600,axial_depth_mm:0.5,radial_width_mm:2,process:'milling',coolant:'dry',toolpath:'parallel',nc_program:'O1'};
      await fetch(`/api/rooms/${host.room_code}/conditions`,{method:'PUT',headers:{Authorization:'Bearer '+host.token,'Content-Type':'application/json'},body:JSON.stringify(values)});return participants;
    });
    for(let i=0;i<3;i++){
      await pages[i].goto('/');await pages[i].evaluate(identity=>{localStorage.setItem('cnc-identities',JSON.stringify([identity]));localStorage.setItem('cnc-current-room',identity.room_code);},state[i]);await pages[i].reload();await expect(pages[i].getByText('伺服器已連線',{exact:true})).toBeVisible();await pages[i].getByRole('button',{name:'測試並授權麥克風'}).click();await expect(pages[i].getByRole('button',{name:'我已就緒，等待主控',exact:true})).toBeEnabled();await pages[i].getByRole('button',{name:'我已就緒，等待主控',exact:true}).click();
    }
    await expect(pages[0].getByRole('button',{name:'開始統一錄音'})).toBeEnabled();await pages[0].getByRole('button',{name:'開始統一錄音'}).click();await expect(pages[0].getByTestId('elapsed')).toHaveText('00:00:02',{timeout:12000});
    if(failure==='refresh'){await pages[1].reload();await expect(pages[1].getByRole('status')).toContainText('中斷');}
    else if(failure==='host-close'){await pages[0].close();pages[0]=await contexts[0].newPage();await pages[0].goto('/');await expect(pages[0].getByRole('status')).toContainText('中斷');}
    else{await pages[0].evaluate(()=>{Object.defineProperty(document,'visibilityState',{configurable:true,value:'hidden'});document.dispatchEvent(new Event('visibilitychange'));});await expect(pages[0].getByRole('status')).toContainText('背景');}
    await pages[0].getByRole('button',{name:'由主控者停止錄音'}).click();
    await expect.poll(async()=>pages[0].evaluate(async()=>{const identity=JSON.parse(localStorage.getItem('cnc-identities')!)[0];const result=await(await fetch('/api/rooms/'+identity.room_code,{headers:{Authorization:'Bearer '+identity.token}})).json();return result.recordings.map((r:{source_label:string;status:string})=>r.source_label+':'+r.status);}),{timeout:15000}).toEqual(failure==='refresh'?['A:stored','B:interrupted','C:stored']:['A:interrupted','B:stored','C:stored']);
    await expect(pages[0].locator('.control-state')).not.toContainText('三聲源儲存完成');
  }finally{await Promise.all(contexts.map(c=>c.close()));}
});
