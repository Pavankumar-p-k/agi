/* ───────────────────────────────────────────────────────────────────────────
 * ImprovementPanel — improvement opportunities + experiment lifecycle.
 * ─────────────────────────────────────────────────────────────────────────── */
'use client';

import { useState, useEffect, useCallback } from 'react';
import { improvements } from '@jarvis/sdk';
import type { ImprovementOpportunity, PlannerExperiment } from '@jarvis/sdk';

// ── Helpers ─────────────────────────────────────────────────────────────────

function statusColor(s: string): string {
  if (s === 'open') return '#22c55e';
  if (s === 'running' || s === 'experimenting') return '#60a5fa';
  if (s === 'promoted' || s === 'completed') return '#a78bfa';
  if (s === 'rolled_back' || s === 'reverted') return '#ef4444';
  return '#8b8b8b';
}

function label(s: string): string {
  return s.replace(/^opp_|^exp_/, '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()).slice(0, 20);
}

// ── Main Component ─────────────────────────────────────────────────────────

export function ImprovementPanel() {
  const [opportunities, setOpportunities] = useState<ImprovementOpportunity[]>([]);
  const [experiments, setExperiments] = useState<PlannerExperiment[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<'opportunities' | 'experiments'>('opportunities');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [opps, exps] = await Promise.all([
        improvements.listOpportunities(),
        improvements.listExperiments(),
      ]);
      setOpportunities(opps);
      setExperiments(exps);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, []);

  const handleCreate = async (opp: ImprovementOpportunity) => {
    setActionLoading(opp.id);
    setError(null);
    try {
      const exp = await improvements.createExperiment(opp.id);
      await improvements.startExperiment(exp.id);
      await load();
    } catch (e) { setError(String(e)); }
    finally { setActionLoading(null); }
  };

  const handleAction = async (expId: string, action: 'complete' | 'promote' | 'rollback') => {
    setActionLoading(`${expId}-${action}`);
    setError(null);
    try {
      if (action === 'complete') {
        await improvements.completeExperiment(expId);
        await improvements.rollbackExperiment(expId);
      } else if (action === 'promote') {
        await improvements.promoteExperiment(expId);
      } else {
        await improvements.rollbackExperiment(expId);
      }
      await load();
    } catch (e) { setError(String(e)); }
    finally { setActionLoading(null); }
  };

  return (
    <div className="hud-panel" style={{ padding: 20 }}>
      {/* ── Header ──────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <h2 className="hud-title" style={{ margin: 0 }}>Improvement System</h2>
        <button onClick={load} disabled={loading} style={{ padding: '4px 10px', fontSize: 10, borderRadius: 3, border: '1px solid var(--j-border)', background: 'var(--j-surface)', color: 'var(--j-text)', cursor: 'pointer' }}>
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {/* ── Tabs ────────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', gap: 0, marginBottom: 12, borderBottom: '1px solid var(--j-border)' }}>
        {(['opportunities', 'experiments'] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)} style={{
            padding: '6px 14px', fontSize: 11, fontWeight: 600, border: 'none', cursor: 'pointer',
            background: tab === t ? 'var(--j-surface)' : 'transparent',
            color: tab === t ? 'var(--j-text)' : 'var(--j-text-dim)',
            borderBottom: tab === t ? '2px solid var(--j-sky)' : '2px solid transparent',
          }}>
            {t === 'opportunities' ? `Opportunities (${opportunities.length})` : `Experiments (${experiments.length})`}
          </button>
        ))}
      </div>

      {error && (
        <div style={{ marginBottom: 12, padding: '6px 12px', borderRadius: 4, background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', color: '#ef4444', fontSize: 11 }}>
          {error}
        </div>
      )}

      {tab === 'opportunities' && (
        <>
          {opportunities.length === 0 && !loading && (
            <div style={{ padding: 20, textAlign: 'center', color: 'var(--j-text-dim)', fontSize: 12 }}>
              No improvement opportunities detected. Run more plans to generate data.
            </div>
          )}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {opportunities.map((opp) => (
              <div key={opp.id} style={{ borderRadius: 4, border: '1px solid var(--j-border)', background: 'var(--j-bg)', padding: '10px 14px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 4 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 2 }}>{opp.description}</div>
                    <div style={{ fontSize: 10, color: 'var(--j-text-dim)' }}>{opp.evidence}</div>
                  </div>
                  <span style={{ fontSize: 9, padding: '2px 5px', borderRadius: 2, background: opp.impact === 'high' ? 'rgba(239,68,68,0.1)' : 'rgba(245,200,66,0.1)', color: opp.impact === 'high' ? '#ef4444' : '#f5c842', whiteSpace: 'nowrap', marginLeft: 8 }}>
                    {opp.impact} impact
                  </span>
                </div>
                <div style={{ fontSize: 10, color: 'var(--j-text)', marginBottom: 6 }}>
                  {opp.recommended_change}
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: 9, color: 'var(--j-text-dim)' }}>
                    Expected gain: {Math.round(opp.expected_gain * 100)}%
                  </span>
                  <button
                    onClick={() => handleCreate(opp)}
                    disabled={actionLoading === opp.id}
                    style={{ padding: '4px 10px', fontSize: 10, borderRadius: 3, border: '1px solid var(--j-border)', background: 'var(--j-surface)', color: 'var(--j-text)', cursor: 'pointer' }}
                  >
                    {actionLoading === opp.id ? 'Creating...' : 'Create Experiment'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {tab === 'experiments' && (
        <>
          {experiments.length === 0 && !loading && (
            <div style={{ padding: 20, textAlign: 'center', color: 'var(--j-text-dim)', fontSize: 12 }}>
              No experiments yet. Create one from an improvement opportunity.
            </div>
          )}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {experiments.map((exp) => (
              <div key={exp.id} style={{ borderRadius: 4, border: '1px solid var(--j-border)', background: 'var(--j-bg)', padding: '10px 14px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, flex: 1 }}>{exp.title}</div>
                  <span style={{ fontSize: 9, padding: '2px 5px', borderRadius: 2, background: `${statusColor(exp.status)}20`, color: statusColor(exp.status), fontWeight: 600, whiteSpace: 'nowrap', marginLeft: 8 }}>
                    {exp.status}
                  </span>
                </div>
                <div style={{ fontSize: 10, color: 'var(--j-text-dim)', marginBottom: 4 }}>{exp.description}</div>

                {exp.result && (
                  <div style={{ fontSize: 10, marginBottom: 6, color: exp.result.overall === 'improved' ? '#22c55e' : exp.result.overall === 'regressed' ? '#ef4444' : 'var(--j-text-dim)' }}>
                    Result: {exp.result.overall}
                    {exp.result.changes && Object.entries(exp.result.changes).map(([k, v]) => (
                      <span key={k} style={{ marginLeft: 8 }}>{k}: {v > 0 ? '+' : ''}{typeof v === 'number' ? (v * 100).toFixed(1) + '%' : v}</span>
                    ))}
                  </div>
                )}

                {exp.status === 'running' && (
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button onClick={() => handleAction(exp.id, 'complete')} disabled={actionLoading === `${exp.id}-complete`} style={{ padding: '3px 8px', fontSize: 9, borderRadius: 3, border: '1px solid var(--j-border)', background: 'rgba(34,197,94,0.1)', color: '#22c55e', cursor: 'pointer' }}>
                      {actionLoading === `${exp.id}-complete` ? '...' : 'Complete & Rollback'}
                    </button>
                  </div>
                )}

                {exp.status === 'completed' && (
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button onClick={() => handleAction(exp.id, 'promote')} disabled={actionLoading === `${exp.id}-promote`} style={{ padding: '3px 8px', fontSize: 9, borderRadius: 3, border: '1px solid var(--j-border)', background: 'rgba(167,139,250,0.1)', color: '#a78bfa', cursor: 'pointer' }}>
                      {actionLoading === `${exp.id}-promote` ? '...' : 'Promote'}
                    </button>
                    <button onClick={() => handleAction(exp.id, 'rollback')} disabled={actionLoading === `${exp.id}-rollback`} style={{ padding: '3px 8px', fontSize: 9, borderRadius: 3, border: '1px solid var(--j-border)', background: 'rgba(239,68,68,0.1)', color: '#ef4444', cursor: 'pointer' }}>
                      {actionLoading === `${exp.id}-rollback` ? '...' : 'Rollback'}
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
