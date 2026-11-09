import type { Identity } from './types';
import {staticHosting} from './config';
export async function api<T>(path:string, identity:Identity|null=null, init:RequestInit={}):Promise<T>{
  if(staticHosting)throw new Error('尚未連接錄音服務；房間、音訊儲存與分析功能待後端連接。');
  const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),15000);
  try{
    const response=await fetch('/api'+path,{...init,signal:init.signal??controller.signal,headers:{...(identity?{Authorization:'Bearer '+identity.token}:{}),...(init.body && typeof init.body==='string'?{'Content-Type':'application/json'}:{}),...init.headers}});
    if(!response.ok){const error=await response.json().catch(()=>({detail:'伺服器暫時無法連線'}));throw new Error(typeof error.detail==='string'?error.detail:'請檢查必填欄位與數值範圍');}
    return await response.json();
  }finally{clearTimeout(timeout);}
}
