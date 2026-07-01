'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { api, type SystemStats, type HealthStatus, type SetupStatus } from '@/lib/api';

/* ── Helpers ─────────────────────────────────────────── */

function fmtBytes(v: number): string {
  const u = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(1)} ${u[i]}`;
}

function fmtTime(ts: string): string {
  const d = new Date(ts);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  if (diff < 60000) return 'Just now';
  if (diff < 3600000) return `${Math.floor(diff / 60000)} min ago`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
  return d.toLocaleDateString();
}

/* ── Types ───────────────────────────────────────────── */

interface ActivityItem {
  type: string;
  description: string;
  ts: string;
}

/* ── Home Page ───────────────────────────────────────── */

const QUICK_TASKS = [
  { label: 'Build a portfolio', query: 'Build a portfolio website with HTML, CSS, and JS' },
  { label: 'Research a topic', query: 'Research a topic and summarize findings' },
  { label: 'Analyze a repository', query: 'Analyze this repository and suggest improvements' },
  { label: 'Deploy to GitHub Pages', query: 'Deploy this project to GitHub Pages' },
];

const READY_NOW: { id: string; label: string; check?: string }[] = [
  { id: 'chat', label: 'Chat', check: undefined },
  { id: 'coding', label: 'Coding', check: undefined },
  { id: 'research', label: 'Research', check: 'models' },
  { id: 'build', label: 'Build', check: undefined },
];

const NEEDS_SETUP: { id: string; label: string; check: string }[] = [
  { id: 'browser', label: 'Browser', check: 'playwright' },
  { id: 'email', label: 'Email', check: 'api_keys' },
  { id: 'voice', label: 'Voice', check: 'api_keys' },
];

export default function HomePage() {
  const router = useRouter();
  const [input, setInput] = useState('');
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [running, setRunning] = useState<{ id: string; label: string; status: string; ts: string }[]>([]);
  const [setup, setSetup] = useState<SetupStatus | null>(null);

  /* ── Redirect if setup incomplete ── */
  useEffect(() => {
    api.setup.status().then(s => {
      setSetup(s);
      if (s.phase !== 'complete') router.replace('/welcome');
    }).catch(() => {});
  }, [router]);

  /* ── Fetch all data ── */
  const fetchAll = useCallback(async () => {
    const [statsResult, healthResult, actResult, queueResult] = await Promise.all([
      api.system.stats().catch(() => null),
      api.health().catch(() => null),
      api.dashboard.activity.today().catch(() => [] as ActivityItem[]),
      api.build.queue().catch(() => ({ projects: [] })),
    ]);
    if (statsResult) setStats(statsResult);
    if (healthResult) setHealth(healthResult);
    if (Array.isArray(actResult)) setActivity(actResult);
    if (queueResult?.projects) {
      setRunning(queueResult.projects.slice(0, 5).map((n: any) => ({
        id: n.name || n.id || `task-${Math.random().toString(36).slice(2, 6)}`,
        label: n.name || n.goal || 'Task',
        status: n.status || 'running',
        ts: n.started_at || '',
      })));
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const iv = setInterval(fetchAll, 15000);
    return () => clearInterval(iv);
  }, [fetchAll]);

  const handleSubmit = (query?: string) => {
    const q = encodeURIComponent(query || input);
    if (q) router.push(`/chat?q=${q}`);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleSubmit();
  };

  const healthy = health?.status === 'healthy' || health?.status === 'ok';
  const memUsed = stats ? stats.memory.total - stats.memory.available : 0;
  const hasRecentActivity = activity.length > 0;
  const hasRunningTasks = running.length > 0;

  return (
    <div className="mx-auto max-w-3xl space-y-10 pb-12">

      {/* ── Hero: command input ── */}
      <section>
        <div className="text-center mb-6">
          <h1 className="text-lg font-light tracking-[0.12em] uppercase" style={{ color: 'var(--j-text-dim)' }}>
            What would you like JARVIS to do?
          </h1>
        </div>

        <div
          className="flex items-center gap-3 px-5 py-3 transition-all duration-200 focus-within:shadow-[0_0_24px_rgba(0,210,255,0.08)]"
          style={{
            border: '1px solid var(--j-border)',
            borderRadius: 'var(--j-radius-md)',
            background: 'rgba(var(--j-bg-rgb),0.6)',
          }}
        >
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything..."
            className="flex-1 bg-transparent text-sm outline-none"
            style={{ color: 'var(--j-text)', fontFamily: 'var(--j-font-sans)' }}
          />
          <button
            onClick={() => handleSubmit()}
            disabled={!input.trim()}
            className="text-xs tracking-[0.12em] uppercase px-4 py-1.5 transition-all duration-200 disabled:opacity-30"
            style={{
              background: 'var(--j-sky)',
              color: '#020406',
              border: 'none',
              borderRadius: 'var(--j-radius-sm)',
              fontFamily: 'var(--j-font-mono)',
            }}
          >
            Ask
          </button>
        </div>

        {/* Quick task chips */}
        <div className="flex flex-wrap gap-2 mt-4">
          {QUICK_TASKS.map(t => (
            <button
              key={t.label}
              onClick={() => handleSubmit(t.query)}
              className="text-xs px-3 py-1.5 transition-all duration-200 cursor-pointer"
              style={{
                border: '1px solid var(--j-border)',
                borderRadius: 'var(--j-radius-sm)',
                color: 'var(--j-text-dim)',
                background: 'rgba(255,255,255,0.02)',
                fontFamily: 'var(--j-font-mono)',
              }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--j-sky)'; e.currentTarget.style.color = 'var(--j-sky)'; }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--j-border)'; e.currentTarget.style.color = 'var(--j-text-dim)'; }}
            >
              {t.label}
            </button>
          ))}
        </div>
      </section>

      {/* ── System Readiness ── */}
      <section>
        <div className="flex items-center gap-2 mb-4">
          <h2 className="text-xs tracking-[0.12em] uppercase" style={{ color: 'var(--j-text-muted)' }}>System</h2>
          <span className="h-px flex-1" style={{ background: 'var(--j-border)' }} />
        </div>

        <div
          className="grid grid-cols-2 md:grid-cols-4 gap-px"
          style={{ border: '1px solid var(--j-border)', borderRadius: 'var(--j-radius-md)', overflow: 'hidden' }}
        >
          {([
            { label: 'Server', value: healthy ? 'Healthy' : 'Offline', ok: healthy },
            { label: 'CPU', value: stats ? `${stats.cpu.percent.toFixed(0)}%` : '--' },
            { label: 'Memory', value: stats ? fmtBytes(memUsed) : '--' },
            { label: 'Running Tasks', value: `${running.length}` },
          ] as const).map(item => (
            <div
              key={item.label}
              className="px-4 py-3 text-center"
              style={{ background: 'rgba(var(--j-bg-rgb),0.4)' }}
            >
              <div className="text-xs font-mono" style={{ color: 'var(--j-text-muted)' }}>{item.label}</div>
              <div
                className="text-sm font-mono mt-1"
                style={{ color: 'ok' in item && item.ok !== undefined ? (item.ok ? 'var(--j-green)' : '#ff4757') : 'var(--j-text)' }}
              >
                {item.value}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Ready Now + Capabilities ── */}
      <section>
        <div className="flex items-center gap-2 mb-4">
          <h2 className="text-xs tracking-[0.12em] uppercase" style={{ color: 'var(--j-text-muted)' }}>Ready Now</h2>
          <span className="h-px flex-1" style={{ background: 'var(--j-border)' }} />
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {READY_NOW.map(c => (
            <div
              key={c.id}
              className="flex items-center gap-2 px-3 py-2"
              style={{
                border: '1px solid rgba(74,222,128,0.15)',
                borderRadius: 'var(--j-radius-sm)',
                background: 'rgba(74,222,128,0.04)',
              }}
            >
              <div
                className="w-1.5 h-1.5 rounded-full shrink-0"
                style={{ background: 'var(--j-green)', boxShadow: '0 0 6px rgba(74,222,128,0.5)' }}
              />
              <span className="text-xs" style={{ color: 'var(--j-text)' }}>{c.label}</span>
            </div>
          ))}
          {NEEDS_SETUP.filter(c => !setup || setup.checks[c.check] !== 'ok').map(c => (
            <div
              key={c.id}
              className="flex items-center gap-2 px-3 py-2"
              style={{
                border: '1px solid var(--j-border)',
                borderRadius: 'var(--j-radius-sm)',
              }}
            >
              <div className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: 'var(--j-text-muted)' }} />
              <span className="text-xs flex-1" style={{ color: 'var(--j-text-dim)' }}>{c.label}</span>
              {c.id === 'browser' && (
                <button
                  onClick={async (e) => {
                    e.stopPropagation();
                    try {
                      await api.setup.install('playwright');
                      const updated = await api.setup.status();
                      setSetup(updated);
                    } catch { /* non-blocking */ }
                  }}
                  className="text-[8px] font-mono uppercase tracking-[0.12em] px-2 py-0.5 transition-all"
                  style={{
                    border: '1px solid var(--j-sky)',
                    borderRadius: 'var(--j-radius-sm)',
                    color: 'var(--j-sky)',
                  }}
                >
                  Install
                </button>
              )}
              {c.id !== 'browser' && (
                <a
                  href="/settings/keys"
                  className="text-[8px] font-mono uppercase tracking-[0.12em] no-underline"
                  style={{ color: 'var(--j-text-muted)' }}
                >
                  Configure
                </a>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* ── Running Tasks ── */}
      {hasRunningTasks && (
        <section>
          <div className="flex items-center gap-2 mb-4">
            <h2 className="text-xs tracking-[0.12em] uppercase m-0" style={{ color: 'var(--j-text-muted)' }}>Running</h2>
            <span className="h-px flex-1" style={{ background: 'var(--j-border)' }} />
          </div>

          <div className="space-y-2">
            {running.map(t => (
              <div
                key={t.id}
                className="flex items-center gap-3 px-4 py-2.5"
                style={{
                  border: '1px solid var(--j-border)',
                  borderRadius: 'var(--j-radius-md)',
                }}
              >
                <div
                  className="w-1.5 h-1.5 rounded-full shrink-0 animate-pulse"
                  style={{ background: 'var(--j-gold)', boxShadow: '0 0 8px rgba(245,200,66,0.4)' }}
                />
                <div className="flex-1 min-w-0">
                  <div className="text-sm truncate" style={{ color: 'var(--j-text)' }}>{t.label}</div>
                  <div className="text-xs mt-0.5" style={{ color: 'var(--j-text-muted)' }}>{t.status}</div>
                </div>
                {t.ts && (
                  <div className="text-xs shrink-0" style={{ color: 'var(--j-text-muted)' }}>{fmtTime(t.ts)}</div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Recent Work ── */}
      <section>
        <div className="flex items-center gap-2 mb-4">
          <h2 className="text-xs tracking-[0.12em] uppercase m-0" style={{ color: 'var(--j-text-muted)' }}>Recent Work</h2>
          <span className="h-px flex-1" style={{ background: 'var(--j-border)' }} />
        </div>

        {hasRecentActivity ? (
          <div className="space-y-2">
            {activity.slice(0, 8).map((a, i) => (
              <div
                key={i}
                className="flex items-center gap-3 px-4 py-2.5"
                style={{
                  border: '1px solid var(--j-border)',
                  borderRadius: 'var(--j-radius-md)',
                }}
              >
                <div
                  className="w-1.5 h-1.5 rounded-full shrink-0"
                  style={{ background: 'var(--j-sky)', boxShadow: '0 0 6px rgba(0,210,255,0.3)' }}
                />
                <div className="flex-1 min-w-0">
                  <div className="text-sm truncate" style={{ color: 'var(--j-text)' }}>{a.description}</div>
                  <div className="text-xs mt-0.5" style={{ color: 'var(--j-text-muted)' }}>{a.type}</div>
                </div>
                <div className="text-xs shrink-0" style={{ color: 'var(--j-text-muted)' }}>{fmtTime(a.ts)}</div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-8">
            <p className="text-xs" style={{ color: 'var(--j-text-muted)' }}>
              No activity yet. Ask JARVIS to do something.
            </p>
          </div>
        )}
      </section>

    </div>
  );
}
