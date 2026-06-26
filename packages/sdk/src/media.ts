/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Media Player API Client
 * ─────────────────────────────────────────────────────────────────────────── */
import { request, api } from './client';

export const media = {
  status: () =>
    request<Record<string, unknown>>('/api/media/status'),

  play: (trackIndex?: number) =>
    request<{ playing: boolean }>(
      trackIndex !== undefined ? `/api/media/play?track_index=${trackIndex}` : '/api/media/play',
      { method: 'POST' },
    ),

  pause: () =>
    request<{ paused: boolean }>('/api/media/pause', { method: 'POST' }),

  next: () =>
    request<Record<string, unknown>>('/api/media/next', { method: 'POST' }),

  prev: () =>
    request<Record<string, unknown>>('/api/media/prev', { method: 'POST' }),

  volume: (level: number) =>
    request<{ volume: number }>(`/api/media/volume/${level}`, { method: 'POST' }),

  playlist: () =>
    request<Record<string, unknown>>('/api/media/playlist'),

  suggest: (mood: string) =>
    request<Record<string, unknown>>(`/api/media/suggest/${encodeURIComponent(mood)}`),
};
