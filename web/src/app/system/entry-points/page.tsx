'use client';

import { useEffect, useState, useCallback } from 'react';
import { api } from '@/lib/api';

/* ── Known Entry Points (system constants — hardcoded) ── */

const ENTRY_POINTS = [
  {
    source: 'CLI',
    command: 'jarvis chat',
    path: 'cli_commands.py → WebSocket → stream_agent_loop',
    pipeline: true,
    runtime: 'websocket',
    note: 'Interactive terminal session',
  },
  {
    source: 'CLI',
    command: 'jarvis code / build / run',
    path: 'cli_commands.py → AgentOrchestrator',
    pipeline: false,
    runtime: null,
    note: 'Direct call, bypasses pipeline',
  },
  {
    source: 'CLI',
    command: 'jarvis understand / workspace / doctor',
    path: 'cli_commands.py → direct call',
    pipeline: false,
    runtime: null,
    note: 'Direct local execution',
  },
  {
    source: 'Server',
    command: 'HTTP /api/* routes',
    path: 'core/main.py → ~40+ routers → direct handlers',
    pipeline: false,
    runtime: 'http',
    note: 'Each route handles independently',
  },
  {
    source: 'Server',
    command: 'WebSocket /ws/chat_stream',
    path: 'routes/websocket.py → stream_agent_loop → RuntimePipeline',
    pipeline: true,
    runtime: 'websocket',
    note: 'Only path entering RuntimePipeline',
  },
  {
    source: 'Server',
    command: 'WebSocket /ws/agent_stream',
    path: 'routes/websocket.py → graph execution',
    pipeline: false,
    runtime: 'websocket',
    note: 'Uses graph directly',
  },
  {
    source: 'Scheduler',
    command: 'Activity scheduler tick',
    path: 'scheduler/scheduler.py → executors → ResumeEngine',
    pipeline: false,
    runtime: 'background',
    note: 'Autonomous continuation',
  },
  {
    source: 'Scheduler',
    command: 'Cron jobs',
    path: 'cron/scheduler.py → direct handlers',
    pipeline: false,
    runtime: 'background',
    note: 'Scheduled tasks',
  },
  {
    source: 'Channels',
    command: 'Discord / Slack / Telegram / Matrix / IRC',
    path: 'lifespan.py → channel_controller → handlers',
    pipeline: false,
    runtime: 'background',
    note: 'External messaging',
  },
  {
    source: 'MCP',
    command: 'MCP server tools',
    path: 'mcp/mcp_server.py → tool dispatch',
    pipeline: false,
    runtime: 'http',
    note: 'Model Context Protocol',
  },
  {
    source: 'Voice',
    command: 'Wake word / voice pipeline',
    path: 'assistant/voice_pipeline.py → STT → TTS',
    pipeline: false,
    runtime: 'background',
    note: 'Speech-driven interaction',
  },
  {
    source: 'External',
    command: 'AgentStream / IDE integrations',
    path: 'External HTTP → core/main.py',
    pipeline: false,
    runtime: 'http',
    note: 'Third-party integrations',
  },
  {
    source: 'External',
    command: 'OpenCode Delegate',
    path: 'External → core/main.py',
    pipeline: false,
    runtime: 'http',
    note: 'AI coding tool delegate',
  },
];

/* ── Frontend Dashboard Routes ── */

const FRONTEND_ROUTES = [
  { path: '/', page: 'Home', file: 'web/src/app/page.tsx', status: 'active' },
  { path: '/welcome', page: 'Setup Wizard', file: 'web/src/app/welcome/page.tsx', status: 'active' },
  { path: '/chat', page: 'Chat', file: 'web/src/app/chat/page.tsx', status: 'active' },
  { path: '/tasks', page: 'Tasks', file: 'web/src/app/tasks/page.tsx', status: 'active' },
  { path: '/history', page: 'History', file: 'web/src/app/history/page.tsx', status: 'active' },
  { path: '/system', page: 'System', file: 'web/src/app/system/page.tsx', status: 'active' },
  { path: '/providers', page: 'Provider Manager', file: 'web/src/app/providers/page.tsx', status: 'active' },
  { path: '/settings', page: 'Settings', file: 'web/src/app/settings/page.tsx', status: 'active' },
  { path: '/operations', page: 'Operations Center', file: 'web/src/app/operations/page.tsx', status: 'active' },
  { path: '/diagnostics', page: 'Diagnostics', file: 'web/src/app/diagnostics/page.tsx', status: 'active' },
  { path: '/monitor', page: 'System Monitor', file: 'web/src/app/monitor/page.tsx', status: 'active' },
  { path: '/logs', page: 'Log Viewer', file: 'web/src/app/logs/page.tsx', status: 'active' },
  { path: '/backend', page: 'Backend Control', file: 'web/src/app/backend/page.tsx', status: 'active' },
];

