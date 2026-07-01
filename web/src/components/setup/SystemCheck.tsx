'use client';

import { motion } from 'framer-motion';
import type { SetupStatus } from '@/lib/api';

interface Props {
  status: SetupStatus;
  onInstall: (component: string) => Promise<void>;
  onContinue: () => void;
  installing: string | null;
}

const LABELS: Record<string, string> = {
  python: 'Python',
  git: 'Git',
  ollama_installed: 'Ollama',
  ollama_running: 'Ollama Service',
  models: 'AI Models',
  playwright: 'Playwright',
  docker: 'Docker',
  config: 'Configuration',
  api_keys: 'API Keys',
};

const DESCRIPTIONS: Record<string, { ok: string; missing: string }> = {
  python: { ok: 'Runtime ready', missing: 'Python 3.10+ required' },
  git: { ok: 'Version control ready', missing: 'Install git' },
  ollama_installed: { ok: 'Local AI engine installed', missing: 'Install Ollama' },
  ollama_running: { ok: 'Ollama service running', missing: 'Start Ollama' },
  models: { ok: 'Local models available', missing: 'Download a model to chat locally' },
  playwright: { ok: 'Browser automation ready', missing: 'Install Playwright for web tasks' },
  docker: { ok: 'Container sandbox available', missing: 'Install Docker for sandboxing' },
  config: { ok: 'Configuration found', missing: 'No configuration detected' },
  api_keys: { ok: 'Cloud providers configured', missing: 'Add API keys for cloud models' },
};

export default function SystemCheck({ status, onInstall, onContinue, installing }: Props) {
  const entries = Object.entries(status.checks);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -12 }}
      className="max-w-lg mx-auto"
    >
      <h2 className="text-center text-sm tracking-[0.12em] uppercase mb-6" style={{ color: 'var(--j-text-dim)' }}>
        System Check
      </h2>

      <div className="space-y-3">
        {entries.map(([key, val]) => {
          const ok = val === 'ok';
          const label = LABELS[key] || key;
          const desc = ok ? DESCRIPTIONS[key]?.ok : DESCRIPTIONS[key]?.missing;

          return (
            <div
              key={key}
              className="flex items-center gap-3 px-4 py-2.5"
              style={{
                background: ok ? 'rgba(74,222,128,0.04)' : 'rgba(255,255,255,0.02)',
                border: `1px solid ${ok ? 'rgba(74,222,128,0.15)' : 'var(--j-border)'}`,
                borderRadius: 'var(--j-radius-md)',
              }}
            >
              {/* Status dot */}
              <div
                className="w-2 h-2 rounded-full shrink-0"
                style={{
                  background: ok ? 'var(--j-green)' : 'var(--j-text-muted)',
                  boxShadow: ok ? '0 0 8px rgba(74,222,128,0.5)' : 'none',
                }}
              />

              {/* Label + description */}
              <div className="flex-1 min-w-0">
                <div className="text-sm" style={{ color: ok ? 'var(--j-text)' : 'var(--j-text-dim)' }}>
                  {label}
                </div>
                {desc && (
                  <div className="text-xs mt-0.5" style={{ color: 'var(--j-text-muted)' }}>
                    {desc}
                  </div>
                )}
              </div>

              {/* Action button for missing components */}
              {!ok && (
                <button
                  onClick={() => onInstall(key)}
                  disabled={installing === key}
                  className="text-xs tracking-[0.08em] uppercase px-3 py-1.5 transition-all duration-200 disabled:opacity-40"
                  style={{
                    background: 'rgba(0,210,255,0.08)',
                    border: '1px solid rgba(0,210,255,0.2)',
                    color: 'var(--j-sky)',
                    borderRadius: 'var(--j-radius-sm)',
                    fontFamily: 'var(--j-font-mono)',
                  }}
                >
                  {installing === key ? 'Installing...' : 'Install'}
                </button>
              )}
            </div>
          );
        })}
      </div>

      <div className="text-center mt-8">
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
