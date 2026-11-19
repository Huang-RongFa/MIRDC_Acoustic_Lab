import type { Identity } from './types';
import {staticHosting} from './config';
export class ApiError extends Error {
  constructor(message:string,public status:number){super(message);}
}

export async function api<T>(path:string, identity:Identity|null=null, init:RequestInit={}, timeoutMs=15000):Promise<T>{
  if(staticHosting)throw new Error('尚未連接錄音服務；房間、音訊儲存與分析功能待後端連接。');
  const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),timeoutMs);
  try{
    const response=await fetch('/api'+path,{...init,signal:init.signal??controller.signal,headers:{...(identity?{Authorization:'Bearer '+identity.token}:{}),...(init.body && typeof init.body==='string'?{'Content-Type':'application/json'}:{}),...init.headers}});
    if(!response.ok){const error=await response.json().catch(()=>({detail:'伺服器暫時無法連線'}));throw new ApiError(typeof error.detail==='string'?error.detail:'請檢查必填欄位與數值範圍',response.status);}
    return await response.json();
  }catch(error){
    if(controller.signal.aborted)throw new Error('伺服器請求逾時');
    throw error;
  }finally{clearTimeout(timeout);}
}
