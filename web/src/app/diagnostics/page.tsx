'use client';

import { useEffect, useState, useCallback } from 'react';
import { motion, type Variants } from 'framer-motion';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import { Skeleton } from '@/components/ui/Skeleton';
import { api } from '@/lib/api';

interface DiagnosticsResult {
  models: { status: string; provider: string; latency_ms?: number }[];
  integrations: { name: string; status: string }[];
  voice: { stt: string; tts: string; wake_word: string };
  environment: Record<string, string>;
  features: { name: string; enabled: boolean; category: string }[];
}

const containerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.06, delayChildren: 0.08 } },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 28 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.62, ease: [0.16, 1, 0.3, 1] } },
};

export default function DiagnosticsPage() {
  const [result, setResult] = useState<DiagnosticsResult | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchDiagnostics = useCallback(async () => {
    try {
      const data = await api.diagnostics.all();
      setResult(data as unknown as DiagnosticsResult);
    } catch (e) { console.warn('[Diagnostics] fetch failed', e); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchDiagnostics(); }, [fetchDiagnostics]);

  const statusColor = (s: string) => {
    if (s === 'healthy' || s === 'ok' || s === 'available' || s === 'ready') return '#28c840';
    if (s === 'unhealthy' || s === 'error') return '#ff4757';
    return 'var(--j-gold)';
  };

  if (loading) return <div className="hud-page p-6"><Skeleton /></div>;

  return (
    <motion.div variants={containerVariants} initial="hidden" animate="visible" className="hud-page h-full overflow-y-auto space-y-6 p-6">
      <motion.section variants={itemVariants} className="hud-panel hud-scan-box p-6 md:p-8">
        <div className="hud-label">System Analysis</div>
        <h1 className="hud-title mt-2 text-6xl md:text-7xl">Diagnostics <span className="text-[var(--j-sky)]">Dashboard</span></h1>
        <p className="mt-4 max-w-2xl text-sm leading-7 text-[var(--j-text-dim)]">
          Full platform health scan: models, integrations, voice pipeline, features, and environment.
        </p>
      </motion.section>

      {result && (
        <>
          <motion.section variants={itemVariants}>
            <div className="hud-label mb-4">Model Health</div>
            <div className="grid grid-cols-1 gap-px bg-[var(--j-border)] md:grid-cols-2 xl:grid-cols-3">
              {result.models.map(m => (
                <div key={m.provider} className="bg-[var(--j-surface)] p-5">
                  <div className="flex items-center justify-between">
                    <span className="font-display text-lg tracking-[0.08em] text-[var(--j-text)]">{m.provider}</span>
                    <span style={{ color: statusColor(m.status) }} className="font-mono text-xs">{m.status}</span>
                  </div>
                  {m.latency_ms !== undefined && (
                    <div className="mt-2 font-mono text-[10px] text-[var(--j-text-muted)]">{m.latency_ms}ms</div>
                  )}
                </div>
              ))}
            </div>
          </motion.section>

          <motion.section variants={itemVariants}>
            <div className="hud-label mb-4">Integration Health</div>
            <div className="grid grid-cols-1 gap-px bg-[var(--j-border)] md:grid-cols-2 xl:grid-cols-3">
              {result.integrations.map(ix => (
                <div key={ix.name} className="bg-[var(--j-surface)] p-5">
                  <div className="flex items-center justify-between">
                    <span className="font-display text-lg tracking-[0.08em] text-[var(--j-text)]">{ix.name}</span>
                    <span style={{ color: statusColor(ix.status) }} className="font-mono text-xs">{ix.status}</span>
                  </div>
                </div>
              ))}
            </div>
          </motion.section>

          <motion.section variants={itemVariants}>
            <div className="hud-label mb-4">Voice Pipeline</div>
            <div className="grid grid-cols-1 gap-px bg-[var(--j-border)] md:grid-cols-3">
              <VoiceStatus label="STT" value={result.voice.stt} />
              <VoiceStatus label="TTS" value={result.voice.tts} />
              <VoiceStatus label="Wake Word" value={result.voice.wake_word} />
            </div>
          </motion.section>

          <motion.section variants={itemVariants}>
            <div className="hud-label mb-4">Environment</div>
            <div className="grid grid-cols-1 gap-px bg-[var(--j-border)] md:grid-cols-2 xl:grid-cols-3">
              {Object.entries(result.environment).map(([k, v]) => (
                <div key={k} className="bg-[var(--j-surface)] p-4">
                  <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-[var(--j-text-dim)]">{k}</div>
                  <div className="mt-1 font-mono text-xs text-[var(--j-text)] truncate">{v}</div>
                </div>
              ))}
            </div>
          </motion.section>
        </>
      )}
    </motion.div>
  );
}

function VoiceStatus({ label, value }: { label: string; value: string }) {
  const ok = value === 'healthy' || value === 'available';
  return (
    <div className="bg-[var(--j-surface)] p-5">
      <div className="text-xs text-[var(--j-text-dim)]">{label}</div>
      <div className="mt-1 font-display text-2xl tracking-[0.08em]" style={{ color: ok ? '#28c840' : 'var(--j-gold)' }}>{value}</div>
    </div>
  );
}
