import { artifacts, chat, dashboard } from '@jarvis/sdk';
import type { Artifact } from '@jarvis/sdk';

export type { Artifact };
export const apiClient = {
  artifacts: {
    list: (params?: Parameters<typeof artifacts.list>[0]) => artifacts.list(params),
    downloadUrl: (id: string) => artifacts.downloadUrl(id),
  },
  chat: { send: (text: string) => chat.send(text) },
  dashboard: { stats: (signal?: AbortSignal) => dashboard.stats(signal) },
};
