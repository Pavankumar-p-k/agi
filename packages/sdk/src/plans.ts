/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Planner / Plan API Client
 *
 * First-class plan resources with full lifecycle:
 *   draft → approve → reject → execute → replan → complete/fail
 * Also supports node-level editing (rename, reorder, reassign agents).
 * ─────────────────────────────────────────────────────────────────────────── */
import { request, api } from './client';
import type { Plan, PlanListResponse, PlanNode, PlanEvidence, PlanRisks, PlanAlternatives, PlanConfidence, PlanComparison, PlanOutcome, PlanPrediction, PlanAccuracy, PlanHealth, ReplanOptions, AutoReplanResult } from '../generated/types';

export const plans = {
  /** List plans, optionally filtered by status. */
  list: (status?: string) => {
    const q = status ? `?status=${encodeURIComponent(status)}` : '';
    return request<PlanListResponse>(`/api/plans${q}`);
  },

  /** Get a single plan by ID. */
  get: (id: string) =>
    request<Plan>(`/api/plans/${encodeURIComponent(id)}`),

  /** Create a new plan from a goal string (auto-decomposes). */
  create: (goal: string) =>
    api.post<Plan>('/api/plans', { goal }),

  /** Approve a draft/rejected plan. */
  approve: (id: string) =>
    api.post<Plan>(`/api/plans/${encodeURIComponent(id)}/approve`),

  /** Reject a draft/approved plan. */
  reject: (id: string) =>
    api.post<Plan>(`/api/plans/${encodeURIComponent(id)}/reject`),

  /** Execute an approved plan (creates scheduled activities from leaf nodes). */
  execute: (id: string) =>
    api.post<Plan>(`/api/plans/${encodeURIComponent(id)}/execute`),

  /** Replan (re-decompose) a plan back to draft status. */
  replan: (id: string) =>
    api.post<Plan>(`/api/plans/${encodeURIComponent(id)}/replan`),

  /** Update a single node within a plan. Supports all PlanNode fields except id. */
  updateNode: (planId: string, nodeId: string, patch: Partial<Omit<PlanNode, 'id'>>) =>
    api.patch<Plan>(`/api/plans/${encodeURIComponent(planId)}/nodes/${encodeURIComponent(nodeId)}`, patch),

  /** Delete a plan. */
  delete: (id: string) =>
    request<{ deleted: string }>(`/api/plans/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  /** Get per-node evidence for a plan. */
  evidence: (id: string) =>
    request<PlanEvidence>(`/api/plans/${encodeURIComponent(id)}/evidence`),

  /** Get aggregated risks for a plan. */
  risks: (id: string) =>
    request<PlanRisks>(`/api/plans/${encodeURIComponent(id)}/risks`),

  /** Get alternative approaches for a plan. */
  alternatives: (id: string) =>
    request<PlanAlternatives>(`/api/plans/${encodeURIComponent(id)}/alternatives`),

  /** Get overall and per-node confidence scores. */
  confidence: (id: string) =>
    request<PlanConfidence>(`/api/plans/${encodeURIComponent(id)}/confidence`),

  /** Compare multiple candidate plans for a goal. */
  compare: (goal: string, strategies?: string[]) =>
    api.post<PlanComparison>('/api/plans/compare', { goal, strategies }),

  /** Auto-recommend: infer strategies and compare. */
  recommend: (goal: string) =>
    api.post<PlanComparison>('/api/plans/compare', { goal }),

  /** Get outcome data (predicted vs actual) for a plan. */
  outcome: (id: string) =>
    request<PlanOutcome>(`/api/plans/${encodeURIComponent(id)}/outcome`),

  /** Get prediction data for a plan. */
  prediction: (id: string) =>
    request<PlanPrediction>(`/api/plans/${encodeURIComponent(id)}/prediction`),

  /** Get prediction accuracy (predicted vs actual comparison). */
  accuracy: (id: string) =>
    request<PlanAccuracy>(`/api/plans/${encodeURIComponent(id)}/accuracy`),

  /** Get plan health assessment. */
  health: (id: string) =>
    request<PlanHealth>(`/api/plans/${encodeURIComponent(id)}/health`),

  /** Get replan options with improvement deltas. */
  replanOptions: (id: string) =>
    request<ReplanOptions>(`/api/plans/${encodeURIComponent(id)}/replan-options`),

  /** Replan with an optional specific strategy. */
  replanWithStrategy: (id: string, strategy?: string) =>
    api.post<Plan>(`/api/plans/${encodeURIComponent(id)}/replan`, { strategy }),

  /** Auto-replan: evaluate health and replan with best strategy if needed. */
  autoReplan: (id: string) =>
    api.post<AutoReplanResult>(`/api/plans/${encodeURIComponent(id)}/auto-replan`),
};
