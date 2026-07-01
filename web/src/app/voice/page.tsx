'use client';

import { useEffect, useState, useCallback } from 'react';
import { motion, type Variants } from 'framer-motion';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import { Skeleton } from '@/components/ui/Skeleton';
import { api } from '@/lib/api';

interface VoiceConfig {
  stt_provider: string;
  tts_provider: string;
  wake_word_enabled: boolean;
  voice_emotion_enabled: boolean;
  language: string;
}

interface VoiceHealth {
  stt: string;
  tts: string;
  wake_word: string;
  emotion: string;
}

const containerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.06, delayChildren: 0.08 } },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 28 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.62, ease: [0.16, 1, 0.3, 1] } },
};

export default function VoicePage() {
  const [config, setConfig] = useState<VoiceConfig | null>(null);
  const [health, setHealth] = useState<VoiceHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchAll = useCallback(async () => {
    setError('');
    try {
      const [c, h] = await Promise.all([
        api.voice.settings().catch(() => null),
        api.voice.diagnostics().catch(() => null),
      ]);
      if (c) {
        const cfg = c.reduce((acc, s) => {
          const key = s.key.replace('voice.', '');
          return { ...acc, [key]: s.value };
        }, {} as Record<string, unknown>);
        setConfig(cfg as unknown as VoiceConfig);
      }
      if (h) setHealth(h as unknown as VoiceHealth);
    } catch (e) { console.warn('[Voice] fetch failed', e); setError('Failed to load voice data'); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  if (loading) return <div className="hud-page p-6"><Skeleton /></div>;

  return (
    <motion.div variants={containerVariants} initial="hidden" animate="visible" className="hud-page h-full overflow-y-auto space-y-6 p-6">
      <motion.section variants={itemVariants} className="hud-panel hud-scan-box p-6 md:p-8">
        <div className="hud-label">Speech Interface</div>
        <h1 className="hud-title mt-2 text-6xl md:text-7xl">Voice <span className="text-[var(--j-sky)]">Engine</span></h1>
        <p className="mt-4 max-w-2xl text-sm leading-7 text-[var(--j-text-dim)]">
          STT, TTS, wake word detection, and emotion analysis pipeline.
        </p>
      </motion.section>

      {error && (
        <motion.div variants={itemVariants} className="border border-red-500/30 bg-red-500/5 px-5 py-3">
          <p className="text-xs text-red-400">{error}</p>
        </motion.div>
      )}

      <motion.section variants={itemVariants}>
        <div className="hud-label mb-4">Pipeline Status</div>
        <div className="grid grid-cols-1 gap-px bg-[var(--j-border)] md:grid-cols-2">
          <StatusBlock label="STT" value={health?.stt || 'unknown'} />
          <StatusBlock label="TTS" value={health?.tts || 'unknown'} />
          <StatusBlock label="Wake Word" value={health?.wake_word || 'unknown'} />
          <StatusBlock label="Emotion" value={health?.emotion || 'unknown'} />
        </div>
      </motion.section>

      {config && (
        <motion.section variants={itemVariants}>
          <div className="hud-label mb-4">Configuration</div>
          <div className="grid grid-cols-1 gap-px bg-[var(--j-border)] md:grid-cols-2">
            <ConfigBlock label="STT Provider" value={config.stt_provider} />
            <ConfigBlock label="TTS Provider" value={config.tts_provider} />
            <ConfigBlock label="Language" value={config.language} />
            <ConfigBlock label="Wake Word" value={config.wake_word_enabled ? 'Enabled' : 'Disabled'} />
            <ConfigBlock label="Emotion Detection" value={config.voice_emotion_enabled ? 'Enabled' : 'Disabled'} />
          </div>
        </motion.section>
      )}
    </motion.div>
  );
}

function StatusBlock({ label, value }: { label: string; value: string }) {
  const ok = value === 'healthy' || value === 'available';
  return (
    <div className="bg-[var(--j-surface)] p-5">
      <div className="flex items-center justify-between">
        <span className="font-mono text-xs uppercase tracking-[0.12em] text-[var(--j-text-dim)]">{label}</span>
        <span className="font-display text-lg tracking-[0.08em]" style={{ color: ok ? '#28c840' : 'var(--j-gold)' }}>{value}</span>
      </div>
    </div>
  );
}

function ConfigBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-[var(--j-surface)] p-5">
      <div className="text-xs text-[var(--j-text-dim)]">{label}</div>
      <div className="mt-1 font-display text-xl tracking-[0.08em] text-[var(--j-text)]">{value}</div>
    </div>
  );
}
