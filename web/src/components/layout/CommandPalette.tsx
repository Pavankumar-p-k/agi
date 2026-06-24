'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useRouter } from 'next/navigation';

const ACTIONS = [
  { id: 'chat', label: 'Open Chat', icon: '✦', href: '/chat', keys: 'g c' },
  { id: 'cli', label: 'CLI Showcase', icon: '⌁', href: '/cli', keys: 'g x' },
  { id: 'dashboard', label: 'Go to Dashboard', icon: '◈', href: '/', keys: 'g d' },
  { id: 'monitor', label: 'Open Monitor', icon: '◉', href: '/monitor', keys: 'g m' },
  { id: 'logs', label: 'Open Logs', icon: '▤', href: '/logs', keys: 'g l' },
  { id: 'backend', label: 'Backend Control', icon: '⚙', href: '/backend', keys: 'g b' },
  { id: 'operations', label: 'Operations Center', icon: '⚙', href: '/operations', keys: 'g o' },
  { id: 'settings', label: 'Settings', icon: '⚛', href: '/settings', keys: 'g s' },
  { id: 'themes', label: 'Theme Studio', icon: '🎨', href: '/settings/themes', keys: 'g t' },
  { id: 'fonts', label: 'Font Picker', icon: '🔤', href: '/settings/fonts', keys: 'g f' },
  { id: 'login', label: 'Sign In', icon: '🔐', href: '/auth/login', keys: 'g i' },
];

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function CommandPalette({ open, onClose }: Props) {
  const [query, setQuery] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  useEffect(() => {
    if (open) {
      setQuery('');
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  const filtered = query
    ? ACTIONS.filter(a => a.label.toLowerCase().includes(query.toLowerCase()) || a.id.includes(query.toLowerCase()))
    : ACTIONS;

  const execute = useCallback((action: typeof ACTIONS[0]) => {
    router.push(action.href);
    onClose();
  }, [router, onClose]);

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') onClose();
    if (e.key === 'Enter' && filtered.length > 0) execute(filtered[0]);
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.12 }}
          className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]" onClick={onClose}
        >
          <div className="absolute inset-0 bg-black/70 backdrop-blur-md" />
          <motion.div
            initial={{ opacity: 0, y: -16, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -12, scale: 0.97 }}
            transition={{ duration: 0.12 }}
            className="relative w-full max-w-2xl overflow-hidden border shadow-[0_24px_90px_rgba(0,0,0,0.55)]"
            style={{ background: 'rgba(var(--j-surface-rgb), 0.88)', backdropFilter: 'blur(20px)', borderColor: 'var(--j-border-bright)' }}
            onClick={(e) => e.stopPropagation()}
          >
        <div className="hud-scan-box absolute inset-0 pointer-events-none opacity-40" />
        <div className="relative z-[1] flex items-center gap-3 border-b px-4 py-4" style={{ borderColor: 'var(--j-border)' }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: 'var(--j-text-dim)' }}>
            <circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" />
          </svg>
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Search commands..."
            className="flex-1 border-none bg-transparent font-mono text-sm outline-none"
            style={{ color: 'var(--j-text)' }}
          />
          <kbd className="border border-[var(--j-border)] px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em]" style={{ background: 'var(--j-bg)', color: 'var(--j-text-dim)' }}>ESC</kbd>
        </div>
        <div className="relative z-[1] max-h-[380px] space-y-1 overflow-y-auto p-2">
          {filtered.length === 0 && (
            <p className="text-xs text-center py-6" style={{ color: 'var(--j-text-dim)' }}>No results</p>
          )}
          {filtered.map(a => (
            <button
              key={a.id}
              onClick={() => execute(a)}
              className="flex w-full items-center gap-3 border border-transparent px-3 py-3 text-sm transition-all hover:border-[var(--j-border)] hover:bg-[rgba(var(--j-sky-rgb),0.05)]"
              style={{ color: 'var(--j-text)' }}
            >
              <span className="text-base w-5 text-center" style={{ color: 'var(--j-sky)' }}>{a.icon}</span>
              <span className="flex-1 text-left font-mono text-[11px] uppercase tracking-[0.12em]">{a.label}</span>
              <span className="text-[9px] uppercase tracking-[0.12em]" style={{ color: 'var(--j-text-dim)' }}>{a.keys}</span>
            </button>
          ))}
        </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
