export interface DiagnosticsResult {
  status: 'ok' | 'degraded' | 'error';
  services: Record<string, { status: string; message?: string }>;
  models_available: boolean;
  integrations_available: boolean;
  storage_available: boolean;
  memory_available: boolean;
  warnings: string[];
  errors: string[];
}

export interface VoiceDiagnostics {
  stt_available?: boolean;
  tts_available?: boolean;
  microphone?: boolean;
  speaker?: boolean;
}
