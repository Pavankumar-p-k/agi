'use client';

import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { usePathname } from 'next/navigation';
import Link from 'next/link';
import { useThemeStore } from '@/stores/themeStore';

interface Props {
  onMenuClick: () => void;
}

const PAGE_TITLES: Record<string, string> = {
  '/': 'Dashboard',
  '/chat': 'Chat',
  '/cli': 'CLI',
  '/monitor': 'Monitor',
  '/logs': 'Logs',
  '/backend': 'Backend',
  '/settings': 'Settings',
  '/settings/themes': 'Theme Studio',
  '/settings/fonts': 'Font Picker',
  '/auth/login': 'Sign In',
};

interface Notification {
  id: string;
  text: string;
  time: number;
  unread: boolean;
}

const SAMPLE_NOTIFICATIONS: Notification[] = [
  { id: '1', text: 'System ready — all services online', time: Date.now() - 60000, unread: true },
  { id: '2', text: 'Model loaded: qwen3:4b', time: Date.now() - 300000, unread: false },
  { id: '3', text: 'Web UI export complete', time: Date.now() - 3600000, unread: false },
];

export default function Navbar({ onMenuClick }: Props) {
  const pathname = usePathname();
  const [notifOpen, setNotifOpen] = useState(false);
  const [notifs, setNotifs] = useState(SAMPLE_NOTIFICATIONS);
  const notifRef = useRef<HTMLDivElement>(null);

  const title = PAGE_TITLES[pathname] || 'JARVIS';

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) setNotifOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const unreadCount = notifs.filter(n => n.unread).length;

  const markRead = () => setNotifs(prev => prev.map(n => ({ ...n, unread: false })));

  return (
    <motion.header
      initial={{ opacity: 0, y: -12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className="h-16 border-b border-[var(--j-border)] flex items-center gap-3 px-4 md:px-6 shrink-0"
      style={{ background: 'rgba(var(--j-bg-rgb), 0.86)', backdropFilter: 'blur(20px)' }}
    >
      <motion.button
        whileHover={{ scale: 1.1 }}
        whileTap={{ scale: 0.9 }}
        onClick={onMenuClick}
        className="md:hidden w-9 h-9 flex items-center justify-center border border-[var(--j-border)] text-lg text-[var(--j-text-dim)] hover:bg-[var(--j-surface-hover)]"
      >
        ☰
      </motion.button>
      <div>
        <span className="hud-label text-[9px]">Console</span>
        <div className="font-display text-[24px] leading-none tracking-[0.14em]">{title}</div>
      </div>
      <div className="flex-1" />
      <div className="hidden md:flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-[var(--j-text-muted)]">
        <span className="h-1.5 w-1.5 rounded-full bg-[#00ff88] shadow-[0_0_8px_#00ff88] animate-[pulse-dot_2s_ease-in-out_infinite]" />
        System Online
      </div>

      {/* Notifications */}
      <div ref={notifRef} className="relative">
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={() => { setNotifOpen(!notifOpen); if (!notifOpen) markRead(); }}
          className="relative w-9 h-9 flex items-center justify-center border border-[var(--j-border)] transition-colors hover:bg-[var(--j-surface-hover)] hover:border-[var(--j-border-bright)]"
          style={{ color: 'var(--j-text-dim)' }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
            <path d="M13.73 21a2 2 0 0 1-3.46 0" />
          </svg>
          {unreadCount > 0 && (
            <motion.span
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              className="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full flex items-center justify-center text-[8px] font-bold"
              style={{ background: '#ff4757', color: '#fff' }}
            >
              {unreadCount}
            </motion.span>
          )}
        </motion.button>

        <AnimatePresence>
          {notifOpen && (
            <motion.div
              initial={{ opacity: 0, y: -8, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -8, scale: 0.96 }}
              transition={{ duration: 0.1 }}
              className="absolute right-0 top-full mt-2 w-[280px] border shadow-[0_16px_50px_rgba(0,0,0,0.35)] overflow-hidden z-40"
              style={{ background: 'var(--j-surface)', borderColor: 'var(--j-border)' }}
            >
              <div className="flex items-center justify-between px-4 py-2.5 border-b" style={{ borderColor: 'var(--j-border)' }}>
                <span className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--j-text-dim)' }}>Notifications</span>
                <span className="text-[9px]" style={{ color: 'var(--j-text-dim)' }}>{notifs.length}</span>
              </div>
              <div className="max-h-[240px] overflow-y-auto">
                {notifs.length === 0 ? (
                  <p className="text-[11px] text-center py-6" style={{ color: 'var(--j-text-dim)' }}>No notifications</p>
                ) : (
                  notifs.map(n => (
                    <div key={n.id} className="px-4 py-2.5 border-b text-[11px]" style={{ borderColor: 'var(--j-border)', background: n.unread ? 'rgba(56,189,248,0.04)' : 'transparent' }}>
                      <div style={{ color: 'var(--j-text)' }}>{n.text}</div>
                      <div className="text-[9px] mt-0.5" style={{ color: 'var(--j-text-dim)' }}>
                        {Math.floor((Date.now() - n.time) / 60000)}m ago
                      </div>
                    </div>
                  ))
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Keyboard shortcut hint */}
      <div className="hidden sm:flex items-center gap-1 text-[9px] px-2 py-1 font-mono uppercase tracking-[0.12em]" style={{ background: 'var(--j-bg)', color: 'var(--j-text-dim)', border: '1px solid var(--j-border)' }}>
        <kbd className="font-sans">⌘</kbd><kbd className="font-sans">K</kbd>
      </div>

      {/* User menu */}
      <UserMenu />
    </motion.header>
  );
}

function UserMenu() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  return (
    <div ref={ref} className="relative">
      <motion.button
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
        onClick={() => setOpen(!open)}
        className="w-9 h-9 flex items-center justify-center text-xs font-bold transition-colors hover:bg-[var(--j-surface-hover)]"
        style={{ background: 'var(--j-bg)', color: 'var(--j-sky)', border: '1px solid var(--j-border)' }}
      >
        J
      </motion.button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.96 }}
            transition={{ duration: 0.1 }}
            className="absolute right-0 top-full mt-2 w-[200px] border shadow-[0_16px_50px_rgba(0,0,0,0.35)] overflow-hidden z-40"
            style={{ background: 'var(--j-surface)', borderColor: 'var(--j-border)' }}
          >
            <div className="px-4 py-3 border-b" style={{ borderColor: 'var(--j-border)' }}>
              <div className="text-sm font-medium" style={{ color: 'var(--j-text)' }}>JARVIS User</div>
              <div className="text-[10px]" style={{ color: 'var(--j-text-dim)' }}>Signed in locally</div>
            </div>
            <div className="py-1">
              {[
                { label: 'Settings', icon: '⚛', href: '/settings' },
                { label: 'Theme Studio', icon: '🎨', href: '/settings/themes' },
                { label: 'Sign Out', icon: '↩', href: '/auth/login' },
              ].map(item => (
                <Link key={item.label} href={item.href} onClick={() => setOpen(false)}
                  className="flex items-center gap-2.5 px-4 py-2 text-[11px] transition-colors hover:bg-[var(--j-surface-hover)]"
                  style={{ color: item.href === '/auth/login' ? '#ff4757' : 'var(--j-text-dim)' }}>
                  <span>{item.icon}</span>
                  {item.label}
                </Link>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
