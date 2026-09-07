/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Knowledge Store API Client
 *
 * Full read + search for the KnowledgeStore backend.
 * Knowledge items, experiences, patterns, and failures.
 * ─────────────────────────────────────────────────────────────────────────── */
import { request, api } from './client';
import type {
  KnowledgeItem,
  Experience,
  KnowledgeStatistics,
  KnowledgeSearchResponse,
  KnowledgeListResponse,
  ExperienceListResponse,
  PatternEntry,
  FailureEntry,
} from '../generated/types';

export const knowledge = {
  /** List all knowledge items, optionally filtered by category, tag, or min_confidence. */
  list: (params?: { category?: string; tag?: string; min_confidence?: number; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.category) q.set('category', params.category);
    if (params?.tag) q.set('tag', params.tag);
    if (params?.min_confidence) q.set('min_confidence', String(params.min_confidence));
    if (params?.limit) q.set('limit', String(params.limit));
    const qs = q.toString();
    return request<KnowledgeListResponse>(`/api/knowledge${qs ? '?' + qs : ''}`);
  },

  /** Search knowledge items by text query. */
  search: (query: string, limit?: number) =>
    api.post<KnowledgeSearchResponse>('/api/knowledge/search', { query, limit }),

  /** Get a single knowledge item by ID. */
  get: (id: string) =>
    request<KnowledgeItem>(`/api/knowledge/${encodeURIComponent(id)}`),

  /** Get aggregated knowledge statistics. */
  statistics: () =>
    request<KnowledgeStatistics>('/api/knowledge/statistics'),

  /** List experiences, optionally filtered by domain. */
  listExperiences: (params?: { domain?: string; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.domain) q.set('domain', params.domain);
    if (params?.limit) q.set('limit', String(params.limit));
    const qs = q.toString();
    return request<ExperienceListResponse>(`/api/knowledge/experiences${qs ? '?' + qs : ''}`);
  },

  /** Get a single experience by activity_id. */
  getExperience: (activityId: string) =>
    request<Experience>(`/api/knowledge/experiences/${encodeURIComponent(activityId)}`),

  /** List repair patterns from PatternFailureMemory. */
  listPatterns: (limit?: number) => {
    const q = limit ? `?limit=${limit}` : '';
    return request<{ patterns: PatternEntry[]; total: number }>(`/api/knowledge/patterns${q}`);
  },

  /** List failures from PatternFailureMemory. */
  listFailures: (limit?: number) => {
    const q = limit ? `?limit=${limit}` : '';
    return request<{ failures: FailureEntry[]; total: number }>(`/api/knowledge/failures${q}`);
  },
};
