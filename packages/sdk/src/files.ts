/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Files API Client
 * ─────────────────────────────────────────────────────────────────────────── */
import { request, api } from './client';

export interface FileEntry {
  name: string;
  is_dir: boolean;
  size: number;
  modified: string;
}

export const files = {
  list: (path?: string) =>
    request<{ path: string; entries: FileEntry[] }>(
      path ? `/api/files?path=${encodeURIComponent(path)}` : '/api/files',
    ),

  upload: (path: string, file: File) => {
    const formData = new FormData();
    formData.append('path', path);
    formData.append('file', file);
    return api.postForm<{ saved_to: string; size: number }>('/api/files/upload', formData);
  },
};
