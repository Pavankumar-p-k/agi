'use client';

import { useEffect, useState, useCallback } from 'react';
import { motion, type Variants } from 'framer-motion';
import Card from '@/components/ui/Card';
import Pill from '@/components/ui/Pill';
import Badge from '@/components/ui/Badge';
import Button from '@/components/ui/Button';
import { DashboardSkeleton } from '@/components/ui/Skeleton';

interface SystemStats {
  cpu: { percent: number; count: number };
  memory: { total: number; available: number; percent: number };
  disk: { total: number; free: number; percent: number };
}

function fmtBytes(v: number): string {
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(1)} ${units[i]}`;
}

const containerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.08, delayChildren: 0.08 },
  },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 28 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.62, ease: [0.16, 1, 0.3, 1] } },
};

export default function DashboardPage() {
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [health, setHealth] = useState<{ status: string; version?: string; uptime?: string } | null>(null);
  const [plugins, setPlugins] = useState<{ plugins: { name: string }[] } | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchAll = useCallback(async () => {
    try {
      const [s, h, p] = await Promise.all([
        fetch('/api/system/stats').then(r => r.ok ? r.json() : null),
        fetch('/api/health').then(r => r.ok ? r.json() : null),
        fetch('/api/plugins').then(r => r.ok ? r.json() : null),
      ]);
      if (s) setStats(s);
      if (h) setHealth(h);
      if (p) setPlugins(p);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const t = setInterval(fetchAll, 10000);
    return () => clearInterval(t);
  }, [fetchAll]);

  const isHealthy = health?.status === 'healthy' || health?.status === 'ok';
  const memUsed = stats ? stats.memory.total - stats.memory.available : 0;
  const pluginCount = plugins?.plugins.length ?? 0;

  if (loading) return <DashboardSkeleton />;

  return (
    <motion.div variants={containerVariants} initial="hidden" animate="visible" className="space-y-8 pb-8">
      <motion.section
        variants={itemVariants}
        className="relative min-h-[520px] overflow-hidden border border-[var(--j-border)] bg-[rgba(var(--j-bg-rgb),0.64)] px-5 py-12 md:px-10 md:py-16"
      >
        <div className="hud-grid absolute inset-0" />
        <div className="absolute left-1/2 top-[-240px] h-[720px] w-[720px] -translate-x-1/2 rounded-full bg-[radial-gradient(circle,rgba(var(--j-sky-rgb),0.10),transparent_68%)]" />
        <div className="absolute bottom-[-220px] right-[-160px] h-[520px] w-[520px] rounded-full bg-[radial-gradient(circle,rgba(var(--j-gold-rgb),0.08),transparent_70%)]" />

        <div className="relative z-[1] mx-auto flex max-w-5xl flex-col items-center text-center">
          <motion.div variants={itemVariants} className="hud-label mb-6">
            Just A Rather Very Intelligent System
          </motion.div>
          <motion.h1
            variants={itemVariants}
            className="hud-title bg-gradient-to-br from-white via-[#b0d8f5] to-[var(--j-sky)] bg-clip-text text-[clamp(76px,13vw,150px)] text-transparent"
          >
            JARVIS
          </motion.h1>
          <motion.div variants={itemVariants} className="my-5 flex items-center justify-center gap-4">
            <span className="h-px w-14 bg-gradient-to-r from-transparent to-[var(--j-sky)] md:w-24" />
            <span className="font-mono text-[11px] uppercase tracking-[0.24em] text-[var(--j-text-dim)]">
              Production Web UI
            </span>
            <span className="h-px w-14 bg-gradient-to-r from-[var(--j-sky)] to-transparent md:w-24" />
          </motion.div>
          <motion.p variants={itemVariants} className="max-w-2xl text-base leading-8 text-[var(--j-text-dim)] md:text-lg">
            Full-stack AI dashboard with multi-theme control, live backend operations, voice-ready chat,
            real-time telemetry, and cinematic HUD interaction patterns.
          </motion.p>

          <motion.div variants={itemVariants} className="mt-10 flex flex-wrap justify-center gap-3">
            <Button variant="primary" size="md" onClick={() => window.location.href = '/chat'}>Open Chat</Button>
            <Button variant="ghost" size="md" onClick={() => window.location.href = '/cli'}>CLI Mode</Button>
            <Button variant="ghost" size="md" onClick={() => window.location.href = '/monitor'}>Monitor System</Button>
          </motion.div>

          <motion.div variants={containerVariants} className="mt-12 grid w-full grid-cols-2 gap-px border border-[var(--j-border)] bg-[var(--j-border)] md:grid-cols-4">
            <HeroStat label="System" value={isHealthy ? 'ONLINE' : 'OFFLINE'} accent={isHealthy ? '#00ff88' : '#ff4757'} />
            <HeroStat label="CPU Load" value={stats ? `${stats.cpu.percent.toFixed(0)}%` : '--'} />
            <HeroStat label="Active Plugins" value={`${pluginCount}`} />
            <HeroStat label="Version" value={health?.version ? `v${health.version}` : 'v1.0'} gold />
          </motion.div>
        </div>
      </motion.section>

      {stats && (
        <motion.section variants={itemVariants}>
          <SectionTitle label="Live Telemetry" title="System Pulse" />
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <MetricCard label="CPU" value={stats.cpu.percent} detail={`${stats.cpu.count} cores`} />
            <MetricCard label="Memory" value={stats.memory.percent} detail={`${fmtBytes(memUsed)} / ${fmtBytes(stats.memory.total)}`} gold />
            <MetricCard label="Disk" value={stats.disk.percent} detail={`${fmtBytes(stats.disk.total - stats.disk.free)} / ${fmtBytes(stats.disk.total)}`} />
          </div>
        </motion.section>
      )}

      <motion.section variants={itemVariants}>
        <SectionTitle label="Architecture" title="Core Modules" />
        <motion.div variants={containerVariants} className="grid grid-cols-1 gap-px bg-[var(--j-border)] md:grid-cols-2 xl:grid-cols-3">
          {MODULES.map((m, index) => (
            <motion.div key={m.title} variants={itemVariants}>
              <Card variant={m.gold ? 'deep' : 'sky'} onClick={() => window.location.href = m.href} className="h-full min-h-[230px] rounded-none">
                <div className="absolute right-6 top-5 font-display text-6xl leading-none tracking-[0.04em] text-[rgba(var(--j-sky-rgb),0.10)] group-hover:text-[rgba(var(--j-sky-rgb),0.20)]">
                  {String(index + 1).padStart(2, '0')}
                </div>
                <div
                  className="mb-8 h-0.5 w-8 shadow-[0_0_10px_currentColor]"
                  style={{ background: m.gold ? 'var(--j-gold)' : 'var(--j-sky)', color: m.gold ? 'var(--j-gold)' : 'var(--j-sky)' }}
                />
                <Badge variant={m.gold ? 'hot' : 'default'}>{m.tag}</Badge>
                <h3 className="mt-4 font-display text-3xl tracking-[0.08em] text-[var(--j-text)]">{m.title}</h3>
                <p className="mt-3 text-sm leading-7 text-[var(--j-text-dim)]">{m.desc}</p>
                <div className="mt-6 flex flex-wrap gap-2">
                  {m.tags.map(tag => <Pill key={tag}>{tag}</Pill>)}
                </div>
              </Card>
            </motion.div>
          ))}
        </motion.div>
      </motion.section>

      <motion.section variants={itemVariants} className="grid grid-cols-1 gap-px bg-[var(--j-border)] lg:grid-cols-[1fr_1.2fr]">
        <div className="bg-[var(--j-surface)] p-6 md:p-8">
          <SectionTitle label="Operations" title="Backend Control" compact />
          <div className="mt-8 grid grid-cols-1 gap-px bg-[var(--j-border)] sm:grid-cols-2">
            {BACKEND.map(item => (
              <div key={item.title} className="bg-[var(--j-surface-hover)] p-5 transition-colors hover:bg-[rgba(var(--j-sky-rgb),0.08)]">
                <div className="hud-label mb-3">{item.kicker}</div>
                <div className="font-display text-2xl tracking-[0.08em]">{item.title}</div>
                <p className="mt-2 text-xs leading-6 text-[var(--j-text-dim)]">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
        <TerminalPanel health={health} stats={stats} />
      </motion.section>
    </motion.div>
  );
}

function HeroStat({ label, value, gold = false, accent }: { label: string; value: string; gold?: boolean; accent?: string }) {
  return (
    <motion.div variants={itemVariants} className="bg-[rgba(var(--j-bg-rgb),0.84)] px-4 py-5 text-center">
      <div className="font-display text-4xl leading-none tracking-[0.08em]" style={{ color: accent || (gold ? 'var(--j-gold)' : 'var(--j-text)') }}>
        {value}
      </div>
      <div className="mt-2 font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--j-text-muted)]">{label}</div>
    </motion.div>
  );
}

function SectionTitle({ label, title, compact = false }: { label: string; title: string; compact?: boolean }) {
  return (
    <div className={compact ? '' : 'mb-8'}>
      <div className="hud-label flex items-center gap-3 before:h-px before:w-6 before:bg-[var(--j-sky)]">{label}</div>
      <h2 className="hud-title mt-3 text-5xl text-[var(--j-text)] md:text-6xl">
        {title.split(' ')[0]} <span className="text-[var(--j-sky)]">{title.split(' ').slice(1).join(' ')}</span>
      </h2>
    </div>
  );
}

function MetricCard({ label, value, detail, gold = false }: { label: string; value: number; detail: string; gold?: boolean }) {
  const color = gold ? 'var(--j-gold)' : 'var(--j-sky)';
  return (
    <Card variant={gold ? 'deep' : 'sky'} className="rounded-none">
      <div className="flex items-center justify-between">
        <span className="hud-label">{label}</span>
        <span className="font-display text-4xl leading-none tracking-[0.08em]" style={{ color }}>{value.toFixed(0)}%</span>
      </div>
      <div className="mt-5 h-1.5 bg-[rgba(var(--j-sky-rgb),0.08)]">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${Math.min(value, 100)}%` }}
          transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
          className="h-full shadow-[0_0_14px_currentColor]"
          style={{ background: color, color }}
        />
      </div>
      <div className="mt-3 font-mono text-[10px] uppercase tracking-[0.12em] text-[var(--j-text-muted)]">{detail}</div>
    </Card>
  );
}

