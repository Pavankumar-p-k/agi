'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import Button from '@/components/ui/Button';

interface LogEntry {
  id: number;
  message: string;
  severity: string;
  timestamp: number;
}

const SEVERITY_COLORS: Record<string, string> = {
  ERROR: '#ff4757',
  WARNING: 'var(--j-gold)',
  INFO: 'var(--j-sky)',
  DEBUG: '#7f8c8d',
  CRITICAL: '#ff6b81',
};

const WS_BASE = process.env.NEXT_PUBLIC_WS_URL || 'ws://127.0.0.1:8000';

function tryParseJson(line: string): Record<string, unknown> | null {
  try {
    const j = JSON.parse(line);
    if (typeof j === 'object' && j) return j;
  } catch {
    return null;
  }
  return null;
}

export default function LogsPage() {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const [filter, setFilter] = useState('');
  const [severityFilter, setSeverityFilter] = useState<string>('ALL');
  const [autoScroll, setAutoScroll] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);
  const idRef = useRef(0);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    function scheduleReconnect() {
      if (reconnectTimer) return;
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        connect();
      }, 3000);
    }

    function connect() {
      try {
        ws = new WebSocket(`${WS_BASE}/ws/logs`);
      } catch {
        scheduleReconnect();
        return;
      }
      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        ws = null;
        scheduleReconnect();
      };
      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          if (data.type === 'log_entry') {
            setEntries(prev => {
              const next = [...prev, {
                id: ++idRef.current,
                message: data.message as string,
                severity: (data.severity as string) || 'INFO',
                timestamp: (data.timestamp as number) || Date.now(),
              }];
              return next.length > 2000 ? next.slice(next.length - 2000) : next;
            });
          }
        } catch {
          setEntries(prev => prev);
        }
      };
      ws.onerror = () => ws?.close();
    }

    connect();
    return () => {
      if (reconnectTimer) clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, []);

  useEffect(() => {
    if (autoScroll) bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [entries, autoScroll]);

  const handleScroll = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 50;
    if (!atBottom && autoScroll) setAutoScroll(false);
    if (atBottom && !autoScroll) setAutoScroll(true);
  }, [autoScroll]);

  const filtered = entries.filter(e => {
    if (severityFilter !== 'ALL' && e.severity !== severityFilter) return false;
    if (filter && !e.message.toLowerCase().includes(filter.toLowerCase())) return false;
    return true;
  });

  const severityCounts = entries.reduce<Record<string, number>>((acc, e) => {
    acc[e.severity] = (acc[e.severity] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="hud-page flex h-full flex-col overflow-hidden">
      <section className="hud-panel hud-scan-box mb-4 shrink-0 p-5">
        <div className="relative z-[1] flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <div className="hud-label">Telemetry Stream</div>
            <h1 className="hud-title mt-2 text-5xl md:text-6xl">Log <span className="text-[var(--j-sky)]">Viewer</span></h1>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter stream..."
              className="hud-input h-10 w-48 px-3 font-mono text-xs"
            />
            <Button variant="ghost" size="sm" onClick={() => setEntries([])}>Clear</Button>
            <div className="flex items-center gap-2 border border-[var(--j-border)] bg-[var(--j-bg)] px-3 py-2 font-mono text-[10px] uppercase tracking-[0.14em] text-[var(--j-text-dim)]">
              <span className={`h-1.5 w-1.5 rounded-full ${connected ? 'bg-[#00ff88]' : 'bg-[#ff4757]'}`} />
              {connected ? `${entries.length} entries` : 'offline'}
            </div>
          </div>
        </div>
      </section>

      <div className="mb-3 flex shrink-0 flex-wrap gap-2">
        {['ALL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'].map(s => {
          const count = s === 'ALL' ? entries.length : (severityCounts[s] || 0);
          const active = severityFilter === s;
          return (
            <button
              key={s}
              onClick={() => setSeverityFilter(s)}
              className="clip-hud border px-3 py-2 font-mono text-[10px] uppercase tracking-[0.14em] transition-all"
              style={{
                background: active ? 'rgba(var(--j-sky-rgb),0.1)' : 'var(--j-bg)',
                borderColor: active ? (SEVERITY_COLORS[s] || 'var(--j-sky)') : 'var(--j-border)',
                color: active ? (SEVERITY_COLORS[s] || 'var(--j-sky)') : 'var(--j-text-dim)',
              }}
            >
              {s} {count}
            </button>
          );
        })}
      </div>

      <section className="min-h-0 flex-1 overflow-hidden border border-[var(--j-border)] bg-[#020a0f]">
        <div ref={containerRef} onScroll={handleScroll} className="h-full overflow-y-auto p-3 font-mono text-[11px] leading-6">
          {filtered.length === 0 && (
            <div className="flex h-full items-center justify-center text-center text-[var(--j-text-dim)]">
              <div>
                <div className="mx-auto mb-4 h-16 w-16 hud-scan-box" />
                <p>{connected ? 'No matching log entries' : 'Connecting to log stream...'}</p>
                <p className="mt-1 text-[10px] uppercase tracking-[0.14em] text-[var(--j-text-muted)]">WebSocket feed</p>
              </div>
            </div>
          )}
          {filtered.map(e => {
            const color = SEVERITY_COLORS[e.severity] || 'var(--j-text-dim)';
            const parsed = tryParseJson(e.message);
            const display = parsed
              ? `[${String(parsed.level || e.severity).padEnd(7)}] ${parsed.message || ''}`
              : e.message;
            return (
              <div key={e.id} className="grid grid-cols-[72px_78px_1fr] gap-3 border-b border-[rgba(var(--j-sky-rgb),0.04)] px-2 py-1 hover:bg-[rgba(var(--j-sky-rgb),0.04)]">
                <span className="text-[var(--j-text-muted)]">{new Date(e.timestamp).toLocaleTimeString()}</span>
                <span style={{ color }}>{e.severity}</span>
                <span className="truncate text-[var(--j-text)]">{display}</span>
              </div>
            );
          })}
          <div ref={bottomRef} />
        </div>
      </section>

      {!autoScroll && (
        <button
          onClick={() => { setAutoScroll(true); bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }}
          className="absolute bottom-12 right-8 clip-hud border border-[var(--j-border-bright)] bg-[var(--j-surface)] px-3 py-2 font-mono text-[10px] uppercase tracking-[0.14em] text-[var(--j-sky)]"
        >
          Follow Stream
        </button>
      )}
    </div>
  );
}
