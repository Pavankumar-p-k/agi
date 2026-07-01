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
  const [error, setError] = useState('');
  const [tokenInputs, setTokenInputs] = useState<Record<string, string>>({});
  const [connecting, setConnecting] = useState<string | null>(null);

  const fetchIntegrations = useCallback(async () => {
    setError('');
    try {
      const data = await api.integrations.list();
      setIntegrations((data.integrations || []).map((ix: { name: string; connected: boolean; status?: Record<string, unknown> }) => ({ name: ix.name, label: ix.name.charAt(0).toUpperCase() + ix.name.slice(1), enabled: ix.connected, connected: ix.connected, config: {} })));
    } catch (e) { console.warn('[IntegrationSettings] fetch failed', e); setError('Failed to load integrations'); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchIntegrations(); }, [fetchIntegrations]);

  const handleConnect = async (name: string) => {
    const token = tokenInputs[name]?.trim();
    if (!token) return;
    setConnecting(name);
    try {
      await api.integrations.connect(name, { token });
      setTokenInputs(prev => ({ ...prev, [name]: '' }));
      await fetchIntegrations();
    } catch (e) {
      setError(`Failed to connect ${name}: ${e instanceof Error ? e.message : 'Unknown error'}`);
    } finally {
      setConnecting(null);
    }
  };

  const handleDisconnect = async (name: string) => {
    setConnecting(name);
    try {
      await api.integrations.disconnect(name);
      await fetchIntegrations();
    } catch (e) {
      setError(`Failed to disconnect ${name}`);
    } finally {
      setConnecting(null);
    }
  };

  const INTEGRATION_HINTS: Record<string, string> = {
    github: 'Paste a Personal Access Token with repo and user permissions.',
    email: 'Configure SMTP settings in environment variables.',
    slack: 'Coming soon.',
  };

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

      {error && (
        <motion.div variants={itemVariants} className="border border-red-500/30 bg-red-500/5 px-5 py-3">
          <p className="text-xs text-red-400">{error}</p>
        </motion.div>
      )}

      <motion.section variants={itemVariants}>
        <div className="hud-label mb-4">Service Configuration</div>
        <div className="grid grid-cols-1 gap-px bg-[var(--j-border)]">
          {integrations.length === 0 && !error && (
            <motion.div variants={itemVariants} className="bg-[var(--j-surface)] p-8 text-center text-sm text-[var(--j-text-dim)]">
              No integrations configured.
            </motion.div>
          )}
          {integrations.map(ix => (
            <motion.div key={ix.name} variants={itemVariants} className="bg-[var(--j-surface)] p-5 transition-colors hover:bg-[var(--j-surface-hover)]">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <div className="font-display text-xl tracking-[0.08em] text-[var(--j-text)]">{ix.label}</div>
                  <div className="mt-1 font-mono text-[10px] uppercase text-[var(--j-text-muted)]">{ix.name}</div>
                </div>
                <div className="flex items-center gap-3">
                  <Badge variant={ix.connected ? 'new' : 'default'}>{ix.connected ? 'Connected' : 'Disconnected'}</Badge>
                  {ix.connected ? (
                    <button
                      onClick={() => handleDisconnect(ix.name)}
                      disabled={connecting === ix.name}
                      className="text-[9px] font-mono uppercase tracking-[0.12em] px-2 py-1 transition-all disabled:opacity-40"
                      style={{ border: '1px solid rgba(255,71,87,0.3)', borderRadius: 'var(--j-radius-sm)', color: '#ff4757' }}
                    >
                      {connecting === ix.name ? '...' : 'Disconnect'}
                    </button>
                  ) : null}
                </div>
              </div>

              {!ix.connected && INTEGRATION_HINTS[ix.name] && (
                <div className="mt-3 space-y-2">
                  <p className="text-[10px]" style={{ color: 'var(--j-text-muted)' }}>
                    {INTEGRATION_HINTS[ix.name]}
                  </p>
                  <div className="flex gap-2">
                    <input
                      type="password"
                      value={tokenInputs[ix.name] || ''}
                      onChange={(e) => setTokenInputs(prev => ({ ...prev, [ix.name]: e.target.value }))}
                      placeholder="Paste token or API key..."
                      className="flex-1 bg-[var(--j-bg)] border border-[var(--j-border)] px-3 py-2 text-sm text-[var(--j-text)] outline-none focus:border-[var(--j-sky)]"
                      onKeyDown={(e) => { if (e.key === 'Enter') handleConnect(ix.name); }}
                    />
                    <button
                      onClick={() => handleConnect(ix.name)}
                      disabled={connecting === ix.name || !tokenInputs[ix.name]?.trim()}
                      className="px-4 py-2 text-[9px] font-mono uppercase tracking-[0.12em] transition-all disabled:opacity-40"
                      style={{
                        border: '1px solid var(--j-sky)',
                        borderRadius: 'var(--j-radius-sm)',
                        color: 'var(--j-sky)',
                        background: 'rgba(var(--j-sky-rgb),0.08)',
                      }}
                    >
                      {connecting === ix.name ? 'Connecting...' : 'Connect'}
                    </button>
                  </div>
                </div>
              )}

              {ix.connected && ix.config && Object.keys(ix.config).length > 0 && (
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
