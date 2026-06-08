'use client';

import { useEffect, useState } from 'react';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';

interface ToggleProps {
  label: string;
  desc: string;
  value: boolean;
  onChange: (v: boolean) => void;
}

function Toggle({ label, desc, value, onChange }: ToggleProps) {
  return (
    <button
      onClick={() => onChange(!value)}
      className="group grid w-full grid-cols-[1fr_auto] items-center gap-4 border border-[var(--j-border)] bg-[var(--j-surface)] px-5 py-4 text-left transition-all hover:border-[var(--j-border-bright)] hover:bg-[var(--j-surface-hover)]"
    >
      <div>
        <div className="font-display text-2xl tracking-[0.08em] text-[var(--j-text)]">{label}</div>
        <div className="mt-1 text-xs leading-5 text-[var(--j-text-dim)]">{desc}</div>
      </div>
      <span className="relative h-6 w-12 border border-[var(--j-border)] bg-[var(--j-bg)]">
        <span
          className="absolute top-1 h-4 w-4 transition-all"
          style={{
            left: value ? '26px' : '4px',
            background: value ? 'var(--j-sky)' : 'var(--j-text-muted)',
            boxShadow: value ? '0 0 12px var(--j-sky)' : 'none',
          }}
        />
      </span>
    </button>
  );
}

interface SettingsPrefs {
  notifications: boolean;
  soundEffects: boolean;
  autoScrollLogs: boolean;
  markdownEnabled: boolean;
  compactMode: boolean;
  showTimestamps: boolean;
}

const DEFAULTS: SettingsPrefs = {
  notifications: true,
  soundEffects: false,
  autoScrollLogs: true,
  markdownEnabled: true,
  compactMode: false,
  showTimestamps: true,
};

export default function SettingsPage() {
  const [prefs, setPrefs] = useState<SettingsPrefs>(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('jarvis:settings');
      if (saved) {
        try { return { ...DEFAULTS, ...JSON.parse(saved) }; } catch { return { ...DEFAULTS }; }
      }
    }
    return { ...DEFAULTS };
  });
  const [health, setHealth] = useState<{ status: string; version?: string } | null>(null);

  useEffect(() => {
    localStorage.setItem('jarvis:settings', JSON.stringify(prefs));
  }, [prefs]);

  useEffect(() => {
    fetch('/api/health').then(r => r.ok ? r.json() : null).then(d => setHealth(d)).catch(() => setHealth(null));
  }, []);

  const update = (key: keyof typeof prefs) => (v: boolean) => setPrefs(prev => ({ ...prev, [key]: v }));

  return (
    <div className="hud-page h-full overflow-y-auto space-y-6">
      <section className="hud-panel hud-scan-box p-6 md:p-8">
        <div className="relative z-[1]">
          <div className="hud-label">Control Matrix</div>
          <h1 className="hud-title mt-2 text-6xl md:text-7xl">Settings <span className="text-[var(--j-sky)]">Core</span></h1>
          <p className="mt-4 max-w-2xl text-sm leading-7 text-[var(--j-text-dim)]">
            Tune the JARVIS browser shell, interaction behavior, and visual engines from one hardened panel.
          </p>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-px bg-[var(--j-border)] md:grid-cols-2">
        <Card variant="sky" onClick={() => window.location.href = '/settings/themes'} className="min-h-44 rounded-none">
          <div className="hud-label mb-4">Appearance</div>
          <h2 className="font-display text-4xl tracking-[0.08em]">Theme Studio</h2>
          <p className="mt-3 text-sm leading-6 text-[var(--j-text-dim)]">Four visual modes, live token editor, export/import, and swatches.</p>
        </Card>
        <Card variant="deep" onClick={() => window.location.href = '/settings/fonts'} className="min-h-44 rounded-none">
          <div className="hud-label mb-4">Typography</div>
          <h2 className="font-display text-4xl tracking-[0.08em]">Font Engine</h2>
          <p className="mt-3 text-sm leading-6 text-[var(--j-text-dim)]">Outfit, DM Mono, and Bebas Neue mapped to exact HUD usage.</p>
        </Card>
      </section>

      <section>
        <div className="mb-4 flex items-center justify-between">
          <div className="hud-label">Preferences</div>
          <Badge variant="new">Local Storage</Badge>
        </div>
        <div className="grid grid-cols-1 gap-px bg-[var(--j-border)] lg:grid-cols-2">
          <Toggle label="Notifications" desc="Push notifications for background tasks" value={prefs.notifications} onChange={update('notifications')} />
          <Toggle label="Sound Effects" desc="Audio feedback on events and alerts" value={prefs.soundEffects} onChange={update('soundEffects')} />
          <Toggle label="Auto-scroll Logs" desc="Follow new log entries automatically" value={prefs.autoScrollLogs} onChange={update('autoScrollLogs')} />
          <Toggle label="Markdown Rendering" desc="Render markdown in chat messages" value={prefs.markdownEnabled} onChange={update('markdownEnabled')} />
          <Toggle label="Compact Mode" desc="Reduced spacing in chat and lists" value={prefs.compactMode} onChange={update('compactMode')} />
          <Toggle label="Show Timestamps" desc="Display message timestamps in chat" value={prefs.showTimestamps} onChange={update('showTimestamps')} />
        </div>
      </section>

      <section className="hud-panel p-5">
        <div className="hud-label mb-4">About</div>
        <div className="grid grid-cols-1 gap-4 font-mono text-xs text-[var(--j-text-dim)] md:grid-cols-3">
          <div>WEB UI <span className="text-[var(--j-sky)]">v1.0.0</span></div>
          <div>API <span className="text-[var(--j-gold)]">{health?.version ? `v${health.version}` : 'local'}</span></div>
          <div>STATUS <span style={{ color: health?.status === 'healthy' ? '#28c840' : '#ff4757' }}>{health?.status || 'unknown'}</span></div>
        </div>
      </section>
    </div>
  );
}
