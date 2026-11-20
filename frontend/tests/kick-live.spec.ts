import {test,expect} from '@playwright/test';
declare const process:{env:Record<string,string|undefined>};

test('host removes a disconnected recorder through the real API',async({page,browser,request})=>{
  test.skip(process.env.CNC_KICK_LIVE!=='1','Requires an explicitly selected live test server');
  const created=await request.post('/api/rooms',{data:{name:'移除驗證主控',required_recorder_count:3}});
  expect(created.ok()).toBeTruthy();
  const host=await created.json();
  const base='/api/rooms/'+host.room_code;
  const joined=await request.post(base+'/join',{data:{name:'移除驗證K'}});
  expect(joined.ok()).toBeTruthy();
  const member=await joined.json();
  await page.addInitScript(identity=>{localStorage.setItem('cnc-identities',JSON.stringify([identity]));localStorage.setItem('cnc-current-room',identity.room_code);},host);
  await page.goto('/');
  const context=await browser.newContext();
  await context.addInitScript(identity=>{localStorage.setItem('cnc-identities',JSON.stringify([identity]));localStorage.setItem('cnc-current-room',identity.room_code);},member);
  const phone=await context.newPage();
  const clockSynced=phone.waitForEvent('websocket').then(async socket=>{
    await socket.waitForEvent('framesent',{predicate:event=>JSON.parse(String(event.payload)).type==='clock'});
    await socket.waitForEvent('framereceived',{predicate:event=>JSON.parse(String(event.payload)).type==='state'});
  });
  await phone.goto(process.env.CNC_TEST_URL!);
  await expect(phone.getByText('伺服器已連線',{exact:true})).toBeVisible();
  await clockSynced;
  await context.close();
  const row=page.locator('.person').filter({hasText:'移除驗證K'});
  await expect(row).toContainText('裝置錯誤');
  await row.getByRole('button',{name:'強制退出 移除驗證K',exact:true}).click();
  await page.getByRole('dialog',{name:'移除錄音者'}).getByRole('button',{name:'確認移除',exact:true}).click();
  await expect(row).toHaveCount(0);
  await expect(page.locator('.notice[role=status]')).toContainText('已移除錄音者 移除驗證K');
  const state=await request.get(base,{headers:{Authorization:'Bearer '+host.token}});
  expect((await state.json()).participants.some((p:{id:string})=>p.id===member.participant_id)).toBe(false);
  expect((await request.get(base,{headers:{Authorization:'Bearer '+member.token}})).status()).toBe(403);
});
