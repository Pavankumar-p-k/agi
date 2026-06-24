/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Analytics / Performance Client
 *
 * Aggregate planner and system performance metrics.
 * ─────────────────────────────────────────────────────────────────────────── */
import { request } from './client';
import type { PlannerPerformance } from '../generated/types';

export const analytics = {
  /** Get aggregate planner performance metrics. */
  plannerPerformance: () =>
    request<PlannerPerformance>('/api/analytics/planner-performance'),
};
