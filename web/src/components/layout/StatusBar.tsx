'use client';

import { useEffect, useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import { api } from '@/lib/api';

type HealthDot = 'green' | 'red' | 'yellow';

export default function StatusBar() {
  const [time, setTime] = useState('');
  const [status, setStatus] = useState<'online' | 'offline'>('offline');
  const [stats, setStats] = useState<{ cpu?: number; mem?: number }>({});
  const [diagnostics, setDiagnostics] = useState<{
    ollama?: boolean;
    db?: boolean;
    integrations?: boolean;
    openai?: boolean;
    gemini?: boolean;
  }>({});

  useEffect(() => {
    const t = setInterval(() => {
      setTime(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
    }, 10000);
    return () => clearInterval(t);
  }, []);

  const fetchAll = useCallback(async () => {
    const withTimeout = <T,>(promise: Promise<T>, ms: number): Promise<T> =>
      Promise.race([
        promise,
        new Promise<never>((_, reject) => setTimeout(() => reject(new Error('timeout')), ms)),
      ]);

    await Promise.allSettled([
      (async () => {
        try {
          const s = await withTimeout(api.system.stats(), 4000);
          setStats({ cpu: s.cpu.percent, mem: s.memory.percent });
          setStatus('online');
        } catch { setStatus('offline'); }
      })(),
      (async () => {
        try {
          const d = await withTimeout(api.diagnostics.environment(), 6000);
          setDiagnostics(prev => ({ ...prev, ollama: d.ollama_available }));
        } catch {}
      })(),
      (async () => {
        try {
          const h = await withTimeout(api.health(), 4000);
          setDiagnostics(prev => ({ ...prev, db: h.status === 'healthy' }));
        } catch {}
      })(),
      (async () => {
        try {
          const m = await withTimeout(api.diagnostics.models(), 6000);
          const openai = m.providers.find(p => p.name === 'openai')?.available;
          const gemini = m.providers.find(p => p.name === 'gemini')?.available;
          setDiagnostics(prev => ({ ...prev, openai, gemini }));
        } catch {}
      })(),
      (async () => {
        try {
          const i = await withTimeout(api.diagnostics.integrations(), 6000);
          const someConnected = i.integrations.some(ix => ix.connected);
          setDiagnostics(prev => ({ ...prev, integrations: someConnected }));
        } catch {}
      })(),
    ]);
  }, []);

  useEffect(() => {
    fetchAll();
    const t = setInterval(fetchAll, 15000);
    return () => clearInterval(t);
  }, [fetchAll]);

  const dots: { label: string; color: HealthDot }[] = [
    { label: 'BE', color: status === 'online' ? 'green' : 'red' },
    { label: 'DB', color: diagnostics.db ? 'green' : 'red' },
    { label: 'OL', color: diagnostics.ollama ? 'green' : 'red' },
    { label: 'GPT', color: diagnostics.openai ? 'green' : 'red' },
    { label: 'GEM', color: diagnostics.gemini ? 'green' : 'red' },
    { label: 'INT', color: diagnostics.integrations ? 'green' : 'red' },
  ];

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, delay: 0.1 }}
      role="status"
      aria-label="System status"
      className="h-7 border-t flex items-center justify-between px-3 text-[10px] shrink-0 font-mono uppercase tracking-[0.12em]"
      style={{
        background: 'rgba(var(--j-bg-rgb), 0.76)',
        backdropFilter: 'blur(14px)',
        borderColor: 'var(--j-border)',
        color: 'var(--j-text-dim)',
      }}
    >
      <div className="flex items-center gap-1 sm:gap-3 overflow-hidden">
        <div className="hidden sm:flex items-center gap-3" role="list" aria-label="Service health">
          {dots.map(d => (
            <span key={d.label} role="listitem" className="flex items-center gap-1">
              <span className={`inline-block w-1.5 h-1.5 rounded-full bg-${d.color === 'green' ? 'green' : d.color === 'red' ? 'red' : 'yellow'}-400`} aria-hidden="true" />
              <span className="sr-only">{d.label} {d.color === 'green' ? 'healthy' : 'unhealthy'}</span>
              <span aria-hidden="true">{d.label}</span>
            </span>
          ))}
        </div>
        {stats.cpu !== undefined && (
          <>
            <span className="hidden sm:inline text-[var(--j-text-muted)]" aria-hidden="true">|</span>
            <span aria-label={`CPU ${stats.cpu.toFixed(0)} percent`}>CPU {stats.cpu.toFixed(0)}%</span>
            <span className="hidden sm:inline" aria-label={`Memory ${stats.mem?.toFixed(0)} percent`}>MEM {stats.mem?.toFixed(0)}%</span>
          </>
        )}
      </div>
      <div className="flex items-center gap-1 sm:gap-3 shrink-0">
        <span aria-label={`Current time ${time}`} className="truncate max-w-[80px] sm:max-w-none">{time}</span>
      </div>
    </motion.div>
  );
}
