'use client';

import { motion } from 'framer-motion';

interface Props {
  onContinue: () => void;
}

export default function WelcomeCard({ onContinue }: Props) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -12 }}
      className="flex flex-col items-center text-center max-w-lg mx-auto"
    >
      <div className="w-16 h-16 rounded-full border border-[var(--j-sky)] flex items-center justify-center mb-6"
           style={{ boxShadow: '0 0 24px rgba(0,210,255,0.15)' }}>
        <span className="text-2xl font-bold text-[var(--j-sky)]" style={{ fontFamily: 'var(--j-font-mono)' }}>J</span>
      </div>

      <h1 className="text-3xl font-light tracking-[0.15em] uppercase mb-3">
        <span style={{ color: 'var(--j-text)' }}>Welcome to </span>
        <span style={{ color: 'var(--j-sky)' }}>JARVIS</span>
      </h1>

      <p className="text-sm leading-relaxed mb-8" style={{ color: 'var(--j-text-dim)', letterSpacing: '0.04em' }}>
        A local-first AI workspace that completes real tasks.
        <br />
        This setup takes about 30 seconds.
      </p>

      <button
        onClick={onContinue}
        className="px-8 py-2.5 text-sm tracking-[0.12em] uppercase cursor-pointer transition-all duration-200"
        style={{
          background: 'var(--j-sky)',
          color: '#020406',
          border: 'none',
          fontFamily: 'var(--j-font-mono)',
          letterSpacing: '0.12em',
        }}
        onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 0 20px rgba(0,210,255,0.4)'; }}
        onMouseLeave={e => { e.currentTarget.style.boxShadow = 'none'; }}
      >
        Continue
      </button>
    </motion.div>
  );
}
