export interface HealthStatus {
  status: 'ok' | 'degraded' | 'error';
  version: string;
  uptime_seconds: number;
  services: Record<string, 'ok' | 'error' | 'unknown'>;
  database: 'ok' | 'error';
}

export interface SystemStatus {
  status: string;
  mode: string;
  version: string;
  uptime: string;
  processes: Record<string, string>;
}

export interface SystemStats {
  cpu_percent: number;
  memory_percent: number;
  memory_used_gb: number;
  memory_total_gb: number;
  disk_free_gb: number;
  disk_total_gb: number;
  gpu_available: boolean;
  gpu_vram?: string;
  ollama_running: boolean;
  active_models: number;
  python_version: string;
  platform: string;
}
