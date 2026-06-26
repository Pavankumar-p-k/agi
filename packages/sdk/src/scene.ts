/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — 3D Scene Generation API Client
 * ─────────────────────────────────────────────────────────────────────────── */
import { request } from './client';

export const scene = {
  generate: (description: string, outputFormat: string = 'auto') =>
    request<any>('/api/scene/generate', {
      method: 'POST',
      body: JSON.stringify({ description, output_format: outputFormat }),
    }),
};
