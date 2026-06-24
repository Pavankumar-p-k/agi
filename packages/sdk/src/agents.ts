/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Agents API Client
 * ─────────────────────────────────────────────────────────────────────────── */
import { request } from './client';
import type { Agent } from '../generated/types';

export const agents = {
  list: () =>
    request<{ agents: Agent[] }>('/api/v1/agents/').then((r) => r.agents),

  run: (name: string, task: string, mode?: string) =>
    request<{ result: unknown }>(`/api/v1/agents/${encodeURIComponent(name)}/run`, {
      method: 'POST',
      body: JSON.stringify({ task, mode: mode || undefined }),
      headers: { 'Content-Type': 'application/json' },
    }),

  modes: (name: string) =>
    request<{ agent: string; modes: string[]; default_mode: string }>(
      `/api/v1/agents/${encodeURIComponent(name)}/modes`,
    ),
};
