/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Reminders API Client
 * ─────────────────────────────────────────────────────────────────────────── */
import { request, api } from './client';

export interface Reminder {
  id: number;
  title: string;
  remind_at: string;
  repeat?: string;
}

export const reminders = {
  list: () =>
    request<Reminder[]>('/api/reminders'),

  create: (data: { title: string; remind_at: string; description?: string }) =>
    request<{ id: number; title: string; remind_at: string }>('/api/reminders', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  delete: (id: number) =>
    request<{ deleted: boolean }>(`/api/reminders/${id}`, { method: 'DELETE' }),
};
