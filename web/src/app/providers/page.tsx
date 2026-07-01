'use client';

import { useEffect, useState, useCallback } from 'react';
import { api } from '@/lib/api';

/* ── Known Internal Providers (static — always registered by bootstrap) ── */

const INTERNAL_PROVIDERS = [
  { id: 'forge', name: 'Forge', capability: 'coding', description: 'Code generation, refactoring, debugging, building' },
  { id: 'browser', name: 'BrowserProvider', capability: 'browser', description: 'Web navigation, search, browsing' },
  { id: 'research', name: 'ResearchProvider', capability: 'research', description: 'Research, fact extraction, analysis' },
  { id: 'automation', name: 'AutomationProvider', capability: 'automation', description: 'Workflows, scheduling, pipelines' },
  { id: 'messaging', name: 'MessagingProvider', capability: 'messaging', description: 'Notifications, messaging, broadcast' },
  { id: 'deployment', name: 'DeploymentProvider', capability: 'deployment', description: 'Deploy, publish, docker, rollback' },
  { id: 'workspace', name: 'WorkspaceProvider', capability: 'workspace', description: 'Desktop state, clipboard, system stats' },
  { id: 'github', name: 'GitHubProvider', capability: 'github', description: 'Git, PRs, code review, CI/CD' },
  { id: 'email', name: 'EmailProvider', capability: 'email', description: 'Send email, compose, attachments' },
];

const CAPABILITY_MAP: { capability: string; icon: string; providers: string[] }[] = [
  { capability: 'Coding', icon: '⊚', providers: ['forge'] },
  { capability: 'Browser', icon: '◈', providers: ['browser'] },
  { capability: 'Research', icon: '◎', providers: ['research'] },
  { capability: 'Automation', icon: '⟁', providers: ['automation'] },
  { capability: 'Messaging', icon: '⇌', providers: ['messaging'] },
  { capability: 'Deployment', icon: '⚒', providers: ['deployment'] },
  { capability: 'Workspace', icon: '⊞', providers: ['workspace'] },
  { capability: 'GitHub', icon: '⌘', providers: ['github'] },
  { capability: 'Email', icon: '✉', providers: ['email'] },
];

/* ── Model Provider Names ── */

const MODEL_PROVIDER_LABELS: Record<string, string> = {
  ollama: 'Ollama',
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  gemini: 'Gemini',
  groq: 'Groq',
  openrouter: 'OpenRouter',
};

/* ── Helpers ── */

