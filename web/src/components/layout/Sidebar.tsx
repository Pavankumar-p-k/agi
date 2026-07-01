'use client';

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useThemeStore } from '@/stores/themeStore';
import type { ThemeId } from '@/stores/themeStore';

const PRIMARY = [
  { href: '/', label: 'Home', icon: '◈' },
  { href: '/chat', label: 'Chat', icon: '✦' },
  { href: '/tasks', label: 'Tasks', icon: '⚒' },
  { href: '/history', label: 'History', icon: '⟁' },
  { href: '/system', label: 'System', icon: '◉' },
  { href: '/settings', label: 'Settings', icon: '⚛' },
];

const DEV_ITEMS = [
  { href: '/voice', label: 'Voice', icon: '♢' },
  { href: '/models', label: 'Models', icon: '◎' },
  { href: '/agents', label: 'Agents', icon: '⊚' },
  { href: '/operations', label: 'Operations', icon: '⚙' },
  { href: '/automation', label: 'Automation', icon: '⟁' },
  { href: '/memory', label: 'Memory', icon: '◈' },
  { href: '/skills', label: 'Skills', icon: '⌘' },
  { href: '/plugins', label: 'Plugins', icon: '⊕' },
  { href: '/integrations', label: 'Integrations', icon: '⇌' },
  { href: '/projects', label: 'Projects', icon: '▣' },
  { href: '/build', label: 'Build', icon: '⚒' },
  { href: '/media', label: 'Media', icon: '♫' },
  { href: '/files', label: 'Files', icon: '⊞' },
  { href: '/notes', label: 'Notes', icon: '✎' },
  { href: '/email', label: 'Email', icon: '✉' },
  { href: '/knowledge', label: 'Knowledge', icon: '⚯' },
  { href: '/diagnostics', label: 'Diagnostics', icon: '◉' },
  { href: '/system/entry-points', label: 'Entry Points', icon: '⌁' },
  { href: '/monitor', label: 'Monitor', icon: '◉' },
  { href: '/logs', label: 'Logs', icon: '▤' },
  { href: '/backend', label: 'Backend', icon: '⚙' },
  { href: '/cli', label: 'CLI', icon: '⌁' },
  { href: '/features', label: 'Features', icon: '⊕' },
  { href: '/providers', label: 'Providers', icon: '⇌' },
];

