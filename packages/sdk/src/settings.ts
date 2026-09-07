/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Settings API Client
 * ─────────────────────────────────────────────────────────────────────────── */
import { request, api } from './client';
import type { Setting } from './types/settings';

export const settings = {
  list: (category?: string) =>
    request<Setting[]>(category ? `/api/settings?category=${encodeURIComponent(category)}` : '/api/settings'),

  get: (key: string) =>
    request<Setting>(`/api/settings/${encodeURIComponent(key)}`),

  update: (key: string, value: unknown) =>
    request<{ key: string; value: unknown; restart_required: boolean }>(
      `/api/settings/${encodeURIComponent(key)}`,
      { method: 'PUT', body: JSON.stringify({ value }) },
    ),

  bulk: (values: Record<string, unknown>) =>
    request<{ updated: Record<string, unknown>; errors: Record<string, unknown> }>(
      '/api/settings/bulk',
      { method: 'POST', body: JSON.stringify(values) },
    ),

  reset: (key?: string) =>
    request<{ message: string }>(
      key ? `/api/settings/reset/${encodeURIComponent(key)}` : '/api/settings/reset',
      { method: 'POST' },
    ),

  categories: () =>
    request<{ categories: { id: string; label: string; count: number }[] }>('/api/settings/meta/categories'),
};
