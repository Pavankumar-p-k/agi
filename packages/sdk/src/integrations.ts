/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Integrations API Client
 * ─────────────────────────────────────────────────────────────────────────── */
import { request, api } from './client';

export interface Integration {
  name: string;
  connected: boolean;
  status: Record<string, unknown>;
}

export const integrations = {
  list: () =>
    request<{ integrations: Integration[] }>('/api/integrations'),

  get: (name: string) =>
    request<Integration>(`/api/integrations/${encodeURIComponent(name)}`),

  connect: (name: string, credentials?: Record<string, unknown>) =>
    request<{ name: string; connected: boolean }>(
      `/api/integrations/${encodeURIComponent(name)}/connect`,
      { method: 'POST', body: credentials ? JSON.stringify({ credentials }) : undefined },
    ),

  disconnect: (name: string) =>
    request<{ name: string; connected: boolean }>(
      `/api/integrations/${encodeURIComponent(name)}/disconnect`,
      { method: 'POST' },
    ),

  send: (name: string, target: string, message: string) =>
    request<{ sent: boolean }>(
      `/api/integrations/${encodeURIComponent(name)}/send`,
      { method: 'POST', body: JSON.stringify({ target, message }) },
    ),

  health: () =>
    request<{ integrations: Integration[] }>('/api/integrations/health', { method: 'POST' }),
};
