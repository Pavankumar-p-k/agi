/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Audio Emotion Analysis API Client
 * ─────────────────────────────────────────────────────────────────────────── */
import { api } from './client';

export const audio = {
  analyzeEmotion: (file: Blob | File) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.postForm<{ emotion: string; confidence: number }>(
      '/api/audio/analyze-emotion',
      formData,
    );
  },
};
