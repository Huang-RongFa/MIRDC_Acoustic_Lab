import {test,expect} from '@playwright/test';
declare const process:{env:Record<string,string|undefined>};
const url=process.env.CNC_PAGES_TEST_URL||'http://localhost:4173/MIRDC_Acoustic_Lab/';
test.use({locale:'zh-TW'});

test('錄音分析 on GitHub Pages is the segment viewer, without backend calls',async({page})=>{
  const apiCalls:string[]=[],failed:string[]=[],errors:string[]=[];
  page.on('request',r=>{if(r.url().includes('/api/'))apiCalls.push(r.url());});
  page.on('response',r=>{if(r.status()>=400&&r.url().includes('/MIRDC_Acoustic_Lab/'))failed.push(`${r.status()} ${r.url()}`);});
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(url);
  await page.getByRole('button',{name:'錄音分析',exact:true}).click();
  await expect(page.getByText('尚無正式分析結果')).toHaveCount(0);
  await expect(page.getByText('尚未連接分析服務')).toHaveCount(0);

  const frame=page.frameLocator('iframe[title="切段驗證頁"]');
  await expect(frame.locator('#title')).toContainText('CTWA mill dataset308');
  await expect(frame.locator('#pm option')).toHaveCount(4);
  await expect(frame.locator('#pd option')).toHaveCount(402);
  await expect(frame.locator('canvas')).toHaveCount(7);
  await expect(frame.locator('#play')).toBeEnabled();
  await expect.poll(()=>frame.locator('#audio').evaluate((a:HTMLAudioElement)=>a.duration),{timeout:15000}).toBeGreaterThan(0);

  await frame.locator('#pm').selectOption('imi_vm20i');
  await expect(frame.locator('#title')).toContainText('VM20i');
  await expect(frame.locator('#play')).toBeDisabled();
  await expect(frame.locator('#audio')).toBeHidden();
  await expect(frame.locator('#audionote')).toContainText('此場次未附音檔');
  await frame.locator('#tb tr[data-i]').nth(1).click();
  await expect(frame.locator('#card')).toContainText('目前事件 #1');

  await frame.locator('#pm').selectOption('tmf_vf10');
  await expect(frame.locator('#card')).toContainText('切段封存');
  await expect(frame.locator('#tb')).toContainText('不列事件');

  await frame.getByRole('button',{name:'EN',exact:true}).click();
  await expect(frame.locator('#card')).toContainText('Segments sealed');
  await expect(frame.locator('#audionote')).toContainText('Audio is not included');

  await page.setViewportSize({width:375,height:812});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  expect(apiCalls).toEqual([]);expect(failed).toEqual([]);expect(errors).toEqual([]);
});
