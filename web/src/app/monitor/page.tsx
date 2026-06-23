'use client';

import { useEffect, useState, useRef, useCallback } from 'react';
import type { ReactNode } from 'react';
import { MonitorSkeleton } from '@/components/ui/Skeleton';
import { api, type SystemStats, type HealthStatus } from '@/lib/api';

interface DataPoint {
  time: string;
  cpu: number;
  mem: number;
  netIn: number;
  netOut: number;
}

function fmtBytes(v: number): string {
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(1)} ${units[i]}`;
}

function fmtNet(v: number): string {
  if (v < 1024) return `${v.toFixed(0)} B/s`;
  if (v < 1048576) return `${(v / 1024).toFixed(0)} KB/s`;
  return `${(v / 1048576).toFixed(1)} MB/s`;
}

function Gauge({ label, value, color, unit = '%' }: { label: string; value: number; color: string; unit?: string }) {
  const r = 54;
  const circ = 2 * Math.PI * r;
  const offset = circ - (value / 100) * circ;
  return (
    <div className="flex flex-col items-center gap-1">
      <svg width="130" height="130" viewBox="0 0 130 130">
        <circle cx="65" cy="65" r={r} fill="none" stroke="var(--j-border)" strokeWidth="8" />
        <circle cx="65" cy="65" r="42" fill="none" stroke="rgba(var(--j-sky-rgb),0.08)" strokeWidth="1" />
        <circle cx="65" cy="65" r={r} fill="none" stroke={color} strokeWidth="8"
          strokeDasharray={circ} strokeDashoffset={offset}
          strokeLinecap="round" transform="rotate(-90 65 65)"
          style={{ transition: 'stroke-dashoffset 0.6s ease', filter: 'drop-shadow(0 0 8px currentColor)' }}
        />
        <text x="65" y="62" textAnchor="middle" fill="var(--j-text)" fontSize="24" fontFamily="var(--j-font-display)" letterSpacing="2">{value.toFixed(0)}<tspan fontSize="12" fill="var(--j-text-dim)">{unit}</tspan></text>
        <text x="65" y="82" textAnchor="middle" fill="var(--j-text-dim)" fontSize="9" fontFamily="var(--j-font-mono)" letterSpacing="1.4">{label.toUpperCase()}</text>
      </svg>
    </div>
  );
}

function MiniChart({ data, color, label }: { data: { time: string; value: number }[]; color: string; label: string }) {
  if (data.length < 2) return null;
  const w = 200, h = 60;
  const max = Math.max(...data.map(d => d.value), 1);
  const min = Math.min(...data.map(d => d.value), 0);
  const range = max - min || 1;
  const pts = data.map((d, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((d.value - min) / range) * (h - 4) - 2;
    return `${x},${y}`;
  }).join(' ');
  return (
    <svg width={w} height={h} className="shrink-0">
      <defs>
        <linearGradient id={`fill-${label}`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.28" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function StatCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="hud-panel hud-panel-line p-4">
      <div className="relative z-[1]">
        <div className="hud-label mb-3">{title}</div>
        {children}
      </div>
    </div>
  );
}

const MAX_HISTORY = 60;

export default function MonitorPage() {
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [history, setHistory] = useState<DataPoint[]>([]);
  const [serverInfo, setServerInfo] = useState<{ status: string; version?: string; uptime?: string } | null>(null);
  const prevNet = useRef({ in: 0, out: 0, time: 0 });
  const intRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchStats = useCallback(async () => {
    try {
      const data = await api.system.stats();
      setStats(data);

      const now = Date.now();
      const dt = prevNet.current.time ? (now - prevNet.current.time) / 1000 : 1;
      const netIn = prevNet.current.time ? Math.max(0, (data.network.bytes_recv - prevNet.current.in) / dt) : 0;
      const netOut = prevNet.current.time ? Math.max(0, (data.network.bytes_sent - prevNet.current.out) / dt) : 0;
      prevNet.current = { in: data.network.bytes_recv, out: data.network.bytes_sent, time: now };

      setHistory(prev => {
        const pt: DataPoint = {
          time: new Date().toLocaleTimeString(),
          cpu: data.cpu.percent,
          mem: data.memory.percent,
          netIn, netOut,
        };
        const next = [...prev, pt];
        return next.length > MAX_HISTORY ? next.slice(next.length - MAX_HISTORY) : next;
      });
    } catch (e) { console.warn('[Monitor] stats fetch failed', e); }
  }, []);

  const fetchServer = useCallback(async () => {
    try {
      const info = await api.health();
      setServerInfo(info);
    } catch (e) { console.warn('[Monitor] health fetch failed', e); }
  }, []);

  useEffect(() => {
    fetchStats();
    fetchServer();
    intRef.current = setInterval(fetchStats, 1500);
    return () => { if (intRef.current) clearInterval(intRef.current); };
  }, [fetchStats, fetchServer]);

  if (!stats) return (
    <div className="p-5">
      <MonitorSkeleton />
    </div>
  );

  const cpu = stats.cpu;
  const mem = stats.memory;
  const disk = stats.disk;
  const net = prevNet.current;

  return (
    <div className="hud-page h-full overflow-y-auto space-y-6">
      <div className="hud-panel hud-scan-box p-6 md:p-8">
        <div className="relative z-[1] flex items-end justify-between gap-4">
          <div>
            <div className="hud-label">Realtime Telemetry</div>
            <h1 className="hud-title mt-2 text-6xl md:text-7xl">System <span className="text-[var(--j-sky)]">Monitor</span></h1>
          </div>
          <div className="flex items-center gap-2 border border-[var(--j-border)] bg-[var(--j-bg)] px-3 py-2 font-mono text-[10px] uppercase tracking-[0.14em]" style={{ color: 'var(--j-text-dim)' }}>
            <span className={`inline-block h-1.5 w-1.5 rounded-full ${stats ? 'bg-[#00ff88]' : 'bg-red-400'}`} />
            {stats ? 'Live' : 'Disconnected'}
          </div>
        </div>
      </div>

      {/* Gauges */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard title="CPU">
          <div className="flex flex-col items-center">
            <Gauge label={`${cpu?.count ?? 0} cores`} value={cpu?.percent ?? 0} color="var(--j-sky)" />
            <div className="mt-2 text-[10px]" style={{ color: 'var(--j-text-dim)' }}>
              {cpu ? `${cpu.percent.toFixed(1)}% used` : '—'}
            </div>
          </div>
        </StatCard>
        <StatCard title="Memory">
          <div className="flex flex-col items-center">
            <Gauge label={mem ? `${fmtBytes(mem.available)} free` : ''} value={mem?.percent ?? 0} color="var(--j-green, #4ade80)" />
            <div className="mt-2 text-[10px]" style={{ color: 'var(--j-text-dim)' }}>
              {mem ? `${fmtBytes(mem.total - mem.available)} / ${fmtBytes(mem.total)}` : '—'}
            </div>
          </div>
        </StatCard>
        <StatCard title="Disk">
          <div className="flex flex-col items-center">
            <Gauge label={disk ? `${fmtBytes(disk.free)} free` : ''} value={disk?.percent ?? 0} color="#EA580C" />
            <div className="mt-2 text-[10px]" style={{ color: 'var(--j-text-dim)' }}>
              {disk ? `${fmtBytes(disk.total - disk.free)} / ${fmtBytes(disk.total)}` : '—'}
            </div>
          </div>
        </StatCard>
      </div>

      {/* Mini charts */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard title="CPU Trend">
          <div className="flex justify-center">
            <MiniChart data={history.map(d => ({ time: d.time, value: d.cpu }))} color="var(--j-sky)" label="CPU" />
          </div>
        </StatCard>
        <StatCard title="Memory Trend">
          <div className="flex justify-center">
            <MiniChart data={history.map(d => ({ time: d.time, value: d.mem }))} color="var(--j-green, #4ade80)" label="Memory" />
          </div>
        </StatCard>
        <StatCard title="Network I/O">
          <div className="flex flex-col items-center gap-2">
            <div className="flex items-center gap-4 font-mono text-xs">
              <span style={{ color: 'var(--j-sky)' }}>▼ {fmtNet(history.length > 1 ? history[history.length - 1].netIn : 0)}</span>
              <span style={{ color: '#EA580C' }}>▲ {fmtNet(history.length > 1 ? history[history.length - 1].netOut : 0)}</span>
            </div>
            <div className="waveform mt-4">
              <span className="wave-bar" /><span className="wave-bar" /><span className="wave-bar" />
              <span className="wave-bar" /><span className="wave-bar" /><span className="wave-bar" />
            </div>
          </div>
        </StatCard>
      </div>

      {/* Server info */}
      {serverInfo && (
        <StatCard title="Server">
          <div className="grid grid-cols-3 gap-4 font-mono text-xs">
            <div><span style={{ color: 'var(--j-text-dim)' }}>Status</span><br /><span className="text-green-400">{serverInfo.status}</span></div>
            <div><span style={{ color: 'var(--j-text-dim)' }}>Version</span><br />{serverInfo.version || '—'}</div>
            <div><span style={{ color: 'var(--j-text-dim)' }}>Uptime</span><br />{serverInfo.uptime || '—'}</div>
          </div>
        </StatCard>
      )}
    </div>
  );
}
