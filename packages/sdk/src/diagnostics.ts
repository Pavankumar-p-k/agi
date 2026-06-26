/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Diagnostics API Client
 * ─────────────────────────────────────────────────────────────────────────── */
import { request } from './client';
import type { DiagnosticsResult, VoiceDiagnostics } from './types/diagnostics';

export interface IntegrationStatus {
  name: string;
  connected: boolean;
  status: Record<string, unknown>;
}

export const diagnostics = {
  all: () =>
    request<DiagnosticsResult>('/api/diagnostics'),

  models: () =>
    request<{ providers: { name: string; available: boolean }[] }>('/api/diagnostics/models'),

  integrations: () =>
    request<{ integrations: IntegrationStatus[] }>('/api/diagnostics/integrations'),

  voice: () =>
    request<VoiceDiagnostics>('/api/diagnostics/voice'),

  environment: () =>
    request<{ disk_free_gb: number; memory_free_mb: number; ollama_available: boolean }>('/api/diagnostics/environment'),

  features: () =>
    request<Record<string, unknown>[]>('/api/diagnostics/features'),
};
