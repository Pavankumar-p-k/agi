'use client';

import { useState, useEffect, useCallback } from 'react';
import { research } from '@jarvis/sdk';
import type { ResearchSession, ResearchFact, ResearchStatistics, ResearchContradiction, ResearchSessionDetail } from '@jarvis/sdk';

/* ── Helpers ───────────────────────────────────────────────────────────── */

function timeAgo(dateStr: string | null | undefined): string {
  if (!dateStr) return '';
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function formatConfidence(c: number): string {
  return `${Math.round(c * 100)}%`;
}

function sourceShort(url: string): string {
  try { return new URL(url).hostname; } catch { return url.slice(0, 40); }
}

type Tab = 'sessions' | 'facts' | 'contradictions';

/* ── Component ─────────────────────────────────────────────────────────── */

export function ResearchExplorer() {
  const [tab, setTab] = useState<Tab>('sessions');
  const [searchQuery, setSearchQuery] = useState('');

  // Stats
  const [stats, setStats] = useState<ResearchStatistics | null>(null);

  // Sessions
  const [sessions, setSessions] = useState<ResearchSession[]>([]);
  const [sLoading, setSLoading] = useState(false);

  // Session detail
  const [sessionDetail, setSessionDetail] = useState<ResearchSessionDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Facts
  const [facts, setFacts] = useState<ResearchFact[]>([]);
  const [fLoading, setFLoading] = useState(false);

  // Contradictions
  const [contradictions, setContradictions] = useState<ResearchContradiction[]>([]);
  const [cLoading, setCLoading] = useState(false);

  // Search results
  const [searchResults, setSearchResults] = useState<ResearchFact[] | null>(null);

  const loadStats = useCallback(() => {
    research.statistics().then(setStats).catch(() => {});
  }, []);

  const loadSessions = useCallback(() => {
    setSLoading(true);
    research.listSessions(50)
      .then((r) => setSessions(r.sessions))
      .catch(() => {})
      .finally(() => setSLoading(false));
  }, []);

  const loadFacts = useCallback(() => {
    setFLoading(true);
    research.listFacts({ limit: 50 })
      .then((r) => setFacts(r.facts))
      .catch(() => {})
      .finally(() => setFLoading(false));
  }, []);

  const loadContradictions = useCallback(() => {
    setCLoading(true);
    research.listContradictions(50)
      .then((r) => setContradictions(r.contradictions))
      .catch(() => {})
      .finally(() => setCLoading(false));
  }, []);

  useEffect(() => { loadStats(); }, []);
  useEffect(() => { if (tab === 'sessions') loadSessions(); }, [tab]);
  useEffect(() => { if (tab === 'facts') loadFacts(); }, [tab]);
  useEffect(() => { if (tab === 'contradictions') loadContradictions(); }, [tab]);

  const handleSearch = useCallback(() => {
    if (!searchQuery.trim()) { setSearchResults(null); return; }
    research.search(searchQuery.trim(), 30)
      .then((r) => setSearchResults(r.facts))
      .catch(() => setSearchResults([]));
  }, [searchQuery]);

  const openSession = useCallback(async (activityId: string) => {
    setDetailLoading(true);
    setSessionDetail(null);
    try {
      const detail = await research.getSession(activityId);
      setSessionDetail(detail);
    } catch {
      setSessionDetail(null);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const closeSession = useCallback(() => {
    setSessionDetail(null);
  }, []);

  const isLoading = (): boolean => {
    if (searchResults !== null) return false;
    switch (tab) {
      case 'sessions': return sLoading;
      case 'facts': return fLoading;
      case 'contradictions': return cLoading;
    }
  };

  const renderStats = () => {
    if (!stats) return null;
    return (
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: 8, marginBottom: 16 }}>
        {[
          { label: 'Facts', value: stats.total_facts, color: '#6384ff' },
          { label: 'Sessions', value: stats.total_sessions, color: '#22c55e' },
          { label: 'Categories', value: Object.keys(stats.fact_count_by_category).length, color: '#f5c842' },
          { label: 'Sources', value: Object.keys(stats.fact_count_by_source).length, color: '#a78bfa' },
        ].map((s) => (
          <div key={s.label} style={{ padding: '10px 12px', borderRadius: 4, background: 'var(--j-surface)', border: '1px solid var(--j-border)', textAlign: 'center' }}>
            <div style={{ fontSize: 22, fontWeight: 600, color: s.color }}>{s.value}</div>
            <div style={{ fontSize: 11, color: 'var(--j-text-dim)', marginTop: 2 }}>{s.label}</div>
          </div>
        ))}
      </div>
    );
  };

  const renderTabs = () => (
    <div style={{ display: 'flex', gap: 4, marginBottom: 12 }}>
      {(['sessions', 'facts', 'contradictions'] as Tab[]).map((t) => (
        <button
          key={t}
          onClick={() => { setTab(t); setSearchResults(null); setSessionDetail(null); }}
          style={{
            padding: '6px 14px', borderRadius: 4, border: 'none',
            background: tab === t ? 'var(--j-sky)' : 'var(--j-surface)',
            color: tab === t ? '#020406' : 'var(--j-text)',
            cursor: 'pointer', fontSize: 12,
            fontWeight: tab === t ? 500 : 400,
          }}
        >
          {t.charAt(0).toUpperCase() + t.slice(1)}
        </button>
      ))}
    </div>
  );

  // ── Session detail overlay ────────────────────────────────────────────

  if (sessionDetail) {
    const s = sessionDetail.session;
    return (
      <div className="hud-panel" style={{ padding: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
          <button onClick={closeSession} style={{ background: 'none', border: 'none', color: 'var(--j-sky)', cursor: 'pointer', fontSize: 13 }}>&larr; Back</button>
          <h2 className="hud-title" style={{ margin: 0, fontSize: 16 }}>Research Session</h2>
        </div>

        {/* Session header */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 16 }}>
          <div style={{ padding: '8px 12px', borderRadius: 4, background: 'var(--j-surface)', border: '1px solid var(--j-border)' }}>
            <div style={{ fontSize: 10, color: 'var(--j-text-dim)' }}>Activity</div>
            <div style={{ fontSize: 12, fontFamily: 'monospace', marginTop: 2 }}>{s.activity_id.slice(0, 24)}</div>
          </div>
          <div style={{ padding: '8px 12px', borderRadius: 4, background: 'var(--j-surface)', border: '1px solid var(--j-border)' }}>
            <div style={{ fontSize: 10, color: 'var(--j-text-dim)' }}>Facts</div>
            <div style={{ fontSize: 12, fontWeight: 500, marginTop: 2 }}>{s.fact_count}</div>
          </div>
          <div style={{ padding: '8px 12px', borderRadius: 4, background: 'var(--j-surface)', border: '1px solid var(--j-border)' }}>
            <div style={{ fontSize: 10, color: 'var(--j-text-dim)' }}>Sources</div>
            <div style={{ fontSize: 12 }}>{s.sources.length}</div>
          </div>
          <div style={{ padding: '8px 12px', borderRadius: 4, background: 'var(--j-surface)', border: '1px solid var(--j-border)' }}>
            <div style={{ fontSize: 10, color: 'var(--j-text-dim)' }}>Avg Confidence</div>
            <div style={{ fontSize: 12 }}>{formatConfidence(s.avg_confidence)}</div>
          </div>
        </div>

        {/* Sources */}
        <div style={{ marginBottom: 16 }}>
          <h3 style={{ fontSize: 12, fontWeight: 500, margin: '0 0 8px' }}>Sources</h3>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {s.sources.map((url) => (
              <span key={url} style={{ fontSize: 10, padding: '2px 8px', borderRadius: 3, background: 'var(--j-surface)', border: '1px solid var(--j-border)' }}>
                {sourceShort(url)}
              </span>
            ))}
          </div>
        </div>

        {/* Contradictions */}
        {sessionDetail.contradictions.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <h3 style={{ fontSize: 12, fontWeight: 500, margin: '0 0 8px', color: '#f5c842' }}>Contradictions ({sessionDetail.contradictions.length})</h3>
            {sessionDetail.contradictions.map((c, i) => (
              <div key={i} style={{ fontSize: 11, padding: '6px 10px', marginBottom: 4, borderRadius: 4, background: 'rgba(245,200,66,0.08)', border: '1px solid rgba(245,200,66,0.2)' }}>
                <strong>{c.entity} / {c.attribute}:</strong> {c.values.join(', ')}
              </div>
            ))}
          </div>
        )}

        {/* Agreements */}
        {sessionDetail.agreements.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <h3 style={{ fontSize: 12, fontWeight: 500, margin: '0 0 8px', color: '#22c55e' }}>Agreements ({sessionDetail.agreements.length})</h3>
            {sessionDetail.agreements.map((a, i) => (
              <div key={i} style={{ fontSize: 11, padding: '6px 10px', marginBottom: 4, borderRadius: 4, background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.2)' }}>
                <strong>{a.entity} / {a.attribute}:</strong> {a.value}
              </div>
            ))}
          </div>
        )}

        {/* Synthesis */}
        {sessionDetail.syntheses.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <h3 style={{ fontSize: 12, fontWeight: 500, margin: '0 0 8px', color: '#6384ff' }}>Synthesis</h3>
            {sessionDetail.syntheses.map((s, i) => (
              <div key={i} style={{ fontSize: 11, padding: '6px 10px', marginBottom: 4, borderRadius: 4, background: 'rgba(99,132,255,0.08)', border: '1px solid rgba(99,132,255,0.2)' }}>
                {s}
              </div>
            ))}
          </div>
        )}

        {/* Facts */}
        <h3 style={{ fontSize: 12, fontWeight: 500, margin: '0 0 8px' }}>Facts ({sessionDetail.facts.length})</h3>
        {sessionDetail.facts.map((f) => (
          <div key={f.fact_id} style={{ fontSize: 11, padding: '6px 10px', marginBottom: 4, borderRadius: 4, background: 'var(--j-surface)', border: '1px solid var(--j-border)' }}>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              <span style={{ fontSize: 10, padding: '1px 5px', borderRadius: 2, background: 'rgba(99,132,255,0.15)', color: '#6384ff' }}>{f.category}</span>
              <span style={{ flex: 1 }}>{f.claim}</span>
              <span style={{ fontSize: 10, color: 'var(--j-text-dim)' }}>{formatConfidence(f.confidence)}</span>
              <span style={{ fontSize: 10, color: 'var(--j-text-dim)' }}>{sourceShort(f.source_url)}</span>
            </div>
          </div>
        ))}
      </div>
    );
  }

  // ── List views ────────────────────────────────────────────────────────

  return (
    <div className="hud-panel" style={{ padding: 24 }}>
      <h2 className="hud-title" style={{ marginBottom: 16 }}>Research Explorer</h2>

      {renderStats()}

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        {renderTabs()}
        <div style={{ flex: 1 }} />
        <input
          placeholder="Search facts..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') handleSearch(); }}
          style={{ padding: '6px 10px', borderRadius: 4, border: '1px solid var(--j-border)', background: 'var(--j-bg)', color: 'var(--j-text)', fontSize: 12, width: 200, outline: 'none' }}
        />
        <button onClick={handleSearch} style={{ padding: '6px 12px', borderRadius: 4, border: 'none', background: 'var(--j-sky)', color: '#020406', cursor: 'pointer', fontSize: 12 }}>Search</button>
      </div>

      {isLoading() && <div style={{ textAlign: 'center', padding: 16, color: 'var(--j-text-dim)', fontSize: 13 }}>Loading...</div>}

      {!isLoading() && searchResults !== null && (
        <>
          <div style={{ marginBottom: 4, fontSize: 11, color: 'var(--j-text-dim)' }}>
            Search results ({searchResults.length})
            <button onClick={() => setSearchResults(null)} style={{ marginLeft: 8, textDecoration: 'underline', background: 'none', border: 'none', color: 'var(--j-sky)', cursor: 'pointer', fontSize: 11 }}>Clear</button>
          </div>
          {searchResults.length === 0 && <div style={{ textAlign: 'center', padding: 16, color: 'var(--j-text-dim)', fontSize: 13 }}>No results</div>}
          {searchResults.map((f) => (
            <div key={f.fact_id} style={{ fontSize: 11, padding: '6px 10px', marginBottom: 4, borderRadius: 4, background: 'var(--j-surface)', border: '1px solid var(--j-border)' }}>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <span style={{ fontSize: 10, padding: '1px 5px', borderRadius: 2, background: 'rgba(99,132,255,0.15)', color: '#6384ff' }}>{f.category}</span>
                <span style={{ flex: 1 }}>{f.claim}</span>
                <span style={{ fontSize: 10, color: 'var(--j-text-dim)' }}>{formatConfidence(f.confidence)}</span>
              </div>
            </div>
          ))}
        </>
      )}

      {!isLoading() && searchResults === null && tab === 'sessions' && (
        <>
          {sessions.length === 0 && <div style={{ textAlign: 'center', padding: 16, color: 'var(--j-text-dim)', fontSize: 13 }}>No research sessions yet</div>}
          {sessions.map((s) => (
            <div
              key={s.activity_id}
              onClick={() => openSession(s.activity_id)}
              style={{ padding: '10px 12px', borderRadius: 4, background: 'var(--j-surface)', border: '1px solid var(--j-border)', marginBottom: 4, cursor: 'pointer' }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12, fontWeight: 500, fontFamily: 'monospace', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {s.activity_id.slice(0, 28)}
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--j-text-dim)', marginTop: 1 }}>
                    {s.fact_count} facts · {s.sources.length} sources · {s.categories.length} categories · {formatConfidence(s.avg_confidence)} avg
                  </div>
                </div>
                <div style={{ fontSize: 10, color: 'var(--j-text-dim)', textAlign: 'right', flexShrink: 0 }}>
                  {timeAgo(s.last_fact_at)}
                </div>
              </div>
            </div>
          ))}
        </>
      )}

      {!isLoading() && searchResults === null && tab === 'facts' && (
        <>
          {facts.length === 0 && <div style={{ textAlign: 'center', padding: 16, color: 'var(--j-text-dim)', fontSize: 13 }}>No facts yet</div>}
          {facts.map((f) => (
            <div key={f.fact_id} style={{ fontSize: 11, padding: '6px 10px', marginBottom: 4, borderRadius: 4, background: 'var(--j-surface)', border: '1px solid var(--j-border)' }}>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <span style={{ fontSize: 10, padding: '1px 5px', borderRadius: 2, background: 'rgba(99,132,255,0.15)', color: '#6384ff' }}>{f.category}</span>
                <span style={{ flex: 1 }}>{f.claim}</span>
                <span style={{ fontSize: 10, color: 'var(--j-text-dim)' }}>{formatConfidence(f.confidence)}</span>
                <span style={{ fontSize: 10, color: 'var(--j-text-dim)' }}>{sourceShort(f.source_url)}</span>
              </div>
            </div>
          ))}
        </>
      )}

      {!isLoading() && searchResults === null && tab === 'contradictions' && (
        <>
          {contradictions.length === 0 && <div style={{ textAlign: 'center', padding: 16, color: 'var(--j-text-dim)', fontSize: 13 }}>No contradictions found</div>}
          {contradictions.map((c, i) => (
            <div key={i} style={{ fontSize: 11, padding: '10px 12px', marginBottom: 4, borderRadius: 4, background: 'rgba(245,200,66,0.08)', border: '1px solid rgba(245,200,66,0.2)' }}>
              <div style={{ fontWeight: 500, marginBottom: 4 }}>{c.entity} / {c.attribute}</div>
              <div style={{ color: 'var(--j-text-dim)', marginBottom: 4 }}>{c.values.join(' vs ')}</div>
              <div style={{ fontSize: 10, color: 'var(--j-text-dim)' }}>{c.summary}</div>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
