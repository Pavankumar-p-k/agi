/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Plugins API Client
 * ─────────────────────────────────────────────────────────────────────────── */
import { request } from './client';

export interface Plugin {
  name: string;
  version: string;
  description: string;
  hooks: string[];
  health: string;
  enabled?: boolean;
}

export const plugins = {
  list: (signal?: AbortSignal) =>
    request<{ plugins: Plugin[]; total: number }>('/api/plugins', { signal }),

  toggle: (name: string) =>
    request<{ enabled: boolean }>(`/api/plugins/${encodeURIComponent(name)}/toggle`, { method: 'POST' }),
};
