/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Workflows API Client
 *
 * Full CRUD + resume/cancel for the WorkflowEngine backend.
 * ─────────────────────────────────────────────────────────────────────────── */
import { request, api } from './client';
import type { Workflow } from '../generated/types';

export interface WorkflowListResponse {
  workflows: WorkflowSummary[];
  total: number;
}

export interface WorkflowSummary {
  workflow_id: string;
  workflow_type: string;
  status: string;
  current_step: number;
  total_steps: number;
  progress: string;
  created_at: string | null;
  updated_at: string | null;
  owner: string;
  artifacts: unknown[];
}

export interface WorkflowDetail extends WorkflowSummary {
  steps: WorkflowStepDetail[];
  last_heartbeat: string | null;
  session_id: string;
  timeout_seconds: number | null;
  retry_count: number;
  retry_budget: number;
  parent_workflow_id: string | null;
  execution_context: Record<string, unknown>;
}

export interface WorkflowStepDetail {
  step_id: string;
  tool_name: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  retry_count: number;
}

export const workflows = {
  /** List workflows, optionally filtered by status. */
  list: (status?: string, limit?: number) => {
    const q = new URLSearchParams();
    if (status) q.set('status', status);
    if (limit) q.set('limit', String(limit));
    const qs = q.toString();
    return request<WorkflowListResponse>(`/api/workflows${qs ? '?' + qs : ''}`);
  },

  /** Get a single workflow with full step details. */
  get: (id: string) =>
    request<WorkflowDetail>(`/api/workflows/${encodeURIComponent(id)}`),

  /** Resume a paused/failed workflow. */
  resume: (id: string) =>
    api.post<{ workflow_id: string; status: string; resumed: boolean }>(`/api/workflows/${encodeURIComponent(id)}/resume`),

  /** Cancel a running workflow. */
  cancel: (id: string) =>
    api.post<{ workflow_id: string; status: string; cancelled: boolean }>(`/api/workflows/${encodeURIComponent(id)}/cancel`),
};
