'use client';

import { useEffect, useState, useCallback } from 'react';
import { motion, type Variants } from 'framer-motion';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import Pill from '@/components/ui/Pill';
import { Skeleton } from '@/components/ui/Skeleton';
import { api } from '@/lib/api';

interface ProjectInfo {
  name: string;
  path: string;
  type: string;
  last_modified: string | null;
}

const containerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.06, delayChildren: 0.08 } },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 28 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.62, ease: [0.16, 1, 0.3, 1] } },
};

export default function ProjectsPage() {
  const [projects, setProjects] = useState<ProjectInfo[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchProjects = useCallback(async () => {
    try {
      const data = await api.projects.list();
      setProjects((data.projects || []).map((p: { id: string; name: string; status?: string; description?: string }) => ({ name: p.name, path: p.id, type: p.status || 'active', last_modified: null })));
    } catch (e) { console.warn('[Projects] fetch failed', e); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchProjects(); }, [fetchProjects]);

  if (loading) return <div className="hud-page p-6"><Skeleton /></div>;

  return (
    <motion.div variants={containerVariants} initial="hidden" animate="visible" className="hud-page h-full overflow-y-auto space-y-6 p-6">
      <motion.section variants={itemVariants} className="hud-panel hud-scan-box p-6 md:p-8">
        <div className="hud-label">Workspace</div>
        <h1 className="hud-title mt-2 text-6xl md:text-7xl">Projects <span className="text-[var(--j-sky)]">Dashboard</span></h1>
        <p className="mt-4 max-w-2xl text-sm leading-7 text-[var(--j-text-dim)]">
          Manage development projects, generated artifacts, and workspace directories.
        </p>
        <div className="mt-6 flex gap-2">
          <Badge variant="new">{projects.length} projects</Badge>
        </div>
      </motion.section>

      <motion.section variants={itemVariants}>
        <div className="hud-label mb-4">All Projects</div>
        <div className="grid grid-cols-1 gap-px bg-[var(--j-border)] md:grid-cols-2 xl:grid-cols-3">
          {projects.map(p => (
            <motion.div key={p.name} variants={itemVariants} className="bg-[var(--j-surface)] p-5 transition-colors hover:bg-[var(--j-surface-hover)]">
              <div className="font-display text-xl tracking-[0.08em] text-[var(--j-text)]">{p.name}</div>
              <div className="mt-2 font-mono text-[10px] text-[var(--j-text-dim)]">{p.path}</div>
              <div className="mt-4 flex items-center justify-between">
                <Pill>{p.type}</Pill>
                <span className="font-mono text-[10px] text-[var(--j-text-muted)]">{p.last_modified || 'unknown'}</span>
              </div>
            </motion.div>
          ))}
          {projects.length === 0 && (
            <div className="col-span-full bg-[var(--j-surface)] p-8 text-center text-sm text-[var(--j-text-dim)]">
              No projects yet.
            </div>
          )}
        </div>
      </motion.section>
    </motion.div>
  );
}
