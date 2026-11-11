/** 地端分析佇列與對齊判定的顯示文字。後端只回傳狀態；這裡不推測、不補值。 */
export type AnalysisJob = {
  id: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  attempts: number;
  max_attempts: number;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type AlignmentVerdict = { verified: boolean; channels?: string[]; failed_pairs: Record<string, string> };

export function jobLabel(job: AnalysisJob): { text: string; tone: 'ok' | 'warn' | 'neutral' } {
  switch (job.status) {
    case 'queued':
      return job.attempts > 0
        ? { text: `等待地端重試（已試 ${job.attempts}/${job.max_attempts} 次）：${job.error ?? '原因未回報'}`, tone: 'warn' }
        : { text: '等待地端分析：地端電腦開機並連線後會自動處理', tone: 'neutral' };
    case 'running':
      return { text: `地端分析中（第 ${job.attempts} 次）`, tone: 'neutral' };
    case 'completed':
      return { text: '地端分析完成', tone: 'ok' };
    case 'failed':
      return { text: `地端分析失敗：${job.error ?? '原因未回報'}`, tone: 'warn' };
  }
}

/** 佇列中或執行中時，分析頁需要定期重新讀取。 */
export function hasActiveJob(jobs: AnalysisJob[]): boolean {
  return jobs.some(j => j.status === 'queued' || j.status === 'running');
}

/** 對齊後殘差超出門檻時，同步與相位數字不可當作結果使用。 */
export function alignmentLabel(result: unknown): { text: string; tone: 'ok' | 'warn' } | null {
  const verdict = (result as { alignment?: AlignmentVerdict } | null)?.alignment;
  if (!verdict || typeof verdict.verified !== 'boolean') return null;
  const channels = Array.isArray(verdict.channels) ? verdict.channels : [];
  if (verdict.verified) return { text: channels.length ? `${channels.length} 軌對齊已驗證（${channels.join('、')}）` : '對齊已驗證', tone: 'ok' };
  const pairs = Object.entries(verdict.failed_pairs ?? {}).map(([pair, why]) => `${pair}：${why}`);
  return { text: `對齊未通過驗證，同步與相位數字不可使用（${pairs.join('；') || '原因未回報'}）`, tone: 'warn' };
}
