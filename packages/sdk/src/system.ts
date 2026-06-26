/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — System API Client
 * ─────────────────────────────────────────────────────────────────────────── */
import { request, api } from './client';
import type { SystemStats, SystemStatus, HealthStatus } from './types/system';

export const system = {
  health: (signal?: AbortSignal) =>
    request<HealthStatus>('/health', { signal }),

  status: () =>
    request<SystemStatus>('/api/system/status'),

  stats: (signal?: AbortSignal) =>
    request<SystemStats>('/api/system/stats', { signal }),

  testAlert: () =>
    request<{ fired: boolean }>('/api/system/test-alert', { method: 'POST' }),

  prompt: {
    optimize: (agent?: string) =>
      request<any[]>(agent ? `/api/system/prompt-optimize?agent=${encodeURIComponent(agent)}` : '/api/system/prompt-optimize', { method: 'POST' }),
    versions: (agent?: string) =>
      request<any>(agent ? `/api/system/prompt-versions?agent=${encodeURIComponent(agent)}` : '/api/system/prompt-versions'),
    rollback: (agent: string) =>
      request<any>(`/api/system/prompt-rollback/${encodeURIComponent(agent)}`, { method: 'POST' }),
  },
};
