'use client';

import { useEffect, useState } from 'react';
import Card from '@/components/ui/Card';
import Badge from '@/components/ui/Badge';
import { api } from '@/lib/api';

interface MemoryResult {
  id?: string;
  content?: string;
  type?: string;
  timestamp?: string;
  score?: number;
  [key: string]: unknown;
}

export default function KnowledgePage() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<MemoryResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState('');

  async function search() {
    if (!query.trim()) return;
    setSearching(true);
    setError('');
    try {
      const res = await api.get<{ query: string; results: MemoryResult[] }>(`/api/memory/search?q=${encodeURIComponent(query)}&limit=20`);
      setResults(res.results || []);
    } catch {
      setError('Search failed');
      setResults([]);
    } finally {
      setSearching(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl p-6">
      <h1 className="font-display text-[28px] tracking-[0.12em] text-[var(--j-text)]">Knowledge & Memory</h1>
      <p className="mt-1 text-xs text-[var(--j-text-dim)]">Search across all stored memory</p>

      <div className="mt-6 flex gap-3">
        <input
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && search()}
          placeholder="Search memory..."
          className="flex-1 bg-[var(--j-bg)] border border-[var(--j-border)] px-4 py-3 text-sm text-[var(--j-text)] outline-none focus:border-[var(--j-sky)]"
        />
        <button onClick={search} disabled={searching} className="border border-[var(--j-sky)] px-6 py-2 text-xs tracking-[0.12em] text-[var(--j-sky)] transition-colors hover:bg-[var(--j-sky)] hover:text-[var(--j-bg)] disabled:opacity-30">
          {searching ? 'SEARCHING...' : 'SEARCH'}
        </button>
      </div>

      {error && <p className="mt-4 text-xs text-red-500">{error}</p>}

      {results.length > 0 && (
        <div className="mt-6 space-y-3">
          <p className="text-xs text-[var(--j-text-dim)]">{results.length} result(s)</p>
          {results.map((r, i) => (
            <Card key={r.id || i}>
              <div className="flex items-start gap-3">
                <span className="font-mono text-[10px] text-[var(--j-text-muted)] mt-0.5">{i + 1}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-[var(--j-text)]">{String(r.content || '(empty)')}</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {r.type && <Badge>{String(r.type)}</Badge>}
                    {r.score !== undefined && <Badge variant="hot">{(r.score * 100).toFixed(0)}%</Badge>}
                    {r.timestamp && <span className="font-mono text-[10px] text-[var(--j-text-muted)]">{new Date(r.timestamp).toLocaleString()}</span>}
                  </div>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {!searching && results.length === 0 && !error && (
        <div className="mt-12 text-center">
          <p className="font-display text-sm tracking-[0.12em] text-[var(--j-text-dim)]">Enter a query to search memory</p>
          <p className="mt-2 text-xs text-[var(--j-text-muted)]">Searches conversations, notes, and stored knowledge</p>
        </div>
      )}
    </div>
  );
}
