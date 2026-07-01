'use client';

import { useEffect, useState, useCallback } from 'react';
import { motion, type Variants } from 'framer-motion';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import Pill from '@/components/ui/Pill';
import { Skeleton } from '@/components/ui/Skeleton';
import { api } from '@/lib/api';

interface SkillInfo {
  name: string;
  description: string;
  version: string;
  enabled: boolean;
  triggers: string[];
}

const containerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.06, delayChildren: 0.08 } },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 28 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.62, ease: [0.16, 1, 0.3, 1] } },
};

export default function SkillsPage() {
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchSkills = useCallback(async () => {
    setError('');
    try {
      const data = await api.skills.list();
      setSkills(data.skills.map(s => ({ ...s, version: '1.0', triggers: [] })) || []);
    } catch (e) { console.warn('[Skills] fetch failed', e); setError('Failed to load skills'); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchSkills(); }, [fetchSkills]);

  const toggleSkill = async (name: string, enabled: boolean) => {
    try {
      await api.skills.toggle(name);
      setSkills(prev => prev.map(s => s.name === name ? { ...s, enabled: !enabled } : s));
    } catch (e) { console.warn('[Skills] toggle failed', e); setError(`Failed to toggle ${name}`); }
  };

  if (loading) return <div className="hud-page p-6"><Skeleton /></div>;

  return (
    <motion.div variants={containerVariants} initial="hidden" animate="visible" className="hud-page h-full overflow-y-auto space-y-6 p-6">
      <motion.section variants={itemVariants} className="hud-panel hud-scan-box p-6 md:p-8">
        <div className="hud-label">Capability Modules</div>
        <h1 className="hud-title mt-2 text-6xl md:text-7xl">Skills <span className="text-[var(--j-sky)]">Manager</span></h1>
        <p className="mt-4 max-w-2xl text-sm leading-7 text-[var(--j-text-dim)]">
          Load, enable, and inspect specialized skill modules. Skills are markdown-defined capabilities with Python handlers.
        </p>
        <div className="mt-6 flex gap-2">
          <Badge variant="new">{skills.length} installed</Badge>
        </div>
      </motion.section>

      {error && (
        <motion.div variants={itemVariants} className="border border-red-500/30 bg-red-500/5 px-5 py-3">
          <p className="text-xs text-red-400">{error}</p>
        </motion.div>
      )}

      <motion.section variants={itemVariants}>
        <div className="hud-label mb-4">Installed Skills</div>
        <div className="grid grid-cols-1 gap-px bg-[var(--j-border)] md:grid-cols-2 xl:grid-cols-3">
          {skills.map(s => (
            <motion.div key={s.name} variants={itemVariants} className="bg-[var(--j-surface)] p-5 transition-colors hover:bg-[var(--j-surface-hover)]">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-display text-xl tracking-[0.08em] text-[var(--j-text)]">{s.name}</div>
                  <div className="mt-1 font-mono text-[10px] text-[var(--j-text-muted)]">v{s.version}</div>
                </div>
                <button
                  onClick={() => toggleSkill(s.name, s.enabled)}
                  className={`relative h-6 w-12 border flex-shrink-0 ${s.enabled ? 'border-[var(--j-sky)]' : 'border-[var(--j-border)]'}`}
                  style={{ background: s.enabled ? 'rgba(56,189,248,0.15)' : 'var(--j-bg)' }}
                >
                  <span
                    className="absolute top-1 h-4 w-4 transition-all"
                    style={{
                      left: s.enabled ? '26px' : '4px',
                      background: s.enabled ? 'var(--j-sky)' : 'var(--j-text-muted)',
                      boxShadow: s.enabled ? '0 0 12px var(--j-sky)' : 'none',
                    }}
                  />
                </button>
              </div>
              <p className="mt-3 text-xs leading-6 text-[var(--j-text-dim)]">{s.description}</p>
              {s.triggers?.length > 0 && (
                <div className="mt-4 flex flex-wrap gap-1.5">
                  {s.triggers.map(t => <Pill key={t}>{t}</Pill>)}
                </div>
              )}
            </motion.div>
          ))}
          {skills.length === 0 && (
            <div className="col-span-full bg-[var(--j-surface)] p-8 text-center text-sm text-[var(--j-text-dim)]">
              No skills installed.
            </div>
          )}
        </div>
      </motion.section>
    </motion.div>
  );
}
