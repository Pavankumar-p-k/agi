'use client';

import { useEffect, useState, useCallback } from 'react';
import { motion, type Variants } from 'framer-motion';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import Pill from '@/components/ui/Pill';
import { Skeleton } from '@/components/ui/Skeleton';
import { api } from '@/lib/api';

interface Feature {
  name: string;
  enabled: boolean;
  category: string;
  description: string;
}

const containerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.06, delayChildren: 0.08 } },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 28 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.62, ease: [0.16, 1, 0.3, 1] } },
};

export default function FeaturesPage() {
  const [features, setFeatures] = useState<Feature[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchFeatures = useCallback(async () => {
    try {
      const data = await api.features.list();
      setFeatures((data.features || []).map((f: { name: string; enabled: boolean; category: string; description: string }) => ({ name: f.name, enabled: f.enabled, category: f.category, description: f.description })));
      setError(null);
    } catch (e) {
      console.warn('[Features] fetch failed', e);
      setError('Failed to load features');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchFeatures(); }, [fetchFeatures]);

  const toggleFeature = async (name: string, enabled: boolean) => {
    try {
      await api.features.toggle(name, !enabled);
      setFeatures(prev => prev.map(f => f.name === name ? { ...f, enabled: !enabled } : f));
    } catch (e) { console.warn('[Features] toggle failed', e); }
  };

  const categories = [...new Set(features.map(f => f.category))];

  if (loading) return <div className="hud-page p-6"><Skeleton /></div>;

  return (
    <motion.div variants={containerVariants} initial="hidden" animate="visible" className="hud-page h-full overflow-y-auto space-y-6 p-6">
      <motion.section variants={itemVariants} className="hud-panel hud-scan-box p-6 md:p-8">
        <div className="hud-label">Control Matrix</div>
        <h1 className="hud-title mt-2 text-6xl md:text-7xl">Feature <span className="text-[var(--j-sky)]">Registry</span></h1>
        <p className="mt-4 max-w-2xl text-sm leading-7 text-[var(--j-text-dim)]">
          Inspect and toggle every platform capability. Each feature maps to a backend module, route, or integration.
        </p>
        <div className="mt-6 flex flex-wrap gap-2">
          <Badge variant="new">{features.length} features</Badge>
          <Badge variant="default">{categories.length} categories</Badge>
        </div>
      </motion.section>

      {error && (
        <motion.div variants={itemVariants} className="border border-[var(--j-gold)] bg-[rgba(var(--j-gold-rgb),0.08)] p-4 text-sm text-[var(--j-gold)]">
          {error}
        </motion.div>
      )}

      {features.length === 0 && !error && (
        <motion.div variants={itemVariants} className="bg-[var(--j-surface)] p-8 text-center text-sm text-[var(--j-text-dim)]">
          No features registered.
        </motion.div>
      )}

      {categories.map(cat => (
        <motion.section key={cat} variants={itemVariants}>
          <div className="hud-label mb-4 flex items-center gap-3 before:h-px before:w-6 before:bg-[var(--j-sky)]">{cat}</div>
          <div className="grid grid-cols-1 gap-px bg-[var(--j-border)] md:grid-cols-2 xl:grid-cols-3">
            {features.filter(f => f.category === cat).map(f => (
              <motion.div key={f.name} variants={itemVariants} className="bg-[var(--j-surface)] p-5 transition-colors hover:bg-[var(--j-surface-hover)]">
                <div className="flex items-start justify-between gap-3">
                  <div className="font-display text-xl tracking-[0.08em] text-[var(--j-text)]">{f.name}</div>
                  <button
                    onClick={() => toggleFeature(f.name, f.enabled)}
                    className={`relative h-6 w-12 border flex-shrink-0 ${f.enabled ? 'border-[var(--j-sky)]' : 'border-[var(--j-border)]'}`}
                    style={{ background: f.enabled ? 'rgba(56,189,248,0.15)' : 'var(--j-bg)' }}
                  >
                    <span
                      className="absolute top-1 h-4 w-4 transition-all"
                      style={{
                        left: f.enabled ? '26px' : '4px',
                        background: f.enabled ? 'var(--j-sky)' : 'var(--j-text-muted)',
                        boxShadow: f.enabled ? '0 0 12px var(--j-sky)' : 'none',
                      }}
                    />
                  </button>
                </div>
                <p className="mt-3 text-xs leading-6 text-[var(--j-text-dim)]">{f.description}</p>
                <div className="mt-4 flex items-center gap-2">
                  <Pill>{f.enabled ? 'Active' : 'Disabled'}</Pill>
                </div>
              </motion.div>
            ))}
          </div>
        </motion.section>
      ))}
    </motion.div>
  );
}
