'use client';

import { useThemeStore } from '@/stores/themeStore';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';

const FONTS = [
  { id: 'sans' as const, label: 'Outfit', style: 'Interface', sample: 'Operational clarity', desc: 'Primary UI font for panels, chat copy, settings, and dense dashboard surfaces.' },
  { id: 'mono' as const, label: 'DM Mono', style: 'Terminal', sample: 'jarvis@core:~$', desc: 'Command palette, logs, telemetry labels, code output, and AI stream metadata.' },
  { id: 'display' as const, label: 'Bebas Neue', style: 'HUD Display', sample: 'JARVIS ONLINE', desc: 'Hero titles, KPI numerals, module headers, boot screens, and cinematic mode labels.' },
];

export default function FontsPage() {
  const { font, setFont } = useThemeStore();

  return (
    <div className="hud-page h-full overflow-y-auto space-y-6">
      <section className="hud-panel hud-scan-box p-6 md:p-8">
        <div className="relative z-[1]">
          <div className="hud-label">Typography System</div>
          <h1 className="hud-title mt-2 text-6xl md:text-7xl">Font <span className="text-[var(--j-sky)]">Engine</span></h1>
          <p className="mt-4 max-w-2xl text-sm leading-7 text-[var(--j-text-dim)]">
            Three type roles tuned for a production AI console: readable body text, surgical monospace, and cinematic display.
          </p>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-px bg-[var(--j-border)] lg:grid-cols-3">
        {FONTS.map(f => (
          <Card
            key={f.id}
            variant={font === f.id ? 'sky' : 'default'}
            onClick={() => setFont(f.id)}
            className={`min-h-[280px] rounded-none ${font === f.id ? 'ring-1 ring-[var(--j-sky)]' : ''}`}
          >
            <div className="mb-8 flex items-center justify-between">
              <Badge variant={font === f.id ? 'new' : 'default'}>{f.style}</Badge>
              {font === f.id && <span className="h-2 w-2 rounded-full bg-[#00ff88] shadow-[0_0_10px_#00ff88]" />}
            </div>
            <div
              className="mb-5 min-h-[96px] text-[clamp(34px,5vw,58px)] leading-none"
              style={{
                fontFamily: f.id === 'sans' ? 'var(--j-font-sans)' : f.id === 'mono' ? 'var(--j-font-mono)' : 'var(--j-font-display)',
                letterSpacing: f.id === 'display' ? '0.08em' : '0',
                color: f.id === 'mono' ? 'var(--j-sky)' : 'var(--j-text)',
              }}
            >
              {f.sample}
            </div>
            <h2 className="font-display text-3xl tracking-[0.08em]">{f.label}</h2>
            <p className="mt-3 text-sm leading-7 text-[var(--j-text-dim)]">{f.desc}</p>
          </Card>
        ))}
      </section>
    </div>
  );
}