const PIPELINE_DIAGRAM = [
  { label: 'User', indent: 0, arrow: false },
  { label: '▼', indent: 0, arrow: false },
  { label: 'Entry Points (13)', indent: 0, arrow: false },
  { label: '│', indent: 0, arrow: false },
  { label: '├─ CLI (jarvis chat) ──→ WebSocket', indent: 0, arrow: false },
  { label: '├─ CLI (code/build/run) ──→ AgentOrchestrator', indent: 0, arrow: false, dim: true },
  { label: '├─ HTTP API ──→ ~40 routers', indent: 0, arrow: false, dim: true },
  { label: '├─ WebSocket ──→ stream_agent_loop ★', indent: 0, arrow: false },
  { label: '├─ Scheduler ──→ executors', indent: 0, arrow: false, dim: true },
  { label: '├─ Channels ──→ handlers', indent: 0, arrow: false, dim: true },
  { label: '├─ MCP ──→ tool dispatch', indent: 0, arrow: false, dim: true },
  { label: '└─ Voice / IDE / External', indent: 0, arrow: false, dim: true },
  { label: '▼', indent: 0, arrow: false },
  { label: 'RuntimePipeline (1 path)', indent: 0, arrow: false },
  { label: '├─ Knowledge Injection', indent: 1, arrow: false },
  { label: '├─ Planning', indent: 1, arrow: false },
  { label: '├─ Strategy Selection', indent: 1, arrow: false },
  { label: '├─ Decision', indent: 1, arrow: false },
  { label: '├─ Provider Selection', indent: 1, arrow: false },
  { label: '├─ Activity Recording', indent: 1, arrow: false },
  { label: '├─ Graph Execution', indent: 1, arrow: false },
  { label: '└─ Learning Feedback', indent: 1, arrow: false },
];

/* ── Helpers ── */

