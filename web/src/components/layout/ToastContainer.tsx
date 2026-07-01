'use client';

import { motion, AnimatePresence } from 'framer-motion';
import { useToastStore } from '@/stores/toastStore';

const ICONS: Record<string, string> = {
  info: '✦',
  success: '✓',
  error: '✗',
};

const COLORS: Record<string, { bg: string; border: string; text: string }> = {
  info: { bg: 'rgba(56,189,248,0.1)', border: 'rgba(56,189,248,0.25)', text: 'var(--j-sky)' },
  success: { bg: 'rgba(74,222,128,0.1)', border: 'rgba(74,222,128,0.25)', text: '#4ade80' },
  error: { bg: 'rgba(255,71,87,0.1)', border: 'rgba(255,71,87,0.25)', text: '#ff4757' },
};

export default function ToastContainer() {
  const { toasts, removeToast } = useToastStore();

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none" role="region" aria-label="Notifications" aria-live="polite">
      <AnimatePresence mode="popLayout">
        {toasts.map(t => {
          const c = COLORS[t.type];
          return (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, x: 40, scale: 0.95 }}
              animate={{ opacity: 1, x: 0, scale: 1 }}
              exit={{ opacity: 0, x: 40, scale: 0.95 }}
              transition={{ duration: 0.15, type: 'spring', stiffness: 300, damping: 25 }}
              onClick={() => removeToast(t.id)}
              className="pointer-events-auto clip-hud flex cursor-pointer items-center gap-2.5 border px-4 py-3 text-sm shadow-[0_14px_40px_rgba(0,0,0,0.35)] backdrop-blur-xl"
              style={{ background: c.bg, borderColor: c.border, color: c.text }}
            >
              <span>{ICONS[t.type]}</span>
              <span className="font-mono text-[11px] uppercase tracking-[0.12em]" style={{ color: 'var(--j-text)' }}>{t.message}</span>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
