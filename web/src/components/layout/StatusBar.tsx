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
    try {
      const ac = new AbortController();
      const timer = setTimeout(() => ac.abort(), 4000);
      try {
        const s = await api.system.stats(ac.signal);
        setStats({ cpu: s.cpu.percent, mem: s.memory.percent });
        setStatus('online');
      } finally {
        clearTimeout(timer);
      }
    } catch (e) {
      console.warn('[StatusBar] stats fetch failed', e);
      setStatus('offline');
    }
    try {
      const d = await api.diagnostics.environment();
      setDiagnostics(prev => ({ ...prev, ollama: d.ollama_available }));
    } catch (e) {
      console.warn('[StatusBar] diagnostics failed', e);
    }
    try {
      const h = await api.health();
      setDiagnostics(prev => ({ ...prev, db: h.status === 'healthy' }));
    } catch (e) {
      console.warn('[StatusBar] health check failed', e);
    }
    try {
      const m = await api.diagnostics.models();
      const openai = m.providers.find(p => p.name === 'openai')?.available;
      const gemini = m.providers.find(p => p.name === 'gemini')?.available;
      setDiagnostics(prev => ({ ...prev, openai, gemini }));
    } catch (e) {
      console.warn('[StatusBar] model diagnostics failed', e);
    }
    try {
      const i = await api.diagnostics.integrations();
      const someConnected = i.integrations.some(ix => ix.connected);
      setDiagnostics(prev => ({ ...prev, integrations: someConnected }));
    } catch (e) {
      console.warn('[StatusBar] integration diagnostics failed', e);
    }
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
      className="h-7 border-t flex items-center justify-between px-3 text-[10px] shrink-0 font-mono uppercase tracking-[0.12em]"
      style={{
        background: 'rgba(var(--j-bg-rgb), 0.76)',
        backdropFilter: 'blur(14px)',
        borderColor: 'var(--j-border)',
        color: 'var(--j-text-dim)',
      }}
    >
      <div className="flex items-center gap-3">
        {dots.map(d => (
          <span key={d.label} className="flex items-center gap-1">
            <span className={`inline-block w-1.5 h-1.5 rounded-full bg-${d.color === 'green' ? 'green' : d.color === 'red' ? 'red' : 'yellow'}-400`} />
            {d.label}
          </span>
        ))}
        {stats.cpu !== undefined && (
          <>
            <span className="text-[var(--j-text-muted)]">|</span>
            <span>CPU {stats.cpu.toFixed(0)}%</span>
            <span>MEM {stats.mem?.toFixed(0)}%</span>
          </>
        )}
      </div>
      <div className="flex items-center gap-3">
        <span>{time}</span>
      </div>
    </motion.div>
  );
}
