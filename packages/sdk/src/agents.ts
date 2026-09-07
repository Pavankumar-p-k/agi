/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Agents API Client
 * ─────────────────────────────────────────────────────────────────────────── */
import { request } from './client';
import type { Agent } from '../generated/types';

export const agents = {
  list: () =>
    request<{ agents: Agent[] }>('/agents/').then((r) => r.agents),

  run: (name: string, task: string, mode?: string) =>
    request<{ result: unknown }>(`/agents/${encodeURIComponent(name)}/run`, {
      method: 'POST',
      body: JSON.stringify({ task, mode: mode || undefined }),
      headers: { 'Content-Type': 'application/json' },
    }),

  modes: (name: string) =>
    request<{ agent: string; modes: string[]; default_mode: string }>(
      `/agents/${encodeURIComponent(name)}/modes`,
    ),
};
