import { defineConfig } from 'vite';
declare const process:{env:Record<string,string|undefined>};
export default defineConfig({build:{emptyOutDir:false},server:{port:5173,proxy:{'/api':{target:process.env.CNC_BACKEND_URL||'http://127.0.0.1:8000',ws:true}}}});
