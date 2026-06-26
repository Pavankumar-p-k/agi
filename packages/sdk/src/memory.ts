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
  by_category?: Record<string, number>;
}

export const memory = {
  list: () =>
    request<MemoryEntry[]>('/api/memory'),

  stats: () =>
    request<MemoryStats>('/api/memory/stats'),

  search: (q: string, limit?: number) =>
    request<{ query: string; results: MemoryEntry[] }>(
      `/api/memory/search?q=${encodeURIComponent(q)}${limit ? `&limit=${limit}` : ''}`,
    ),
};
