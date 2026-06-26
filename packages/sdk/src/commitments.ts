/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Commitments API Client
 * ─────────────────────────────────────────────────────────────────────────── */
import { request } from './client';

export interface Commitment {
  id: string;
  description: string;
  status?: string;
}

export const commitments = {
  list: (status?: string) =>
    request<{ commitments: Commitment[] }>(
      status ? `/api/commitments?status=${encodeURIComponent(status)}` : '/api/commitments',
    ),

  create: (data: { description: string; due?: string; priority?: string }) =>
    request<Record<string, unknown>>('/api/commitments', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  complete: (id: string) =>
    request<{ success: boolean }>(`/api/commitments/${encodeURIComponent(id)}/complete`, { method: 'POST' }),

  dismiss: (id: string) =>
    request<{ success: boolean }>(`/api/commitments/${encodeURIComponent(id)}/dismiss`, { method: 'POST' }),
};
