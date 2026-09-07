/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Code Review API Client
 * ─────────────────────────────────────────────────────────────────────────── */
import { request } from './client';

export const code = {
  review: (code: string, language: string) =>
    request<{ review: string; language: string }>('/api/code/review', {
      method: 'POST',
      body: JSON.stringify({ code, language }),
    }),
};
