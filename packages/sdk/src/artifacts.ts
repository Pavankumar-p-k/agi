/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Artifacts API Client
 *
 * Full CRUD + search + download for the ArtifactStore backend.
 * ─────────────────────────────────────────────────────────────────────────── */
import { request, api } from './client';
import type { Artifact } from '../generated/types';

export interface ArtifactListResponse {
  artifacts: Artifact[];
  total: number;
  offset: number;
  limit: number;
}

export const artifacts = {
  /** List artifacts, optionally filtered by workflow_id and artifact_type. */
  list: (params?: { workflowId?: string; artifactType?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    if (params?.workflowId) q.set('workflow_id', params.workflowId);
    if (params?.artifactType) q.set('artifact_type', params.artifactType);
    if (params?.limit) q.set('limit', String(params.limit));
    if (params?.offset) q.set('offset', String(params.offset));
    const qs = q.toString();
    return request<ArtifactListResponse>(`/api/artifacts${qs ? '?' + qs : ''}`);
  },

  /** Get a single artifact by ID. */
  get: (id: string) =>
    request<Artifact>(`/api/artifacts/${encodeURIComponent(id)}`),

  /** Search artifacts by name, type, or path. */
  search: (query: string, limit?: number) => {
    const q = new URLSearchParams({ q: query });
    if (limit) q.set('limit', String(limit));
    return request<{ artifacts: Artifact[]; total: number }>(`/api/artifacts/search?${q}`);
  },

  /** Get the download URL for an artifact. */
  downloadUrl: (id: string) => `/api/artifacts/${encodeURIComponent(id)}/download`,

  /** Delete an artifact by ID. */
  delete: (id: string) =>
    api.del<{ deleted: string }>(`/api/artifacts/${encodeURIComponent(id)}`),
};
