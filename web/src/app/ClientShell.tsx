'use client';

import { useEffect, useState, type ReactNode } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { usePathname } from 'next/navigation';
import ThemeProvider from '@/components/theme/ThemeProvider';
import Sidebar from '@/components/layout/Sidebar';
import Navbar from '@/components/layout/Navbar';
import CommandPalette from '@/components/layout/CommandPalette';
import ToastContainer from '@/components/layout/ToastContainer';
import StatusBar from '@/components/layout/StatusBar';
import ErrorBoundary from '@/components/ui/ErrorBoundary';

export default function ClientShell({ children }: { children: ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const pathname = usePathname();

  useEffect(() => {
    const cursor = document.querySelector<HTMLElement>('.jarvis-cursor');
    const ring = document.querySelector<HTMLElement>('.jarvis-cursor-ring');
    if (!cursor || !ring) return;

    let mx = 0;
    let my = 0;
    let rx = 0;
    let ry = 0;
    let frame = 0;

    const move = (e: MouseEvent) => {
      mx = e.clientX;
      my = e.clientY;
      cursor.style.transform = `translate(${mx - 4}px, ${my - 4}px)`;
    };
    const enter = () => {
      cursor.style.transform = `translate(${mx - 4}px, ${my - 4}px) scale(1.8)`;
      ring.style.width = '48px';
      ring.style.height = '48px';
      ring.style.borderColor = 'rgba(var(--j-sky-rgb),0.62)';
    };
    const leave = () => {
      ring.style.width = '32px';
      ring.style.height = '32px';
      ring.style.borderColor = 'rgba(var(--j-sky-rgb),0.4)';
    };
    const animate = () => {
      rx += (mx - rx - 16) * 0.14;
      ry += (my - ry - 16) * 0.14;
      ring.style.transform = `translate(${rx}px, ${ry}px)`;
      frame = requestAnimationFrame(animate);
    };

    document.addEventListener('mousemove', move);
    document.querySelectorAll('a, button, select, input, textarea, [role="button"]').forEach((el) => {
      el.addEventListener('mouseenter', enter);
      el.addEventListener('mouseleave', leave);
    });
    frame = requestAnimationFrame(animate);

    return () => {
      document.removeEventListener('mousemove', move);
      document.querySelectorAll('a, button, select, input, textarea, [role="button"]').forEach((el) => {
        el.removeEventListener('mouseenter', enter);
        el.removeEventListener('mouseleave', leave);
      });
      cancelAnimationFrame(frame);
    };
  }, [pathname]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setPaletteOpen(p => !p);
      }
      if (e.key === 'Escape') {
        setPaletteOpen(false);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  return (
    <ThemeProvider>
      <div className="jarvis-cursor" />
      <div className="jarvis-cursor-ring" />
      <div
        className="relative flex h-screen overflow-hidden"
        style={{
          background: 'linear-gradient(180deg, rgba(var(--j-bg-rgb),0.92), var(--j-bg))',
          color: 'var(--j-text)',
        }}
      >
        <div className="hud-grid pointer-events-none absolute inset-0 opacity-80" />
        <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
        <main className="relative z-[1] flex-1 flex flex-col min-w-0 overflow-hidden">
          <Navbar onMenuClick={() => setSidebarOpen(true)} />
          <div className="flex-1 overflow-y-auto p-4 md:p-6">
            <ErrorBoundary>
              <AnimatePresence mode="wait">
                <motion.div
                  key={pathname}
                  initial={{ opacity: 0, y: 18, filter: 'blur(3px)' }}
                  animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
                  exit={{ opacity: 0, y: -12, filter: 'blur(3px)' }}
                  transition={{ duration: 0.34, ease: [0.16, 1, 0.3, 1] }}
                >
                  {children}
                </motion.div>
              </AnimatePresence>
            </ErrorBoundary>
          </div>
          <StatusBar />
        </main>
      </div>
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
      <ToastContainer />
    </ThemeProvider>
  );
}
