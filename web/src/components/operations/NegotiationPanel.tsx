/* ───────────────────────────────────────────────────────────────────────────
 * NegotiationPanel — multi-agent negotiation view.
 * Shows agent opinions, consensus, dissent, and resolve actions.
 * ─────────────────────────────────────────────────────────────────────────── */
'use client';

import { useState, useEffect, useCallback } from 'react';
import { negotiations } from '@jarvis/sdk';
import type { NegotiationSession } from '@jarvis/sdk';

// ── Agent colors ──────────────────────────────────────────────────────────

const AGENT_COLORS: Record<string, string> = {
  planner: '#60a5fa',
  research: '#a78bfa',
  risk: '#ef4444',
  reviewer: '#f5c842',
  execution: '#22c55e',
};

const AGENT_LABELS: Record<string, string> = {
  planner: 'Planner',
  research: 'Research',
  risk: 'Risk',
  reviewer: 'Reviewer',
  execution: 'Execution',
};

function agentColor(name: string): string {
  return AGENT_COLORS[name] || '#8b8b8b';
}

function agentLabel(name: string): string {
  return AGENT_LABELS[name] || name;
}

function confidenceColor(c: number): string {
  if (c >= 0.7) return '#22c55e';
  if (c >= 0.4) return '#f5c842';
  return '#ef4444';
}

// ── Main Component ─────────────────────────────────────────────────────────

