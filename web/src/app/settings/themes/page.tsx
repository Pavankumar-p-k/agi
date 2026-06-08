'use client';

import { useState, useCallback, useRef } from 'react';
import { useThemeStore, type ThemeId } from '@/stores/themeStore';
import Button from '@/components/ui/Button';
import Badge from '@/components/ui/Badge';
import { useToastStore } from '@/stores/toastStore';

const THEME_DATA: { id: ThemeId; label: string; sub: string; colors: string[]; desc: string }[] = [
  {
    id: 'sky',
    label: 'JARVIS Default',
    sub: 'Sky + Deep Navy',
    colors: ['#020406', '#0a2b45', '#0d3a6b', '#1a6fa8', '#00d2ff'],
    desc: 'Cinematic HUD dark mode with cyan scanlines, glass panels, and high-contrast operations.',
  },
  {
    id: 'phantom',
    label: 'Phantom Dark',
    sub: 'Void + Violet OLED',
    colors: ['#050508', '#0d0d1f', '#1a1040', '#4c2db0', '#a78bfa'],
    desc: 'OLED-heavy violet interface for late-night command work and premium console feel.',
  },
  {
    id: 'arctic',
    label: 'Arctic Light',
    sub: 'Ice + Enterprise Day',
    colors: ['#f0f4f8', '#dde8f0', '#b3cfe0', '#6098c0', '#1d5fa8'],
    desc: 'Bright operational mode with restrained blues for daytime dashboards and reports.',
  },
  {
    id: 'ember',
    label: 'Ember',
    sub: 'Coal + Gold Flame',
    colors: ['#0a0702', '#1a1008', '#2e1a08', '#ff6b35', '#f5c842'],
    desc: 'Warm high-contrast shell with gold telemetry accents and molten warning states.',
  },
];

const EDITABLE_VARS = [
  { key: '--j-sky', label: 'Accent', fallback: '#00d2ff' },
  { key: '--j-gold', label: 'Gold', fallback: '#f5c842' },
  { key: '--j-bg', label: 'Background', fallback: '#020406' },
  { key: '--j-surface', label: 'Surface', fallback: '#0f1e2d' },
  { key: '--j-text', label: 'Text', fallback: '#e8f4ff' },
  { key: '--j-border', label: 'Border', fallback: '#003344' },
];

function safeColor(value: string, fallback: string) {
  return /^#[0-9a-f]{6}$/i.test(value) ? value : fallback;
}

