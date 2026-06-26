/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Chat API Client
 * ─────────────────────────────────────────────────────────────────────────── */
import { request } from './client';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
}

export interface ChatSession {
  session_id: string;
  title: string;
  message_count: number;
  created_at: string;
}

export const chat = {
  send: (text: string) =>
    request<{ response: string }>('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ text }),
    }),

  history: (userId?: string, sessionId?: string) => {
    const q = new URLSearchParams();
    if (userId) q.set('user_id', userId);
    if (sessionId) q.set('session_id', sessionId);
    const qs = q.toString();
    return request<{ messages: ChatMessage[]; sessions: ChatSession[] }>(`/api/chat/history${qs ? '?' + qs : ''}`);
  },

  sessions: () =>
    request<{ sessions: ChatSession[] }>('/api/sessions'),

  upload: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return request<{ filename: string; content: string }>('/api/chat/upload', {
      method: 'POST',
      body: formData,
    });
  },
};
