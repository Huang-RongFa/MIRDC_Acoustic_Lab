import {test,expect} from '@playwright/test';
import {staticRoom} from '../src/staticState';

for(const name of ['K','另一位錄音者'])for(const outcome of ['removed','pending','error','server-error','cancel'] as const)test(`removal of ${name} handles ${outcome} without a state broadcast`,async({page})=>{
  const identity={room_code:'KICK01',participant_id:'host',session_id:'take',source_label:'',token:'test-token',is_host:true};
  let removed=false;
  let leaving=false;
  let refreshes=0;
  const state=()=>({...staticRoom,id:'take',room_id:'room',event_version:removed?3:leaving?2:1,recordings:[],participants:removed?[]:[{id:'member',source_label:'A',name,is_host:false,mic:false,ready:false,connected:false,error:'裝置錯誤',leaving}]});
  await page.addInitScript(identity=>{
    localStorage.setItem('cnc-identities',JSON.stringify([identity]));
    localStorage.setItem('cnc-current-room',identity.room_code);
  },identity);
  await page.route('**/api/rooms/KICK01',route=>{
    if(leaving&&++refreshes>1)removed=true;
    return route.fulfill({json:state()});
  });
  await page.route('**/api/rooms/KICK01/participants/member',route=>{
    expect(route.request().method()).toBe('DELETE');
    if(outcome==='server-error')return route.fulfill({status:500,contentType:'text/plain',body:'Internal Server Error'});
    if(outcome==='error')return route.fulfill({status:403,json:{detail:'只有主控者可操作'}});
    if(outcome==='pending')leaving=true;
    else removed=true;
    return route.fulfill({json:leaving?{pending_upload:true}:{ok:true}});
  });
  await page.routeWebSocket('**/api/rooms/KICK01/ws',ws=>{
    ws.onMessage(message=>{if(JSON.parse(String(message)).type==='auth')ws.send(JSON.stringify({type:'state',state:state()}));});
  });
  await page.goto('/');
  const kick=page.getByRole('button',{name:'強制退出 '+name,exact:true});
  await expect(kick).toBeVisible();
  page.on('dialog',()=>{throw new Error('Removal must use the in-page confirmation');});
  await kick.click();
  const confirmation=page.getByRole('dialog',{name:'移除錄音者'});
  await expect(confirmation).toContainText(name);
  await confirmation.getByRole('button',{name:outcome==='cancel'?'取消':'確認移除',exact:true}).click();
  if(outcome==='cancel'||outcome==='error'||outcome==='server-error'){
    await expect(kick).toBeVisible();
    await expect(kick).toBeEnabled();
    if(outcome==='error')await expect(confirmation.getByRole('alert')).toContainText('只有主控者可操作');
    else if(outcome==='server-error')await expect(confirmation.getByRole('alert')).toContainText('HTTP 500');
    else await expect(confirmation).not.toBeVisible();
    expect(removed).toBe(false);
    if(outcome==='error')await expect(page.locator('.notice[role=status]')).toContainText('只有主控者可操作');
    return;
  }
  if(outcome==='pending'){
    await expect(page.locator('.notice[role=status]')).toContainText('正在等待音訊保存');
    await expect(page.locator('.person-status').first()).toHaveText('退出中');
    await expect(kick).toBeDisabled();
  }
  await expect(kick).toHaveCount(0);
  if(outcome==='removed')await expect(page.locator('.notice[role=status]')).toContainText('已移除錄音者 '+name);
});
