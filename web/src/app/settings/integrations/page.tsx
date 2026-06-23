'use client';

import { useEffect, useState, useCallback } from 'react';
import { motion, type Variants } from 'framer-motion';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import Pill from '@/components/ui/Pill';
import Button from '@/components/ui/Button';
import { Skeleton } from '@/components/ui/Skeleton';
import { api } from '@/lib/api';

interface IntegrationConfig {
  name: string;
  label: string;
  enabled: boolean;
  connected: boolean;
  config: Record<string, string>;
}

const containerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.06, delayChildren: 0.08 } },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 28 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.62, ease: [0.16, 1, 0.3, 1] } },
};

export default function IntegrationSettingsPage() {
  const [integrations, setIntegrations] = useState<IntegrationConfig[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchIntegrations = useCallback(async () => {
    try {
      const data = await api.integrations.list();
      setIntegrations((data.integrations || []).map((ix: { name: string; connected: boolean; status?: Record<string, unknown> }) => ({ name: ix.name, label: ix.name.charAt(0).toUpperCase() + ix.name.slice(1), enabled: ix.connected, connected: ix.connected, config: {} })));
    } catch (e) { console.warn('[IntegrationSettings] fetch failed', e); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchIntegrations(); }, [fetchIntegrations]);

  if (loading) return <div className="hud-page p-6"><Skeleton /></div>;

  return (
    <motion.div variants={containerVariants} initial="hidden" animate="visible" className="hud-page h-full overflow-y-auto space-y-6 p-6">
      <motion.section variants={itemVariants} className="hud-panel hud-scan-box p-6 md:p-8">
        <div className="hud-label">Configuration</div>
        <h1 className="hud-title mt-2 text-6xl md:text-7xl">Integration <span className="text-[var(--j-sky)]">Settings</span></h1>
        <p className="mt-4 max-w-2xl text-sm leading-7 text-[var(--j-text-dim)]">
          Configure API keys, webhook URLs, and connection parameters for all external services.
        </p>
      </motion.section>

      <motion.section variants={itemVariants}>
        <div className="hud-label mb-4">Service Configuration</div>
        <div className="grid grid-cols-1 gap-px bg-[var(--j-border)]">
          {integrations.map(ix => (
            <motion.div key={ix.name} variants={itemVariants} className="bg-[var(--j-surface)] p-5 transition-colors hover:bg-[var(--j-surface-hover)]">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <div className="font-display text-xl tracking-[0.08em] text-[var(--j-text)]">{ix.label}</div>
                  <div className="mt-1 font-mono text-[10px] uppercase text-[var(--j-text-muted)]">{ix.name}</div>
                </div>
                <Badge variant={ix.connected ? 'new' : 'default'}>{ix.connected ? 'Connected' : 'Disconnected'}</Badge>
              </div>
              {ix.config && Object.keys(ix.config).length > 0 && (
                <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {Object.entries(ix.config).map(([k, v]) => (
                    <div key={k} className="font-mono text-[10px]">
                      <span className="text-[var(--j-text-dim)]">{k}: </span>
                      <span className="text-[var(--j-text)]">{v}</span>
                    </div>
                  ))}
                </div>
              )}
            </motion.div>
          ))}
        </div>
      </motion.section>
    </motion.div>
  );
}