function fmtMs(ms: number): string {
  if (ms < 1) return '<1ms';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/* ── Provider Card ── */

function ProviderCard({
  id,
  name,
  capability,
  description,
  healthy,
  latency,
  statusText,
  priority,
  model,
  error,
}: {
  id: string;
  name: string;
  capability: string;
  description?: string;
  healthy?: boolean;
  latency?: number;
  statusText?: string;
  priority?: number;
  model?: string | null;
  error?: string | null;
}) {
  const health = healthy === true ? 'healthy' : healthy === false ? 'degraded' : 'unknown';
  const dotColor = health === 'healthy' ? 'var(--j-green)' : health === 'degraded' ? '#ff4757' : 'var(--j-text-muted)';
  const shadowColor = health === 'healthy' ? 'rgba(74,222,128,0.5)' : health === 'degraded' ? 'rgba(255,71,87,0.5)' : 'transparent';

  return (
    <div
      className="px-4 py-3.5 space-y-2.5"
      style={{
        border: `1px solid ${health === 'healthy' ? 'rgba(74,222,128,0.15)' : 'var(--j-border)'}`,
        borderRadius: 'var(--j-radius-md)',
        background: health === 'healthy' ? 'rgba(74,222,128,0.03)' : 'transparent',
      }}
    >
      {/* Header */}
      <div className="flex items-center gap-2.5">
        <div className="w-2 h-2 rounded-full shrink-0" style={{ background: dotColor, boxShadow: `0 0 6px ${shadowColor}` }} />
        <div className="flex-1 min-w-0">
          <div className="text-sm font-mono truncate" style={{ color: 'var(--j-text)' }}>{name}</div>
          <div className="text-[10px] font-mono uppercase tracking-[0.12em] mt-0.5" style={{ color: 'var(--j-text-muted)' }}>{id}</div>
        </div>
        {priority !== undefined && (
          <div className="text-[10px] font-mono px-2 py-0.5" style={{ border: '1px solid var(--j-border)', borderRadius: 'var(--j-radius-sm)', color: 'var(--j-text-dim)' }}>
            P{priority}
          </div>
        )}
      </div>

      {/* Capability */}
      <div className="text-[11px]" style={{ color: 'var(--j-text-dim)' }}>
        <span className="font-mono uppercase tracking-[0.12em] text-[10px]" style={{ color: 'var(--j-sky)' }}>{capability}</span>
        {description && <span className="ml-2">{description}</span>}
      </div>

      {/* Stats row */}
      <div className="flex items-center gap-3 text-[10px] font-mono" style={{ color: 'var(--j-text-muted)' }}>
        <span className="uppercase tracking-[0.12em]" style={{ color: health === 'healthy' ? 'var(--j-green)' : health === 'degraded' ? '#ff4757' : 'var(--j-text-muted)' }}>
          {health}
        </span>
        {latency !== undefined && <span>{fmtMs(latency)}</span>}
        {model && <span className="truncate">{model}</span>}
        {statusText && <span>{statusText}</span>}
      </div>

      {/* Error */}
      {error && (
        <div className="text-[10px] font-mono mt-1" style={{ color: '#ff4757' }}>
          {error}
        </div>
      )}
    </div>
  );
}

/* ── Capability Row ── */

function CapabilityRow({ capability, icon, providers }: { capability: string; icon: string; providers: string[] }) {
  return (
    <div
      className="flex items-center gap-3 px-4 py-2.5"
      style={{ border: '1px solid var(--j-border)', borderRadius: 'var(--j-radius-sm)' }}
    >
      <span className="text-base w-5 text-center shrink-0" style={{ color: 'var(--j-sky)' }}>{icon}</span>
      <span className="text-xs font-mono uppercase tracking-[0.12em] w-24 shrink-0" style={{ color: 'var(--j-text)' }}>{capability}</span>
      <div className="flex-1" />
      {providers.map(pid => {
        const p = INTERNAL_PROVIDERS.find(x => x.id === pid);
        return p ? (
          <span
            key={pid}
            className="text-[10px] font-mono px-2 py-0.5"
            style={{ border: '1px solid rgba(74,222,128,0.2)', borderRadius: 'var(--j-radius-sm)', color: 'var(--j-green)', background: 'rgba(74,222,128,0.05)' }}
          >
            {p.name}
          </span>
        ) : null;
      })}
      <span className="text-[10px] font-mono" style={{ color: 'var(--j-text-muted)' }}>→</span>
    </div>
  );
}

/* ── Types ── */

interface ModelProviderHealth {
  name: string;
  available: boolean;
  healthy: boolean;
  latency_ms: number;
  error: string | null;
  model: string | null;
}

interface FailoverProfile {
  name: string;
  provider: string;
  priority: number;
  healthy: boolean;
  cooldown_remaining_s: number;
  failures: number;
}

/* ── Provider Manager Page ── */

export default function ProvidersPage() {
  const [modelProviders, setModelProviders] = useState<ModelProviderHealth[]>([]);
  const [failover, setFailover] = useState<{ enabled: boolean; profiles: FailoverProfile[] } | null>(null);
  const [modelGroups, setModelGroups] = useState<Record<string, string>>({});
  const [ollamaStatus, setOllamaStatus] = useState<{ available: boolean; models: number }>({ available: false, models: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [initialLoad, setInitialLoad] = useState(true);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const [diagModels, failoverRes, modelGroupsRes, modelsRes] = await Promise.all([
        api.diagnostics.models().catch(() => ({ providers: [] as ModelProviderHealth[] })),
        api.infrastructure.failover().catch(() => null),
        api.models.groups().catch(() => ({ groups: {} as Record<string, string> })),
        api.models.list().catch(() => null),
      ]);

      setModelProviders(diagModels.providers);
      if (failoverRes) setFailover(failoverRes);
      setModelGroups(modelGroupsRes.groups);
      if (modelsRes) setOllamaStatus({ available: modelsRes.ollama_available, models: modelsRes.total });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load provider data. The server might be starting up or unreachable.');
    }

    setLoading(false);
    if (initialLoad) setInitialLoad(false);
  }, [initialLoad]);

  useEffect(() => {
    fetchAll();
    const iv = setInterval(fetchAll, 30000);
    return () => clearInterval(iv);
  }, [fetchAll]);

  /* ── Compute overview counts ── */
  const healthyCount = modelProviders.filter(p => p.healthy).length;
  const degradedCount = modelProviders.filter(p => !p.healthy && p.available).length;
  const disabledCount = modelProviders.filter(p => !p.available).length;
  const totalCount = INTERNAL_PROVIDERS.length + modelProviders.length;

  /* ── Find matching health for known model providers ── */
  const getModelHealth = (name: string) => modelProviders.find(p => p.name === name);

  return (
    <div className="mx-auto max-w-4xl space-y-10 pb-12">

      {/* ── Overview ── */}
      <section>
        <div className="flex items-center gap-2 mb-4">
            <h2 className="text-xs tracking-[0.12em] uppercase m-0" style={{ color: 'var(--j-text-muted)' }}>Overview</h2>
          <span className="h-px flex-1" style={{ background: 'var(--j-border)' }} />
        </div>

        <div
          className="grid grid-cols-4 gap-3"
        >
          {([
            { label: 'Loaded', value: `${totalCount}`, color: 'var(--j-sky)' },
            { label: 'Healthy', value: `${healthyCount + INTERNAL_PROVIDERS.length}`, color: 'var(--j-green)' },
            { label: 'Degraded', value: `${degradedCount}`, color: 'var(--j-gold)' },
            { label: 'Disabled', value: `${disabledCount}`, color: 'var(--j-text-muted)' },
          ]).map(item => (
            <div
              key={item.label}
              className="px-4 py-3 text-center"
              style={{ border: '1px solid var(--j-border)', borderRadius: 'var(--j-radius-md)' }}
            >
              <div className="text-lg font-mono" style={{ color: item.color }}>{item.value}</div>
              <div className="text-[10px] font-mono uppercase tracking-[0.12em] mt-1" style={{ color: 'var(--j-text-muted)' }}>{item.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Capability Graph ── */}
      <section>
        <div className="flex items-center gap-2 mb-4">
            <h2 className="text-xs tracking-[0.12em] uppercase m-0" style={{ color: 'var(--j-text-muted)' }}>Capability Graph</h2>
          <span className="h-px flex-1" style={{ background: 'var(--j-border)' }} />
          <span className="text-[10px] font-mono" style={{ color: 'var(--j-text-muted)' }}>{CAPABILITY_MAP.length}</span>
        </div>

        <div className="space-y-1.5">
          {CAPABILITY_MAP.map(c => (
            <CapabilityRow key={c.capability} {...c} />
          ))}
        </div>
        <p className="text-[10px] font-mono mt-2" style={{ color: 'var(--j-text-muted)' }}>
          Each capability is served by its registered internal provider. External providers (claude-code, codex) are registered if installed.
        </p>
      </section>

      {/* ── Internal Provider Cards ── */}
      <section>
        <div className="flex items-center gap-2 mb-4">
            <h2 className="text-xs tracking-[0.12em] uppercase m-0" style={{ color: 'var(--j-text-muted)' }}>Internal Providers</h2>
          <span className="h-px flex-1" style={{ background: 'var(--j-border)' }} />
          <span className="text-[10px] font-mono" style={{ color: 'var(--j-text-muted)' }}>{INTERNAL_PROVIDERS.length}</span>
        </div>

        <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-3">
          {INTERNAL_PROVIDERS.map(p => (
            <ProviderCard key={p.id} id={p.id} name={p.name} capability={p.capability} description={p.description} priority={10} />
          ))}
        </div>
      </section>

      {/* ── Model Provider Health ── */}
      <section>
        <div className="flex items-center gap-2 mb-4">
            <h2 className="text-xs tracking-[0.12em] uppercase m-0" style={{ color: 'var(--j-text-muted)' }}>Model Providers</h2>
          <span className="h-px flex-1" style={{ background: 'var(--j-border)' }} />
          <span className="text-[10px] font-mono" style={{ color: 'var(--j-text-muted)' }}>{modelProviders.length}</span>
        </div>

        {modelProviders.length === 0 ? (
          <div
            className="text-center py-10 px-6"
            style={{ border: '1px dashed var(--j-border)', borderRadius: 'var(--j-radius-md)' }}
          >
            <p className="text-sm font-mono mb-2" style={{ color: 'var(--j-text-dim)' }}>No model providers detected</p>
            <p className="text-xs leading-relaxed" style={{ color: 'var(--j-text-muted)' }}>
              Install{' '}
              <a href="https://ollama.ai" target="_blank" rel="noopener noreferrer"
                className="underline underline-offset-2" style={{ color: 'var(--j-sky)' }}>
                Ollama
              </a>
              {' '}for local models, or configure API keys in{' '}
              <span className="font-mono" style={{ color: 'var(--j-sky)' }}>Settings → Providers</span>
              {' '}for OpenAI, Anthropic, Gemini, or Groq.
            </p>
          </div>
        ) : (
          <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-3">
            {modelProviders.map(mp => (
              <ProviderCard
                key={mp.name}
                id={mp.name}
                name={MODEL_PROVIDER_LABELS[mp.name] || mp.name}
                capability="llm"
                healthy={mp.healthy}
                latency={mp.latency_ms}
                model={mp.model}
                error={mp.error}
                priority={mp.name === 'ollama' ? 10 : mp.name === 'openai' ? 20 : 30}
              />
            ))}
          </div>
        )}
      </section>

      {/* ── Model Groups (Routing) ── */}
      {Object.keys(modelGroups).length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-4">
            <h2 className="text-xs tracking-[0.12em] uppercase m-0" style={{ color: 'var(--j-text-muted)' }}>Model Groups</h2>
            <span className="h-px flex-1" style={{ background: 'var(--j-border)' }} />
            <span className="text-[10px] font-mono" style={{ color: 'var(--j-text-muted)' }}>{Object.keys(modelGroups).length}</span>
          </div>

          <div className="space-y-1.5">
            {Object.entries(modelGroups).map(([group, model]) => (
              <div
                key={group}
                className="flex items-center gap-3 px-4 py-2.5"
                style={{ border: '1px solid var(--j-border)', borderRadius: 'var(--j-radius-sm)' }}
              >
                <span className="text-xs font-mono uppercase tracking-[0.12em] w-28 shrink-0" style={{ color: 'var(--j-text)' }}>{group}</span>
                <span className="h-px flex-1" style={{ background: 'var(--j-border)' }} />
                <span className="text-[11px] font-mono" style={{ color: 'var(--j-sky)' }}>{model}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Failover Profiles ── */}
      {failover && (
        <section>
          <div className="flex items-center gap-2 mb-4">
            <h2 className="text-xs tracking-[0.12em] uppercase m-0" style={{ color: 'var(--j-text-muted)' }}>Failover</h2>
            <span className="h-px flex-1" style={{ background: 'var(--j-border)' }} />
            <span
              className="text-[10px] font-mono px-2 py-0.5"
              style={{
                border: '1px solid',
                borderColor: failover.enabled ? 'rgba(74,222,128,0.3)' : 'var(--j-border)',
                borderRadius: 'var(--j-radius-sm)',
                color: failover.enabled ? 'var(--j-green)' : 'var(--j-text-muted)',
                background: failover.enabled ? 'rgba(74,222,128,0.05)' : 'transparent',
              }}
            >
              {failover.enabled ? 'Enabled' : 'Disabled'}
            </span>
          </div>

          <div className="space-y-2">
            {failover.profiles.length === 0 ? (
              <p className="text-xs text-center py-6" style={{ color: 'var(--j-text-muted)' }}>No failover profiles configured.</p>
            ) : (
              failover.profiles.map(fp => {
                const health = getModelHealth(fp.provider);
                return (
                  <div
                    key={fp.name}
                    className="flex items-center gap-3 px-4 py-2.5"
                    style={{ border: '1px solid var(--j-border)', borderRadius: 'var(--j-radius-md)' }}
                  >
                    <div
                      className="w-1.5 h-1.5 rounded-full shrink-0"
                      style={{
                        background: fp.healthy ? 'var(--j-green)' : '#ff4757',
                        boxShadow: fp.healthy ? '0 0 6px rgba(74,222,128,0.5)' : '0 0 6px rgba(255,71,87,0.5)',
                      }}
                    />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-mono truncate" style={{ color: 'var(--j-text)' }}>{fp.name}</div>
                      <div className="text-[10px] font-mono mt-0.5" style={{ color: 'var(--j-text-muted)' }}>
                        {fp.provider} · Priority {fp.priority}
                      </div>
                    </div>
                    <div className="flex items-center gap-3 text-[10px] font-mono" style={{ color: 'var(--j-text-muted)' }}>
                      {fp.cooldown_remaining_s > 0 && (
                        <span style={{ color: 'var(--j-gold)' }}>Cooldown {fp.cooldown_remaining_s}s</span>
                      )}
                      {fp.failures > 0 && (
                        <span style={{ color: '#ff4757' }}>{fp.failures} failures</span>
                      )}
                      <span style={{ color: fp.healthy ? 'var(--j-green)' : '#ff4757' }}>
                        {fp.healthy ? 'Healthy' : 'Down'}
                      </span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </section>
      )}

      {/* ── Ollama ── */}
      {ollamaStatus.available && (
        <section>
          <div className="flex items-center gap-2 mb-4">
            <h2 className="text-xs tracking-[0.12em] uppercase m-0" style={{ color: 'var(--j-text-muted)' }}>Ollama</h2>
            <span className="h-px flex-1" style={{ background: 'var(--j-border)' }} />
          </div>
          <div
            className="flex items-center gap-3 px-4 py-3"
            style={{ border: '1px solid rgba(74,222,128,0.15)', borderRadius: 'var(--j-radius-md)', background: 'rgba(74,222,128,0.03)' }}
          >
            <div className="w-2 h-2 rounded-full shrink-0" style={{ background: 'var(--j-green)', boxShadow: '0 0 6px rgba(74,222,128,0.5)' }} />
            <span className="text-sm font-mono" style={{ color: 'var(--j-text)' }}>Ollama available</span>
            <span className="text-xs font-mono" style={{ color: 'var(--j-text-muted)' }}>{ollamaStatus.models} models loaded</span>
          </div>
        </section>
      )}

      {/* ── Error State ── */}
      {error && !loading && (
        <div
          className="text-center py-8 px-6"
          style={{ border: '1px solid rgba(255,71,87,0.2)', borderRadius: 'var(--j-radius-md)', background: 'rgba(255,71,87,0.04)' }}
        >
          <p className="text-xs font-mono mb-3" style={{ color: '#ff4757' }}>{error}</p>
          <button
            onClick={fetchAll}
            className="text-[9px] font-mono uppercase tracking-[0.12em] px-2 py-1 transition-all hover:opacity-80"
            style={{ border: '1px solid var(--j-border)', borderRadius: 'var(--j-radius-sm)', color: 'var(--j-text-dim)' }}
          >
            Retry
          </button>
        </div>
      )}

      {/* ── Loading Skeleton ── */}
      {initialLoad && loading && (
        <div className="space-y-4 animate-pulse">
          <div className="h-16 rounded-md" style={{ background: 'rgba(var(--j-bg-rgb),0.4)' }} />
          <div className="h-16 rounded-md" style={{ background: 'rgba(var(--j-bg-rgb),0.4)' }} />
          <div className="h-16 rounded-md" style={{ background: 'rgba(var(--j-bg-rgb),0.4)' }} />
          <p className="text-[10px] font-mono text-center mt-4" style={{ color: 'var(--j-text-muted)' }}>
            Loading provider data…
          </p>
        </div>
      )}

      {/* ── Auto-refresh indicator ── */}
      {!initialLoad && (
        <div className="text-center">
          <span
            className="text-[9px] font-mono tracking-[0.12em]"
            style={{ color: 'var(--j-text-muted)' }}
          >
            Auto-refreshes every 30s · {new Date().toLocaleTimeString()}
          </span>
        </div>
      )}
    </div>
  );
}
