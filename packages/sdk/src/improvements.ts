/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Improvement System Client
 *
 * Improvement opportunities, experiments, promote/rollback lifecycle.
 * ─────────────────────────────────────────────────────────────────────────── */
import { request, api } from './client';
import type { ImprovementOpportunity, PlannerExperiment } from '../generated/types';

export const improvements = {
  /** List all improvement opportunities from planner analytics. */
  listOpportunities: () =>
    request<ImprovementOpportunity[]>('/api/improvements'),

  /** List experiments, optionally filtered by status. */
  listExperiments: (status?: string) => {
    const q = status ? `?status=${encodeURIComponent(status)}` : '';
    return request<PlannerExperiment[]>(`/api/improvements/experiments${q}`);
  },

  /** Create an experiment from an opportunity. */
  createExperiment: (opportunityId: string) =>
    api.post<PlannerExperiment>('/api/improvements/experiments', { opportunity_id: opportunityId }),

  /** Start an experiment (applies config change). */
  startExperiment: (expId: string) =>
    api.post<PlannerExperiment>(`/api/improvements/experiments/${encodeURIComponent(expId)}/start`),

  /** Complete an experiment (measures results, rolls back). */
  completeExperiment: (expId: string) =>
    api.post<{ overall: string; changes: Record<string, number>; improved: boolean }>(
      `/api/improvements/experiments/${encodeURIComponent(expId)}/complete`,
    ),

  /** Promote an experiment (keep the config change). */
  promoteExperiment: (expId: string) =>
    api.post<PlannerExperiment>(`/api/improvements/experiments/${encodeURIComponent(expId)}/promote`),

  /** Roll back an experiment (restore original config). */
  rollbackExperiment: (expId: string) =>
    api.post<PlannerExperiment>(`/api/improvements/experiments/${encodeURIComponent(expId)}/rollback`),
};
