'use client';

import { useEffect, useState, useCallback } from 'react';
import { motion, type Variants } from 'framer-motion';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import { Skeleton } from '@/components/ui/Skeleton';
import { api } from '@/lib/api';

interface JobInfo {
  id: string;
  name: string;
  schedule: string;
  status: string;
  last_run: string | null;
  next_run: string | null;
}

const containerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.06, delayChildren: 0.08 } },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 28 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.62, ease: [0.16, 1, 0.3, 1] } },
};

export default function AutomationPage() {
  const [jobs, setJobs] = useState<JobInfo[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchJobs = useCallback(async () => {
    try {
      const data = await api.automation.jobs();
      setJobs((data.jobs || []).map((j: { id: string; name?: string; schedule?: string; status?: string; last_run?: string | null; next_run?: string | null }) => ({ id: j.id, name: j.name || j.id, schedule: j.schedule || '', status: j.status || 'unknown', last_run: j.last_run || null, next_run: j.next_run || null })));
    } catch (e) { console.warn('[Automation] fetch failed', e); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchJobs(); }, [fetchJobs]);

  if (loading) return <div className="hud-page p-6"><Skeleton /></div>;

  return (
    <motion.div variants={containerVariants} initial="hidden" animate="visible" className="hud-page h-full overflow-y-auto space-y-6 p-6">
      <motion.section variants={itemVariants} className="hud-panel hud-scan-box p-6 md:p-8">
        <div className="hud-label">Task Orchestrator</div>
        <h1 className="hud-title mt-2 text-6xl md:text-7xl">Automation <span className="text-[var(--j-sky)]">Dashboard</span></h1>
        <p className="mt-4 max-w-2xl text-sm leading-7 text-[var(--j-text-dim)]">
          Scheduled jobs, cron triggers, recurring tasks, and background automation pipelines.
        </p>
        <div className="mt-6 flex gap-2">
          <Badge variant="new">{jobs.length} jobs</Badge>
        </div>
      </motion.section>

      <motion.section variants={itemVariants}>
        <div className="hud-label mb-4">Scheduled Jobs</div>
        <div className="grid grid-cols-1 gap-px bg-[var(--j-border)]">
          {jobs.map(j => (
            <motion.div key={j.id} variants={itemVariants} className="bg-[var(--j-surface)] p-5 transition-colors hover:bg-[var(--j-surface-hover)]">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <div className="font-display text-xl tracking-[0.08em] text-[var(--j-text)]">{j.name}</div>
                  <div className="mt-1 font-mono text-xs text-[var(--j-text-dim)]">{j.schedule}</div>
                </div>
                <Badge variant={j.status === 'active' ? 'new' : 'default'}>{j.status}</Badge>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-4 font-mono text-[10px] uppercase tracking-[0.12em] text-[var(--j-text-muted)]">
                <div>Last Run: <span className="text-[var(--j-text-dim)]">{j.last_run || 'never'}</span></div>
                <div>Next Run: <span className="text-[var(--j-sky)]">{j.next_run || 'unscheduled'}</span></div>
              </div>
            </motion.div>
          ))}
          {jobs.length === 0 && (
            <div className="bg-[var(--j-surface)] p-8 text-center text-sm text-[var(--j-text-dim)]">
              No scheduled jobs. Create one via the CLI or API.
            </div>
          )}
        </div>
      </motion.section>
    </motion.div>
  );
}
