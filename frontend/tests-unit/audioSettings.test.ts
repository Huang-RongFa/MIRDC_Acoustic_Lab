import {test} from 'node:test';
import assert from 'node:assert/strict';
import {summarizeProcessing,processingLabel} from '../src/audioSettings.ts';

test('三項處理都回報關閉 → 原始收音',()=>{
  const r=summarizeProcessing({echoCancellation:false,noiseSuppression:false,autoGainControl:false,sampleRate:48000,channelCount:1,latency:0.01});
  assert.equal(r.raw,true);assert.deepEqual(r.warnings,[]);
  assert.match(processingLabel(r),/原始收音/);
});

test('任一項仍開啟 → raw=false 並列出',()=>{
  const r=summarizeProcessing({echoCancellation:false,noiseSuppression:true,autoGainControl:true,sampleRate:48000});
  assert.equal(r.raw,false);
  assert.match(processingLabel(r),/降噪仍開啟/);
  assert.match(processingLabel(r),/自動增益仍開啟/);
});

test('未回報（例如 iOS Safari）→ raw=null，不得當成原始收音',()=>{
  const r=summarizeProcessing({sampleRate:48000});
  assert.equal(r.raw,null);
  assert.match(processingLabel(r),/無法確認/);
});

test('開啟優先於未回報',()=>{
  const r=summarizeProcessing({echoCancellation:true});
  assert.equal(r.raw,false);
});

test('低取樣率警告；非數值欄位當成未知',()=>{
  const r=summarizeProcessing({echoCancellation:false,noiseSuppression:false,autoGainControl:false,sampleRate:16000,latency:'x'});
  assert.equal(r.raw,true);assert.equal(r.latency,null);
  assert.ok(r.warnings.some(w=>w.includes('16000')));
});

test('尚未授權',()=>{assert.match(processingLabel(null),/尚未授權/);});
