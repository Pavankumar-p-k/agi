/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Evidence Generation Client
 *
 * Generate continuous evidence to feed the autonomous learning loop.
 * ─────────────────────────────────────────────────────────────────────────── */
import { api } from './client';

export const evidence = {
  /** Generate one batch from the next source mode. */
  tick: (count = 5) =>
    api.post<{ mode: string; count: number; items: unknown[]; timestamp: string }>(
      '/api/evidence/tick', { count },
    ),

  /** Run multiple cycles across all modes. */
  run: (cycles = 100, batchSize = 5) =>
    api.post<{ cycles: number; totals: Record<string, number>; grand_total: number; duration_seconds: number }>(
      '/api/evidence/run', { cycles, batch_size: batchSize },
    ),
};
