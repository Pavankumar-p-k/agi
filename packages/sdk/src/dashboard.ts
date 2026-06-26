/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Dashboard API Client
 * ─────────────────────────────────────────────────────────────────────────── */
import { request } from './client';

export interface DashboardStats {
  gpu_vram: string;
  gpu_pct: number;
  memory_hot: number;
  memory_cold: number;
  search_queries: number;
  commands: number;
  reminders: number;
  notes: number;
  active_models: Record<string, unknown>;
}

export interface MonthlyHighlights {
  month: string;
  conversations: number;
  commands_executed: number;
  searches: number;
  reminders: number;
  top_models: string[];
}

export const dashboard = {
  stats: (signal?: AbortSignal) =>
    request<DashboardStats>('/api/stats', { signal }),

  highlights: () =>
    request<MonthlyHighlights>('/api/monthly-highlights'),

  activity: {
    today: () =>
      request<{ type: string; description: string; ts: string }[]>('/api/activity/today'),
    summary: () =>
      request<{ date: string; summary: string; productivity_score: number }>('/api/activity/summary'),
  },
};