const THEMES: { id: ThemeId; label: string }[] = [
  { id: 'sky', label: 'Sky' },
  { id: 'phantom', label: 'Phantom' },
  { id: 'arctic', label: 'Arctic' },
  { id: 'ember', label: 'Ember' },
];

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function Sidebar({ open, onClose }: Props) {
  const pathname = usePathname();
  const { theme, setTheme, font, setFont } = useThemeStore();
  const [devMode, setDevMode] = useState(false);

  useEffect(() => {
    setDevMode(localStorage.getItem('j-dev-mode') === 'true');
  }, []);

  const toggleDev = () => {
    const next = !devMode;
    setDevMode(next);
    localStorage.setItem('j-dev-mode', String(next));
  };

  return (
    <>
      {open && <div className="fixed inset-0 bg-black/50 z-10 md:hidden" onClick={onClose} />}
      <aside
        role="navigation"
        aria-label="Main navigation"
        className={`fixed md:static z-20 inset-y-0 left-0 w-[280px] bg-[rgba(var(--j-surface-rgb),0.88)] border-r border-[var(--j-border)] flex flex-col transition-transform duration-250 backdrop-blur-xl ${
          open ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
        }`}
      >
        <div className="flex items-center justify-between px-5 h-16 border-b border-[var(--j-border)]">
          <Link href="/" className="flex items-center gap-3" aria-label="JARVIS Home">
            <span className="relative h-8 w-8 rotate-45 border border-[var(--j-sky)] shadow-[0_0_18px_rgba(var(--j-sky-rgb),0.18)]" aria-hidden="true">
              <span className="absolute left-1/2 top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 bg-[var(--j-sky)] shadow-[0_0_16px_var(--j-sky)]" />
            </span>
            <span className="font-display text-[25px] tracking-[0.18em] text-[var(--j-text)]">JARVIS</span>
          </Link>
        </div>

        <nav className="flex-1 py-4 px-3 space-y-1 overflow-y-auto" aria-label="Primary pages">
          {PRIMARY.map((n, i) => {
            const active = pathname === n.href;
            return (
              <motion.div
                key={n.href}
                initial={{ opacity: 0, x: -12 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.03, duration: 0.2 }}
              >
                <Link
                  href={n.href}
                  onClick={onClose}
                  className={`group flex items-center gap-3 px-3 py-3 text-xs relative border transition-all duration-200 font-mono uppercase tracking-[0.12em] ${
                    active
                      ? 'text-[var(--j-sky)]'
                      : 'text-[var(--j-text-dim)] hover:text-[var(--j-text)]'
                  }`}
                  style={{
                    background: active ? 'rgba(var(--j-sky-rgb), 0.08)' : 'transparent',
                    borderColor: active ? 'var(--j-border-bright)' : 'transparent',
                  }}
                >
                  {active && (
                    <motion.span
                      layoutId="sidebar-active"
                      className="absolute left-0 top-1/2 h-6 w-0.5 -translate-y-1/2"
                      style={{ background: 'var(--j-sky)' }}
                      transition={{ type: 'spring', stiffness: 300, damping: 25 }}
                    />
                  )}
                  <motion.span whileHover={{ scale: 1.15 }} className="text-base w-5 text-center text-[var(--j-sky)]">{n.icon}</motion.span>
                  {n.label}
                </Link>
              </motion.div>
            );
          })}

          {/* Developer mode toggle */}
          <div className="pt-3 pb-1">
            <button
              onClick={toggleDev}
              aria-expanded={devMode}
              aria-controls="dev-nav-items"
              className="flex w-full items-center gap-3 px-3 py-2.5 text-xs relative border border-transparent transition-all duration-200 font-mono uppercase tracking-[0.12em] hover:border-[var(--j-border)]"
              style={{ color: devMode ? 'var(--j-sky)' : 'var(--j-text-muted)' }}
            >
              <span className="text-base w-5 text-center" aria-hidden="true">{devMode ? '⊟' : '⊞'}</span>
              Dev Mode
              <span className="ml-auto text-[9px] opacity-60">{devMode ? 'ON' : 'OFF'}</span>
            </button>
          </div>

          {devMode && (
            <>
              <div className="h-px mx-3" style={{ background: 'var(--j-border)' }} role="separator" />
              <div id="dev-nav-items" role="group" aria-label="Developer pages">
              {DEV_ITEMS.map((n, i) => {
                const active = pathname === n.href;
                return (
                  <motion.div
                    key={n.href}
                    initial={{ opacity: 0, x: -12 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.015, duration: 0.2 }}
                  >
                    <Link
                      href={n.href}
                      onClick={onClose}
                      className={`group flex items-center gap-3 px-3 py-2.5 text-[11px] relative border transition-all duration-200 font-mono uppercase tracking-[0.12em] ${
                        active
                          ? 'text-[var(--j-sky)]'
                          : 'text-[var(--j-text-dim)] hover:text-[var(--j-text)]'
                      }`}
                      style={{
                        background: active ? 'rgba(var(--j-sky-rgb), 0.08)' : 'transparent',
                        borderColor: active ? 'var(--j-border-bright)' : 'transparent',
                      }}
                    >
                      <motion.span whileHover={{ scale: 1.15 }} className="text-sm w-5 text-center opacity-60">{n.icon}</motion.span>
                      {n.label}
                    </Link>
                  </motion.div>
                );
              })}
              </div>
            </>
          )}
        </nav>

        <div className="border-t border-[var(--j-border)] p-4 space-y-4">
          <div>
            <div className="hud-label mb-2 px-1" id="theme-label">Theme</div>
            <div className="flex gap-1.5 flex-wrap" role="radiogroup" aria-labelledby="theme-label">
              {THEMES.map((t) => (
                <motion.button
                  key={t.id}
                  onClick={() => setTheme(t.id)}
                  whileHover={{ scale: 1.15 }}
                  whileTap={{ scale: 0.9 }}
                  role="radio"
                  aria-checked={theme === t.id}
                  aria-label={`${t.label} theme`}
                  className={`w-7 h-7 text-[10px] font-mono font-medium transition-all focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--j-sky)] ${
                    theme === t.id
                      ? 'ring-1 ring-[var(--j-sky)] scale-110'
                      : 'opacity-50 hover:opacity-80'
                  }`}
                  style={{
                    background: t.id === 'sky' ? '#0EA5E9' : t.id === 'phantom' ? '#7C3AED' : t.id === 'arctic' ? '#E0F2FE' : '#EA580C',
                    color: t.id === 'arctic' ? '#0C4A6E' : '#fff',
                  }}
                >
                  {t.label[0]}
                </motion.button>
              ))}
            </div>
          </div>
          <div>
            <div className="hud-label mb-1.5 px-1" id="font-label">Font</div>
            <select
              value={font}
              onChange={(e) => setFont(e.target.value as 'sans' | 'mono' | 'display')}
              aria-labelledby="font-label"
              className="w-full bg-[var(--j-bg)] border border-[var(--j-border)] px-2 py-2 text-xs text-[var(--j-text)] outline-none focus-visible:ring-1 focus-visible:ring-[var(--j-sky)]"
            >
              <option value="sans">Sans (Outfit)</option>
              <option value="mono">Mono (DM Mono)</option>
              <option value="display">Display (Bebas)</option>
            </select>
          </div>
        </div>
      </aside>
    </>
  );
}
