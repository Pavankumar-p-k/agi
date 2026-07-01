'use client';

import { useEffect, useState, useCallback } from 'react';
import { motion, type Variants } from 'framer-motion';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import Pill from '@/components/ui/Pill';
import Button from '@/components/ui/Button';
import { Skeleton } from '@/components/ui/Skeleton';
import ModelDownloader from '@/components/models/ModelDownloader';
import { api, type SetupStatus } from '@/lib/api';

interface ModelConfig {
  id: string;
  name: string;
  provider: string;
  type: string;
  priority: number;
  enabled: boolean;
}

const containerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.06, delayChildren: 0.08 } },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 28 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.62, ease: [0.16, 1, 0.3, 1] } },
};

export default function ModelSettingsPage() {
  const [models, setModels] = useState<ModelConfig[]>([]);
  const [primary, setPrimary] = useState<string>('auto');
  const [mode, setMode] = useState<string>('hybrid');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [setupStatus, setSetupStatus] = useState<SetupStatus | null>(null);

  const fetchAll = useCallback(async () => {
    setError('');
    try {
      const [m, s, setup] = await Promise.all([
        api.models.list().catch(() => null),
        api.settings.list().catch(() => []),
        api.setup.status().catch(() => null),
      ]);
      if (m?.models) setModels(m.models.map((mdl: { id: string; name: string; provider: string }) => ({ id: mdl.id, name: mdl.name, provider: mdl.provider, type: mdl.provider === 'ollama' ? 'local' : 'remote', priority: 0, enabled: true })));
      const primarySetting = (s || []).find((setting: { key: string }) => setting.key === 'model.primary');
      if (primarySetting) setPrimary(String(primarySetting.value));
      const modeSetting = (s || []).find((setting: { key: string }) => setting.key === 'model.mode');
      if (modeSetting) setMode(String(modeSetting.value));
      if (setup) setSetupStatus(setup);
    } catch (e) { console.warn('[ModelSettings] fetch failed', e); setError('Failed to load settings'); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const setPrimaryModel = async (id: string) => {
    try {
      await api.settings.update('model.primary', id);
      setPrimary(id);
    } catch (e) { console.warn('[ModelSettings] update primary failed', e); setError('Failed to set primary model'); }
  };

  const setModelMode = async (m: string) => {
    try {
      await api.settings.update('model.mode', m);
      setMode(m);
    } catch (e) { console.warn('[ModelSettings] update mode failed', e); setError('Failed to set model mode'); }
  };

  if (loading) return <div className="hud-page p-6"><Skeleton /></div>;

  return (
    <motion.div variants={containerVariants} initial="hidden" animate="visible" className="hud-page h-full overflow-y-auto space-y-6 p-6">
      <motion.section variants={itemVariants} className="hud-panel hud-scan-box p-6 md:p-8">
        <div className="hud-label">Configuration</div>
        <h1 className="hud-title mt-2 text-6xl md:text-7xl">Model <span className="text-[var(--j-sky)]">Settings</span></h1>
        <p className="mt-4 max-w-2xl text-sm leading-7 text-[var(--j-text-dim)]">
          Set primary inference model, configure provider priorities, and manage per-task routing.
        </p>
      </motion.section>

      {error && (
        <motion.div variants={itemVariants} className="border border-red-500/30 bg-red-500/5 px-5 py-3">
          <p className="text-xs text-red-400">{error}</p>
        </motion.div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <motion.section variants={itemVariants}>
          <div className="hud-label mb-4">Inference Mode</div>
          <div className="grid grid-cols-3 gap-px bg-[var(--j-border)]">
            {['local', 'cloud', 'hybrid'].map(m => (
              <button
                key={m}
                onClick={() => setModelMode(m)}
                className={`bg-[var(--j-surface)] p-5 text-center transition-all ${
                  mode === m ? 'ring-1 ring-[var(--j-sky)]' : 'opacity-60 hover:opacity-100'
                }`}
              >
                <div className={`font-display text-2xl uppercase tracking-widest ${mode === m ? 'text-[var(--j-sky)]' : 'text-[var(--j-text-dim)]'}`}>{m}</div>
                <div className="mt-1 text-[9px] uppercase tracking-widest text-[var(--j-text-muted)]">
                  {m === 'hybrid' ? 'Best of both' : m === 'local' ? 'Privacy first' : 'Power first'}
                </div>
              </button>
            ))}
          </div>
        </motion.section>

        <motion.section variants={itemVariants}>
          <div className="hud-label mb-4">Primary Model</div>
          <div className="bg-[var(--j-surface)] p-5 border border-[var(--j-border)]">
            <div className="font-display text-3xl tracking-[0.08em] text-[var(--j-sky)]">{primary}</div>
            <div className="mt-4 flex flex-wrap gap-2">
              {models.map(m => (
                <button
                  key={m.id}
                  onClick={() => setPrimaryModel(m.id)}
                  className={`px-4 py-2 border font-mono text-xs uppercase tracking-[0.12em] transition-all ${
                    primary === m.id
                      ? 'border-[var(--j-sky)] text-[var(--j-sky)] bg-[rgba(56,189,248,0.1)]'
                      : 'border-[var(--j-border)] text-[var(--j-text-dim)] hover:border-[var(--j-border-bright)]'
                  }`}
                >
                  {m.name}
                </button>
              ))}
            </div>
          </div>
        </motion.section>
      </div>

      {/* ── Download Models ── */}
      <motion.section variants={itemVariants}>
        <div className="hud-label mb-4">Download Models</div>
        <div
          className="p-5"
          style={{ border: '1px solid var(--j-border)', borderRadius: 'var(--j-radius-md)', background: 'rgba(var(--j-bg-rgb),0.3)' }}
        >
          {setupStatus ? (
            <ModelDownloader status={setupStatus} />
          ) : (
            <div className="text-center py-4">
              <span className="text-[10px] font-mono" style={{ color: 'var(--j-text-muted)' }}>
                Detecting hardware…
              </span>
            </div>
          )}
        </div>
      </motion.section>

      <motion.section variants={itemVariants}>
        <div className="hud-label mb-4">All Models</div>
        <div className="grid grid-cols-1 gap-px bg-[var(--j-border)] md:grid-cols-2 xl:grid-cols-3">
          {models.length === 0 && !error && (
            <div className="col-span-full bg-[var(--j-surface)] p-8 text-center text-sm text-[var(--j-text-dim)]">
              No models found. Configure providers in Settings.
            </div>
          )}
          {models.map(m => (
            <div key={m.id} className="bg-[var(--j-surface)] p-5">
              <div className="font-display text-xl tracking-[0.08em] text-[var(--j-text)]">{m.name}</div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Pill>{m.provider}</Pill>
                <Pill>{m.type}</Pill>
                <Pill>Priority {m.priority}</Pill>
              </div>
            </div>
          ))}
        </div>
      </motion.section>
    </motion.div>
  );
}
