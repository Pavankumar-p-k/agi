/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Negotiation Client
 *
 * Multi-agent negotiation: create sessions, view opinions, resolve.
 * ─────────────────────────────────────────────────────────────────────────── */
import { request, api } from './client';
import type { NegotiationSession } from '../generated/types';

export const negotiations = {
  /** Create a negotiation session for a goal. */
  create: (goal: string) =>
    api.post<NegotiationSession>('/api/negotiations', { goal }),

  /** List negotiation sessions, optionally filtered by status. */
  list: (status?: string) => {
    const q = status ? `?status=${encodeURIComponent(status)}` : '';
    return request<NegotiationSession[]>(`/api/negotiations${q}`);
  },

  /** Get a single negotiation session with opinions. */
  get: (id: string) =>
    request<NegotiationSession>(`/api/negotiations/${encodeURIComponent(id)}`),

  /** Accept or reject the consensus of a session. */
  resolve: (id: string, accepted: boolean) =>
    api.post<NegotiationSession>(`/api/negotiations/${encodeURIComponent(id)}/resolve`, { accepted }),

  /** Re-collect opinions and re-compute consensus. */
  renegotiate: (id: string) =>
    api.post<NegotiationSession>(`/api/negotiations/${encodeURIComponent(id)}/renegotiate`),
};
