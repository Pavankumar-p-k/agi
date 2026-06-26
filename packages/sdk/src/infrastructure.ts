/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Infrastructure API Client
 *
 * Sandbox, Backup, Failover, Cron management.
 * ─────────────────────────────────────────────────────────────────────────── */
import { request, api } from './client';

export interface BackupEntry {
  path: string;
  created_at: string;
}

export interface FailoverProfile {
  name: string;
  healthy: boolean;
}

export const infrastructure = {
  sandbox: {
    status: () =>
      request<{ available: boolean }>('/api/sandbox/status'),
    exec: (code: string, timeout?: number) =>
      request<Record<string, unknown>>('/api/sandbox/exec', {
        method: 'POST',
        body: JSON.stringify({ code, timeout }),
      }),
  },

  backup: {
    create: () =>
      request<Record<string, unknown>>('/api/backup/create', { method: 'POST' }),
    list: () =>
      request<{ backups: BackupEntry[] }>('/api/backup/list'),
    restore: (path: string) =>
      request<Record<string, unknown>>('/api/backup/restore', {
        method: 'POST',
        body: JSON.stringify({ path }),
      }),
  },

  failover: () =>
    request<{ enabled: boolean; profiles: FailoverProfile[] }>('/api/failover/status'),

  cron: {
    list: () =>
      request<{ jobs: any[] }>('/api/cron/jobs'),
    create: (job: { id: string; schedule: string; action: string; params?: Record<string, unknown> }) =>
      request<any>('/api/cron/jobs', { method: 'POST', body: JSON.stringify(job) }),
    delete: (jobId: string) =>
      request<{ removed: boolean }>(`/api/cron/jobs/${encodeURIComponent(jobId)}`, { method: 'DELETE' }),
  },
};