function TerminalPanel({ health, stats }: { health: { status: string; version?: string; uptime?: string } | null; stats: SystemStats | null }) {
  return (
    <div className="bg-[#020a0f] p-6 font-mono text-xs leading-7 text-[var(--j-text-dim)] md:p-8">
      <div className="mb-5 flex items-center gap-2 border-b border-[var(--j-border)] pb-4">
        <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
        <span className="h-2.5 w-2.5 rounded-full bg-[#febc2e]" />
        <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
        <span className="ml-2 text-[10px] uppercase tracking-[0.18em] text-[var(--j-text-muted)]">jarvis-core</span>
      </div>
      <TermLine prompt cmd="status --all" />
      <div className="mt-3">
        <StatusLine ok label="api-server" value={health?.status || 'unknown'} />
        <StatusLine ok label="ai-worker" value="ready" />
        <StatusLine warn label="memory" value={stats ? `${stats.memory.percent.toFixed(0)}% used` : 'standby'} />
        <StatusLine ok label="plugins" value="indexed" />
        <StatusLine ok label="web-ui" value="hud active" />
      </div>
      <div className="mt-5">
        <TermLine prompt cmd="system --pulse" />
        <div className="mt-2 grid grid-cols-2 gap-x-5">
          <span>CPU</span><span className="text-[var(--j-sky)]">{stats ? `${stats.cpu.percent.toFixed(1)}%` : '--'}</span>
          <span>DISK</span><span className="text-[var(--j-sky)]">{stats ? `${stats.disk.percent.toFixed(1)}%` : '--'}</span>
          <span>UPTIME</span><span className="text-[var(--j-gold)]">{health?.uptime || 'local'}</span>
        </div>
      </div>
      <div className="mt-5 flex items-center gap-2">
        <span className="text-[var(--j-sky)]">jarvis@core:~$</span>
        <span className="h-4 w-2 bg-[var(--j-sky)] animate-[blink-block_1s_step-end_infinite]" />
      </div>
    </div>
  );
}

