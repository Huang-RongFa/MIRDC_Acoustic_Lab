// 瀏覽器實際套用的收音處理狀態。網頁要求關閉 echoCancellation / noiseSuppression / autoGainControl，
// 但瀏覽器或作業系統不一定照做；只有 getSettings() 回報的值才算數。iOS Safari 可能不回報（undefined）。
export type ProcessingReport={
  echoCancellation:boolean|null;
  noiseSuppression:boolean|null;
  autoGainControl:boolean|null;
  sampleRate:number|null;
  channelCount:number|null;
  latency:number|null;
  /** true：三項都回報為關閉；false：至少一項仍開啟；null：至少一項未回報、無法確認。 */
  raw:boolean|null;
  warnings:string[];
};

type SettingsLike={echoCancellation?:unknown;noiseSuppression?:unknown;autoGainControl?:unknown;sampleRate?:unknown;channelCount?:unknown;latency?:unknown};

const names:Record<'echoCancellation'|'noiseSuppression'|'autoGainControl',string>={echoCancellation:'回音消除',noiseSuppression:'降噪',autoGainControl:'自動增益'};

export function summarizeProcessing(settings:SettingsLike):ProcessingReport{
  const flag=(v:unknown)=>typeof v==='boolean'?v:null;
  const num=(v:unknown)=>typeof v==='number'&&Number.isFinite(v)?v:null;
  const report:ProcessingReport={
    echoCancellation:flag(settings.echoCancellation),noiseSuppression:flag(settings.noiseSuppression),autoGainControl:flag(settings.autoGainControl),
    sampleRate:num(settings.sampleRate),channelCount:num(settings.channelCount),latency:num(settings.latency),raw:true,warnings:[]
  };
  for(const key of Object.keys(names) as (keyof typeof names)[]){
    if(report[key]===true){report.raw=false;report.warnings.push(`${names[key]}仍開啟，相位與位準會被改變`);}
    else if(report[key]===null){if(report.raw)report.raw=null;report.warnings.push(`瀏覽器未回報${names[key]}狀態`);}
  }
  if(report.sampleRate!==null&&report.sampleRate<44100)report.warnings.push(`取樣率 ${report.sampleRate} Hz 偏低，高頻機台聲會遺失`);
  return report;
}

export function processingLabel(report:ProcessingReport|null):string{
  if(!report)return '尚未授權，無法確認收音處理';
  if(report.raw===true)return '原始收音：回音消除、降噪、自動增益皆已關閉';
  if(report.raw===false)return '收音被處理：'+report.warnings.filter(w=>w.includes('仍開啟')).join('；');
  return '無法確認收音處理：'+report.warnings.filter(w=>w.includes('未回報')).join('；');
}
