/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Models API Client
 * ─────────────────────────────────────────────────────────────────────────── */
import { request, api } from './client';
import type { Model, ModelListResponse } from './types/models';

export const models = {
  list: () =>
    request<ModelListResponse>('/api/models'),

  groups: () =>
    request<{ groups: Record<string, string> }>('/api/models/groups'),

  providers: () =>
    request<{ providers: { name: string; available: boolean }[] }>('/api/diagnostics/models'),

  usage: () =>
    request<{ total_tokens: number; by_model: Record<string, number> }>('/api/models/usage').catch(() => ({ total_tokens: 0, by_model: {} })),

  costs: () =>
    request<{ total_cost: number; by_model: Record<string, number> }>('/api/models/costs').catch(() => ({ total_cost: 0, by_model: {} })),
};
