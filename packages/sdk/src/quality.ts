/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Quality API Client
 * ─────────────────────────────────────────────────────────────────────────── */
import { request } from './client';

export const quality = {
  grade: (type: string, content: string) =>
    request<{ aggregate_score: number; passed: boolean; criteria: any[] }>(
      '/api/quality/grade',
      { method: 'POST', body: JSON.stringify({ type, content }) },
    ),

  health: () =>
    request<{ healthy: boolean; message: string }>('/api/quality/health'),
};
