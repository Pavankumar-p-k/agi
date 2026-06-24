/* ───────────────────────────────────────────────────────────────────────────
 * OpportunityPanel — opportunity discovery, scoring, forecast, roadmap.
 *
 * Bridges Phases 17-23 into a single UI: discover opportunities from
 * 4 sources, view scored candidates, accept/reject, forecast, roadmap,
 * bottleneck analysis.
 * ─────────────────────────────────────────────────────────────────────────── */
'use client';

import { useState, useEffect, useCallback } from 'react';
import { opportunities, negotiations } from '@jarvis/sdk';
import type {
  Opportunity,
  RoadmapPhase,
  Bottleneck,
  ForecastedOpportunity,
} from '@jarvis/sdk';

function sourceColor(s: string): string {
  const m: Record<string, string> = {
    bottleneck: '#ef4444',
    ceiling: '#60a5fa',
    experiment: '#a78bfa',
    principle: '#22c55e',
  };
  return m[s] || '#8b8b8b';
}

function sourceLabel(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function scoreColor(c: number): string {
  if (c >= 0.6) return '#22c55e';
  if (c >= 0.3) return '#f5c842';
  return '#ef4444';
}

function statusColor(s: string): string {
  if (s === 'open') return '#22c55e';
  if (s === 'in_progress') return '#60a5fa';
  if (s === 'completed') return '#a78bfa';
  if (s === 'rejected') return '#ef4444';
  return '#8b8b8b';
}

type Tab = 'discoveries' | 'scores' | 'forecast' | 'roadmap' | 'bottlenecks';

export function OpportunityPanel() {
  const [tab, setTab] = useState<Tab>('discoveries');
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [list, setList] = useState<Opportunity[]>([]);
  const [scores, setScores] = useState<Record<string, number>>({});
  const [forecasts, setForecasts] = useState<ForecastedOpportunity[]>([]);
  const [roadmap, setRoadmap] = useState<RoadmapPhase[]>([]);
  const [bottlenecks, setBottlenecks] = useState<Bottleneck[]>([]);
  const [discoverResult, setDiscoverResult] = useState<{ discovered: number; total: number } | null>(null);

  const loadDiscoveries = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await opportunities.list();
      setList(data);
    } catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  }, []);

  const loadScores = useCallback(async () => {
    try {
      const data = await opportunities.scoredSystems();
      setScores(data);
    } catch (e) { /* silent */ }
  }, []);

  const loadForecasts = useCallback(async () => {
    try {
      const data = await opportunities.forecast();
      setForecasts(data);
    } catch (e) { /* silent */ }
  }, []);

  const loadRoadmap = useCallback(async () => {
    try {
      const data = await opportunities.roadmap();
      setRoadmap(data);
    } catch (e) { /* silent */ }
  }, []);

  const loadBottlenecks = useCallback(async () => {
    try {
      const data = await opportunities.bottlenecks();
      setBottlenecks(data);
    } catch (e) { /* silent */ }
  }, []);

  useEffect(() => {
    loadDiscoveries();
    loadScores();
    loadForecasts();
    loadBottlenecks();
  }, []);

  const handleDiscover = async () => {
    setActionLoading('discover');
    setError(null);
    try {
      const result = await opportunities.discover();
      setDiscoverResult(result);
      await loadDiscoveries();
    } catch (e) { setError(String(e)); }
    finally { setActionLoading(null); }
  };

  const handleAccept = async (opp: Opportunity) => {
    setActionLoading(opp.id);
    setError(null);
    try {
      const result = await opportunities.accept(opp.id, true);
      if (result.negotiation) {
        // If negotiation was created, show it
        setError(`Negotiation created: ${result.negotiation.decision}`);
      }
      await loadDiscoveries();
    } catch (e) { setError(String(e)); }
    finally { setActionLoading(null); }
  };

  const handleReject = async (id: string) => {
    setActionLoading(id);
    setError(null);
    try {
      await opportunities.reject(id);
      await loadDiscoveries();
    } catch (e) { setError(String(e)); }
    finally { setActionLoading(null); }
  };

  const handleGenerateRoadmap = async () => {
    setActionLoading('roadmap');
    setError(null);
    try {
      await loadRoadmap();
    } catch (e) { setError(String(e)); }
    finally { setActionLoading(null); }
  };

  return (
    <div className="hud-panel" style={{ padding: 20 }}>
      {/* ── Header ──────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <h2 className="hud-title" style={{ margin: 0 }}>Opportunity Discovery</h2>
        <button onClick={loadDiscoveries} disabled={loading} style={{ padding: '4px 10px', fontSize: 10, borderRadius: 3, border: '1px solid var(--j-border)', background: 'var(--j-surface)', color: 'var(--j-text)', cursor: 'pointer' }}>
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {/* ── Tabs ────────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', gap: 0, marginBottom: 12, borderBottom: '1px solid var(--j-border)' }}>
        {(['discoveries', 'scores', 'forecast', 'roadmap', 'bottlenecks'] as Tab[]).map((t) => (
          <button key={t} onClick={() => { setTab(t); if (t === 'roadmap') handleGenerateRoadmap(); if (t === 'forecast') loadForecasts(); }} style={{
            padding: '6px 10px', fontSize: 10, fontWeight: 600, border: 'none', cursor: 'pointer',
            background: tab === t ? 'var(--j-surface)' : 'transparent',
            color: tab === t ? 'var(--j-text)' : 'var(--j-text-dim)',
            borderBottom: tab === t ? '2px solid var(--j-sky)' : '2px solid transparent',
            textTransform: 'capitalize',
          }}>
            {t}
          </button>
        ))}
      </div>

      {error && (
        <div style={{ marginBottom: 12, padding: '6px 12px', borderRadius: 4, background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', color: '#ef4444', fontSize: 11 }}>
          {error}
        </div>
      )}

      {/* ═══════════════════ Discoveries Tab ═══════════════════════════ */}
      {tab === 'discoveries' && (
        <>
          <div style={{ marginBottom: 12 }}>
            <button
              onClick={handleDiscover}
              disabled={actionLoading === 'discover'}
              style={{ padding: '6px 16px', fontSize: 11, borderRadius: 3, border: '1px solid var(--j-sky)', background: 'rgba(96,165,250,0.1)', color: 'var(--j-sky)', cursor: 'pointer', fontWeight: 600 }}
            >
              {actionLoading === 'discover' ? 'Discovering...' : 'Run Discovery'}
            </button>
            {discoverResult && (
              <span style={{ marginLeft: 12, fontSize: 11, color: 'var(--j-text-dim)' }}>
                Found {discoverResult.total} opportunities ({discoverResult.discovered} new)
              </span>
            )}
          </div>

          {list.length === 0 && !loading && (
            <div style={{ padding: 20, textAlign: 'center', color: 'var(--j-text-dim)', fontSize: 12 }}>
              No opportunities discovered yet. Click &quot;Run Discovery&quot; to scan all systems.
            </div>
          )}

          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 400, overflowY: 'auto' }}>
            {list.map((opp) => (
              <div key={opp.id} style={{ borderRadius: 4, border: '1px solid var(--j-border)', background: 'var(--j-bg)', padding: '10px 14px' }}>
                {/* Header row */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 4 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 2 }}>{opp.target_system}</div>
                    <div style={{ fontSize: 10, color: 'var(--j-text-dim)', lineHeight: 1.4 }}>{opp.improvement_description}</div>
                  </div>
                  <div style={{ display: 'flex', gap: 4, alignItems: 'center', marginLeft: 8, flexShrink: 0 }}>
                    <span style={{ fontSize: 9, padding: '2px 5px', borderRadius: 2, background: `${sourceColor(opp.source)}20`, color: sourceColor(opp.source), fontWeight: 600 }}>
                      {sourceLabel(opp.source)}
                    </span>
                    <span style={{ fontSize: 9, padding: '2px 5px', borderRadius: 2, background: `${statusColor(opp.status)}20`, color: statusColor(opp.status) }}>
                      {opp.status}
                    </span>
                  </div>
                </div>

                {/* Score bar */}
                <div style={{ marginBottom: 4 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: 'var(--j-text-dim)', marginBottom: 2 }}>
                    <span>Score: {opp.opportunity_score.toFixed(3)}</span>
                    <span>{Math.round(opp.opportunity_score * 100)}%</span>
                  </div>
                  <div style={{ height: 4, borderRadius: 2, background: 'var(--j-border)', overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${Math.min(100, opp.opportunity_score * 100)}%`, borderRadius: 2, background: scoreColor(opp.opportunity_score) }} />
                  </div>
                </div>

                {/* Dimension breakdown */}
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 6 }}>
                  {[
                    { label: 'Impact', value: opp.bottleneck_impact },
                    { label: 'Headroom', value: opp.improvement_headroom },
                    { label: 'Success Prob', value: opp.success_probability },
                    { label: 'Confidence', value: opp.confidence },
                    { label: 'Calibration', value: opp.calibration_accuracy },
                  ].map((d) => (
                    <div key={d.label} style={{ fontSize: 8, color: 'var(--j-text-dim)' }}>
                      {d.label}: <span style={{ color: scoreColor(d.value), fontWeight: 600 }}>{d.value.toFixed(2)}</span>
                    </div>
                  ))}
                </div>

                {/* Rationale */}
                <div style={{ fontSize: 9, color: 'var(--j-text-dim)', marginBottom: 6, lineHeight: 1.4 }}>{opp.rationale}</div>

                {/* Actions */}
                {opp.status === 'open' && (
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button
                      onClick={() => handleAccept(opp)}
                      disabled={actionLoading === opp.id}
                      style={{ padding: '3px 8px', fontSize: 9, borderRadius: 3, border: '1px solid transparent', background: 'rgba(34,197,94,0.15)', color: '#22c55e', cursor: 'pointer', fontWeight: 600 }}
                    >
                      {actionLoading === opp.id ? '...' : 'Accept & Debate'}
                    </button>
                    <button
                      onClick={() => handleReject(opp.id)}
                      disabled={actionLoading === opp.id}
                      style={{ padding: '3px 8px', fontSize: 9, borderRadius: 3, border: '1px solid transparent', background: 'rgba(239,68,68,0.15)', color: '#ef4444', cursor: 'pointer', fontWeight: 600 }}
                    >
                      {actionLoading === opp.id ? '...' : 'Reject'}
                    </button>
                  </div>
                )}

                {opp.status === 'in_progress' && (
                  <div style={{ fontSize: 9, color: '#60a5fa', fontWeight: 600 }}>In progress</div>
                )}
                {opp.status === 'rejected' && (
                  <div style={{ fontSize: 9, color: '#ef4444' }}>Rejected</div>
                )}
                {opp.status === 'completed' && (
                  <div style={{ fontSize: 9, color: '#a78bfa' }}>Completed</div>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {/* ═══════════════════ Scores Tab ════════════════════════════════ */}
      {tab === 'scores' && (
        <div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
            {Object.entries(scores).sort(([, a], [, b]) => b - a).map(([system, score]) => (
              <div key={system} style={{ borderRadius: 4, border: '1px solid var(--j-border)', background: 'var(--j-bg)', padding: '10px 14px' }}>
                <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 4, textTransform: 'capitalize' }}>
                  {system.replace(/_/g, ' ')}
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: 'var(--j-text-dim)', marginBottom: 2 }}>
                  <span>{Math.round(score * 100)}% capacity</span>
                  <span>{Math.round((1 - score) * 100)}% headroom</span>
                </div>
                <div style={{ height: 6, borderRadius: 3, background: 'var(--j-border)', overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${score * 100}%`, borderRadius: 3, background: scoreColor(score) }} />
                </div>
              </div>
            ))}
          </div>
          {Object.keys(scores).length === 0 && (
            <div style={{ padding: 20, textAlign: 'center', color: 'var(--j-text-dim)', fontSize: 12 }}>
              No system scores available.
            </div>
          )}
        </div>
      )}

      {/* ═══════════════════ Forecast Tab ══════════════════════════════ */}
      {tab === 'forecast' && (
        <div>
          {forecasts.length === 0 ? (
            <div style={{ padding: 20, textAlign: 'center', color: 'var(--j-text-dim)', fontSize: 12 }}>
              No forecast data available. Run discovery first.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {forecasts.map((f, i) => (
                <div key={i} style={{ borderRadius: 4, border: '1px solid var(--j-border)', background: 'var(--j-bg)', padding: '10px 14px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                    <span style={{ fontSize: 12, fontWeight: 600, textTransform: 'capitalize' }}>
                      {f.system.replace(/_/g, ' ')}
                    </span>
                    <span style={{ fontSize: 9, padding: '2px 5px', borderRadius: 2, background: f.trend === 'improving' ? 'rgba(34,197,94,0.1)' : f.trend === 'declining' ? 'rgba(239,68,68,0.1)' : 'rgba(139,139,139,0.1)', color: f.trend === 'improving' ? '#22c55e' : f.trend === 'declining' ? '#ef4444' : '#8b8b8b' }}>
                      {f.trend}
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: 'var(--j-text-dim)', marginBottom: 4 }}>
                    <span>Current: {(f.current_score * 100).toFixed(0)}%</span>
                    <span>Predicted: {(f.predicted_score * 100).toFixed(0)}%</span>
                    <span>Horizon: {f.horizon}</span>
                  </div>
                  <div style={{ height: 4, borderRadius: 2, background: 'var(--j-border)', overflow: 'hidden' }}>
                    <div style={{ display: 'flex', height: '100%' }}>
                      <div style={{ height: '100%', width: `${f.current_score * 100}%`, borderRadius: '2px 0 0 2px', background: '#8b8b8b' }} />
                      <div style={{ height: '100%', width: `${(f.predicted_score - f.current_score) * 100}%`, borderRadius: '0 2px 2px 0', background: f.predicted_score > f.current_score ? '#22c55e' : '#ef4444' }} />
                    </div>
                  </div>
                  <div style={{ fontSize: 9, color: 'var(--j-text-dim)', marginTop: 4 }}>{f.rationale}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ═══════════════════ Roadmap Tab ═══════════════════════════════ */}
      {tab === 'roadmap' && (
        <div>
          {roadmap.length === 0 ? (
            <div style={{ padding: 20, textAlign: 'center', color: 'var(--j-text-dim)', fontSize: 12 }}>
              No roadmap generated. Accept some opportunities and generate a roadmap.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {roadmap.map((phase, pi) => (
                <div key={pi} style={{ borderRadius: 4, border: '1px solid var(--j-border)', background: 'var(--j-bg)', padding: '12px 14px' }}>
                  <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 6, color: 'var(--j-sky)' }}>{phase.name}</div>
                  {phase.items.map((item, ii) => (
                    <div key={ii} style={{ padding: '6px 0', borderBottom: ii < phase.items.length - 1 ? '1px solid var(--j-border)' : 'none' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, fontWeight: 600, marginBottom: 2 }}>
                        <span style={{ textTransform: 'capitalize' }}>{item.system.replace(/_/g, ' ')}</span>
                        <span style={{ color: scoreColor(item.priority) }}>{(item.priority * 100).toFixed(0)}%</span>
                      </div>
                      <div style={{ fontSize: 9, color: 'var(--j-text-dim)' }}>{item.rationale}</div>
                      {item.dependencies.length > 0 && (
                        <div style={{ fontSize: 8, color: 'var(--j-text-dim)', marginTop: 2 }}>
                          Depends on: {item.dependencies.join(', ')}
                        </div>
                      )}
                      {item.unlocks.length > 0 && (
                        <div style={{ fontSize: 8, color: '#22c55e', marginTop: 1 }}>
                          Unlocks: {item.unlocks.join(', ')}
                        </div>
                      )}
                      <div style={{ fontSize: 8, color: 'var(--j-text-dim)', marginTop: 2 }}>{item.rationale}</div>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ═══════════════════ Bottlenecks Tab ═══════════════════════════ */}
      {tab === 'bottlenecks' && (
        <div>
          {bottlenecks.length === 0 ? (
            <div style={{ padding: 20, textAlign: 'center', color: 'var(--j-text-dim)', fontSize: 12 }}>
              No bottlenecks detected. Run discovery first.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {bottlenecks.map((b, i) => (
                <div key={i} style={{ borderRadius: 4, border: '1px solid var(--j-border)', background: 'var(--j-bg)', padding: '10px 14px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                    <span style={{ fontSize: 12, fontWeight: 600, textTransform: 'capitalize' }}>
                      {b.subsystem.replace(/_/g, ' ')}
                    </span>
                    <span style={{ fontSize: 11, fontWeight: 600, color: scoreColor(b.total_constrained_value) }}>
                      {(b.total_constrained_value * 100).toFixed(0)}% constrained
                    </span>
                  </div>
                  <div style={{ fontSize: 9, color: 'var(--j-text-dim)', marginBottom: 4 }}>
                    Local: {(b.local_impact * 100).toFixed(0)}% | Propagated: {(b.propagated_impact * 100).toFixed(0)}% | Confidence: {(b.confidence * 100).toFixed(0)}%
                  </div>
                  {b.affected_systems.length > 0 && (
                    <div style={{ fontSize: 9, color: 'var(--j-text-dim)' }}>
                      Constrains: {b.affected_systems.join(', ')}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