export function NegotiationPanel() {
  const [sessions, setSessions] = useState<NegotiationSession[]>([]);
  const [goalInput, setGoalInput] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await negotiations.list();
      setSessions(list);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, []);

  const handleCreate = useCallback(async () => {
    if (!goalInput.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const session = await negotiations.create(goalInput.trim());
      setGoalInput('');
      setSelectedId(session.id);
      await load();
    } catch (e) {
      setError(String(e));
    } finally {
      setCreating(false);
    }
  }, [goalInput, load]);

  const handleResolve = useCallback(async (id: string, accepted: boolean) => {
    setError(null);
    try {
      await negotiations.resolve(id, accepted);
      await load();
    } catch (e) {
      setError(String(e));
    }
  }, [load]);

  const selected = selectedId ? sessions.find((s) => s.id === selectedId) || null : null;

  return (
    <div className="hud-panel" style={{ padding: 20 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <h2 className="hud-title" style={{ margin: 0 }}>Negotiations</h2>
        <button onClick={load} disabled={loading} style={{ padding: '4px 10px', fontSize: 10, borderRadius: 3, border: '1px solid var(--j-border)', background: 'var(--j-surface)', color: 'var(--j-text)', cursor: 'pointer' }}>
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {/* ── Create form ──────────────────────────────────────────────── */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <input
          value={goalInput}
          onChange={(e) => setGoalInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
          placeholder="Enter a goal to negotiate..."
          style={{ flex: 1, padding: '6px 10px', fontSize: 12, borderRadius: 3, border: '1px solid var(--j-border)', background: 'var(--j-bg)', color: 'var(--j-text)' }}
        />
        <button onClick={handleCreate} disabled={creating || !goalInput.trim()} style={{ padding: '5px 12px', fontSize: 11, borderRadius: 3, border: '1px solid var(--j-border)', background: 'var(--j-surface)', color: 'var(--j-text)', cursor: 'pointer', fontWeight: 600 }}>
          {creating ? 'Negotiating...' : 'Negotiate'}
        </button>
      </div>

      {error && (
        <div style={{ marginBottom: 12, padding: '6px 12px', borderRadius: 4, background: 'rgba(239,68,68,0.1)', color: '#ef4444', fontSize: 11 }}>
          {error}
        </div>
      )}

      {!selected && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {sessions.map((s) => (
            <div
              key={s.id}
              onClick={() => setSelectedId(s.id)}
              style={{
                padding: '10px 14px', borderRadius: 4, border: '1px solid var(--j-border)',
                background: 'var(--j-bg)', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {s.goal.slice(0, 80)}
                </div>
                <div style={{ fontSize: 10, color: 'var(--j-text-dim)', marginTop: 2 }}>
                  {s.opinions.length} agents &middot; {s.consensus?.decision || 'no consensus'}
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                {s.consensus && (
                  <span style={{ fontSize: 14, fontWeight: 700, color: confidenceColor(s.consensus.confidence) }}>
                    {Math.round(s.consensus.confidence * 100)}%
                  </span>
                )}
                <span style={{ fontSize: 9, padding: '2px 5px', borderRadius: 2, background: s.status === 'accepted' ? 'rgba(34,197,94,0.1)' : s.status === 'open' ? 'rgba(96,165,250,0.1)' : 'rgba(239,68,68,0.1)', color: s.status === 'accepted' ? '#22c55e' : s.status === 'open' ? '#60a5fa' : '#ef4444' }}>
                  {s.status}
                </span>
              </div>
            </div>
          ))}
          {!loading && sessions.length === 0 && (
            <div style={{ padding: 20, textAlign: 'center', color: 'var(--j-text-dim)', fontSize: 12 }}>
              No negotiation sessions yet. Enter a goal above.
            </div>
          )}
        </div>
      )}

      {selected && (
        <div>
          {/* Back button */}
          <button onClick={() => setSelectedId(null)} style={{ background: 'none', border: 'none', color: 'var(--j-sky)', cursor: 'pointer', fontSize: 12, marginBottom: 10 }}>
            &larr; All Sessions
          </button>

          {/* Goal header */}
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>{selected.goal}</div>

          {/* Consensus banner */}
          {selected.consensus && (
            <div style={{ borderRadius: 4, border: '1px solid var(--j-border)', background: 'var(--j-bg)', padding: '12px 16px', marginBottom: 12 }}>
              <div style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--j-text-dim)', marginBottom: 6 }}>Consensus</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ fontSize: 24, fontWeight: 700 }}>{selected.consensus.decision.replace(/_/g, ' ')}</span>
                <span style={{ fontSize: 14, fontWeight: 600, color: confidenceColor(selected.consensus.confidence) }}>
                  {Math.round(selected.consensus.confidence * 100)}% confidence
                </span>
              </div>
              <div style={{ fontSize: 11, color: 'var(--j-text-dim)', marginTop: 4 }}>{selected.consensus.reasoning}</div>
              {selected.consensus.dissent.length > 0 && (
                <div style={{ fontSize: 11, color: '#ef4444', marginTop: 6 }}>
                  Dissent: {selected.consensus.dissent.map((d) => agentLabel(d)).join(', ')}
                </div>
              )}
            </div>
          )}

          {/* Agent opinions */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 12 }}>
            {selected.opinions.map((op) => (
              <div key={op.agent_name} style={{ borderRadius: 4, border: '1px solid var(--j-border)', background: 'var(--j-bg)', padding: '10px 14px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: agentColor(op.agent_name), flexShrink: 0 }} />
                    <span style={{ fontSize: 11, fontWeight: 600 }}>{agentLabel(op.agent_name)}</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ fontSize: 11, color: confidenceColor(op.confidence), fontWeight: 600 }}>
                      {Math.round(op.confidence * 100)}%
                    </span>
                    {selected.consensus?.dissent.includes(op.agent_name) && (
                      <span style={{ fontSize: 9, padding: '1px 4px', borderRadius: 2, background: 'rgba(239,68,68,0.1)', color: '#ef4444' }}>DISSENT</span>
                    )}
                  </div>
                </div>
                <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 2 }}>{op.position.replace(/_/g, ' ')}</div>
                <div style={{ fontSize: 10, color: 'var(--j-text-dim)' }}>{op.reasoning}</div>
                {op.evidence_sources.length > 0 && (
                  <div style={{ marginTop: 4, fontSize: 9, color: 'var(--j-text-dim)' }}>
                    {op.evidence_sources.map((e, i) => (
                      <div key={i} style={{ opacity: 0.7 }}>&bull; {e.slice(0, 120)}</div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Action buttons */}
          {selected.status === 'open' && (
            <div style={{ display: 'flex', gap: 8 }}>
              <button onClick={() => handleResolve(selected.id, true)} style={{ padding: '6px 16px', fontSize: 11, borderRadius: 3, border: '1px solid transparent', background: 'rgba(34,197,94,0.15)', color: '#22c55e', cursor: 'pointer', fontWeight: 600 }}>
                Accept Consensus
              </button>
              <button onClick={() => handleResolve(selected.id, false)} style={{ padding: '6px 16px', fontSize: 11, borderRadius: 3, border: '1px solid transparent', background: 'rgba(239,68,68,0.15)', color: '#ef4444', cursor: 'pointer', fontWeight: 600 }}>
                Reject
              </button>
            </div>
          )}

          {selected.status === 'accepted' && (
            <div style={{ fontSize: 11, color: '#22c55e', fontWeight: 600 }}>Consensus accepted</div>
          )}
          {selected.status === 'rejected' && (
            <div style={{ fontSize: 11, color: '#ef4444', fontWeight: 600 }}>Consensus rejected</div>
          )}
        </div>
      )}
    </div>
  );
}
