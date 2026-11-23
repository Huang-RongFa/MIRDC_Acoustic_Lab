export type RecordingSyncOptions={multiDeviceSyncEnabled:boolean;requestedSampleRate:44100|48000;channelCount?:1|2};
const key='cnc-recording-sync-options';
export function recordingSyncOptions():RecordingSyncOptions{
  try{const value=JSON.parse(localStorage.getItem(key)||'{}');return {multiDeviceSyncEnabled:true,requestedSampleRate:value.requestedSampleRate===44100?44100:48000,channelCount:value.channelCount===2?2:1};}
  catch{return {multiDeviceSyncEnabled:true,requestedSampleRate:48000,channelCount:1};}
}
export function saveRecordingSyncOptions(value:RecordingSyncOptions){localStorage.setItem(key,JSON.stringify(value));}
