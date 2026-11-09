import {test,expect} from '@playwright/test';
declare const process:{env:Record<string,string|undefined>};
test('GitHub Pages displays the design without backend calls or simulated state',async({page})=>{
  const apiCalls:string[]=[];page.on('request',request=>{if(request.url().includes('/api/'))apiCalls.push(request.url());});
  await page.goto(process.env.CNC_PAGES_TEST_URL||'http://localhost:4173/MIRDC_Acoustic_Lab/');
  await expect(page.getByRole('heading',{name:'三手機協作錄音'})).toBeVisible();
  await expect(page.getByRole('heading',{name:'三聲源錄音波形'})).toBeVisible();
  await expect(page.getByText('介面預覽',{exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'開始統一錄音'})).toBeDisabled();
  for(const label of ['錄音者','實驗紀錄','分析結果','設定管理','主控台'])await page.getByRole('button',{name:label,exact:true}).click();
  await page.setViewportSize({width:1440,height:1000});await page.screenshot({path:'../tmp/pages-desktop.png',fullPage:true});
  await page.setViewportSize({width:375,height:812});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:'../tmp/pages-mobile.png',fullPage:true});
  expect(apiCalls).toEqual([]);
});
