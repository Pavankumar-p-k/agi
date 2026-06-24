'use client';

import { useState, useEffect, useCallback } from 'react';
import { knowledge } from '@jarvis/sdk';
import type { KnowledgeItem, Experience, KnowledgeStatistics, PatternEntry, FailureEntry } from '@jarvis/sdk';

/* ── Helpers ───────────────────────────────────────────────────────────── */

function formatConfidence(c: number): string {
  return `${Math.round(c * 100)}%`;
}

function colorForCategory(cat: string): string {
  switch (cat) {
    case 'pattern': return '#6384ff';
    case 'principle': return '#22c55e';
    case 'heuristic': return '#f5c842';
    case 'factoid': return '#a78bfa';
    case 'warning': return '#ef4444';
    default: return '#8b8b8b';
  }
}

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

type Tab = 'facts' | 'experiences' | 'patterns' | 'failures';

/* ── Component ─────────────────────────────────────────────────────────── */

export function KnowledgeExplorer() {
  const [tab, setTab] = useState<Tab>('facts');
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<KnowledgeItem[] | null>(null);

  // Stats
  const [stats, setStats] = useState<KnowledgeStatistics | null>(null);

  // Knowledge
  const [knowledgeItems, setKnowledgeItems] = useState<KnowledgeItem[]>([]);
  const [kLoading, setKLoading] = useState(false);

  // Experiences
  const [experiences, setExperiences] = useState<Experience[]>([]);
  const [eLoading, setELoading] = useState(false);

  // Patterns
  const [patterns, setPatterns] = useState<PatternEntry[]>([]);
  const [pLoading, setPLoading] = useState(false);

  // Failures
  const [failures, setFailures] = useState<FailureEntry[]>([]);
  const [fLoading, setFLoading] = useState(false);

  // Selected for source trace
  const [selectedItem, setSelectedItem] = useState<KnowledgeItem | null>(null);

  const loadStats = useCallback(() => {
    knowledge.statistics().then(setStats).catch(() => {});
  }, []);

  const loadKnowledge = useCallback(() => {
    setKLoading(true);
    knowledge.list({ limit: 50 })
      .then((r) => setKnowledgeItems(r.knowledge))
      .catch(() => {})
      .finally(() => setKLoading(false));
  }, []);

  const loadExperiences = useCallback(() => {
    setELoading(true);
    knowledge.listExperiences({ limit: 50 })
      .then((r) => setExperiences(r.experiences))
      .catch(() => {})
      .finally(() => setELoading(false));
  }, []);

  const loadPatterns = useCallback(() => {
    setPLoading(true);
    knowledge.listPatterns(50)
      .then((r) => setPatterns(r.patterns || []))
      .catch(() => {})
      .finally(() => setPLoading(false));
  }, []);

  const loadFailures = useCallback(() => {
    setFLoading(true);
    knowledge.listFailures(50)
      .then((r) => setFailures(r.failures || []))
      .catch(() => {})
      .finally(() => setFLoading(false));
  }, []);

  useEffect(() => { loadStats(); }, []);
  useEffect(() => { if (tab === 'facts') loadKnowledge(); }, [tab]);
  useEffect(() => { if (tab === 'experiences') loadExperiences(); }, [tab]);
  useEffect(() => { if (tab === 'patterns') loadPatterns(); }, [tab]);
  useEffect(() => { if (tab === 'failures') loadFailures(); }, [tab]);

  const handleSearch = useCallback(() => {
    if (!searchQuery.trim()) {
      setSearchResults(null);
      return;
    }
    knowledge.search(searchQuery.trim(), 30)
      .then((r) => setSearchResults(r.knowledge))
      .catch(() => setSearchResults([]));
  }, [searchQuery]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleSearch();
  };

  const isLoading = (): boolean => {
    if (searchResults !== null) return false;
    switch (tab) {
      case 'facts': return kLoading;
      case 'experiences': return eLoading;
      case 'patterns': return pLoading;
      case 'failures': return fLoading;
    }
  };

  const renderStats = () => {
    if (!stats) return null;
    return (
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: 8, marginBottom: 16 }}>
        {[
          { label: 'Knowledge', value: stats.total_knowledge_items, color: '#6384ff' },
          { label: 'Experiences', value: stats.total_experiences, color: '#22c55e' },
          { label: 'Patterns', value: stats.total_patterns, color: '#f5c842' },
          { label: 'Failures', value: stats.total_failures, color: '#ef4444' },
        ].map((s) => (
          <div
            key={s.label}
            style={{
              padding: '10px 12px',
              borderRadius: 4,
              background: 'var(--j-surface)',
              border: '1px solid var(--j-border)',
              textAlign: 'center',
            }}
          >
            <div style={{ fontSize: 22, fontWeight: 600, color: s.color }}>{s.value}</div>
            <div style={{ fontSize: 11, color: 'var(--j-text-dim)', marginTop: 2 }}>{s.label}</div>
          </div>
        ))}
      </div>
    );
  };

  const renderTabs = () => (
    <div style={{ display: 'flex', gap: 4, marginBottom: 12 }}>
      {(['facts', 'experiences', 'patterns', 'failures'] as Tab[]).map((t) => (
        <button
          key={t}
          onClick={() => { setTab(t); setSearchResults(null); setSelectedItem(null); }}
          style={{
            padding: '6px 14px',
            borderRadius: 4,
            border: 'none',
            background: tab === t ? 'var(--j-sky)' : 'var(--j-surface)',
            color: tab === t ? '#020406' : 'var(--j-text)',
            cursor: 'pointer',
            fontSize: 12,
            fontWeight: tab === t ? 500 : 400,
          }}
        >
          {t.charAt(0).toUpperCase() + t.slice(1)}
        </button>
      ))}
    </div>
  );

  const renderItem = (k: KnowledgeItem) => (
    <div
      key={k.knowledge_id}
      onClick={() => setSelectedItem(selectedItem?.knowledge_id === k.knowledge_id ? null : k)}
      style={{
        padding: '10px 12px',
        borderRadius: 4,
        background: selectedItem?.knowledge_id === k.knowledge_id ? 'rgba(99,132,255,0.08)' : 'var(--j-surface)',
        border: `1px solid ${selectedItem?.knowledge_id === k.knowledge_id ? 'var(--j-sky)' : 'var(--j-border)'}`,
        marginBottom: 4,
        cursor: 'pointer',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span
          style={{
            fontSize: 10,
            padding: '1px 6px',
            borderRadius: 3,
            background: `${colorForCategory(k.category)}22`,
            color: colorForCategory(k.category),
            fontWeight: 500,
          }}
        >
          {k.category}
        </span>
        <span style={{ flex: 1, fontSize: 12, lineHeight: 1.4 }}>{k.claim}</span>
        <span style={{ fontSize: 10, color: 'var(--j-text-dim)', whiteSpace: 'nowrap' }}>
          {formatConfidence(k.confidence)}
        </span>
        <span style={{ fontSize: 10, color: 'var(--j-text-dim)', whiteSpace: 'nowrap' }}>
          {timeAgo(k.created_at)}
        </span>
      </div>

      {selectedItem?.knowledge_id === k.knowledge_id && (
        <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--j-border)', fontSize: 11, color: 'var(--j-text-dim)' }}>
          <div><strong>Evidence count:</strong> {k.evidence_count}</div>
          <div><strong>Activity sources:</strong> {k.source_activity_ids.length > 0
            ? k.source_activity_ids.map((id) => <code key={id} style={{ fontSize: 10, marginLeft: 4 }}>{id.slice(0, 16)}</code>)
            : 'none'}
          </div>
          <div><strong>Pattern keys:</strong> {k.source_pattern_keys.length > 0 ? k.source_pattern_keys.join(', ') : 'none'}</div>
          <div><strong>Tags:</strong> {k.tags.length > 0 ? k.tags.join(', ') : 'none'}</div>
        </div>
      )}
    </div>
  );

  const renderExperience = (e: Experience) => (
    <div
      key={e.activity_id}
      style={{
        padding: '10px 12px',
        borderRadius: 4,
        background: 'var(--j-surface)',
        border: '1px solid var(--j-border)',
        marginBottom: 4,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: e.success ? '#22c55e' : '#ef4444',
            flexShrink: 0,
          }}
        />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 12, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {e.goal}
          </div>
          <div style={{ fontSize: 10, color: 'var(--j-text-dim)', marginTop: 1 }}>
            {e.domain} · {e.status} · {e.node_count} nodes · {e.tools_used.length} tools
          </div>
        </div>
        <div style={{ fontSize: 10, color: 'var(--j-text-dim)', textAlign: 'right', flexShrink: 0 }}>
          {e.duration_seconds != null && <div>{e.duration_seconds.toFixed(0)}s</div>}
          {e.outcome_quality != null && <div>{formatConfidence(e.outcome_quality)} quality</div>}
        </div>
      </div>
      {e.error_summary && (
        <div style={{ fontSize: 10, color: '#ef4444', marginTop: 4 }}>{e.error_summary}</div>
      )}
    </div>
  );

  const renderPattern = (p: PatternEntry) => (
    <div
      key={p.pattern}
      style={{
        padding: '10px 12px',
        borderRadius: 4,
        background: 'var(--j-surface)',
        border: '1px solid var(--j-border)',
        marginBottom: 4,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 12, fontWeight: 500, fontFamily: 'monospace', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {p.pattern}
          </div>
          <div style={{ fontSize: 10, color: 'var(--j-text-dim)', marginTop: 1, fontFamily: 'monospace' }}>
            {p.regex.slice(0, 120)}
          </div>
        </div>
        <div style={{ fontSize: 10, color: 'var(--j-text-dim)', textAlign: 'right', flexShrink: 0 }}>
          <div>{p.count} matches</div>
          {p.best_strategy && <div style={{ color: '#22c55e' }}>{p.best_strategy}</div>}
        </div>
      </div>
    </div>
  );

  const renderFailure = (f: FailureEntry) => (
    <div
      key={f.pattern}
      style={{
        padding: '10px 12px',
        borderRadius: 4,
        background: 'rgba(239,68,68,0.05)',
        border: '1px solid rgba(239,68,68,0.2)',
        marginBottom: 4,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ color: '#ef4444', fontSize: 16 }}>⚠</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 12, fontFamily: 'monospace', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {f.pattern.replace('FAILED:', '')}
          </div>
          <div style={{ fontSize: 10, color: 'var(--j-text-dim)', marginTop: 1 }}>
            Strategy: {f.fix_strategy || 'none'} · Seen {f.count} times
            {f.last_seen && ` · Last: ${timeAgo(f.last_seen)}`}
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <div className="hud-panel" style={{ padding: 24 }}>
      <h2 className="hud-title" style={{ marginBottom: 16 }}>
        Knowledge Explorer
      </h2>

      {/* Stats */}
      {renderStats()}

      {/* Tabs + Search */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        {renderTabs()}
        <div style={{ flex: 1 }} />
        <input
          placeholder="Search knowledge..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          style={{
            padding: '6px 10px',
            borderRadius: 4,
            border: '1px solid var(--j-border)',
            background: 'var(--j-bg)',
            color: 'var(--j-text)',
            fontSize: 12,
            width: 200,
            outline: 'none',
          }}
        />
        <button
          onClick={handleSearch}
          style={{
            padding: '6px 12px',
            borderRadius: 4,
            border: 'none',
            background: 'var(--j-sky)',
            color: '#020406',
            cursor: 'pointer',
            fontSize: 12,
          }}
        >
          Search
        </button>
      </div>

      {/* Results */}
      {isLoading() && (
        <div style={{ textAlign: 'center', padding: 16, color: 'var(--j-text-dim)', fontSize: 13 }}>Loading...</div>
      )}

      {!isLoading() && (
        <>
          {/* Search results override current tab */}
          {searchResults !== null && (
            <div style={{ marginBottom: 4, fontSize: 11, color: 'var(--j-text-dim)' }}>
              Search results ({searchResults.length})
              <button
                onClick={() => setSearchResults(null)}
                style={{ marginLeft: 8, textDecoration: 'underline', background: 'none', border: 'none', color: 'var(--j-sky)', cursor: 'pointer', fontSize: 11 }}
              >
                Clear
              </button>
            </div>
          )}

          {searchResults !== null && searchResults.length === 0 && (
            <div style={{ textAlign: 'center', padding: 16, color: 'var(--j-text-dim)', fontSize: 13 }}>No results</div>
          )}

          {searchResults !== null && searchResults.map(renderItem)}

          {searchResults === null && tab === 'facts' && knowledgeItems.length === 0 && (
            <div style={{ textAlign: 'center', padding: 16, color: 'var(--j-text-dim)', fontSize: 13 }}>No knowledge items yet</div>
          )}
          {searchResults === null && tab === 'facts' && knowledgeItems.map(renderItem)}

          {searchResults === null && tab === 'experiences' && experiences.length === 0 && (
            <div style={{ textAlign: 'center', padding: 16, color: 'var(--j-text-dim)', fontSize: 13 }}>No experiences yet</div>
          )}
          {searchResults === null && tab === 'experiences' && experiences.map(renderExperience)}

          {searchResults === null && tab === 'patterns' && patterns.length === 0 && (
            <div style={{ textAlign: 'center', padding: 16, color: 'var(--j-text-dim)', fontSize: 13 }}>No patterns yet</div>
          )}
          {searchResults === null && tab === 'patterns' && patterns.map(renderPattern)}

          {searchResults === null && tab === 'failures' && failures.length === 0 && (
            <div style={{ textAlign: 'center', padding: 16, color: 'var(--j-text-dim)', fontSize: 13 }}>No failures recorded</div>
          )}
          {searchResults === null && tab === 'failures' && failures.map(renderFailure)}
        </>
      )}
    </div>
  );
}
