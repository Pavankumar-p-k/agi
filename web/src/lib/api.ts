const API = process.env.NEXT_PUBLIC_API_URL || '';

function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('j-token');
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = path.startsWith('http') ? path : `${API}${path}`;
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init?.headers as Record<string, string>),
  };
  const token = getToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  const res = await fetch(url, { ...init, headers });
  if (!res.ok) {
    if (res.status === 401) {
      localStorage.removeItem('j-token');
    }
    throw new ApiError(res.status, await res.text());
  }
  return res.json();
}

async function requestBlob(path: string, init?: RequestInit): Promise<Blob> {
  const url = path.startsWith('http') ? path : `${API}${path}`;
  const headers: Record<string, string> = {
    ...(init?.headers as Record<string, string>),
  };
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(url, { ...init, headers });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return res.blob();
}

export interface SystemStats {
  cpu: { percent: number; count: number };
  memory: { total: number; available: number; percent: number };
  disk: { total: number; free: number; percent: number };
  network: { bytes_sent: number; bytes_recv: number };
  timestamp: number;
}

export interface HealthStatus {
  status: string;
  version?: string;
}

export interface Plugin {
  name: string;
  version: string;
  description: string;
  hooks: string[];
  health: string;
  enabled?: boolean;
}

export interface Skill {
  name: string;
  description: string;
  enabled: boolean;
}

export interface MemoryEntry {
  id: string;
  content: string;
  type: string;
  timestamp: string;
  tags?: string[];
}

export interface MemoryStats {
  total: number;
  by_category?: Record<string, number>;
}

export interface Agent {
  name: string;
  status: string;
  description?: string;
}

export interface Model {
  id: string;
  name: string;
  provider: string;
  size?: string;
  modified_at?: string;
}

export interface ModelListResponse {
  ollama_url: string;
  ollama_available: boolean;
  ollama_error: string | null;
  models: Model[];
  total: number;
}

export interface Setting {
  key: string;
  value: unknown;
  category?: string;
}

export interface Integration {
  name: string;
  connected: boolean;
  status: Record<string, unknown>;
}

export interface Feature {
  name: string;
  slug: string;
  enabled: boolean;
  category: string;
  description: string;
}

export interface Project {
  id: string;
  name: string;
  status: string;
  description?: string;
  created_at?: string;
}

export interface ScheduledJob {
  id: string;
  name: string;
  schedule: string;
  action: string;
  enabled?: boolean;
}

export interface AuthResponse {
  token?: string;
  username?: string;
}

export interface SystemStatus {
  status: string;
  ollama: string;
  model: string;
  model_router?: { models: string[] };
  version: string;
}

export interface DiagnosticsResult {
  timestamp: string;
  data: {
    models: unknown;
    integrations: unknown;
    voice: unknown;
    features: unknown;
    environment: unknown;
    system: unknown;
  };
  errors: Record<string, unknown>;
  healthy: boolean;
}

export interface VoiceDiagnostics {
  stt_available?: boolean;
  tts_available?: boolean;
  microphone?: boolean;
  speaker?: boolean;
}

export interface BuildProject {
  name: string;
  goal: string;
  status: string;
  retries: number;
  plan?: string[];
  issues?: string[];
  quality_score?: number;
  partial_progress?: number;
}

export interface McpTool {
  id: string;
  name: string;
  description: string;
  category: string;
  available: boolean;
}

