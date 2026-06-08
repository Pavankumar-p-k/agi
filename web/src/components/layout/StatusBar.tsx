'use client';

import { useEffect, useState, useCallback } from 'react';
import { motion } from 'framer-motion';

export default function StatusBar() {
  const [time, setTime] = useState('');
  const [status, setStatus] = useState<'online' | 'offline'>('offline');
  const [stats, setStats] = useState<{ cpu?: number; mem?: number }>({});

  useEffect(() => {
    const t = setInterval(() => {
      setTime(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
    }, 10000);
    return () => clearInterval(t);
  }, []);

  const fetchStatus = useCallback(async () => {
    try {
      const r = await fetch('/api/system/stats');
      if (r.ok) {
        const d = await r.json();
        setStats({ cpu: d.cpu.percent, mem: d.memory.percent });
        setStatus('online');
      } else {
        setStatus('offline');
      }
    } catch {
      setStatus('offline');
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const t = setInterval(fetchStatus, 5000);
    return () => clearInterval(t);
  }, [fetchStatus]);

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
        <motion.span
          animate={{ scale: status === 'online' ? [1, 1.2, 1] : 1 }}
          transition={{ repeat: Infinity, duration: 2 }}
          className={`inline-block w-1.5 h-1.5 rounded-full ${status === 'online' ? 'bg-green-400' : 'bg-red-400'}`}
        />
        <span>{status === 'online' ? 'Connected' : 'Offline'}</span>
        {stats.cpu !== undefined && (
          <>
            <span>CPU {stats.cpu.toFixed(0)}%</span>
            <span>MEM {stats.mem?.toFixed(0)}%</span>
          </>
        )}
      </div>
      <div className="flex items-center gap-3">
        <span>JARVIS v1.0</span>
        <span>{time}</span>
      </div>
    </motion.div>
  );
}
