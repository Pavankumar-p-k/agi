'use client';

import { useEffect, useState, useCallback } from 'react';
import { motion, type Variants } from 'framer-motion';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import Pill from '@/components/ui/Pill';
import { Skeleton } from '@/components/ui/Skeleton';
import { api } from '@/lib/api';

interface AgentInfo {
  id: string;
  name: string;
  description: string;
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

export default function AgentsPage() {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchAgents = useCallback(async () => {
    setError('');
    try {
      const data = await api.agents.list();
      setAgents((data.agents || []).map((a: { name: string; status?: string; description?: string }) => ({ id: a.name, name: a.name, description: a.description || '', status: a.status || 'idle', type: 'agent' })));
    } catch (e) { console.warn('[Agents] fetch failed', e); setError('Failed to load agents'); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchAgents(); }, [fetchAgents]);

  if (loading) return <div className="hud-page p-6"><Skeleton /></div>;

  return (
    <motion.div variants={containerVariants} initial="hidden" animate="visible" className="hud-page h-full overflow-y-auto space-y-6 p-6">
      <motion.section variants={itemVariants} className="hud-panel hud-scan-box p-6 md:p-8">
        <div className="hud-label">Autonomous Units</div>
        <h1 className="hud-title mt-2 text-6xl md:text-7xl">Sub-Agent <span className="text-[var(--j-sky)]">Dashboard</span></h1>
        <p className="mt-4 max-w-2xl text-sm leading-7 text-[var(--j-text-dim)]">
          Deploy, monitor, and manage JARVIS sub-agents. Each agent handles a specialized domain.
        </p>
      </motion.section>

      {error && (
        <motion.div variants={itemVariants} className="border border-red-500/30 bg-red-500/5 px-5 py-3">
          <p className="text-xs text-red-400">{error}</p>
        </motion.div>
      )}

      <motion.section variants={itemVariants}>
        <div className="hud-label mb-4">Deployed Agents</div>
        <div className="grid grid-cols-1 gap-px bg-[var(--j-border)] md:grid-cols-2 xl:grid-cols-3">
          {agents.map(a => (
            <motion.div key={a.id} variants={itemVariants} className="bg-[var(--j-surface)] p-5 transition-colors hover:bg-[var(--j-surface-hover)]">
              <div className="flex items-start justify-between gap-3">
                <div className="font-display text-xl tracking-[0.08em] text-[var(--j-text)]">{a.name}</div>
                <Badge variant={a.status === 'active' ? 'new' : a.status === 'idle' ? 'default' : 'hot'}>{a.status}</Badge>
              </div>
              <p className="mt-3 text-xs leading-6 text-[var(--j-text-dim)]">{a.description}</p>
              <div className="mt-4 flex gap-2">
                <Pill>{a.type}</Pill>
              </div>
            </motion.div>
          ))}
          {agents.length === 0 && (
            <div className="col-span-full bg-[var(--j-surface)] p-8 text-center text-sm text-[var(--j-text-dim)]">
              No agents deployed. Create one from the CLI or API.
            </div>
          )}
        </div>
      </motion.section>
    </motion.div>
  );
}
