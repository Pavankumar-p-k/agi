/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Opportunity Discovery Client
 *
 * Discover, score, and prioritize improvement opportunities across all
 * subsystems. Accept/reject, forecast, roadmap, bottleneck analysis.
 * ─────────────────────────────────────────────────────────────────────────── */
import { request, api } from './client';
import type {
  Opportunity,
  RoadmapPhase,
  Bottleneck,
  ForecastedOpportunity,
} from '../generated/types';

export const opportunities = {
  /** List persisted opportunities, optionally filtered. */
  list: (status?: string, source?: string) => {
    const params = new URLSearchParams();
    if (status) params.set('status', status);
    if (source) params.set('source', source);
    const q = params.toString() ? `?${params.toString()}` : '';
    return request<Opportunity[]>(`/api/opportunities${q}`);
  },

  /** Run discovery engine and persist new opportunities. */
  discover: () =>
    api.post<{ discovered: number; total: number }>('/api/opportunities/discover'),

  /** Accept an opportunity (optionally create a negotiation). */
  accept: (id: string, createNegotiation = false) =>
    api.post<{ status: string; opportunity: Opportunity; negotiation?: { id: string; decision: string } }>(
      `/api/opportunities/${encodeURIComponent(id)}/accept`,
      { create_negotiation: createNegotiation },
    ),

  /** Reject an opportunity. */
  reject: (id: string) =>
    api.post<{ status: string }>(`/api/opportunities/${encodeURIComponent(id)}/reject`),

  /** Get current system capability scores. */
  scoredSystems: () =>
    request<Record<string, number>>('/api/opportunities/scored-systems'),

  /** Forecast future opportunity scores. */
  forecast: (horizon: string = 'medium_term') =>
    request<ForecastedOpportunity[]>(`/api/opportunities/forecast?horizon=${encodeURIComponent(horizon)}`),

  /** List bottleneck systems. */
  bottlenecks: () =>
    request<Bottleneck[]>('/api/opportunities/bottlenecks'),

  /** Generate a phased improvement roadmap. */
  roadmap: () =>
    api.post<RoadmapPhase[]>('/api/opportunities/roadmap'),

  /** Get the opportunity dependency graph. */
  graph: () =>
    request<{ nodes: any[]; edges: any[] }>('/api/opportunities/graph'),
};
