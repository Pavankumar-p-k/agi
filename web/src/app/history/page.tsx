'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';

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

function fmtDate(ts: string): string {
  const d = new Date(ts);
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);

  if (d.toDateString() === today.toDateString()) return 'Today';
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday';
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function groupByDate<T extends { ts: string }>(items: T[]): Map<string, T[]> {
  const groups = new Map<string, T[]>();
  for (const item of items) {
    const date = item.ts ? fmtDate(item.ts) : 'Unknown';
    if (!groups.has(date)) groups.set(date, []);
    groups.get(date)!.push(item);
  }
  return groups;
}

const TYPE_ICON: Record<string, string> = {
  build: '⚒',
  research: '◎',
  chat: '✦',
  command: '⌁',
  email: '✉',
  browser: '◈',
  code: '⊚',
  file: '⊞',
  note: '✎',
  default: '●',
};

function iconForType(type: string): string {
  const lower = type.toLowerCase();
  for (const [key, icon] of Object.entries(TYPE_ICON)) {
    if (lower.includes(key)) return icon;
  }
  return TYPE_ICON.default;
}

/* ── History Page ────────────────────────────────────── */

interface HistoryEntry {
  id: string;
  type: string;
  description: string;
  ts: string;
}

export default function HistoryPage() {
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [highlights, setHighlights] = useState<{
    conversations?: number;
    commands_executed?: number;
    searches?: number;
  }>({});
  const [loading, setLoading] = useState(true);

  const fetchAll = useCallback(async () => {
    setLoading(true);

    const [activityData, highlightsData] = await Promise.all([
      api.dashboard.activity.today().catch(() => [] as { type: string; description: string; ts: string }[]),
      api.dashboard.highlights().catch(() => null as { conversations?: number; commands_executed?: number; searches?: number } | null),
    ]);

    const results: HistoryEntry[] = [];

    if (Array.isArray(activityData)) {
      for (const a of activityData) {
        results.push({
          id: `act-${a.ts}-${Math.random().toString(36).slice(2, 6)}`,
          type: a.type,
          description: a.description,
          ts: a.ts,
        });
      }
    }

    if (highlightsData) {
      setHighlights(highlightsData);
    }

    setEntries(results.sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime()));
    setLoading(false);
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const groups = groupByDate(entries);

  return (
    <div className="mx-auto max-w-3xl space-y-8 pb-12">

      {/* ── Monthly highlights ── */}
      {Object.keys(highlights).length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-4">
            <h2 className="text-xs tracking-[0.12em] uppercase m-0" style={{ color: 'var(--j-text-muted)' }}>Highlights</h2>
            <span className="h-px flex-1" style={{ background: 'var(--j-border)' }} />
          </div>
          <div className="grid grid-cols-3 gap-3">
            {highlights.conversations !== undefined && (
              <div
                className="px-4 py-3 text-center"
                style={{ border: '1px solid var(--j-border)', borderRadius: 'var(--j-radius-md)' }}
              >
                <div className="text-lg font-mono" style={{ color: 'var(--j-sky)' }}>{highlights.conversations}</div>
                <div className="text-[10px] font-mono uppercase tracking-[0.12em] mt-1" style={{ color: 'var(--j-text-muted)' }}>Conversations</div>
              </div>
            )}
            {highlights.commands_executed !== undefined && (
              <div
                className="px-4 py-3 text-center"
                style={{ border: '1px solid var(--j-border)', borderRadius: 'var(--j-radius-md)' }}
              >
                <div className="text-lg font-mono" style={{ color: 'var(--j-green)' }}>{highlights.commands_executed}</div>
                <div className="text-[10px] font-mono uppercase tracking-[0.12em] mt-1" style={{ color: 'var(--j-text-muted)' }}>Commands</div>
              </div>
            )}
            {highlights.searches !== undefined && (
              <div
                className="px-4 py-3 text-center"
                style={{ border: '1px solid var(--j-border)', borderRadius: 'var(--j-radius-md)' }}
              >
                <div className="text-lg font-mono" style={{ color: 'var(--j-gold)' }}>{highlights.searches}</div>
                <div className="text-[10px] font-mono uppercase tracking-[0.12em] mt-1" style={{ color: 'var(--j-text-muted)' }}>Searches</div>
              </div>
            )}
          </div>
        </section>
      )}

      {/* ── Timeline ── */}
      <section>
        <div className="flex items-center gap-2 mb-4">
            <h2 className="text-xs tracking-[0.12em] uppercase m-0" style={{ color: 'var(--j-text-muted)' }}>Timeline</h2>
          <span className="h-px flex-1" style={{ background: 'var(--j-border)' }} />
          <span className="text-[10px] font-mono" style={{ color: 'var(--j-text-muted)' }}>{entries.length}</span>
        </div>

        {loading ? (
          <div className="text-center py-8">
            <p className="text-xs" style={{ color: 'var(--j-text-muted)' }}>Loading timeline...</p>
          </div>
        ) : entries.length === 0 ? (
          <div className="text-center py-12" style={{ border: '1px dashed var(--j-border)', borderRadius: 'var(--j-radius-md)' }}>
            <p className="text-sm font-mono mb-3" style={{ color: 'var(--j-text-dim)' }}>No history yet</p>
            <p className="text-xs mb-5" style={{ color: 'var(--j-text-muted)' }}>Your conversations, commands, and searches will appear here.</p>
            <a
              href="/chat"
              className="inline-block px-5 py-2.5 text-[10px] font-mono uppercase tracking-[0.12em] transition-all hover:opacity-80"
              style={{ border: '1px solid var(--j-sky)', borderRadius: 'var(--j-radius-sm)', color: 'var(--j-sky)' }}
            >
              Start a conversation
            </a>
          </div>
        ) : (
          <div className="space-y-6">
            {Array.from(groups.entries()).map(([date, items]) => (
              <div key={date}>
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-xs font-mono uppercase tracking-[0.12em]" style={{ color: 'var(--j-text-dim)' }}>{date}</span>
                  <span className="h-px flex-1" style={{ background: 'var(--j-border)' }} />
                  <span className="text-[10px] font-mono" style={{ color: 'var(--j-text-muted)' }}>{items.length}</span>
                </div>
                <div className="space-y-2">
                  {items.map(item => (
                    <div
                      key={item.id}
                      className="flex items-start gap-3 px-4 py-2.5"
                      style={{
                        border: '1px solid var(--j-border)',
                        borderRadius: 'var(--j-radius-md)',
                      }}
                    >
                      <div className="text-sm w-5 text-center shrink-0 mt-0.5" style={{ color: 'var(--j-sky)' }}>
                        {iconForType(item.type)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm truncate" style={{ color: 'var(--j-text)' }}>{item.description}</div>
                        <div className="text-[10px] mt-0.5 font-mono uppercase tracking-[0.12em]" style={{ color: 'var(--j-text-muted)' }}>
                          {item.type}
                        </div>
                      </div>
                      <div className="text-xs shrink-0 mt-0.5" style={{ color: 'var(--j-text-muted)' }}>{fmtTime(item.ts)}</div>
                      <Link
                        href={`/explain/${encodeURIComponent(item.id)}`}
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
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
