/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Activity Graph API Client
 *
 * Typed client for all Activity Graph REST endpoints.
 * Every method returns typed promises.
 * ─────────────────────────────────────────────────────────────────────────── */
import { request } from './client';
import type {
  ActivityNode,
  ActivityTree,
  ActivitySummary,
  ActivityCounts,
  ResumeContext,
} from '../generated/types';

export const activity = {
  /** List all active (non-terminal) root-level activities */
  list: () =>
    request<{ activities: ActivityNode[] }>('/api/activity').then((r) => r.activities),

  /** Get aggregate counts of activities by status */
  counts: () =>
    request<ActivityCounts>('/api/activity/counts'),

  /** Get a single activity node by ID */
  get: (id: string) =>
    request<ActivityNode>(`/api/activity/${encodeURIComponent(id)}`),

  /** Get full activity tree (nodes + edges) */
  tree: (id: string) =>
    request<ActivityTree>(`/api/activity/${encodeURIComponent(id)}/tree`),

  /** Get nodes in chronological order */
  timeline: (id: string) =>
    request<{ timeline: ActivityNode[] }>(`/api/activity/${encodeURIComponent(id)}/timeline`)
      .then((r) => r.timeline),

  /** Get summary of an activity */
  summary: (id: string) =>
    request<ActivitySummary>(`/api/activity/${encodeURIComponent(id)}/summary`),

  /** Find where to resume execution */
  resumePoint: (id: string) =>
    request<ResumeContext>(`/api/activity/${encodeURIComponent(id)}/resume`),

  /** Mark a resume point and continue */
  resume: (id: string) =>
    request<ResumeContext>(`/api/activity/${encodeURIComponent(id)}/resume`, { method: 'POST' }),

  /** Suspend/pause a running activity */
  pause: (id: string) =>
    request<{ status: string }>(`/api/activity/${encodeURIComponent(id)}/pause`, { method: 'POST' }),

  /** Cancel a running activity */
  cancel: (id: string, error?: string) =>
    request<{ status: string }>(`/api/activity/${encodeURIComponent(id)}/cancel`, {
      method: 'POST',
      body: JSON.stringify({ activity_id: id, error: error || 'cancelled by user' }),
      headers: { 'Content-Type': 'application/json' },
    }),

  /** Search activities by label */
  search: (q: string, limit = 20) =>
    request<{ results: ActivityNode[] }>(
      `/api/activity/search?q=${encodeURIComponent(q)}&limit=${limit}`,
    ).then((r) => r.results),

  /** Get nodes by agent */
  byAgent: (agentId: string, limit = 50) =>
    request<{ nodes: ActivityNode[] }>(
      `/api/activity/by-agent/${encodeURIComponent(agentId)}?limit=${limit}`,
    ).then((r) => r.nodes),
};
