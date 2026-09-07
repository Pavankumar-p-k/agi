/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Legacy Memory API Client
 *
 * Bridge to the older /api/memory endpoints. New code should prefer
 * the knowledge module (/api/knowledge) for structured storage.
 * ─────────────────────────────────────────────────────────────────────────── */
import { request, api } from './client';

export interface MemoryEntry {
  id: string;
  content: string;
  type: string;
  timestamp: string;
  tags?: string[];
}

export interface MemoryStats {
  total: number;
  total_entries?: number;
  vector_count?: number;
  episodic_count?: number;
  semantic_count?: number;
  by_category?: Record<string, number>;
}

export const memory = {
  list: () =>
    request<{ memories: MemoryEntry[] }>('/api/memory').then((response) => response.memories),

  stats: () =>
    request<MemoryStats>('/api/memory/stats'),

  search: (q: string, limit?: number) =>
    request<{ query: string; results: MemoryEntry[] }>(
      `/api/memory/search?q=${encodeURIComponent(q)}${limit ? `&limit=${limit}` : ''}`,
    ),
};
