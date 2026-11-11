import {test,expect} from '@playwright/test';

// 只需要 npm run dev：分析 API 以固定回應替代，驗證網頁如何呈現地端佇列狀態與對齊判定。
const identity={room_code:'TEST01',token:'t',participant_id:'p-a',session_id:'00000000-0000-4000-8000-000000000001',source_label:'A',is_host:true};
test.use({viewport:{width:390,height:844}});
const job=(status:string,extra:Record<string,unknown>={})=>({id:'j-'+status,status,attempts:1,max_attempts:3,error:null,created_at:'2026-11-11T07:00:00Z',started_at:null,finished_at:null,...extra});

test('analysis page shows local-worker queue state and blocks unverified alignment',async({page})=>{
  await page.addInitScript(id=>{localStorage.setItem('cnc-identities',JSON.stringify([id]));localStorage.setItem('cnc-current-room',id.room_code);},identity);
  await page.route('**/api/rooms/TEST01/analysis',route=>route.fulfill({json:{
    jobs:[job('failed',{attempts:3,error:'聲源 B 第 1 段 SHA256 不符'}),job('queued',{attempts:0}),job('completed')],
    results:[{id:'r1',created_at:'2026-11-11T07:01:00Z',result:{alignment:{verified:false,failed_pairs:{C_vs_A:'對齊後無法重新量測'}},summary:{}}},
             {id:'r2',created_at:'2026-11-11T07:00:30Z',result:{alignment:{verified:true,channels:['A','B','C'],failed_pairs:{}},summary:{}}}]}}));
  await page.route('**/api/rooms/TEST01',route=>route.fulfill({status:503,json:{detail:'offline in test'}}));
  await page.goto('/?room=TEST01');
  await page.getByRole('button',{name:'分析結果',exact:true}).click();
  const jobs=page.getByTestId('analysis-job');
  await expect(jobs).toHaveCount(3);
  await expect(jobs.nth(0)).toHaveText(/地端分析失敗：聲源 B 第 1 段 SHA256 不符/);
  await expect(jobs.nth(0)).toHaveClass(/warn/);
  await expect(jobs.nth(1)).toHaveText(/等待地端分析/);
  await expect(jobs.nth(2)).toHaveText('地端分析完成');
  const verdicts=page.getByTestId('alignment-verdict');
  await expect(verdicts.nth(0)).toHaveText(/不可使用.*C_vs_A/);
  await expect(verdicts.nth(1)).toHaveText('3 軌對齊已驗證（A、B、C）');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test('analysis page refreshes while a local job is running and stops after it finishes',async({page})=>{
  await page.clock.install();
  await page.addInitScript(id=>{localStorage.setItem('cnc-identities',JSON.stringify([id]));localStorage.setItem('cnc-current-room',id.room_code);},identity);
  let calls=0;
  await page.route('**/api/rooms/TEST01/analysis',route=>{calls++;route.fulfill({json:calls===1?{jobs:[job('running')],results:[]}:{jobs:[job('completed')],results:[{id:'r',created_at:'',result:{alignment:{verified:true,channels:['A','B'],failed_pairs:{}}}}]}});});
  await page.route('**/api/rooms/TEST01',route=>route.fulfill({status:503,json:{detail:'offline in test'}}));
  await page.goto('/?room=TEST01');
  await page.getByRole('button',{name:'分析結果',exact:true}).click();
  await expect(page.getByTestId('analysis-job')).toHaveText(/地端分析中/);
  await page.clock.fastForward(16000);
  await expect(page.getByTestId('analysis-job')).toHaveText('地端分析完成');
  await expect(page.getByTestId('alignment-verdict')).toHaveText('2 軌對齊已驗證（A、B）');
  const after=calls;
  await page.clock.fastForward(60000);
  expect(calls).toBe(after);
});
