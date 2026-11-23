import {defineConfig} from '@playwright/test';
declare const process:{env:Record<string,string|undefined>};
export default defineConfig({testDir:'./tests',timeout:90000,workers:1,reporter:'list',outputDir:'../tmp/playwright-results',use:{actionTimeout:10000,baseURL:process.env.CNC_TEST_URL||'http://localhost:5173',channel:'chrome',headless:true,launchOptions:{args:['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream']}}});
