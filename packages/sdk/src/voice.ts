/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Voice (STT / TTS) API Client
 * ─────────────────────────────────────────────────────────────────────────── */
import { request, api } from './client';

export interface VoiceDiagnostics {
  stt_available?: boolean;
  tts_available?: boolean;
  microphone?: boolean;
  speaker?: boolean;
}

export const voice = {
  providers: () =>
    request<{ providers: string[]; default: string }>('/api/stt/providers'),

  diagnostics: () =>
    request<VoiceDiagnostics>('/api/diagnostics/voice'),

  stt: (audio: Blob) => {
    const formData = new FormData();
    formData.append('audio', audio);
    return api.postForm<{ transcript: string }>('/stt', formData);
  },

  sttBase64: (audioBase64: string) =>
    api.post<{ transcript: string }>('/stt/base64', { audio: audioBase64 }),

  tts: (text: string) => {
    const token = typeof localStorage !== 'undefined' ? localStorage.getItem('j-token') : null;
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const base = process.env.NEXT_PUBLIC_API_URL || '';
    return fetch(`${base}/tts`, {
      method: 'POST',
      body: JSON.stringify({ text }),
      headers,
    }).then((r) => {
      if (!r.ok) throw new Error('TTS failed');
      return r.blob();
    });
  },
};
