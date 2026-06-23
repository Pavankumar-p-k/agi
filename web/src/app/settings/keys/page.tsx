'use client';

import { useEffect, useState, useCallback } from 'react';
import { motion, type Variants } from 'framer-motion';
import Badge from '@/components/ui/Badge';
import Button from '@/components/ui/Button';
import { Skeleton } from '@/components/ui/Skeleton';
import { api, type Setting } from '@/lib/api';

const containerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.06, delayChildren: 0.08 } },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 28 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.62, ease: [0.16, 1, 0.3, 1] } },
};

export default function ApiKeysPage() {
  const [keys, setKeys] = useState<Setting[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchKeys = useCallback(async () => {
    try {
      const s = await api.settings.list();
      setKeys(s.filter(item => item.key.includes('api_key') || item.key.includes('token')));
    } catch (e) {
      console.warn('[ApiKeys] fetch failed', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchKeys(); }, [fetchKeys]);

  const updateKey = async (key: string, value: string) => {
    try {
      await api.settings.update(key, value);
      setKeys(prev => prev.map(k => k.key === key ? { ...k, value } : k));
    } catch (e) {
      alert('Failed to update key: ' + e);
    }
  };

  if (loading) return <div className="hud-page p-6"><Skeleton /></div>;

  return (
    <motion.div variants={containerVariants} initial="hidden" animate="visible" className="hud-page h-full overflow-y-auto space-y-6 p-6">
      <motion.section variants={itemVariants} className="hud-panel hud-scan-box p-6 md:p-8">
        <div className="hud-label">Security Vault</div>
        <h1 className="hud-title mt-2 text-6xl md:text-7xl">API <span className="text-[var(--j-sky)]">Keys</span></h1>
        <p className="mt-4 max-w-2xl text-sm leading-7 text-[var(--j-text-dim)]">
          Manage credentials for AI providers and external integrations. Keys are stored securely in the backend vault.
        </p>
      </motion.section>

      <motion.section variants={itemVariants}>
        <div className="hud-label mb-4">Credentials</div>
        <div className="grid grid-cols-1 gap-px bg-[var(--j-border)]">
          {keys.map(k => (
            <div key={k.key} className="bg-[var(--j-surface)] p-5 space-y-3">
              <div className="flex items-center justify-between">
                <div className="font-mono text-xs uppercase tracking-widest text-[var(--j-text-muted)]">{k.key.replace(/\./g, ' / ')}</div>
                <Badge variant={k.value ? 'new' : 'default'}>{k.value ? 'Set' : 'Missing'}</Badge>
              </div>
              <div className="flex gap-2">
                <input
                  type="password"
                  defaultValue={String(k.value || '')}
                  placeholder="Enter key..."
                  className="flex-1 bg-[var(--j-bg)] border border-[var(--j-border)] px-3 py-2 text-sm text-[var(--j-text)] outline-none focus:border-[var(--j-sky)]"
                  onBlur={(e) => {
                    if (e.target.value !== k.value) updateKey(k.key, e.target.value);
                  }}
                />
              </div>
            </div>
          ))}
          {keys.length === 0 && (
            <div className="bg-[var(--j-surface)] p-12 text-center text-xs text-[var(--j-text-dim)]">
              No API key settings found in configuration.
            </div>
          )}
        </div>
      </motion.section>
    </motion.div>
  );
}
