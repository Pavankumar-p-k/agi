/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Features API Client
 * ─────────────────────────────────────────────────────────────────────────── */
import { request, api } from './client';

export interface Feature {
  name: string;
  slug: string;
  enabled: boolean;
  category: string;
  description: string;
}

export const features = {
  list: (category?: string) =>
    request<{ features: Feature[]; total: number }>(
      category ? `/api/features?category=${encodeURIComponent(category)}` : '/api/features',
    ),

  get: (slug: string) =>
    request<Feature>(`/api/features/${encodeURIComponent(slug)}`),

  toggle: (slug: string, enabled?: boolean) =>
    request<{ slug: string; enabled: boolean }>(
      `/api/features/${encodeURIComponent(slug)}/toggle`,
      { method: 'POST', body: enabled !== undefined ? JSON.stringify({ enabled }) : undefined },
    ),

  categories: () =>
    request<{ categories: { id: string; label: string; count: number }[] }>('/api/features/categories'),

  report: () =>
    request<Record<string, unknown>[]>('/api/features/report'),
};
