'use client';

import { useEffect, useState } from 'react';
import { api, type HealthStatus } from '@/lib/api';

export function useHealthCheck() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const check = async () => {
    try {
      const data = await api.health();
      setHealth(data);
      setError(null);
    } catch (e) {
      console.warn('[HealthCheck] failed', e);
      setError('Connection failed');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    check();
    const interval = setInterval(check, 30000);
    return () => clearInterval(interval);
  }, []);

  return { health, error, loading, refresh: check };
}

export function HealthBadge() {
  const { health, error, loading } = useHealthCheck();

  if (loading) {
    return (
      <span className="h-2 w-2 rounded-full bg-[var(--j-text-muted)] animate-pulse" title="Checking..." />
    );
  }

  const isHealthy = health?.status === 'healthy' || health?.status === 'ok';
  const color = error ? '#ff4757' : isHealthy ? '#00ff88' : 'var(--j-gold)';
  const label = error ? 'Offline' : isHealthy ? 'Online' : 'Degraded';

  return (
    <span
      className="inline-block h-2 w-2 rounded-full shadow-[0_0_8px_currentColor]"
      style={{ background: color, color }}
      title={`${health?.status || 'unknown'}${health?.version ? ` v${health.version}` : ''}`}
      aria-label={label}
    />
  );
}
