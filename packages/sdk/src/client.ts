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
    public code = `HTTP_${status}`,
    public data: unknown = null,
  ) {
    super(message);
    this.name = 'ApiError';
  }

}

function parseError(status: number, fallback: string, body: string): ApiError {
  try {
    const payload = JSON.parse(body);
    const error = payload?.error ?? payload;
    if (error && typeof error === 'object') {
      return new ApiError(
        status,
        String(error.message ?? error.detail ?? fallback),
        String(error.code ?? `HTTP_${status}`),
        error.data ?? null,
      );
    }
    if (typeof error === 'string') return new ApiError(status, error);
  } catch {
    // Non-JSON responses are still represented as ApiError.
  }
  return new ApiError(status, body || fallback);
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
    throw parseError(res.status, res.statusText, body);
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
    return fetch(`${API_BASE}${path}`, { method: 'POST', body: formData, headers }).then(async (r) => {
      if (r.ok) return (r.status === 204 ? undefined : await r.json()) as T;
      throw parseError(r.status, r.statusText, await r.text().catch(() => ''));
    });
  },
};

// ── Event source for SSE / WebSocket ──────────────────────────────────────

export type EventHandler = (event: ActivityEvent) => void;
