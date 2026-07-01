'use client';

import { motion } from 'framer-motion';
import { useRouter } from 'next/navigation';

interface Props {
  onOpen: () => void;
}

export default function FinishCard({ onOpen }: Props) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -12 }}
      className="flex flex-col items-center text-center max-w-lg mx-auto"
    >
      <div
        className="w-16 h-16 rounded-full flex items-center justify-center mb-6"
        style={{
          border: '1px solid rgba(74,222,128,0.3)',
          boxShadow: '0 0 24px rgba(74,222,128,0.12)',
        }}
      >
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--j-green)" strokeWidth="2"
             strokeLinecap="round" strokeLinejoin="round">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      </div>

      <h1 className="text-2xl font-light tracking-[0.12em] uppercase mb-3" style={{ color: 'var(--j-text)' }}>
        You&apos;re Ready
      </h1>

      <p className="text-xs mb-4" style={{ color: 'var(--j-text-muted)' }}>
        Try asking JARVIS to:
      </p>

      <div className="space-y-2 text-left mb-8">
        {[
          { label: 'Build a portfolio website', icon: '🎯' },
          { label: 'Research a topic and summarize', icon: '◎' },
          { label: 'Analyze a repository for issues', icon: '⊚' },
          { label: 'Automate a browser workflow', icon: '◈' },
        ].map(item => (
          <div
            key={item.label}
            className="flex items-center gap-3 px-4 py-2"
            style={{
              border: '1px solid var(--j-border)',
              borderRadius: 'var(--j-radius-md)',
            }}
          >
            <span className="text-xs" style={{ color: 'var(--j-sky)' }}>
              {item.icon}
            </span>
            <span className="text-sm" style={{ color: 'var(--j-text-dim)' }}>{item.label}</span>
          </div>
        ))}
      </div>

      <button
        onClick={onOpen}
        className="px-8 py-2.5 text-sm tracking-[0.12em] uppercase cursor-pointer transition-all duration-200"
        style={{
          background: 'var(--j-sky)',
          color: '#020406',
          border: 'none',
          fontFamily: 'var(--j-font-mono)',
        }}
        onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 0 20px rgba(0,210,255,0.4)'; }}
        onMouseLeave={e => { e.currentTarget.style.boxShadow = 'none'; }}
      >
        Open JARVIS
      </button>
    </motion.div>
  );
}