export interface HorizonGoal {
  goal_id: string;
  description: string;
  domain: string;
  horizon: string;
  deadline?: string;
  progress: number;
  milestones: Array<{ id: string; description: string; completed: boolean }>;
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) =>
    request<T>(path, { signal }),
  post: <T>(path: string, body?: unknown, signal?: AbortSignal) =>
    request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined, signal }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'PUT', body: body ? JSON.stringify(body) : undefined }),
  del: <T>(path: string) => request<T>(path, { method: 'DELETE' }),

  postForm: <T>(path: string, formData: FormData) => {
    const token = getToken();
    const headers: Record<string, string> = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const url = path.startsWith('http') ? path : `${API}${path}`;
    return fetch(url, { method: 'POST', body: formData, headers }).then(async (res) => {
      if (!res.ok) throw new ApiError(res.status, await res.text());
      return res.json() as Promise<T>;
    });
  },

  health: (signal?: AbortSignal) =>
    request<HealthStatus>('/health', { signal }),
  chat: (text: string) =>
    request<{ response: string }>('/api/chat', { method: 'POST', body: JSON.stringify({ text }) }),
  status: () => request<SystemStatus>('/api/system/status'),

  system: {
    stats: (signal?: AbortSignal) =>
      request<SystemStats>('/api/system/stats', { signal }),
    status: () => request<SystemStatus>('/api/system/status'),
    testAlert: () => request<{ fired: boolean }>('/api/system/test-alert', { method: 'POST' }),
  },

  auth: {
    login: (username: string, password: string) =>
      request<AuthResponse>('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
    status: () => request<{ status: string }>('/auth/status'),
    providers: () => request<{ providers: string[] }>('/auth/providers'),
  },

  settings: {
    list: (category?: string) =>
      request<Setting[]>(category ? `/api/settings?category=${category}` : '/api/settings'),
    get: (key: string) => request<Setting>(`/api/settings/${key}`),
    update: (key: string, value: unknown) =>
      request<{ key: string; value: unknown; restart_required: boolean }>(`/api/settings/${key}`, {
        method: 'PUT', body: JSON.stringify({ value }),
      }),
    bulk: (values: Record<string, unknown>) =>
      request<{ updated: Record<string, unknown>; errors: Record<string, unknown> }>('/api/settings/bulk', {
        method: 'POST', body: JSON.stringify(values),
      }),
    reset: (key?: string) =>
      request<{ message: string }>(key ? `/api/settings/reset/${key}` : '/api/settings/reset', { method: 'POST' }),
  },

  models: {
    list: () => request<ModelListResponse>('/api/models'),
    groups: () => request<{ groups: Record<string, string> }>('/api/models/groups'),
  },

  plugins: {
    list: (signal?: AbortSignal) =>
      request<{ plugins: Plugin[]; total: number }>('/api/plugins', { signal }),
    toggle: (name: string) =>
      request<{ enabled: boolean }>(`/api/plugins/${name}/toggle`, { method: 'POST' }),
  },

  skills: {
    list: () => request<{ skills: Skill[] }>('/api/skills'),
    toggle: (name: string) =>
      request<{ enabled: boolean }>(`/api/skills/${name}/toggle`, { method: 'POST' }),
  },

  memory: {
    list: () => request<MemoryEntry[]>('/api/memory'),
    stats: () => request<MemoryStats>('/api/memory/stats'),
    search: (q: string, limit?: number) =>
      request<{ query: string; results: MemoryEntry[] }>(`/api/memory/search?q=${encodeURIComponent(q)}${limit ? `&limit=${limit}` : ''}`),
  },

  agents: {
    list: () => request<{ agents: Agent[] }>('/api/v1/agents/'),
    run: (name: string, input: string) =>
      request<Record<string, unknown>>(`/api/v1/agents/${name}/run`, { method: 'POST', body: JSON.stringify({ input }) }),
    modes: (name: string) =>
      request<{ agent: string; modes: string[]; default_mode: string }>(`/api/v1/agents/${name}/modes`),
  },

  integrations: {
    list: () => request<{ integrations: Integration[] }>('/api/integrations'),
    get: (name: string) => request<Integration>(`/api/integrations/${name}`),
    connect: (name: string, credentials?: Record<string, unknown>) =>
      request<{ name: string; connected: boolean }>(`/api/integrations/${name}/connect`, {
        method: 'POST', body: credentials ? JSON.stringify({ credentials }) : undefined,
      }),
    disconnect: (name: string) =>
      request<{ name: string; connected: boolean }>(`/api/integrations/${name}/disconnect`, { method: 'POST' }),
    send: (name: string, target: string, message: string) =>
      request<{ sent: boolean }>(`/api/integrations/${name}/send`, { method: 'POST', body: JSON.stringify({ target, message }) }),
  },

  voice: {
    settings: () => request<Setting[]>('/api/settings?category=voice'),
    diagnostics: () => request<VoiceDiagnostics>('/api/diagnostics/voice'),
    stt: (audio: Blob) => {
      const formData = new FormData();
      formData.append('audio', audio);
      return api.postForm<{ transcript: string }>('/stt', formData);
    },
    tts: (text: string) =>
      requestBlob('/tts', { method: 'POST', body: JSON.stringify({ text }) }),
    providers: () => request<{ providers: string[]; default: string }>('/api/stt/providers'),
  },

  features: {
    list: (category?: string) =>
      request<{ features: Feature[]; total: number }>(category ? `/api/features?category=${category}` : '/api/features'),
    get: (slug: string) => request<Feature>(`/api/features/${slug}`),
    toggle: (slug: string, enabled?: boolean) =>
      request<{ slug: string; enabled: boolean }>(`/api/features/${slug}/toggle`, {
        method: 'POST', body: enabled !== undefined ? JSON.stringify({ enabled }) : undefined,
      }),
    categories: () => request<{ categories: { id: string; label: string; count: number }[] }>('/api/features/categories'),
    report: () => request<Record<string, unknown>[]>('/api/features/report'),
  },

  projects: {
    list: (status?: string) =>
      request<{ projects: Project[] }>(status ? `/projects?status=${status}` : '/projects'),
    get: (id: string) => request<Project>(`/projects/${id}`),
    create: (data: { name: string; description?: string }) =>
      request<Project>('/projects', { method: 'POST', body: JSON.stringify(data) }),
    update: (id: string, data: Record<string, unknown>) =>
      request<{ status: string }>(`/projects/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    delete: (id: string) =>
      request<{ status: string }>(`/projects/${id}`, { method: 'DELETE' }),
  },

  automation: {
    jobs: () => request<{ jobs: ScheduledJob[] }>('/api/scheduler/jobs'),
    cronJobs: () => request<{ jobs: ScheduledJob[] }>('/api/cron/jobs'),
    createCron: (job: { id: string; schedule: string; action: string; params?: Record<string, unknown> }) =>
      request<ScheduledJob>('/api/cron/jobs', { method: 'POST', body: JSON.stringify(job) }),
    deleteCron: (jobId: string) =>
      request<{ removed: boolean }>(`/api/cron/jobs/${jobId}`, { method: 'DELETE' }),
  },

  diagnostics: {
    all: () => request<DiagnosticsResult>('/api/diagnostics'),
    models: () => request<{ providers: { name: string; available: boolean }[] }>('/api/diagnostics/models'),
    integrations: () => request<{ integrations: Integration[] }>('/api/diagnostics/integrations'),
    voice: () => request<VoiceDiagnostics>('/api/diagnostics/voice'),
    environment: () => request<{ disk_free_gb: number; memory_free_mb: number; ollama_available: boolean }>('/api/diagnostics/environment'),
    features: () => request<Record<string, unknown>[]>('/api/diagnostics/features'),
  },

  dashboard: {
    stats: (signal?: AbortSignal) =>
      request<{
        gpu_vram: string;
        gpu_pct: number;
        memory_hot: number;
        memory_cold: number;
        search_queries: number;
        commands: number;
        reminders: number;
        notes: number;
        active_models: Record<string, unknown>;
      }>('/api/stats', { signal }),
    highlights: () => request<{
      month: string;
      conversations: number;
      commands_executed: number;
      searches: number;
      reminders: number;
      top_models: string[];
    }>('/api/monthly-highlights'),
    activity: {
      today: () => request<{ type: string; description: string; ts: string }[]>('/api/activity/today'),
      summary: () => request<{ date: string; summary: string; productivity_score: number }>('/api/activity/summary'),
    },
  },

  notes: {
    list: () => request<{ id: number; title: string; content: string; tags: string[]; updated_at: string }[]>('/api/notes'),
    create: (data: { title: string; content?: string }) =>
      request<{ id: number; title: string }>('/api/notes', { method: 'POST', body: JSON.stringify(data) }),
    update: (id: number, data: { title?: string; content?: string }) =>
      request<{ id: number; title: string }>(`/api/notes/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    delete: (id: number) =>
      request<{ deleted: boolean }>(`/api/notes/${id}`, { method: 'DELETE' }),
  },

  reminders: {
    list: () => request<{ id: number; title: string; remind_at: string; repeat?: string }[]>('/api/reminders'),
    create: (data: { title: string; remind_at: string; description?: string }) =>
      request<{ id: number; title: string; remind_at: string }>('/api/reminders', { method: 'POST', body: JSON.stringify(data) }),
    delete: (id: number) =>
      request<{ deleted: boolean }>(`/api/reminders/${id}`, { method: 'DELETE' }),
  },

  media: {
    status: () => request<Record<string, unknown>>('/api/media/status'),
    play: (trackIndex?: number) =>
      request<{ playing: boolean }>(trackIndex !== undefined ? `/api/media/play?track_index=${trackIndex}` : '/api/media/play', { method: 'POST' }),
    pause: () => request<{ paused: boolean }>('/api/media/pause', { method: 'POST' }),
    next: () => request<Record<string, unknown>>('/api/media/next', { method: 'POST' }),
    prev: () => request<Record<string, unknown>>('/api/media/prev', { method: 'POST' }),
    volume: (level: number) =>
      request<{ volume: number }>(`/api/media/volume/${level}`, { method: 'POST' }),
    playlist: () => request<Record<string, unknown>>('/api/media/playlist'),
    suggest: (mood: string) => request<Record<string, unknown>>(`/api/media/suggest/${mood}`),
  },

  files: {
    list: (path?: string) =>
      request<{ path: string; entries: { name: string; is_dir: boolean; size: number; modified: string }[] }>(
        `/api/files${path ? `?path=${encodeURIComponent(path)}` : ''}`
      ),
    upload: (path: string, file: File) => {
      const formData = new FormData();
      formData.append('path', path);
      formData.append('file', file);
      return api.postForm<{ saved_to: string; size: number }>('/api/files/upload', formData);
    },
  },

  channels: {
    list: () => request<{ channels: { id: string; name: string; running: boolean }[] }>('/api/channels'),
    send: (channel: string, recipient: string, message: string) =>
      request<{ success: boolean }>('/api/channels/send', {
        method: 'POST', body: JSON.stringify({ channel, recipient, message }),
      }),
  },

  commitments: {
    list: (status?: string) =>
      request<{ commitments: { id: string; description: string; status?: string }[] }>(
        status ? `/api/commitments?status=${status}` : '/api/commitments'
      ),
    create: (data: { description: string; due?: string; priority?: string }) =>
      request<Record<string, unknown>>('/api/commitments', { method: 'POST', body: JSON.stringify(data) }),
    complete: (id: string) =>
      request<{ success: boolean }>(`/api/commitments/${id}/complete`, { method: 'POST' }),
    dismiss: (id: string) =>
      request<{ success: boolean }>(`/api/commitments/${id}/dismiss`, { method: 'POST' }),
  },

  code: {
    review: (code: string, language: string) =>
      request<{ review: string; language: string }>('/api/code/review', {
        method: 'POST', body: JSON.stringify({ code, language }),
      }),
  },

  vision: {
    screen: () => request<{ description: string; b64: string; width: number; height: number }>('/api/vision/screen', { method: 'POST' }),
    analyze: (question: string) =>
      request<{ question: string; answer: string; b64: string }>('/api/vision/analyze', { method: 'POST', body: JSON.stringify({ question }) }),
  },

  infrastructure: {
    sandbox: {
      status: () => request<{ available: boolean }>('/api/sandbox/status'),
      exec: (code: string, timeout?: number) =>
        request<Record<string, unknown>>('/api/sandbox/exec', { method: 'POST', body: JSON.stringify({ code, timeout }) }),
    },
    backup: {
      create: () => request<Record<string, unknown>>('/api/backup/create', { method: 'POST' }),
      list: () => request<{ backups: { path: string; created_at: string }[] }>('/api/backup/list'),
      restore: (path: string) =>
        request<Record<string, unknown>>('/api/backup/restore', { method: 'POST', body: JSON.stringify({ path }) }),
    },
    failover: () => request<{ enabled: boolean; profiles: { name: string; healthy: boolean }[] }>('/api/failover/status'),
    daemon: (action: 'start' | 'stop' | 'install' | 'uninstall' | 'status') =>
      request<{ status: string }>('/api/build/daemon', { method: 'POST', body: JSON.stringify({ action }) }),
  },

  build: {
    start: (goal: string, workspace?: string) =>
      request<{ name: string; status: string; goal: string }>('/api/build/start', {
        method: 'POST', body: JSON.stringify({ goal, workspace }),
      }),
    status: (projectName: string) =>
      request<BuildProject>(`/api/build/status/${projectName}`),
    projects: () => request<{ projects: string[] }>('/api/build/projects'),
    queue: () => request<{ projects: any[] }>('/api/build/queue'),
    interrupt: (projectName: string) =>
      request<{ status: string }>(`/api/build/interrupt/${encodeURIComponent(projectName)}`, { method: 'POST' }),
    resume: (projectName: string) =>
      request<{ status: string }>(`/api/build/resume/${encodeURIComponent(projectName)}`, { method: 'POST' }),
    cancel: (projectName: string) =>
      request<{ status: string }>(`/api/build/cancel/${encodeURIComponent(projectName)}`, { method: 'POST' }),
  },

  mcp: {
    tools: () => request<{ tools: McpTool[]; total: number }>('/mcp/tools'),
  },

  quality: {
    grade: (type: string, content: string) =>
      request<{ aggregate_score: number; passed: boolean; criteria: any[] }>('/api/quality/grade', {
        method: 'POST', body: JSON.stringify({ type, content }),
      }),
  },

  horizon: {
    create: (data: { goal: string; domain: string; horizon: string; deadline?: string }) =>
      request<HorizonGoal>('/api/horizon/goal', { method: 'POST', body: JSON.stringify(data) }),
    list: (domain?: string) =>
      request<{ goals: HorizonGoal[] }>(domain ? `/api/horizon/goals?domain=${domain}` : '/api/horizon/goals'),
    advance: (goalId: string) =>
      request<{ result: string; progress: number }>(`/api/horizon/goal/${goalId}/advance`, { method: 'POST' }),
    delete: (goalId: string) =>
      request<{ ok: boolean }>(`/api/horizon/goal/${goalId}`, { method: 'DELETE' }),
  },

  audio: {
    analyzeEmotion: (file: File) => {
      const formData = new FormData();
      formData.append('file', file);
      return api.postForm<any>('/api/audio/analyze-emotion', formData);
    },
  },

  scene: {
    generate: (description: string, outputFormat: string = 'auto') =>
      request<any>('/api/scene/generate', { method: 'POST', body: JSON.stringify({ description, output_format: outputFormat }) }),
  },

  prompt: {
    optimize: (agent?: string) =>
      request<any[]>(agent ? `/api/system/prompt-optimize?agent=${agent}` : '/api/system/prompt-optimize', { method: 'POST' }),
    versions: (agent?: string) =>
      request<any>(agent ? `/api/system/prompt-versions?agent=${agent}` : '/api/system/prompt-versions'),
    rollback: (agent: string) =>
      request<any>(`/api/system/prompt-rollback/${agent}`, { method: 'POST' }),
  },

  knowledge: {
    search: (q: string, limit?: number) =>
      request<{ query: string; results: Record<string, unknown>[] }>(
        `/api/memory/search?q=${encodeURIComponent(q)}${limit ? `&limit=${limit}` : ''}`
      ),
  },

  emails: {
    status: () => request<{ configured: boolean; host?: string; user?: string }>('/email/status'),
    inbox: (limit?: number) =>
      request<{ messages: unknown[]; count: number }>(`/email/inbox${limit ? `?limit=${limit}` : ''}`),
    draft: (message: Record<string, unknown>, instruction?: string) =>
      request<{ draft: string }>('/email/draft', { method: 'POST', body: JSON.stringify({ message, instruction }) }),
    send: (to: string, subject: string, body: string) =>
      request<{ sent: boolean }>('/email/send', { method: 'POST', body: JSON.stringify({ to, subject, body }) }),
  },
};
