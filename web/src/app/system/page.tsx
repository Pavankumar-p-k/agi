'use client';

import { useEffect, useState, useCallback } from 'react';
import { api, type SystemStats, type HealthStatus, type SystemStatus, type ModelListResponse, type Integration } from '@/lib/api';

/* ── Helpers ─────────────────────────────────────────── */

function fmtBytes(v: number): string {
  const u = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(1)} ${u[i]}`;
}

function fmtPct(v: number): string {
  return `${v.toFixed(1)}%`;
}

/* ── Gauges ──────────────────────────────────────────── */

function Gauge({ label, value, max, unit, color }: { label: string; value: number; max: number; unit: string; color: string }) {
  const pct = Math.min((value / max) * 100, 100);
  return (
    <div
      className="px-4 py-3"
      style={{ border: '1px solid var(--j-border)', borderRadius: 'var(--j-radius-md)' }}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-mono" style={{ color: 'var(--j-text-dim)' }}>{label}</span>
        <span className="text-xs font-mono" style={{ color: 'var(--j-text)' }}>{unit === '%' ? fmtPct(value) : `${value.toFixed(0)} ${unit}`}</span>
      </div>
      <div className="h-1.5 w-full" style={{ background: 'var(--j-border)' }}>
        <div
          className="h-full transition-all duration-500"
          style={{
            width: `${pct}%`,
            background: color,
            boxShadow: `0 0 8px ${color}`,
          }}
        />
      </div>
    </div>
  );
}

/* ── Health Dot ──────────────────────────────────────── */

function HealthDot({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className="flex items-center gap-2 px-3 py-2" style={{ border: '1px solid var(--j-border)', borderRadius: 'var(--j-radius-sm)' }}>
      <div
        className="w-1.5 h-1.5 rounded-full shrink-0"
        style={{
          background: ok ? 'var(--j-green)' : '#ff4757',
          boxShadow: ok ? '0 0 6px rgba(74,222,128,0.5)' : '0 0 6px rgba(255,71,87,0.5)',
        }}
      />
      <span className="text-xs" style={{ color: 'var(--j-text)' }}>{label}</span>
      <span className="text-[10px] ml-auto font-mono uppercase tracking-[0.12em]" style={{ color: ok ? 'var(--j-green)' : '#ff4757' }}>
        {ok ? 'OK' : 'DOWN'}
      </span>
    </div>
  );
}

/* ── System Page ─────────────────────────────────────── */

export default function SystemPage() {
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [sysStatus, setSysStatus] = useState<SystemStatus | null>(null);
  const [models, setModels] = useState<ModelListResponse | null>(null);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchAll = useCallback(async () => {
    setLoading(true);

    const [
      statsResult,
      healthResult,
      sysStatusResult,
      modelsResult,
      integrationsResult,
    ] = await Promise.all([
      api.system.stats().catch(() => null),
      api.health().catch(() => null),
      api.system.status().catch(() => null),
      api.models.list().catch(() => null),
      api.integrations.list().catch(() => null),
    ]);

    if (statsResult) setStats(statsResult);
    if (healthResult) setHealth(healthResult);
    if (sysStatusResult) setSysStatus(sysStatusResult);
    if (modelsResult) setModels(modelsResult);
    if (integrationsResult?.integrations) setIntegrations(integrationsResult.integrations);

    setLoading(false);
  }, []);

  useEffect(() => {
    fetchAll();
    const iv = setInterval(fetchAll, 15000);
    return () => clearInterval(iv);
  }, [fetchAll]);

  const healthy = health?.status === 'healthy' || health?.status === 'ok';
  const memUsed = stats ? stats.memory.total - stats.memory.available : 0;
  const memPct = stats ? stats.memory.percent : 0;

  return (
    <div className="mx-auto max-w-3xl space-y-8 pb-12">

      {/* ── Server Health ── */}
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
            className="w-3 h-3 rounded-full shrink-0"
            style={{
              background: healthy ? 'var(--j-green)' : '#ff4757',
              boxShadow: healthy ? '0 0 12px rgba(74,222,128,0.6)' : '0 0 12px rgba(255,71,87,0.6)',
            }}
          />
          <div>
            <div className="text-sm font-mono" style={{ color: 'var(--j-text)' }}>
              {healthy ? 'All systems operational' : 'System degraded'}
            </div>
            <div className="text-xs mt-0.5" style={{ color: 'var(--j-text-muted)' }}>
              {sysStatus?.version || health?.version || 'JARVIS'} · {sysStatus?.model || 'No model loaded'}
            </div>
          </div>
          <div className="ml-auto text-[10px] font-mono uppercase tracking-[0.12em]" style={{ color: healthy ? 'var(--j-green)' : '#ff4757' }}>
            {healthy ? 'Healthy' : 'Degraded'}
          </div>
        </div>
      </section>

      {/* ── Resources ── */}
      <section>
        <div className="flex items-center gap-2 mb-4">
            <h2 className="text-xs tracking-[0.12em] uppercase m-0" style={{ color: 'var(--j-text-muted)' }}>Resources</h2>
          <span className="h-px flex-1" style={{ background: 'var(--j-border)' }} />
        </div>

        <div className="grid gap-3">
          <Gauge
            label="CPU"
            value={stats?.cpu.percent ?? 0}
            max={100}
            unit="%"
            color={stats && stats.cpu.percent > 80 ? '#ff4757' : stats && stats.cpu.percent > 50 ? 'var(--j-gold)' : 'var(--j-sky)'}
          />
          <Gauge
            label="Memory"
            value={memPct}
            max={100}
            unit="%"
            color={memPct > 80 ? '#ff4757' : memPct > 50 ? 'var(--j-gold)' : 'var(--j-green)'}
          />
          {stats?.memory && (
            <div className="text-xs font-mono px-4 py-2" style={{ color: 'var(--j-text-muted)' }}>
              {fmtBytes(memUsed)} / {fmtBytes(stats.memory.total)} used
            </div>
          )}
          {stats?.disk && (
            <Gauge
              label="Disk"
              value={stats.disk.total - stats.disk.free}
              max={stats.disk.total}
              unit="GB"
              color={stats.disk.percent > 90 ? '#ff4757' : stats.disk.percent > 70 ? 'var(--j-gold)' : 'var(--j-sky)'}
            />
          )}
        </div>
      </section>

      {/* ── Providers ── */}
      <section>
        <div className="flex items-center gap-2 mb-4">
            <h2 className="text-xs tracking-[0.12em] uppercase m-0" style={{ color: 'var(--j-text-muted)' }}>Providers</h2>
          <span className="h-px flex-1" style={{ background: 'var(--j-border)' }} />
        </div>

        <div className="grid gap-2">
          <HealthDot ok={models?.ollama_available ?? false} label="Ollama" />
          {sysStatus?.model_router?.models && sysStatus.model_router.models.length > 0 && (
            <HealthDot ok={true} label={`Model: ${sysStatus.model_router.models[0]}`} />
          )}
          {integrations.map(int => (
            <HealthDot key={int.name} ok={int.connected} label={int.name} />
          ))}
        </div>

        {(!models?.ollama_available && integrations.length === 0) && (
          <div className="text-center py-8" style={{ border: '1px dashed var(--j-border)', borderRadius: 'var(--j-radius-md)' }}>
            <p className="text-sm font-mono mb-2" style={{ color: 'var(--j-text-dim)' }}>No providers configured</p>
            <p className="text-xs mb-4" style={{ color: 'var(--j-text-muted)' }}>Run setup to install Ollama and configure integrations.</p>
            <a
              href="/welcome"
              className="inline-block px-5 py-2.5 text-[10px] font-mono uppercase tracking-[0.12em] transition-all hover:opacity-80"
              style={{ border: '1px solid var(--j-sky)', borderRadius: 'var(--j-radius-sm)', color: 'var(--j-sky)' }}
            >
              Run setup
            </a>
          </div>
        )}
      </section>

      {/* ── Hardware info ── */}
      <section>
        <div className="flex items-center gap-2 mb-4">
            <h2 className="text-xs tracking-[0.12em] uppercase m-0" style={{ color: 'var(--j-text-muted)' }}>Hardware</h2>
          <span className="h-px flex-1" style={{ background: 'var(--j-border)' }} />
        </div>

        <div
          className="grid grid-cols-2 md:grid-cols-4 gap-px"
          style={{ border: '1px solid var(--j-border)', borderRadius: 'var(--j-radius-md)', overflow: 'hidden' }}
        >
          {([
            { label: 'CPU Cores', value: stats?.cpu.count ? `${stats.cpu.count} cores` : '--' },
            { label: 'Memory', value: stats?.memory.total ? fmtBytes(stats.memory.total) : '--' },
            { label: 'Disk Total', value: stats?.disk.total ? fmtBytes(stats.disk.total) : '--' },
            { label: 'Disk Free', value: stats?.disk.free ? fmtBytes(stats.disk.free) : '--' },
          ] as const).map(item => (
            <div key={item.label} className="px-4 py-3 text-center" style={{ background: 'rgba(var(--j-bg-rgb),0.4)' }}>
              <div className="text-xs font-mono" style={{ color: 'var(--j-text-muted)' }}>{item.label}</div>
              <div className="text-sm font-mono mt-1" style={{ color: 'var(--j-text)' }}>{item.value}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Loading ── */}
      {loading && (
        <div className="text-center py-8">
          <p className="text-xs" style={{ color: 'var(--j-text-muted)' }}>Loading system status...</p>
        </div>
      )}
    </div>
  );
}
