/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Shared HTTP Client
 *
 * Generic request/response handling for all backend API calls.
 * Auth token injected automatically from localStorage.
 * ─────────────────────────────────────────────────────────────────────────── */
import type { ActivityEvent } from '../generated/types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

function getToken(): string | null {
  if (typeof localStorage === 'undefined') return null;
  return localStorage.getItem('j-token');
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`;
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init?.headers as Record<string, string>),
  };
  const token = getToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  const res = await fetch(url, { ...init, headers });
  if (!res.ok) {
    if (res.status === 401 && typeof localStorage !== 'undefined') {
      localStorage.removeItem('j-token');
    }
    const body = await res.text().catch(() => '');
    throw new ApiError(res.status, body || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export function getTokenForWs(): string | null {
  return getToken();
}

// ── Generic HTTP methods ──────────────────────────────────────────────────

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PUT', body: JSON.stringify(body) }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PATCH', body: body ? JSON.stringify(body) : undefined }),
  del: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  postForm: <T>(path: string, formData: FormData) => {
    const token = getToken();
    const headers: Record<string, string> = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    return fetch(`${API_BASE}${path}`, { method: 'POST', body: formData, headers }).then(
      (r) => (r.ok ? r.json() : Promise.reject(new ApiError(r.status, r.statusText))) as Promise<T>,
    );
  },
};

// ── Event source for SSE / WebSocket ──────────────────────────────────────

export type EventHandler = (event: ActivityEvent) => void;
