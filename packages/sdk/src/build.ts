/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Build System API Client
 * ─────────────────────────────────────────────────────────────────────────── */
import { request, api } from './client';

export interface BuildProject {
  name: string;
  goal: string;
  status: string;
  retries: number;
  plan?: string[];
  issues?: string[];
  quality_score?: number;
  partial_progress?: number;
}

export const build = {
  start: (goal: string, workspace?: string) =>
    request<{ name: string; status: string; goal: string }>('/api/build/start', {
      method: 'POST',
      body: JSON.stringify({ goal, workspace }),
    }),

  status: (projectName: string) =>
    request<BuildProject>(`/api/build/status/${encodeURIComponent(projectName)}`),

  projects: () =>
    request<{ projects: string[] }>('/api/build/projects'),

  queue: () =>
    request<{ projects: any[] }>('/api/build/queue'),

  interrupt: (projectName: string) =>
    request<{ status: string }>(`/api/build/interrupt/${encodeURIComponent(projectName)}`, { method: 'POST' }),

  resume: (projectName: string) =>
    request<{ status: string }>(`/api/build/resume/${encodeURIComponent(projectName)}`, { method: 'POST' }),

  cancel: (projectName: string) =>
    request<{ status: string }>(`/api/build/cancel/${encodeURIComponent(projectName)}`, { method: 'POST' }),

  daemon: (action: 'start' | 'stop' | 'install' | 'uninstall' | 'status') =>
    request<{ status: string }>('/api/build/daemon', {
      method: 'POST',
      body: JSON.stringify({ action }),
    }),
};
