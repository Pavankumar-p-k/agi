/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Research Memory API Client
 *
 * Sessions, facts, contradictions, and statistics for the Research Memory.
 * ─────────────────────────────────────────────────────────────────────────── */
import { request, api } from './client';
import type {
  ResearchFact,
  ResearchSession,
  ResearchSessionDetail,
  ResearchStatistics,
  ResearchContradiction,
  ResearchSessionListResponse,
  ResearchFactListResponse,
  ResearchSearchResponse,
  ResearchContradictionsResponse,
} from '../generated/types';

export const research = {
  /** List all research sessions (grouped by activity_id). */
  listSessions: (limit?: number) => {
    const q = limit ? `?limit=${limit}` : '';
    return request<ResearchSessionListResponse>(`/api/research/sessions${q}`);
  },

  /** Get a single research session with facts, contradictions, agreements, syntheses. */
  getSession: (activityId: string) =>
    request<ResearchSessionDetail>(`/api/research/sessions/${encodeURIComponent(activityId)}`),

  /** List facts, optionally filtered by category, source_url, or activity_id. */
  listFacts: (params?: { category?: string; source_url?: string; activity_id?: string; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.category) q.set('category', params.category);
    if (params?.source_url) q.set('source_url', params.source_url);
    if (params?.activity_id) q.set('activity_id', params.activity_id);
    if (params?.limit) q.set('limit', String(params.limit));
    const qs = q.toString();
    return request<ResearchFactListResponse>(`/api/research/facts${qs ? '?' + qs : ''}`);
  },

  /** Get a single fact by ID. */
  getFact: (id: string) =>
    request<ResearchFact>(`/api/research/facts/${encodeURIComponent(id)}`),

  /** Search facts by text query. */
  search: (query: string, limit?: number) =>
    api.post<ResearchSearchResponse>('/api/research/search', { query, limit }),

  /** Get research statistics. */
  statistics: () =>
    request<ResearchStatistics>('/api/research/statistics'),

  /** List contradictions across all sessions. */
  listContradictions: (limit?: number) => {
    const q = limit ? `?limit=${limit}` : '';
    return request<ResearchContradictionsResponse>(`/api/research/contradictions${q}`);
  },
};
