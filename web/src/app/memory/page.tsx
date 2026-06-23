'use client';

import { useEffect, useState, useCallback } from 'react';
import { motion, type Variants } from 'framer-motion';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import { Skeleton } from '@/components/ui/Skeleton';
import { api } from '@/lib/api';

interface MemoryStats {
  total_entries: number;
  vector_count: number;
  episodic_count: number;
  semantic_count: number;
  last_updated: string | null;
}

interface MemoryEntry {
  id: string;
  type: string;
  summary: string;
  timestamp: string;
}

const containerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.06, delayChildren: 0.08 } },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 28 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.62, ease: [0.16, 1, 0.3, 1] } },
};

export default function MemoryPage() {
  const [stats, setStats] = useState<MemoryStats | null>(null);
  const [entries, setEntries] = useState<MemoryEntry[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchAll = useCallback(async () => {
    try {
      const [s, e] = await Promise.all([
        api.memory.stats().catch(() => null),
        api.memory.list().catch(() => []),
      ]);
      if (s) setStats(s as unknown as MemoryStats);
      if (e && e.length > 0) setEntries(e.map((item: { id: string; type?: string; content?: string; timestamp?: string }) => ({ id: item.id, type: item.type || 'memory', summary: item.content || '', timestamp: item.timestamp || '' })));
    } catch (e) { console.warn('[Memory] fetch failed', e); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  if (loading) return <div className="hud-page p-6"><Skeleton /></div>;

  return (
    <motion.div variants={containerVariants} initial="hidden" animate="visible" className="hud-page h-full overflow-y-auto space-y-6 p-6">
      <motion.section variants={itemVariants} className="hud-panel hud-scan-box p-6 md:p-8">
        <div className="hud-label">Knowledge Store</div>
        <h1 className="hud-title mt-2 text-6xl md:text-7xl">Memory <span className="text-[var(--j-sky)]">Dashboard</span></h1>
        <p className="mt-4 max-w-2xl text-sm leading-7 text-[var(--j-text-dim)]">
          Vector, episodic, and semantic memory stores powering context-aware interactions.
        </p>
      </motion.section>

      {stats && (
        <motion.section variants={itemVariants}>
          <div className="hud-label mb-4">Storage Overview</div>
          <div className="grid grid-cols-2 gap-px bg-[var(--j-border)] md:grid-cols-4">
            <StatBlock label="Total Entries" value={String(stats.total_entries)} />
            <StatBlock label="Vector Store" value={String(stats.vector_count)} />
            <StatBlock label="Episodic" value={String(stats.episodic_count)} />
            <StatBlock label="Semantic" value={String(stats.semantic_count)} />
          </div>
        </motion.section>
      )}

      <motion.section variants={itemVariants}>
        <div className="hud-label mb-4">Recent Entries</div>
        <div className="grid grid-cols-1 gap-px bg-[var(--j-border)]">
          {entries.map(e => (
            <motion.div key={e.id} variants={itemVariants} className="bg-[var(--j-surface)] p-5 transition-colors hover:bg-[var(--j-surface-hover)]">
              <div className="flex items-center justify-between gap-4">
                <div className="font-display text-lg tracking-[0.08em] text-[var(--j-text)]">{e.summary}</div>
                <Badge variant={e.type === 'vector' ? 'new' : 'default'}>{e.type}</Badge>
              </div>
              <div className="mt-2 font-mono text-[10px] text-[var(--j-text-muted)]">{e.timestamp}</div>
            </motion.div>
          ))}
          {entries.length === 0 && (
            <div className="bg-[var(--j-surface)] p-8 text-center text-sm text-[var(--j-text-dim)]">
              No memory entries yet.
            </div>
          )}
        </div>
      </motion.section>
    </motion.div>
  );
}

function StatBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-[var(--j-surface)] p-5 text-center">
      <div className="font-display text-3xl tracking-[0.08em] text-[var(--j-sky)]">{value}</div>
      <div className="mt-2 font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--j-text-muted)]">{label}</div>
    </div>
  );
}
