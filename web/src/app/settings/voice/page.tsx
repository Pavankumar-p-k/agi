'use client';

import { useEffect, useState, useCallback } from 'react';
import { motion, type Variants } from 'framer-motion';
import Badge from '@/components/ui/Badge';
import Button from '@/components/ui/Button';
import { Skeleton } from '@/components/ui/Skeleton';
import { api, type Setting } from '@/lib/api';

const containerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.06, delayChildren: 0.08 } },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 28 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.62, ease: [0.16, 1, 0.3, 1] } },
};

export default function VoiceSettingsPage() {
  const [settings, setSettings] = useState<Setting[]>([]);
  const [loading, setLoading] = useState(true);
  const [providers, setProviders] = useState<string[]>([]);
  const [diagnostics, setDiagnostics] = useState<any>(null);
  const [error, setError] = useState('');

  const fetchAll = useCallback(async () => {
    setError('');
    try {
      const [s, p, d] = await Promise.all([
        api.voice.settings().catch(() => []),
        api.voice.providers().catch(() => ({ providers: [] })),
        api.voice.diagnostics().catch(() => null),
      ]);
      setSettings(s);
      setProviders(p.providers);
      setDiagnostics(d);
    } catch (e) {
      console.warn('[VoiceSettings] fetch failed', e);
      setError('Failed to load voice settings');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const updateSetting = async (key: string, value: any) => {
    try {
      await api.settings.update(key, value);
      setSettings(prev => prev.map(s => s.key === key ? { ...s, value } : s));
    } catch (e) {
      setError(`Failed to update ${key}`);
    }
  };

  if (loading) return <div className="hud-page p-6"><Skeleton /></div>;

  return (
    <motion.div variants={containerVariants} initial="hidden" animate="visible" className="hud-page h-full overflow-y-auto space-y-6 p-6">
      <motion.section variants={itemVariants} className="hud-panel hud-scan-box p-6 md:p-8">
        <div className="hud-label">Audio Interface</div>
        <h1 className="hud-title mt-2 text-6xl md:text-7xl">Voice <span className="text-[var(--j-sky)]">Settings</span></h1>
        <p className="mt-4 max-w-2xl text-sm leading-7 text-[var(--j-text-dim)]">
          Configure speech-to-text, text-to-speech, wake word detection, and audio processing.
        </p>
      </motion.section>

      {error && (
        <motion.div variants={itemVariants} className="border border-red-500/30 bg-red-500/5 px-5 py-3">
          <p className="text-xs text-red-400">{error}</p>
        </motion.div>
      )}

      <motion.section variants={itemVariants} className="grid grid-cols-1 gap-px bg-[var(--j-border)] lg:grid-cols-2">
        <div className="bg-[var(--j-surface)] p-6 space-y-6">
          <div className="hud-label">Providers</div>
          <div className="space-y-4">
            <div>
              <label className="block text-[10px] uppercase tracking-widest text-[var(--j-text-muted)] mb-2">STT Provider</label>
              <select
                className="w-full bg-[var(--j-bg)] border border-[var(--j-border)] px-3 py-2 text-sm text-[var(--j-text)] outline-none"
                value={String(settings.find(s => s.key === 'voice.stt_provider')?.value || '')}
                onChange={(e) => updateSetting('voice.stt_provider', e.target.value)}
              >
                {providers.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-[10px] uppercase tracking-widest text-[var(--j-text-muted)] mb-2">TTS Provider</label>
              <select
                className="w-full bg-[var(--j-bg)] border border-[var(--j-border)] px-3 py-2 text-sm text-[var(--j-text)] outline-none"
                value={String(settings.find(s => s.key === 'voice.tts_provider')?.value || '')}
                onChange={(e) => updateSetting('voice.tts_provider', e.target.value)}
              >
                {providers.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
          </div>
        </div>

        <div className="bg-[var(--j-surface)] p-6 space-y-6">
          <div className="hud-label">Diagnostics</div>
          <div className="space-y-3 font-mono text-xs">
            <DiagLine label="Microphone" ok={diagnostics?.microphone} />
            <DiagLine label="Speaker" ok={diagnostics?.speaker} />
            <DiagLine label="STT Online" ok={diagnostics?.stt_available} />
            <DiagLine label="TTS Online" ok={diagnostics?.tts_available} />
            <DiagLine label="Wake Word" ok={diagnostics?.wake_word_available} />
          </div>
          <Button variant="ghost" size="sm" onClick={fetchAll}>Run Diagnostics</Button>
        </div>
      </motion.section>
    </motion.div>
  );
}

function DiagLine({ label, ok }: { label: string; ok: boolean | undefined }) {
  return (
    <div className="flex items-center justify-between border-b border-[var(--j-border)] py-2">
      <span className="text-[var(--j-text-dim)]">{label}</span>
      <span style={{ color: ok ? '#28c840' : '#ff4757' }}>{ok === undefined ? 'CHECKING...' : ok ? 'READY' : 'OFFLINE'}</span>
    </div>
  );
}
