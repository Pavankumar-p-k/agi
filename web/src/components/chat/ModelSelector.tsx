'use client';

import { useRef, useEffect, useState } from 'react';
import { api, type Model } from '@/lib/api';

interface Props {
  value: string;
  onChange: (model: string) => void;
}

export default function ModelSelector({ value, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const [models, setModels] = useState<{ id: string; label: string }[]>([]);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.models.list().then(r => {
      const fetched = r.models.map((m: Model) => ({ id: m.id, label: m.name }));
      setModels([{ id: 'auto', label: 'Auto' }, ...fetched]);
    }).catch((e) => {
      console.warn('[ModelSelector] fetch failed', e);
      setModels([{ id: 'auto', label: 'Auto' }]);
    });
  }, []);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const current = models.find(m => m.id === value) || models[0] || { id: 'auto', label: 'Auto' };

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="clip-hud flex items-center gap-1.5 border px-3 py-2 font-mono text-[10px] uppercase tracking-[0.12em] transition-all"
        style={{
          background: 'var(--j-bg)',
          borderColor: 'var(--j-border)',
          color: 'var(--j-text-dim)',
        }}
      >
        <span style={{ color: 'var(--j-sky)' }}>◉</span>
        {current.label}
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
          style={{ transform: open ? 'rotate(180deg)' : '', transition: 'transform 0.15s' }}>
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>
      {open && (
        <div className="absolute right-0 top-full z-30 mt-2 min-w-[170px] border py-1 shadow-[0_18px_60px_rgba(0,0,0,0.42)]"
          style={{
            background: 'var(--j-surface)',
            borderColor: 'var(--j-border)',
          }}>
          {models.map(m => (
            <button
              key={m.id}
              onClick={() => { onChange(m.id); setOpen(false); }}
              className="flex w-full items-center gap-2 px-3 py-2 text-left font-mono text-[10px] uppercase tracking-[0.12em] transition-all"
              style={{
                color: value === m.id ? 'var(--j-sky)' : 'var(--j-text-dim)',
                background: value === m.id ? 'rgba(56,189,248,0.08)' : 'transparent',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--j-surface-hover)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = value === m.id ? 'rgba(56,189,248,0.08)' : 'transparent'; }}
            >
              {value === m.id && <span style={{ color: 'var(--j-sky)' }}>✓</span>}
              {value !== m.id && <span className="w-3" />}
              {m.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
