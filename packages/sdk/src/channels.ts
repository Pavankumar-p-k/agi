/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Communication Channels API Client
 * ─────────────────────────────────────────────────────────────────────────── */
import { request } from './client';

export interface Channel {
  id: string;
  name: string;
  running: boolean;
}

export const channels = {
  list: () =>
    request<{ channels: Channel[] }>('/api/channels'),

  send: (channel: string, recipient: string, message: string) =>
    request<{ success: boolean }>('/api/channels/send', {
      method: 'POST',
      body: JSON.stringify({ channel, recipient, message }),
    }),
};
