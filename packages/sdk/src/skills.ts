/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Skills API Client
 * ─────────────────────────────────────────────────────────────────────────── */
import { request } from './client';

export interface Skill {
  name: string;
  description: string;
  enabled: boolean;
}

export const skills = {
  list: () =>
    request<{ skills: Skill[] }>('/api/skills'),

  toggle: (name: string) =>
    request<{ enabled: boolean }>(`/api/skills/${encodeURIComponent(name)}/toggle`, { method: 'POST' }),
};
