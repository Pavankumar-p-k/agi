/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Autonomous Improvement Loop Client
 *
 * Close the opportunity→experiment→outcome→calibration cycle automatically.
 * ─────────────────────────────────────────────────────────────────────────── */
import { api } from './client';

export interface TickResult {
  action: string;
  opp_id?: string;
  experiment_id?: string;
  result?: unknown;
  improved?: boolean;
  delta?: number;
  reason?: string;
  error?: string;
}

export const autonomous = {
  /** Advance one opportunity one step. */
  tick: () =>
    api.post<TickResult>('/api/autonomous/tick'),

  /** Advance a specific opportunity one step. */
  advance: (oppId: string) =>
    api.post<TickResult>(`/api/autonomous/advance/${encodeURIComponent(oppId)}`),

  /** Run the full lifecycle for an opportunity. */
  runCycle: (oppId: string) =>
    api.post<TickResult[]>(`/api/autonomous/run/${encodeURIComponent(oppId)}`),
};
