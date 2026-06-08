'use client';

import { useEffect, useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import Button from '@/components/ui/Button';
import Badge from '@/components/ui/Badge';

interface ServiceStatus {
  name: string;
  status: 'running' | 'warn' | 'error';
  detail: string;
}

function ServiceRow({ s, index }: { s: ServiceStatus; index: number }) {
  const color = s.status === 'running' ? '#28c840' : s.status === 'warn' ? 'var(--j-gold)' : '#ff4757';
  return (
    <motion.div
      initial={{ opacity: 0, x: -16 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.04 }}
      className="group grid grid-cols-[1fr_auto] items-center gap-4 border-b border-[var(--j-border)] px-5 py-3 font-mono text-xs transition-colors hover:bg-[rgba(var(--j-sky-rgb),0.05)]"
    >
      <div className="flex min-w-0 items-center gap-3">
        <span className="h-2 w-2 rounded-full shadow-[0_0_10px_currentColor]" style={{ background: color, color }} />
        <span className="truncate text-[var(--j-text)]">{s.name}</span>
      </div>
      <span className="uppercase tracking-[0.12em]" style={{ color }}>{s.detail || s.status}</span>
    </motion.div>
  );
}

export default function BackendPage() {
  const [health, setHealth] = useState<{ status: string; version?: string; uptime?: string } | null>(null);
  const [stats, setStats] = useState<{ cpu: { percent: number }; memory: { percent: number } } | null>(null);
  const [plugins, setPlugins] = useState<{ plugins: { name: string }[] } | null>(null);

  const fetchAll = useCallback(async () => {
    try {
      const [h, s, p] = await Promise.all([
        fetch('/api/health').then(r => r.ok ? r.json() : null),
        fetch('/api/system/stats').then(r => r.ok ? r.json() : null),
        fetch('/api/plugins').then(r => r.ok ? r.json() : null),
      ]);
      if (h) setHealth(h);
      if (s) setStats(s);
      if (p) setPlugins(p);
    } catch {
      setHealth(prev => prev);
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const t = setInterval(fetchAll, 15000);
    return () => clearInterval(t);
  }, [fetchAll]);

  const isHealthy = health?.status === 'healthy' || health?.status === 'ok';
  const services: ServiceStatus[] = [
    { name: 'api-server', status: isHealthy ? 'running' : 'error', detail: isHealthy ? `${stats ? stats.cpu.percent.toFixed(1) : '0'}% CPU` : 'offline' },
    { name: 'ai-worker', status: 'running', detail: 'ready' },
    { name: 'postgres', status: 'running', detail: 'ready' },
    { name: 'cache-layer', status: stats && stats.memory.percent > 80 ? 'warn' : 'running', detail: stats ? `${stats.memory.percent.toFixed(0)}% MEM` : 'standby' },
    { name: 'plugin-host', status: plugins && plugins.plugins.length > 0 ? 'running' : 'warn', detail: `${plugins?.plugins.length ?? 0} plugins` },
  ];

  return (
    <div className="hud-page h-full overflow-y-auto space-y-6">
      <section className="hud-panel hud-scan-box p-6 md:p-8">
        <div className="relative z-[1] flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="hud-label">Infrastructure</div>
            <h1 className="hud-title mt-3 text-6xl md:text-7xl">Backend <span className="text-[var(--j-sky)]">Control</span></h1>
            <p className="mt-4 max-w-2xl text-sm leading-7 text-[var(--j-text-dim)]">
              Operate the JARVIS core from one browser console: service state, plugin host,
              health checks, and runtime telemetry.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Button variant="primary" onClick={() => window.location.href = '/monitor'}>Monitor</Button>
            <Button variant="ghost" onClick={() => window.location.href = '/logs'}>Logs</Button>
          </div>
        </div>
      </section>

      <section className="grid grid-cols-2 gap-px bg-[var(--j-border)] md:grid-cols-4">
        {[
          { label: 'Status', value: isHealthy ? 'Healthy' : 'Offline', color: isHealthy ? '#28c840' : '#ff4757' },
          { label: 'Version', value: health?.version || 'Local', color: 'var(--j-sky)' },
          { label: 'Uptime', value: health?.uptime || '--', color: 'var(--j-gold)' },
          { label: 'Plugins', value: String(plugins?.plugins.length ?? 0), color: '#a78bfa' },
        ].map(item => (
          <div key={item.label} className="bg-[var(--j-surface)] p-5">
            <div className="hud-label text-[9px]">{item.label}</div>
            <div className="mt-2 font-display text-4xl tracking-[0.08em]" style={{ color: item.color }}>{item.value}</div>
          </div>
        ))}
      </section>

      <section className="grid grid-cols-1 gap-px bg-[var(--j-border)] xl:grid-cols-[1fr_1.1fr]">
        <div className="bg-[var(--j-surface)]">
          <div className="flex items-center justify-between border-b border-[var(--j-border)] px-5 py-4">
            <div>
              <div className="hud-label">Services</div>
              <div className="mt-1 text-sm text-[var(--j-text-dim)]">Live runtime state</div>
            </div>
            <Badge variant={isHealthy ? 'new' : 'hot'}>{isHealthy ? 'Connected' : 'Disconnected'}</Badge>
          </div>
          {services.map((s, i) => <ServiceRow key={s.name} s={s} index={i} />)}
        </div>

        <div className="bg-[#020a0f] p-6 font-mono text-xs leading-7">
          <div className="mb-5 flex items-center gap-2 border-b border-[var(--j-border)] pb-4">
            <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
            <span className="h-2.5 w-2.5 rounded-full bg-[#febc2e]" />
            <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
            <span className="ml-2 text-[10px] uppercase tracking-[0.18em] text-[var(--j-text-muted)]">jarvis-ops</span>
          </div>
          <div><span className="text-[var(--j-sky)]">jarvis@core:~$</span> <span className="text-[var(--j-text)]">status --all</span></div>
          <div className="mt-3">
            {services.map(s => {
              const color = s.status === 'running' ? '#28c840' : s.status === 'warn' ? 'var(--j-gold)' : '#ff4757';
              return (
                <div key={s.name} className="grid grid-cols-[42px_150px_1fr] gap-2">
                  <span style={{ color }}>{s.status === 'running' ? 'OK' : s.status === 'warn' ? 'WRN' : 'ERR'}</span>
                  <span className="text-[var(--j-text-dim)]">{s.name}</span>
                  <span style={{ color }}>{s.detail}</span>
                </div>
              );
            })}
          </div>
          <div className="mt-5 flex items-center gap-2">
            <span className="text-[var(--j-sky)]">jarvis@core:~$</span>
            <span className="h-4 w-2 bg-[var(--j-sky)] animate-[blink-block_1s_step-end_infinite]" />
          </div>
        </div>
      </section>

      {plugins && plugins.plugins.length > 0 && (
        <section className="hud-panel p-5">
          <div className="hud-label mb-4">Active Plugins</div>
          <div className="flex flex-wrap gap-2">
            {plugins.plugins.map(p => <Badge key={p.name}>{p.name}</Badge>)}
          </div>
        </section>
      )}
    </div>
  );
}