function fmtTime(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/* ── Entry Points Page ── */

export default function EntryPointsPage() {
  const [health, setHealth] = useState<{ status: string; version?: string } | null>(null);
  const [sysStatus, setSysStatus] = useState<{ status: string; ollama: string; model: string; version: string } | null>(null);
  const [serverTime, setServerTime] = useState<string | null>(null);
  const [jobCount, setJobCount] = useState(0);
  const [schedulerState, setSchedulerState] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError('');

    const [h, ss, sched, cron] = await Promise.all([
      api.health().catch(() => null),
      api.system.status().catch(() => null),
      api.automation.jobs().catch(() => null),
      api.automation.cronJobs().catch(() => null),
    ]);

    if (!h && !ss) {
      setError('Could not reach the server. Check that JARVIS is running.');
    }

    if (h) setHealth(h);
    if (ss) {
      setSysStatus(ss);
      setServerTime(new Date().toISOString());
    }
    if (sched?.jobs) setJobCount(sched.jobs.length);
    if (cron?.jobs) setJobCount(prev => prev + cron.jobs.length);

    setLoading(false);
  }, []);

  useEffect(() => {
    fetchAll();
    const iv = setInterval(fetchAll, 30000);
    return () => clearInterval(iv);
  }, [fetchAll]);

  const healthy = health?.status === 'healthy' || health?.status === 'ok';
  const ollamaOk = sysStatus?.ollama === 'reachable';

  /* ── Pipeline coverage calc ── */
  const pipelinePaths = ENTRY_POINTS.filter(e => e.pipeline).length;
  const totalPaths = ENTRY_POINTS.length;

  return (
    <div className="mx-auto max-w-4xl space-y-10 pb-12">

      {/* ── Server Status ── */}
      <section>
        <div className="flex items-center gap-2 mb-4">
          <h2 className="text-xs tracking-[0.12em] uppercase m-0" style={{ color: 'var(--j-text-muted)' }}>Server</h2>
          <span className="h-px flex-1" style={{ background: 'var(--j-border)' }} />
        </div>

        <div
          className="flex items-center gap-4 px-5 py-4"
          style={{
            border: `1px solid ${healthy ? 'rgba(74,222,128,0.2)' : 'rgba(255,71,87,0.2)'}`,
            borderRadius: 'var(--j-radius-md)',
            background: healthy ? 'rgba(74,222,128,0.04)' : 'rgba(255,71,87,0.04)',
          }}
        >
          <div
            className="w-3 h-3 rounded-full shrink-0 animate-pulse"
            style={{
              background: healthy ? 'var(--j-green)' : '#ff4757',
              boxShadow: healthy ? '0 0 12px rgba(74,222,128,0.6)' : '0 0 12px rgba(255,71,87,0.6)',
            }}
          />
          <div>
            <div className="text-sm font-mono" style={{ color: 'var(--j-text)' }}>
              {healthy ? 'Server operational' : 'Server degraded'}
            </div>
            <div className="text-xs mt-0.5 font-mono" style={{ color: 'var(--j-text-muted)' }}>
              {sysStatus?.version || health?.version || '0.1.0'} · {sysStatus?.model || 'No model'}
              {serverTime && <> · Last check: {fmtTime(serverTime)}</>}
            </div>
          </div>
          <div className="ml-auto flex items-center gap-4">
            <div className="flex items-center gap-1.5 text-[10px] font-mono" style={{ color: 'var(--j-text-muted)' }}>
              <div className={`w-1.5 h-1.5 rounded-full ${ollamaOk ? 'bg-[var(--j-green)]' : 'bg-[var(--j-gold)]'}`} />
              Ollama {ollamaOk ? 'OK' : 'N/A'}
            </div>
            <div className="flex items-center gap-1.5 text-[10px] font-mono" style={{ color: 'var(--j-text-muted)' }}>
              <div className="w-1.5 h-1.5 rounded-full bg-[var(--j-sky)]" />
              {jobCount} jobs
            </div>
          </div>
        </div>
      </section>

      {error && (
        <div
          className="flex items-center justify-between gap-4 px-5 py-3"
          style={{
            border: '1px solid rgba(255,71,87,0.2)',
            borderRadius: 'var(--j-radius-md)',
            background: 'rgba(255,71,87,0.04)',
          }}
        >
          <p className="text-xs" style={{ color: '#ff4757' }}>{error}</p>
          <button
            onClick={fetchAll}
            className="text-[9px] font-mono uppercase tracking-[0.12em] px-2 py-1 transition-all hover:opacity-80 shrink-0"
            style={{
              border: '1px solid var(--j-border)',
              borderRadius: 'var(--j-radius-sm)',
              color: 'var(--j-text-dim)',
            }}
          >
            Retry
          </button>
        </div>
      )}

      {/* ── Pipeline Coverage ── */}
      <section>
        <div className="flex items-center gap-2 mb-4">
            <h2 className="text-xs tracking-[0.12em] uppercase m-0" style={{ color: 'var(--j-text-muted)' }}>Pipeline Coverage</h2>
          <span className="h-px flex-1" style={{ background: 'var(--j-border)' }} />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div
            className="px-4 py-3"
            style={{ border: '1px solid var(--j-border)', borderRadius: 'var(--j-radius-md)' }}
          >
            <div className="text-lg font-mono" style={{ color: 'var(--j-sky)' }}>{totalPaths}</div>
            <div className="text-[10px] font-mono uppercase tracking-[0.12em] mt-1" style={{ color: 'var(--j-text-muted)' }}>Entry paths</div>
          </div>
          <div
            className="px-4 py-3"
            style={{ border: '1px solid var(--j-border)', borderRadius: 'var(--j-radius-md)' }}
          >
            <div className="flex items-baseline gap-1">
              <span className="text-lg font-mono" style={{ color: pipelinePaths > 0 ? 'var(--j-green)' : '#ff4757' }}>{pipelinePaths}</span>
              <span className="text-xs font-mono" style={{ color: 'var(--j-text-muted)' }}>/ {totalPaths}</span>
            </div>
            <div className="text-[10px] font-mono uppercase tracking-[0.12em] mt-1" style={{ color: 'var(--j-text-muted)' }}>Reach RuntimePipeline</div>
          </div>
        </div>
      </section>

      {/* ── Entry Points Table ── */}
      <section>
        <div className="flex items-center gap-2 mb-4">
            <h2 className="text-xs tracking-[0.12em] uppercase m-0" style={{ color: 'var(--j-text-muted)' }}>Entry Points</h2>
          <span className="h-px flex-1" style={{ background: 'var(--j-border)' }} />
          <span className="text-[10px] font-mono" style={{ color: 'var(--j-text-muted)' }}>{totalPaths}</span>
        </div>

        <div
          className="overflow-hidden"
          style={{ border: '1px solid var(--j-border)', borderRadius: 'var(--j-radius-md)' }}
        >
          {/* Header */}
          <div
            className="grid grid-cols-[80px_1fr_1.5fr_60px_1fr] gap-2 px-4 py-2.5 text-[10px] font-mono uppercase tracking-[0.12em]"
            style={{ background: 'rgba(var(--j-bg-rgb), 0.5)', color: 'var(--j-text-muted)', borderBottom: '1px solid var(--j-border)' }}
          >
            <span>Source</span>
            <span>Command</span>
            <span>Path</span>
            <span className="text-center">Pipeline</span>
            <span>Note</span>
          </div>

          {ENTRY_POINTS.map((ep, i) => (
            <div
              key={i}
              className="grid grid-cols-[80px_1fr_1.5fr_60px_1fr] gap-2 px-4 py-2.5 items-center text-[11px]"
              style={{
                borderBottom: i < ENTRY_POINTS.length - 1 ? '1px solid var(--j-border)' : 'none',
                color: 'var(--j-text)',
                background: ep.pipeline ? 'rgba(74,222,128,0.03)' : 'transparent',
              }}
            >
              {/* Source badge */}
              <span
                className="text-[10px] font-mono px-2 py-0.5 justify-self-start"
                style={{
                  border: '1px solid var(--j-border)',
                  borderRadius: 'var(--j-radius-sm)',
                  color: 'var(--j-text-dim)',
                }}
              >
                {ep.source}
              </span>

              {/* Command */}
              <span className="font-mono truncate" style={{ color: ep.pipeline ? 'var(--j-sky)' : 'var(--j-text)' }}>
                {ep.command}
              </span>

              {/* Path */}
              <span
                className="font-mono truncate text-[10px]"
                style={{ color: ep.pipeline ? 'var(--j-green)' : 'var(--j-text-dim)' }}
              >
                {ep.path}
              </span>

              {/* Pipeline badge */}
              <div className="flex justify-center">
                {ep.pipeline ? (
                  <span
                    className="text-[9px] font-mono px-1.5 py-0.5"
                    style={{ border: '1px solid rgba(74,222,128,0.2)', borderRadius: 'var(--j-radius-sm)', color: 'var(--j-green)', background: 'rgba(74,222,128,0.06)' }}
                  >
                    YES
                  </span>
                ) : (
                  <span className="text-[9px] font-mono" style={{ color: 'var(--j-text-muted)' }}>—</span>
                )}
              </div>

              {/* Note */}
              <span className="text-[10px]" style={{ color: 'var(--j-text-dim)' }}>{ep.note}</span>
            </div>
          ))}
        </div>
      </section>

      {/* ── Pipeline Architecture ── */}
      <section>
        <div className="flex items-center gap-2 mb-4">
            <h2 className="text-xs tracking-[0.12em] uppercase m-0" style={{ color: 'var(--j-text-muted)' }}>Pipeline Architecture</h2>
          <span className="h-px flex-1" style={{ background: 'var(--j-border)' }} />
        </div>

        <div
          className="px-5 py-4 font-mono text-[11px] leading-relaxed"
          style={{
            border: '1px solid var(--j-border)',
            borderRadius: 'var(--j-radius-md)',
            background: 'rgba(var(--j-bg-rgb), 0.4)',
          }}
        >
          {PIPELINE_DIAGRAM.map((line, i) => (
            <div
              key={i}
              className={line.dim ? 'opacity-40' : ''}
              style={{
                paddingLeft: `${line.indent * 16}px`,
                color: line.label === 'RuntimePipeline (1 path)' ? 'var(--j-green)' : line.label.startsWith('├─') && line.label.includes('★') ? 'var(--j-sky)' : line.label === 'User' ? 'var(--j-text)' : 'var(--j-text-dim)',
              }}
            >
              {line.label}
            </div>
          ))}
        </div>

        <p className="text-[10px] font-mono mt-2" style={{ color: 'var(--j-text-muted)' }}>
          ★ = Only path that enters RuntimePipeline. All other paths bypass pipeline infrastructure.
        </p>
      </section>

      {/* ── Active Subsystems ── */}
      <section>
        <div className="flex items-center gap-2 mb-4">
            <h2 className="text-xs tracking-[0.12em] uppercase m-0" style={{ color: 'var(--j-text-muted)' }}>Active Subsystems</h2>
          <span className="h-px flex-1" style={{ background: 'var(--j-border)' }} />
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
          {[
            { label: 'Server', status: healthy ? 'Running' : 'Down', ok: healthy },
            { label: 'Ollama', status: ollamaOk ? 'Reachable' : 'N/A', ok: ollamaOk },
            { label: 'Database', status: healthy ? 'Connected' : 'Down', ok: healthy },
            { label: 'WebSocket', status: healthy ? 'Open' : 'Closed', ok: healthy },
            { label: 'Scheduler', status: jobCount > 0 ? `${jobCount} jobs` : 'Idle', ok: true },
            { label: 'Channels', status: 'Loaded', ok: true },
            { label: 'MCP Server', status: 'Registered', ok: true },
            { label: 'Voice Pipeline', status: 'Initialized', ok: true },
          ].map(item => (
            <div
              key={item.label}
              className="flex items-center gap-2 px-3 py-2.5"
              style={{ border: '1px solid var(--j-border)', borderRadius: 'var(--j-radius-sm)' }}
            >
              <div
                className="w-1.5 h-1.5 rounded-full shrink-0"
                style={{
                  background: item.ok ? 'var(--j-green)' : '#ff4757',
                  boxShadow: item.ok ? '0 0 6px rgba(74,222,128,0.5)' : 'none',
                }}
              />
              <div className="min-w-0">
                <div className="text-[11px] truncate" style={{ color: 'var(--j-text)' }}>{item.label}</div>
                <div className="text-[9px] font-mono mt-0.5" style={{ color: item.ok ? 'var(--j-green)' : '#ff4757' }}>{item.status}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Frontend Routes ── */}
      <section>
        <div className="flex items-center gap-2 mb-4">
            <h2 className="text-xs tracking-[0.12em] uppercase m-0" style={{ color: 'var(--j-text-muted)' }}>Frontend Routes</h2>
          <span className="h-px flex-1" style={{ background: 'var(--j-border)' }} />
          <span className="text-[10px] font-mono" style={{ color: 'var(--j-text-muted)' }}>{FRONTEND_ROUTES.length}</span>
        </div>

        <div
          className="overflow-hidden"
          style={{ border: '1px solid var(--j-border)', borderRadius: 'var(--j-radius-md)' }}
        >
          <div
            className="grid grid-cols-[80px_1fr_1.5fr_60px] gap-2 px-4 py-2.5 text-[10px] font-mono uppercase tracking-[0.12em]"
            style={{ background: 'rgba(var(--j-bg-rgb), 0.5)', color: 'var(--j-text-muted)', borderBottom: '1px solid var(--j-border)' }}
          >
            <span>Route</span>
            <span>Page</span>
            <span>File</span>
            <span className="text-center">Status</span>
          </div>

          {FRONTEND_ROUTES.map((fr, i) => (
            <div
              key={fr.path}
              className="grid grid-cols-[80px_1fr_1.5fr_60px] gap-2 px-4 py-2 items-center text-[11px]"
              style={{
                borderBottom: i < FRONTEND_ROUTES.length - 1 ? '1px solid var(--j-border)' : 'none',
                color: 'var(--j-text)',
              }}
            >
              <span className="font-mono text-[10px]" style={{ color: 'var(--j-sky)' }}>{fr.path}</span>
              <span className="truncate">{fr.page}</span>
              <span className="font-mono text-[10px] truncate" style={{ color: 'var(--j-text-dim)' }}>{fr.file}</span>
              <div className="flex justify-center">
                <span
                  className="text-[9px] font-mono px-1.5 py-0.5"
                  style={{ border: '1px solid rgba(74,222,128,0.2)', borderRadius: 'var(--j-radius-sm)', color: 'var(--j-green)', background: 'rgba(74,222,128,0.06)' }}
                >
                  {fr.status}
                </span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Loading ── */}
      {loading && !health && (
        <div className="text-center py-8">
          <p className="text-xs" style={{ color: 'var(--j-text-muted)' }}>Checking system status...</p>
        </div>
      )}
    </div>
  );
}
