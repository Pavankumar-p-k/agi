/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Email API Client
 * ─────────────────────────────────────────────────────────────────────────── */
import { request, api } from './client';

export interface EmailMessage {
  id: string;
  subject: string;
  from: string;
  snippet: string;
  date: string;
}

export const email = {
  status: () =>
    request<{ configured: boolean; host?: string; user?: string }>('/email/status'),

  inbox: (limit?: number) =>
    request<{ messages: EmailMessage[]; count: number }>(
      limit ? `/email/inbox?limit=${limit}` : '/email/inbox',
    ),

  draft: (message: Record<string, unknown>, instruction?: string) =>
    request<{ draft: string }>('/email/draft', {
      method: 'POST',
      body: JSON.stringify({ message, instruction }),
    }),

  send: (to: string, subject: string, body: string) =>
    request<{ sent: boolean }>('/email/send', {
      method: 'POST',
      body: JSON.stringify({ to, subject, body }),
    }),
};
