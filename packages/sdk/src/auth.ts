/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Auth API Client
 * ─────────────────────────────────────────────────────────────────────────── */
import { request } from './client';

export interface AuthResponse {
  token?: string;
  username?: string;
}

export const auth = {
  login: (username: string, password: string) =>
    request<AuthResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),

  status: () =>
    request<{ status: string }>('/auth/status'),

  providers: () =>
    request<{ providers: string[] }>('/auth/providers'),
};
