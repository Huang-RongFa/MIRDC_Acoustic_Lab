import {chromium} from '@playwright/test';
const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  const response=await page.goto(process.argv[2]||'https://huang-rongfa.github.io/MIRDC_Acoustic_Lab/',{waitUntil:'networkidle'});
  const heading=await page.getByRole('heading',{name:'三手機協作錄音'}).innerText();
  if(response.status()!==200||errors.length)throw new Error(JSON.stringify({status:response.status(),errors}));
  await page.screenshot({path:'../tmp/public-pages.png',fullPage:true});
  console.log(JSON.stringify({status:response.status(),heading,errors,url:page.url()}));
}finally{await browser.close();}
