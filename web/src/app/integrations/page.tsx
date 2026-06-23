'use client';

import { useEffect, useState, useCallback } from 'react';
import { motion, type Variants } from 'framer-motion';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import Pill from '@/components/ui/Pill';
import Button from '@/components/ui/Button';
import { Skeleton } from '@/components/ui/Skeleton';
import { api } from '@/lib/api';

interface IntegrationInfo {
  name: string;
  enabled: boolean;
  connected: boolean;
  label: string;
}

const containerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.06, delayChildren: 0.08 } },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 28 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.62, ease: [0.16, 1, 0.3, 1] } },
};

export default function IntegrationsPage() {
  const [integrations, setIntegrations] = useState<IntegrationInfo[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchIntegrations = useCallback(async () => {
    try {
      const data = await api.integrations.list();
      setIntegrations((data.integrations || []).map((ix: { name: string; connected: boolean; status?: Record<string, unknown> }) => ({ name: ix.name, enabled: ix.connected, connected: ix.connected, label: ix.name.charAt(0).toUpperCase() + ix.name.slice(1) })));
    } catch (e) { console.warn('[Integrations] fetch failed', e); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchIntegrations(); }, [fetchIntegrations]);

  const connectIntegration = async (name: string) => {
    try {
      await api.integrations.connect(name);
      setIntegrations(prev => prev.map(i => i.name === name ? { ...i, connected: true } : i));
    } catch (e) { console.warn('[Integrations] connect failed', e); }
  };

  if (loading) return <div className="hud-page p-6"><Skeleton /></div>;

  return (
    <motion.div variants={containerVariants} initial="hidden" animate="visible" className="hud-page h-full overflow-y-auto space-y-6 p-6">
      <motion.section variants={itemVariants} className="hud-panel hud-scan-box p-6 md:p-8">
        <div className="hud-label">External Services</div>
        <h1 className="hud-title mt-2 text-6xl md:text-7xl">Integrations <span className="text-[var(--j-sky)]">Dashboard</span></h1>
        <p className="mt-4 max-w-2xl text-sm leading-7 text-[var(--j-text-dim)]">
          Connect JARVIS to Gmail, Telegram, WhatsApp, Discord, Slack, GitHub, and Google Drive.
        </p>
      </motion.section>

      <motion.section variants={itemVariants}>
        <div className="hud-label mb-4">Connected Services</div>
        <div className="grid grid-cols-1 gap-px bg-[var(--j-border)] md:grid-cols-2 xl:grid-cols-3">
          {integrations.map(ix => (
            <motion.div key={ix.name} variants={itemVariants} className="bg-[var(--j-surface)] p-5 transition-colors hover:bg-[var(--j-surface-hover)]">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-display text-xl tracking-[0.08em] text-[var(--j-text)]">{ix.label}</div>
                  <div className="mt-1 font-mono text-[10px] uppercase text-[var(--j-text-muted)]">{ix.name}</div>
                </div>
                <Badge variant={ix.connected ? 'new' : 'default'}>{ix.connected ? 'Connected' : 'Disconnected'}</Badge>
              </div>
              <div className="mt-4">
                {!ix.connected && (
                  <Button variant="primary" size="sm" onClick={() => connectIntegration(ix.name)}>Connect</Button>
                )}
                {ix.connected && (
                  <Pill>Active</Pill>
                )}
              </div>
            </motion.div>
          ))}
          {integrations.length === 0 && (
            <div className="col-span-full bg-[var(--j-surface)] p-8 text-center text-sm text-[var(--j-text-dim)]">
              No integrations configured.
            </div>
          )}
        </div>
      </motion.section>
    </motion.div>
  );
}
