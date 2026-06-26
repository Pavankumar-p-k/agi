/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Projects API Client
 * ─────────────────────────────────────────────────────────────────────────── */
import { request, api } from './client';

export interface Project {
  id: string;
  name: string;
  status: string;
  description?: string;
  created_at?: string;
}

export const projects = {
  list: (status?: string) =>
    request<{ projects: Project[] }>(
      status ? `/projects?status=${encodeURIComponent(status)}` : '/projects',
    ),

  get: (id: string) =>
    request<Project>(`/projects/${encodeURIComponent(id)}`),

  create: (data: { name: string; description?: string }) =>
    request<Project>('/projects', { method: 'POST', body: JSON.stringify(data) }),

  update: (id: string, data: Record<string, unknown>) =>
    request<{ status: string }>(`/projects/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    request<{ status: string }>(`/projects/${encodeURIComponent(id)}`, { method: 'DELETE' }),
};
