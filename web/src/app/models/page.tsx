'use client';

import { useEffect, useState, useCallback } from 'react';
import { motion, type Variants } from 'framer-motion';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import Pill from '@/components/ui/Pill';
import { Skeleton } from '@/components/ui/Skeleton';
import { api } from '@/lib/api';

interface ModelInfo {
  id: string;
  name: string;
  provider: string;
  status: string;
  type: string;
}

const containerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.06, delayChildren: 0.08 } },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 28 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.62, ease: [0.16, 1, 0.3, 1] } },
};

export default function ModelsPage() {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchModels = useCallback(async () => {
    try {
      const data = await api.models.list();
      setModels((data.models || []).map((m: { id: string; name: string; provider: string; size?: string }) => ({ id: m.id, name: m.name, provider: m.provider, status: 'ready', type: m.size || 'local' })));
    } catch (e) { console.warn('[Models] fetch failed', e); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchModels(); }, [fetchModels]);

  if (loading) return <div className="hud-page p-6"><Skeleton /></div>;

  return (
    <motion.div variants={containerVariants} initial="hidden" animate="visible" className="hud-page h-full overflow-y-auto space-y-6 p-6">
      <motion.section variants={itemVariants} className="hud-panel hud-scan-box p-6 md:p-8">
        <div className="hud-label">Inference Engine</div>
        <h1 className="hud-title mt-2 text-6xl md:text-7xl">Model <span className="text-[var(--j-sky)]">Management</span></h1>
        <p className="mt-4 max-w-2xl text-sm leading-7 text-[var(--j-text-dim)]">
          Local, cloud, and hybrid model configurations. Assign providers, set priority, and toggle per-task routing.
        </p>
      </motion.section>

      <motion.section variants={itemVariants}>
        <div className="hud-label mb-4 flex items-center gap-3 before:h-px before:w-6 before:bg-[var(--j-sky)]">Available Models</div>
        <div className="grid grid-cols-1 gap-px bg-[var(--j-border)] md:grid-cols-2 xl:grid-cols-3">
          {models.map(m => (
            <motion.div key={m.id} variants={itemVariants} className="bg-[var(--j-surface)] p-5 transition-colors hover:bg-[var(--j-surface-hover)]">
              <div className="flex items-start justify-between">
                <div className="font-display text-xl tracking-[0.08em] text-[var(--j-text)]">{m.name}</div>
                <Badge variant={m.status === 'ready' ? 'new' : 'default'}>{m.status}</Badge>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <Pill>{m.provider}</Pill>
                <Pill>{m.type}</Pill>
              </div>
            </motion.div>
          ))}
          {models.length === 0 && (
            <div className="col-span-full bg-[var(--j-surface)] p-8 text-center text-sm text-[var(--j-text-dim)]">
              No models found. Configure providers in Settings.
            </div>
          )}
        </div>
      </motion.section>
    </motion.div>
  );
}
