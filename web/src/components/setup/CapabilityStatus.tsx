'use client';

import { motion } from 'framer-motion';
import type { SetupStatus } from '@/lib/api';

interface Props {
  status: SetupStatus;
  onContinue: () => void;
}

interface Capability {
  name: string;
  ready: boolean;
  label: string;
}

const CAPABILITIES: Capability[] = [
  { name: 'chat', ready: true, label: 'Chat' },
  { name: 'coding', ready: true, label: 'Coding' },
  { name: 'research', ready: true, label: 'Research' },
  { name: 'files', ready: true, label: 'Files' },
  { name: 'build', ready: true, label: 'Build' },
  { name: 'browser', ready: false, label: 'Browser' },
  { name: 'desktop', ready: false, label: 'Desktop' },
  { name: 'github', ready: false, label: 'GitHub' },
  { name: 'email', ready: false, label: 'Email' },
  { name: 'voice', ready: false, label: 'Voice' },
];

export default function CapabilityStatus({ status, onContinue }: Props) {
  const readyCapabilities = CAPABILITIES.filter(c => c.ready);
  const needsSetup = CAPABILITIES.filter(c => !c.ready);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -12 }}
      className="max-w-lg mx-auto"
    >
      <h2 className="text-center text-sm tracking-[0.12em] uppercase mb-6" style={{ color: 'var(--j-text-dim)' }}>
        Ready Now
      </h2>

      <div className="space-y-2 mb-6">
        {readyCapabilities.map(c => (
          <div
            key={c.name}
            className="flex items-center gap-3 px-4 py-2.5"
            style={{
              background: 'rgba(74,222,128,0.04)',
              border: '1px solid rgba(74,222,128,0.15)',
              borderRadius: 'var(--j-radius-md)',
            }}
          >
            <div
              className="w-2 h-2 rounded-full shrink-0"
              style={{
                background: 'var(--j-green)',
                boxShadow: '0 0 8px rgba(74,222,128,0.5)',
              }}
            />
            <span className="text-sm" style={{ color: 'var(--j-text)' }}>{c.label}</span>
          </div>
        ))}
      </div>

      {needsSetup.length > 0 && (
        <>
          <h3 className="text-center text-xs tracking-[0.12em] uppercase mb-4" style={{ color: 'var(--j-text-muted)' }}>
            Needs Setup
          </h3>

          <div className="space-y-2">
            {needsSetup.map(c => (
              <div
                key={c.name}
                className="flex items-center gap-3 px-4 py-2.5"
                style={{
                  background: 'rgba(255,255,255,0.02)',
                  border: '1px solid var(--j-border)',
                  borderRadius: 'var(--j-radius-md)',
                }}
              >
                <div
                  className="w-2 h-2 rounded-full shrink-0"
                  style={{ background: 'var(--j-text-muted)' }}
                />
                <span className="text-sm" style={{ color: 'var(--j-text-dim)' }}>{c.label}</span>
              </div>
            ))}
          </div>
        </>
      )}

      <p className="text-xs text-center mt-6 leading-relaxed" style={{ color: 'var(--j-text-muted)' }}>
        You can install these later from Settings.
      </p>

      <div className="text-center mt-6">
        <button
          onClick={onContinue}
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
          Continue
        </button>
      </div>
    </motion.div>
  );
}
