/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Automation / Cron API Client
 * ─────────────────────────────────────────────────────────────────────────── */
import { request } from './client';

export interface ScheduledJob {
  id: string;
  name: string;
  schedule: string;
  action: string;
  enabled?: boolean;
}

export const automation = {
  jobs: () =>
    request<{ jobs: ScheduledJob[] }>('/api/scheduler/jobs'),

  cronJobs: () =>
    request<{ jobs: ScheduledJob[] }>('/api/cron/jobs'),

  createCron: (job: { id: string; schedule: string; action: string; params?: Record<string, unknown> }) =>
    request<ScheduledJob>('/api/cron/jobs', { method: 'POST', body: JSON.stringify(job) }),

  deleteCron: (jobId: string) =>
    request<{ removed: boolean }>(`/api/cron/jobs/${encodeURIComponent(jobId)}`, { method: 'DELETE' }),
};
