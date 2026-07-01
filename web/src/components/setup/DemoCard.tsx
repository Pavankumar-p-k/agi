'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import { api } from '@/lib/api';

interface Props {
  onComplete: () => void;
  onSkip: () => void;
}

export default function DemoCard({ onComplete, onSkip }: Props) {
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<{ success: boolean; duration_ms: number } | null>(null);

  const handleRun = async () => {
    setRunning(true);
    setResult(null);
    try {
      const res = await api.setup.demo();
      setResult(res);
    } catch {
      setResult({ success: false, duration_ms: 0 });
    } finally {
      setRunning(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -12 }}
      className="flex flex-col items-center text-center max-w-lg mx-auto"
    >
      <h2 className="text-sm tracking-[0.12em] uppercase mb-3" style={{ color: 'var(--j-text-dim)' }}>
        Watch JARVIS Work
      </h2>

      <p className="text-xs leading-relaxed mb-4" style={{ color: 'var(--j-text-muted)' }}>
        See JARVIS plan, build, and deliver a complete project — start to finish.
      </p>

      <p className="text-xs mb-6" style={{ color: 'var(--j-text-muted)' }}>
        Builds <span className="font-mono" style={{ color: 'var(--j-sky)' }}>hello.html</span> · ~20 seconds
      </p>

      {result ? (
        <div className="mb-6 text-center">
          <div
            className="text-sm mb-1"
            style={{ color: result.success ? 'var(--j-green)' : 'var(--j-text-dim)' }}
          >
            {result.success ? 'Demo complete' : 'Demo failed'}
          </div>
          {result.success && (
            <div className="text-xs" style={{ color: 'var(--j-text-muted)' }}>
              {result.duration_ms}ms
            </div>
          )}
        </div>
      ) : (
        <div className="mb-6">
          <div
            className="w-24 h-24 mx-auto mb-3 flex items-center justify-center"
            style={{
              border: '1px solid var(--j-border)',
              borderRadius: 'var(--j-radius-md)',
              background: 'rgba(0,210,255,0.04)',
            }}
          >
            <span className="text-3xl" style={{ color: 'var(--j-sky)', fontFamily: 'var(--j-font-mono)' }}>
              &lt;/&gt;
            </span>
          </div>
        </div>
      )}

      <div className="flex gap-3">
        <button
          onClick={handleRun}
          disabled={running}
          className="px-6 py-2.5 text-sm tracking-[0.12em] uppercase cursor-pointer transition-all duration-200 disabled:opacity-40"
          style={{
            background: 'var(--j-sky)',
            color: '#020406',
            border: 'none',
            fontFamily: 'var(--j-font-mono)',
          }}
        >
          {running ? 'Running...' : result ? 'Run Again' : 'Run Demo'}
        </button>

        <button
          onClick={onSkip}
          className="px-6 py-2.5 text-sm tracking-[0.12em] uppercase cursor-pointer transition-all duration-200"
          style={{
            background: 'transparent',
            color: 'var(--j-text-dim)',
            border: '1px solid var(--j-border)',
            fontFamily: 'var(--j-font-mono)',
          }}
        >
          Skip
        </button>
      </div>

      {result && (
        <button
          onClick={onComplete}
          className="mt-6 px-8 py-2.5 text-sm tracking-[0.12em] uppercase cursor-pointer transition-all duration-200"
          style={{
            background: 'var(--j-sky)',
            color: '#020406',
            border: 'none',
            fontFamily: 'var(--j-font-mono)',
          }}
        >
          Continue
        </button>
      )}
    </motion.div>
  );
}
