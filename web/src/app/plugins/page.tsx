'use client';

import { useEffect, useState, useCallback } from 'react';
import { motion, type Variants } from 'framer-motion';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import Pill from '@/components/ui/Pill';
import { Skeleton } from '@/components/ui/Skeleton';
import { api } from '@/lib/api';

interface PluginInfo {
  name: string;
  version: string;
  description: string;
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

export default function PluginsPage() {
  const [plugins, setPlugins] = useState<PluginInfo[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchPlugins = useCallback(async () => {
    try {
      const data = await api.plugins.list();
      setPlugins((data.plugins || []).map(p => ({ name: p.name, version: p.version, description: p.description, enabled: p.enabled !== undefined ? p.enabled : true })));
    } catch (e) { console.warn('[Plugins] fetch failed', e); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchPlugins(); }, [fetchPlugins]);

  const togglePlugin = async (name: string, enabled: boolean) => {
    try {
      await api.plugins.toggle(name);
      setPlugins(prev => prev.map(p => p.name === name ? { ...p, enabled: !enabled } : p));
    } catch (e) { console.warn('[Plugins] toggle failed', e); }
  };

  if (loading) return <div className="hud-page p-6"><Skeleton /></div>;

  return (
    <motion.div variants={containerVariants} initial="hidden" animate="visible" className="hud-page h-full overflow-y-auto space-y-6 p-6">
      <motion.section variants={itemVariants} className="hud-panel hud-scan-box p-6 md:p-8">
        <div className="hud-label">Extensions</div>
        <h1 className="hud-title mt-2 text-6xl md:text-7xl">Plugins <span className="text-[var(--j-sky)]">Manager</span></h1>
        <p className="mt-4 max-w-2xl text-sm leading-7 text-[var(--j-text-dim)]">
          Third-party extensions, protocol handlers, and middleware modules extending JARVIS capabilities.
        </p>
        <div className="mt-6 flex gap-2">
          <Badge variant="new">{plugins.length} plugins</Badge>
        </div>
      </motion.section>

      <motion.section variants={itemVariants}>
        <div className="hud-label mb-4">Installed Plugins</div>
        <div className="grid grid-cols-1 gap-px bg-[var(--j-border)] md:grid-cols-2 xl:grid-cols-3">
          {plugins.map(p => (
            <motion.div key={p.name} variants={itemVariants} className="bg-[var(--j-surface)] p-5 transition-colors hover:bg-[var(--j-surface-hover)]">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-display text-xl tracking-[0.08em] text-[var(--j-text)]">{p.name}</div>
                  <div className="mt-1 font-mono text-[10px] text-[var(--j-text-muted)]">v{p.version}</div>
                </div>
                <button
                  onClick={() => togglePlugin(p.name, p.enabled)}
                  className={`relative h-6 w-12 border flex-shrink-0 ${p.enabled ? 'border-[var(--j-sky)]' : 'border-[var(--j-border)]'}`}
                  style={{ background: p.enabled ? 'rgba(56,189,248,0.15)' : 'var(--j-bg)' }}
                >
                  <span
                    className="absolute top-1 h-4 w-4 transition-all"
                    style={{
                      left: p.enabled ? '26px' : '4px',
                      background: p.enabled ? 'var(--j-sky)' : 'var(--j-text-muted)',
                      boxShadow: p.enabled ? '0 0 12px var(--j-sky)' : 'none',
                    }}
                  />
                </button>
              </div>
              <p className="mt-3 text-xs leading-6 text-[var(--j-text-dim)]">{p.description}</p>
            </motion.div>
          ))}
          {plugins.length === 0 && (
            <div className="col-span-full bg-[var(--j-surface)] p-8 text-center text-sm text-[var(--j-text-dim)]">
              No plugins installed.
            </div>
          )}
        </div>
      </motion.section>
    </motion.div>
  );
}
