/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Horizon Goals API Client
 * ─────────────────────────────────────────────────────────────────────────── */
import { request, api } from './client';

export interface HorizonGoal {
  goal_id: string;
  description: string;
  domain: string;
  horizon: string;
  deadline?: string;
  progress: number;
  milestones: Array<{ id: string; description: string; completed: boolean }>;
}

export const horizon = {
  list: (domain?: string) =>
    request<{ goals: HorizonGoal[] }>(
      domain ? `/api/horizon/goals?domain=${encodeURIComponent(domain)}` : '/api/horizon/goals',
    ),

  create: (data: { goal: string; domain: string; horizon: string; deadline?: string }) =>
    request<HorizonGoal>('/api/horizon/goal', { method: 'POST', body: JSON.stringify(data) }),

  advance: (goalId: string) =>
    request<{ result: string; progress: number }>(`/api/horizon/goal/${encodeURIComponent(goalId)}/advance`, { method: 'POST' }),

  delete: (goalId: string) =>
    request<{ ok: boolean }>(`/api/horizon/goal/${encodeURIComponent(goalId)}`, { method: 'DELETE' }),
};