function TermLine({ prompt, cmd }: { prompt: boolean; cmd: string }) {
  return (
    <div className="flex gap-3">
      {prompt && <span className="text-[var(--j-sky)]">jarvis@core:~$</span>}
      <span className="text-[var(--j-text)]">{cmd}</span>
    </div>
  );
}

function StatusLine({ label, value, ok = false, warn = false }: { label: string; value: string; ok?: boolean; warn?: boolean }) {
  return (
    <div className="flex gap-3">
      <span className={ok ? 'text-[#28c840]' : warn ? 'text-[var(--j-gold)]' : 'text-[var(--j-text-muted)]'}>{ok ? 'OK' : warn ? 'WRN' : '--'}</span>
      <span className="min-w-24">{label}</span>
      <span className={warn ? 'text-[var(--j-gold)]' : 'text-[var(--j-text-dim)]'}>{value}</span>
    </div>
  );
}

const MODULES = [
  {
    tag: 'Module 01',
    title: 'AI Core Interface',
    desc: 'Chat panel, streaming responses, voice input, markdown rendering, model controls, and context-aware command flow.',
    tags: ['Voice', 'Streaming', 'Models'],
    href: '/chat',
  },
  {
    tag: 'Module 02',
    title: 'Backend Control',
    desc: 'Service controls, health checks, environment configuration, API key vault surfaces, scheduler, and process management.',
    tags: ['Services', 'Config', 'Vault'],
    href: '/backend',
  },
  {
    tag: 'Module 03',
    title: 'Real-time Monitor',
    desc: 'Live CPU, memory, disk, and network telemetry with animated system pulse indicators and fast operational scanning.',
    tags: ['CPU', 'Memory', 'Network'],
    href: '/monitor',
    gold: true,
  },
  {
    tag: 'Module 04',
    title: 'Log Viewer',
    desc: 'Streaming log console with filtering, severity reading, and browser-native operational visibility.',
    tags: ['Logs', 'Filter', 'Trace'],
    href: '/logs',
  },
  {
    tag: 'Module 05',
    title: 'CLI Control Plane',
    desc: 'Interactive terminal chat, slash commands, nine agent shortcuts, web launcher, diagnostics, and plugin operations.',
    tags: ['Agents', 'REPL', 'Commands'],
    href: '/cli',
  },
  {
    tag: 'Module 06',
    title: 'Theme Studio',
    desc: 'Theme engine, font switching, CSS variable controls, and visual identity presets for the full web UI.',
    tags: ['Themes', 'Fonts', 'Tokens'],
    href: '/settings/themes',
  },
  {
    tag: 'Module 07',
    title: 'Auth Console',
    desc: 'Local sign-in surface, guarded app routes, and clean account controls for the browser shell.',
    tags: ['Session', 'Access', 'Local'],
    href: '/auth/login',
    gold: true,
  },
];

const BACKEND = [
  { kicker: 'Services', title: 'Process Manager', desc: 'Start, stop, restart, and inspect JARVIS services from the browser.' },
  { kicker: 'Config', title: 'Env Control', desc: 'Review runtime settings and prepare safe configuration changes.' },
  { kicker: 'Security', title: 'Key Vault', desc: 'Keep API key operations visible without exposing raw secrets.' },
  { kicker: 'Scheduler', title: 'Cron Jobs', desc: 'Track recurring jobs, automation hooks, and background tasks.' },
];
