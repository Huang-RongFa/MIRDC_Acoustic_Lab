import { test } from 'node:test';
import assert from 'node:assert/strict';
import { alignmentLabel, hasActiveJob, jobLabel, type AnalysisJob } from '../src/analysisStatus.ts';

const base: AnalysisJob = { id: 'j', status: 'queued', attempts: 0, max_attempts: 3, error: null, created_at: '', started_at: null, finished_at: null };

test('job labels cover every queue state without inventing results', () => {
  assert.equal(jobLabel(base).tone, 'neutral');
  assert.match(jobLabel(base).text, /等待地端分析/);
  const retry = jobLabel({ ...base, attempts: 1, error: '聲源 B 第 3 段 SHA256 不符' });
  assert.equal(retry.tone, 'warn');
  assert.match(retry.text, /1\/3.*SHA256/);
  assert.match(jobLabel({ ...base, status: 'running', attempts: 2 }).text, /第 2 次/);
  assert.equal(jobLabel({ ...base, status: 'completed' }).tone, 'ok');
  assert.match(jobLabel({ ...base, status: 'failed', error: null }).text, /原因未回報/);
});

test('alignment verdict blocks numbers when the residual check failed', () => {
  assert.equal(alignmentLabel({}), null);
  assert.equal(alignmentLabel(null), null);
  assert.deepEqual(alignmentLabel({ alignment: { verified: true, channels: ['A', 'B', 'C'], failed_pairs: {} } }), { text: '3 軌對齊已驗證（A、B、C）', tone: 'ok' });
  assert.equal(alignmentLabel({ alignment: { verified: true, channels: ['A', 'B'], failed_pairs: {} } })?.text, '2 軌對齊已驗證（A、B）');
  const bad = alignmentLabel({ alignment: { verified: false, failed_pairs: { C_vs_A: '對齊後無法重新量測' } } });
  assert.equal(bad?.tone, 'warn');
  assert.match(bad!.text, /不可使用.*C_vs_A/);
});

test('only queued or running jobs keep the page polling', () => {
  assert.equal(hasActiveJob([]), false);
  assert.equal(hasActiveJob([{ ...base, status: 'completed' }, { ...base, status: 'failed' }]), false);
  assert.equal(hasActiveJob([{ ...base, status: 'completed' }, { ...base, status: 'running' }]), true);
});
