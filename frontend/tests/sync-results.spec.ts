import {test,expect} from '@playwright/test';
import {referenceSignal} from '../src/syncReference';
import {alignedWav,type SyncInput,type SyncReport} from '../src/syncAnalysis';

test('result UI verifies raw downloads, offers report and aligned WAVs without mobile overflow',async({page})=>{
  const bufferModule='node:buffer',{Buffer}=await import(bufferModule);
  const rate=48000,files:ArrayBuffer[]=[];
  for(const offset of [0,0.12]){
    const data=new Float32Array(rate*18),signal=referenceSignal(rate);
    for(const seconds of [1,1.23,1.61,8,8.23,8.61,14,14.23,14.61])data.set(signal,Math.round((seconds+offset)*rate));
    const input={id:'A',audio:{numberOfChannels:1,sampleRate:rate,getChannelData:()=>data,length:data.length},captureServerMs:1000000} as unknown as SyncInput;
    const report={frames:data.length,sampleRate:rate,startServerMs:1000000,tracks:[{id:'A',intercept:0,scale:1}]} as SyncReport;
    files.push(await alignedWav(input,input,report).arrayBuffer());
  }
  await page.route('**/api/rooms/SYNC01/recordings/*/audio?*',async route=>{
    const file=files[route.request().url().includes('/pA/')?0:1];
    const checksum=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',file)),n=>n.toString(16).padStart(2,'0')).join('');
    await route.fulfill({body:Buffer.from(file),contentType:'audio/wav',headers:{'X-Checksum':checksum}});
  });
  await page.setViewportSize({width:390,height:844});await page.goto('/');
  await page.evaluate(async()=>{
    const componentPath='/src/SyncResults.tsx',reactPath='/node_modules/.vite/deps/react.js',domPath='/node_modules/.vite/deps/react-dom_client.js';
    const [{SyncResults},{default:React},{default:ReactDOM}]=await Promise.all([import(componentPath),import(reactPath),import(domPath)]);
    document.getElementById('root')!.style.display='none';
    const root=document.createElement('main');root.className='shell';document.body.append(root);
    const room={id:'test-take',status:'completed',starts_at:1003000,stopped_at:1016000,recordings:['A','B'].map(source_label=>({source_label,participant_id:'p'+source_label,capture_server_ms:1000000,clock_uncertainty_ms:3,interrupted:false,byte_size:1728044}))};
    ReactDOM.createRoot(root).render(React.createElement(SyncResults,{room,identity:{room_code:'SYNC01',token:'test'}}));
  });
  await page.getByRole('button',{name:'驗證同步並產生共同時間 WAV'}).click();
  await expect(page.getByText('驗證狀態：參考點殘差通過 · 絕對精度：未驗證')).toBeVisible();
  await expect(page.getByRole('link',{name:'下載驗證報告'})).toBeVisible();
  await expect(page.getByRole('link',{name:/同步 WAV/})).toHaveCount(2);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:'../tmp/sync-results-mobile.png',fullPage:true});
});
