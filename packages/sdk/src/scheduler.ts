/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Scheduler API Client
 *
 * Full CRUD + pause/resume for the Scheduler backend.
 * Schedules define recurring activities or workflow triggers.
 * ─────────────────────────────────────────────────────────────────────────── */
import { request, api } from './client';
import type { Schedule, ScheduleListResponse } from '../generated/types';

export interface CreateSchedulePayload {
  name: string;
  activity_id?: string;
  workflow_id?: string;
  cron?: string;
  interval_seconds?: number;
}

export const scheduler = {
  /** List all schedules, optionally filtered by status. */
  list: (status?: string) => {
    const q = status ? `?status=${encodeURIComponent(status)}` : '';
    return request<ScheduleListResponse>(`/api/schedules${q}`);
  },

  /** Get a single schedule by ID. */
  get: (id: string) =>
    request<Schedule>(`/api/schedules/${encodeURIComponent(id)}`),

  /** Create a new schedule. */
  create: (payload: CreateSchedulePayload) =>
    api.post<Schedule>('/api/schedules', payload),

  /** Pause an active schedule. */
  pause: (id: string) =>
    api.post<{ id: string; status: string }>(`/api/schedules/${encodeURIComponent(id)}/pause`),

  /** Resume a paused schedule. */
  resume: (id: string) =>
    api.post<{ id: string; status: string }>(`/api/schedules/${encodeURIComponent(id)}/resume`),

  /** Delete a schedule permanently. */
  delete: (id: string) =>
    api.del<{ deleted: string }>(`/api/schedules/${encodeURIComponent(id)}`),
};
