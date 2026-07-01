'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { api, type BuildProject } from '@/lib/api';

/* ── Helpers ─────────────────────────────────────────── */

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

interface TaskItem {
  id: string;
  label: string;
  type: 'build' | 'commitment' | 'activity';
  status: 'running' | 'pending' | 'completed' | 'failed';
  ts: string;
  detail?: string;
}

/* ── Tasks Page ──────────────────────────────────────── */

const QUICK_TASKS = [
  { label: 'Build a web app', query: 'Build a portfolio website with HTML, CSS, and JS' },
  { label: 'Research + summarize', query: 'Research a topic and summarize findings' },
  { label: 'Analyze repository', query: 'Analyze this repository and suggest improvements' },
  { label: 'Deploy project', query: 'Deploy this project to GitHub Pages' },
];

export default function TasksPage() {
  const router = useRouter();
  const [input, setInput] = useState('');
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchTasks = useCallback(async () => {
    setLoading(true);
    const results: TaskItem[] = [];

    const [buildProjects, buildQueue, todayActivity, commitments] = await Promise.all([
      api.build.projects().catch(() => ({ projects: [] as string[] })),
      api.build.queue().catch(() => ({ projects: [] as any[] })),
      api.dashboard.activity.today().catch(() => [] as { type: string; description: string; ts: string }[]),
      api.commitments.list('pending').catch(() => ({ commitments: [] as { id: string; description: string; status?: string }[] })),
    ]);

    if (buildProjects?.projects) {
      for (const name of buildProjects.projects) {
        results.push({
          id: `build-${name}`,
          label: name,
          type: 'build',
          status: 'completed',
          ts: '',
        });
      }
    }

    if (buildQueue?.projects) {
      for (const p of buildQueue.projects) {
        results.push({
          id: `queue-${p.name || p.id}`,
          label: p.name || p.goal || 'Build task',
          type: 'build',
          status: 'running',
          ts: p.started_at || '',
          detail: p.status || 'running',
        });
      }
    }

    if (commitments?.commitments) {
      for (const c of commitments.commitments) {
        results.push({
          id: `commit-${c.id}`,
          label: c.description,
          type: 'commitment',
          status: (c.status as TaskItem['status']) || 'pending',
          ts: '',
        });
      }
    }

    if (Array.isArray(todayActivity)) {
      for (const a of todayActivity) {
        results.push({
          id: `act-${a.ts}-${Math.random().toString(36).slice(2, 6)}`,
          label: a.description,
          type: 'activity',
          status: 'completed',
          ts: a.ts,
          detail: a.type,
        });
      }
    }

    // deduplicate by label
    const seen = new Set<string>();
    const deduped = results.filter(t => {
      const key = t.label.toLowerCase().slice(0, 40);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });

    setTasks(deduped.sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime()));
    setLoading(false);
  }, []);

  useEffect(() => { fetchTasks(); }, [fetchTasks]);

  const handleSubmit = () => {
    const q = input.trim();
    if (!q) return;
    // route to home page with query
    router.push(`/?q=${encodeURIComponent(q)}`);
  };

  const handleQuick = (query: string) => {
    router.push(`/?q=${encodeURIComponent(query)}`);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleSubmit();
  };

  const running = tasks.filter(t => t.status === 'running');
  const pending = tasks.filter(t => t.status === 'pending');
  const completed = tasks.filter(t => t.status === 'completed' || t.status === 'failed');

  return (
    <div className="mx-auto max-w-3xl space-y-8 pb-12">

      {/* ── New task input ── */}
      <section>
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
            placeholder="What do you need done?"
            className="flex-1 bg-transparent text-sm outline-none"
            style={{ color: 'var(--j-text)', fontFamily: 'var(--j-font-sans)' }}
          />
          <button
            onClick={handleSubmit}
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
            Go
          </button>
        </div>

        <div className="flex flex-wrap gap-2 mt-3">
          {QUICK_TASKS.map(t => (
            <button
              key={t.label}
              onClick={() => handleQuick(t.query)}
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

      {/* ── Running ── */}
      {running.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-4">
            <h2 className="text-xs tracking-[0.12em] uppercase m-0" style={{ color: 'var(--j-text-muted)' }}>Running</h2>
            <span className="h-px flex-1" style={{ background: 'var(--j-border)' }} />
            <span className="text-[10px] font-mono" style={{ color: 'var(--j-text-muted)' }}>{running.length}</span>
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
                  {t.detail && <div className="text-xs mt-0.5" style={{ color: 'var(--j-text-muted)' }}>{t.detail}</div>}
                </div>
                {t.ts && <div className="text-xs shrink-0" style={{ color: 'var(--j-text-muted)' }}>{fmtTime(t.ts)}</div>}
                <Link
                  href={`/explain/${encodeURIComponent(t.id)}`}
                  className="text-[10px] font-mono uppercase tracking-[0.08em] shrink-0 px-2 py-0.5 transition-all duration-200 no-underline"
                  style={{
                    border: '1px solid var(--j-border)',
                    borderRadius: 'var(--j-radius-sm)',
                    color: 'var(--j-text-dim)',
                  }}
                >
                  Explain
                </Link>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Pending ── */}
      {pending.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-4">
            <h2 className="text-xs tracking-[0.12em] uppercase m-0" style={{ color: 'var(--j-text-muted)' }}>Pending</h2>
            <span className="h-px flex-1" style={{ background: 'var(--j-border)' }} />
            <span className="text-[10px] font-mono" style={{ color: 'var(--j-text-muted)' }}>{pending.length}</span>
          </div>
          <div className="space-y-2">
            {pending.map(t => (
              <div
                key={t.id}
                className="flex items-center gap-3 px-4 py-2.5"
                style={{
                  border: '1px solid var(--j-border)',
                  borderRadius: 'var(--j-radius-md)',
                }}
              >
                <div className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: 'var(--j-text-muted)' }} />
                <div className="flex-1 min-w-0">
                  <div className="text-sm truncate" style={{ color: 'var(--j-text)' }}>{t.label}</div>
                  {t.detail && <div className="text-xs mt-0.5" style={{ color: 'var(--j-text-muted)' }}>{t.detail}</div>}
                </div>
                <Link
                  href={`/explain/${encodeURIComponent(t.id)}`}
                  className="text-[10px] font-mono uppercase tracking-[0.08em] shrink-0 px-2 py-0.5 transition-all duration-200 no-underline"
                  style={{
                    border: '1px solid var(--j-border)',
                    borderRadius: 'var(--j-radius-sm)',
                    color: 'var(--j-text-dim)',
                  }}
                >
                  Explain
                </Link>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Recent ── */}
      <section>
        <div className="flex items-center gap-2 mb-4">
            <h2 className="text-xs tracking-[0.12em] uppercase m-0" style={{ color: 'var(--j-text-muted)' }}>Completed</h2>
          <span className="h-px flex-1" style={{ background: 'var(--j-border)' }} />
          <span className="text-[10px] font-mono" style={{ color: 'var(--j-text-muted)' }}>{completed.length}</span>
        </div>

        {loading ? (
          <div className="text-center py-8">
            <p className="text-xs" style={{ color: 'var(--j-text-muted)' }}>Loading tasks...</p>
          </div>
        ) : completed.length === 0 && running.length === 0 && pending.length === 0 ? (
          <div className="text-center py-12" style={{ border: '1px dashed var(--j-border)', borderRadius: 'var(--j-radius-md)' }}>
            <p className="text-sm font-mono mb-3" style={{ color: 'var(--j-text-dim)' }}>No tasks yet</p>
            <p className="text-xs mb-5" style={{ color: 'var(--j-text-muted)' }}>Tell JARVIS what to accomplish.</p>
            <a
              href="/"
              className="inline-block px-5 py-2.5 text-[10px] font-mono uppercase tracking-[0.12em] transition-all hover:opacity-80"
              style={{ border: '1px solid var(--j-sky)', borderRadius: 'var(--j-radius-sm)', color: 'var(--j-sky)' }}
            >
              Start a task
            </a>
          </div>
        ) : (
          <div className="space-y-2">
            {completed.slice(0, 20).map(t => (
              <div
                key={t.id}
                className="flex items-center gap-3 px-4 py-2.5"
                style={{
                  border: '1px solid var(--j-border)',
                  borderRadius: 'var(--j-radius-md)',
                }}
              >
                <div
                  className="w-1.5 h-1.5 rounded-full shrink-0"
                  style={{
                    background: t.status === 'failed' ? '#ff4757' : 'var(--j-green)',
                    boxShadow: t.status === 'failed' ? '0 0 6px rgba(255,71,87,0.4)' : '0 0 6px rgba(74,222,128,0.3)',
                  }}
                />
                <div className="flex-1 min-w-0">
                  <div className="text-sm truncate" style={{ color: 'var(--j-text)' }}>{t.label}</div>
                  {t.detail && <div className="text-xs mt-0.5" style={{ color: 'var(--j-text-muted)' }}>{t.detail}</div>}
                </div>
                {t.ts && <div className="text-xs shrink-0" style={{ color: 'var(--j-text-muted)' }}>{fmtTime(t.ts)}</div>}
                <Link
                  href={`/explain/${encodeURIComponent(t.id)}`}
                  className="text-[10px] font-mono uppercase tracking-[0.08em] shrink-0 px-2 py-0.5 transition-all duration-200 no-underline"
                  style={{
                    border: '1px solid var(--j-border)',
                    borderRadius: 'var(--j-radius-sm)',
                    color: 'var(--j-text-dim)',
                  }}
                >
                  Explain
                </Link>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