export default function ThemesPage() {
  const { theme, setTheme, customVars, setCustomVar, resetCustomVars } = useThemeStore();
  const [mode, setMode] = useState<'themes' | 'tokens'>('themes');
  const importRef = useRef<HTMLInputElement>(null);
  const addToast = useToastStore(s => s.addToast);

  const getVal = (key: string, fallback: string) => customVars[key] || fallback;

  const exportTheme = useCallback(() => {
    const data = JSON.stringify({ theme, customVars, exportedAt: new Date().toISOString() }, null, 2);
    const blob = new Blob([data], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `jarvis-theme-${theme}.json`;
    a.click();
    URL.revokeObjectURL(url);
    addToast('Theme exported', 'success');
  }, [theme, customVars, addToast]);

  const importTheme = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const data = JSON.parse(ev.target?.result as string);
        if (data.theme) setTheme(data.theme as ThemeId);
        if (data.customVars) {
          Object.entries(data.customVars).forEach(([k, v]) => setCustomVar(k, v as string));
        }
        addToast('Theme imported', 'success');
      } catch {
        addToast('Invalid theme file', 'error');
      }
    };
    reader.readAsText(file);
    e.target.value = '';
  }, [setTheme, setCustomVar, addToast]);

  const copyCSS = useCallback(() => {
    const lines = EDITABLE_VARS.map(s => `  ${s.key}: ${getVal(s.key, s.fallback)};`).join('\n');
    navigator.clipboard.writeText(`:root {\n${lines}\n}`);
    addToast('CSS copied', 'success');
  }, [customVars, addToast]);

  return (
    <div className="hud-page h-full overflow-y-auto space-y-6">
      <input ref={importRef} type="file" accept=".json" onChange={importTheme} className="hidden" />

      <section className="hud-panel hud-scan-box p-6 md:p-8">
        <div className="relative z-[1] flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="hud-label">Visual Identity</div>
            <h1 className="hud-title mt-2 text-6xl md:text-7xl">Theme <span className="text-[var(--j-sky)]">Studio</span></h1>
            <p className="mt-4 max-w-2xl text-sm leading-7 text-[var(--j-text-dim)]">Switch palettes, tune live CSS variables, and export your JARVIS skin.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant={mode === 'themes' ? 'primary' : 'ghost'} size="sm" onClick={() => setMode('themes')}>Themes</Button>
            <Button variant={mode === 'tokens' ? 'primary' : 'ghost'} size="sm" onClick={() => setMode('tokens')}>Tokens</Button>
          </div>
        </div>
      </section>

      {mode === 'themes' && (
        <section className="grid grid-cols-1 gap-px bg-[var(--j-border)] md:grid-cols-2 xl:grid-cols-4">
          {THEME_DATA.map(t => (
            <button
              key={t.id}
              onClick={() => setTheme(t.id)}
              className="group min-h-[250px] bg-[var(--j-surface)] p-5 text-left transition-all hover:bg-[var(--j-surface-hover)]"
            >
              <div className="mb-6 flex gap-1">
                {t.colors.map(c => <span key={c} className="h-14 flex-1 border-t-2" style={{ background: c, borderColor: c }} />)}
              </div>
              <div className="flex items-center justify-between gap-2">
                <h2 className="font-display text-3xl tracking-[0.08em]">{t.label}</h2>
                {theme === t.id && <Badge variant="new">Active</Badge>}
              </div>
              <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.16em] text-[var(--j-sky)]">{t.sub}</div>
              <p className="mt-4 text-xs leading-6 text-[var(--j-text-dim)]">{t.desc}</p>
            </button>
          ))}
        </section>
      )}

      {mode === 'tokens' && (
        <section className="grid grid-cols-1 gap-px bg-[var(--j-border)] xl:grid-cols-[1fr_0.8fr]">
          <div className="bg-[var(--j-surface)] p-5">
            <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="hud-label">Live Tokens</div>
                <p className="mt-2 text-xs text-[var(--j-text-dim)]">Inline custom variables override the current theme.</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button variant="ghost" size="sm" onClick={exportTheme}>Export</Button>
                <Button variant="ghost" size="sm" onClick={() => importRef.current?.click()}>Import</Button>
                <Button variant="ghost" size="sm" onClick={copyCSS}>Copy CSS</Button>
                <Button variant="danger" size="sm" onClick={resetCustomVars}>Reset</Button>
              </div>
            </div>
            <div className="space-y-3">
              {EDITABLE_VARS.map(v => {
                const value = getVal(v.key, v.fallback);
                return (
                  <div key={v.key} className="grid grid-cols-[120px_42px_1fr] items-center gap-3">
                    <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-[var(--j-text-dim)]">{v.label}</div>
                    <input
                      type="color"
                      value={safeColor(value, v.fallback)}
                      onChange={(e) => setCustomVar(v.key, e.target.value)}
                      className="h-9 w-10 border-0 bg-transparent"
                    />
                    <input
                      value={value}
                      onChange={(e) => setCustomVar(v.key, e.target.value)}
                      className="hud-input px-3 py-2 font-mono text-xs"
                    />
                  </div>
                );
              })}
            </div>
          </div>

          <div className="bg-[var(--j-bg)] p-5">
            <div className="hud-label mb-5">Preview</div>
            <div className="hud-panel p-5">
              <div className="mb-6 flex items-center gap-3">
                <span className="relative h-10 w-10 rotate-45 border border-[var(--j-sky)]">
                  <span className="absolute left-1/2 top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 bg-[var(--j-sky)] shadow-[0_0_16px_var(--j-sky)]" />
                </span>
                <div>
                  <div className="font-display text-3xl tracking-[0.12em]">JARVIS</div>
                  <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-[var(--j-text-dim)]">Theme online</div>
                </div>
              </div>
              <div className="mb-5 h-1.5 bg-[var(--j-border)]">
                <div className="h-full w-2/3 bg-[var(--j-sky)] shadow-[0_0_14px_var(--j-sky)]" />
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge>Chat</Badge>
                <Badge variant="hot">Monitor</Badge>
                <Badge variant="core">Vault</Badge>
              </div>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
