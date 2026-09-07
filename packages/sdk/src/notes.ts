/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Notes API Client
 * ─────────────────────────────────────────────────────────────────────────── */
import { request, api } from './client';

export interface Note {
  id: number;
  title: string;
  content: string;
  tags: string[];
  updated_at: string;
}

export const notes = {
  list: () =>
    request<Note[]>('/api/notes'),

  create: (data: { title: string; content?: string }) =>
    request<{ id: number; title: string }>('/api/notes', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (id: number, data: { title?: string; content?: string }) =>
    request<{ id: number; title: string }>(`/api/notes/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  delete: (id: number) =>
    request<{ deleted: boolean }>(`/api/notes/${id}`, { method: 'DELETE' }),
};
