import {test,expect} from '@playwright/test';

test('two separate recorders retain countdown audio over two takes; missing acoustic references never pass',async({browser})=>{
  const contexts=await Promise.all([0,1,2].map(()=>browser.newContext({permissions:['microphone']})));
  const [host,...phones]=await Promise.all(contexts.map(c=>c.newPage()));
  try{
    await host.goto('/');await host.getByLabel('你的名稱').fill('Sync host');
    await host.getByLabel('錄音人數').selectOption('2');await host.getByRole('button',{name:'建立新房間',exact:true}).click();
    await expect(host.getByText('伺服器已連線',{exact:true})).toBeVisible();
    const code=await host.locator('.room-identity strong').innerText();
    await host.getByRole('button',{name:'編輯加工條件'}).click();
    await host.getByLabel('從已登錄機台選擇').selectOption({index:1});
    await host.getByRole('button',{name:'儲存設定',exact:true}).click();
    for(let i=0;i<phones.length;i++){
      await phones[i].goto('/?room='+code);await phones[i].getByLabel('錄音人員',{exact:true}).fill('Sync '+i);
      await phones[i].getByRole('button',{name:'加入此錄音房間'}).click();
      await phones[i].getByRole('button',{name:'連接麥克風',exact:true}).click();
    }
    const takeIds:string[]=[];
    for(let take=0;take<2;take++){
      await expect(host.getByRole('button',{name:'開始統一錄音'})).toBeEnabled();
      await host.getByRole('button',{name:'開始統一錄音'}).click();
      await expect(host.locator('.control-state')).toContainText('錄音進行中',{timeout:15000});
      await expect(host.getByTestId('elapsed')).toHaveText('00:00:02',{timeout:12000});
      await host.getByRole('button',{name:'由主控者停止錄音'}).click();
      await expect(host.locator('.control-state')).toContainText('錄音儲存完成',{timeout:30000});
      const state=await host.evaluate(async()=>{
        const identity=JSON.parse(localStorage.getItem('cnc-identities')!)[0];
        return (await fetch('/api/rooms/'+identity.room_code,{headers:{Authorization:'Bearer '+identity.token}})).json();
      });
      takeIds.push(state.id);expect(state.started_at).toBe(state.starts_at);
      expect(state.recordings).toHaveLength(2);
      for(const r of state.recordings){expect(r.capture_server_ms).not.toBeNull();expect(state.starts_at-r.capture_server_ms).toBeGreaterThan(1500);expect(r.interrupted).toBe(false);expect(r.byte_size).toBeGreaterThan(1000);}
      if(take===0)await host.getByRole('button',{name:'準備下一次錄音'}).click();
    }
    expect(new Set(takeIds).size).toBe(2);
    await host.getByRole('button',{name:'錄音結果',exact:true}).click();
    await host.getByRole('button',{name:'驗證同步並產生共同時間 WAV'}).click();
    await expect(host.getByText(/無法驗證：參考音缺失/)).toBeVisible();
    await expect(host.getByRole('link',{name:/同步 WAV/})).toHaveCount(0);
  }finally{await Promise.all(contexts.map(c=>c.close()));}
});
