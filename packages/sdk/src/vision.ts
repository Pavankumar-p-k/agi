/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Vision API Client
 * ─────────────────────────────────────────────────────────────────────────── */
import { request } from './client';

export const vision = {
  screen: () =>
    request<{ description: string; b64: string; width: number; height: number }>(
      '/api/vision/screen',
      { method: 'POST' },
    ),

  analyze: (question: string) =>
    request<{ question: string; answer: string; b64: string }>(
      '/api/vision/analyze',
      { method: 'POST', body: JSON.stringify({ question }) },
    ),
};
