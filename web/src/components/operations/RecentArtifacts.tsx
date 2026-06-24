'use client';

import { useState, useEffect } from 'react';
import { artifacts } from '@jarvis/sdk';
import type { Artifact } from '@jarvis/sdk';

const ARTIFACT_ICONS: Record<string, string> = {
  screenshot: '🖼',
  apk: '📦',
  aab: '📦',
  build_log: '📋',
  report: '📊',
  coverage: '📈',
  test_result: '✅',
  email_sent: '✉',
  html_snapshot: '📄',
  file: '📎',
};

function formatSize(bytes: number | null | undefined): string {
  if (!bytes) return '';
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
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

interface Props {
  limit?: number;
}

export function RecentArtifacts({ limit = 12 }: Props) {
  const [artifactList, setArtifactList] = useState<Artifact[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    artifacts
      .list({ limit })
      .then((r) => {
        setArtifactList(r.artifacts);
        setTotal(r.total);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load artifacts'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [limit]);

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this artifact?')) return;
    setDeleting(id);
    try {
      await artifacts.delete(id);
      setArtifactList((prev) => prev.filter((a) => a.artifact_id !== id));
      setTotal((prev) => prev - 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete artifact');
    } finally {
      setDeleting(null);
    }
  };

  if (loading && artifactList.length === 0) {
    return (
      <div className="hud-panel" style={{ padding: 24 }}>
        <h2 className="hud-title">Recent Artifacts</h2>
        <div style={{ textAlign: 'center', padding: 16, color: 'var(--j-text-dim)', fontSize: 13 }}>Loading...</div>
      </div>
    );
  }

  if (artifactList.length === 0) {
    return null;
  }

  return (
    <div className="hud-panel" style={{ padding: 24 }}>
      <h2 className="hud-title" style={{ marginBottom: 16 }}>
        Recent Artifacts
        <span style={{ fontSize: 12, marginLeft: 8, opacity: 0.6 }}>({total})</span>
      </h2>

      {error && (
        <div style={{ fontSize: 12, color: '#f55', marginBottom: 8 }}>{error}</div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 8 }}>
        {artifactList.map((art) => (
          <div
            key={art.artifact_id}
            className="artifact-card"
            style={{
              padding: '12px 16px',
              borderRadius: 4,
              background: 'var(--j-surface)',
              border: '1px solid var(--j-border)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
              <div style={{ fontSize: 20, marginBottom: 4 }}>
                {ARTIFACT_ICONS[art.artifact_type] || '📎'}
              </div>
              <button
                onClick={() => handleDelete(art.artifact_id)}
                disabled={deleting === art.artifact_id}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--j-text-dim)',
                  cursor: 'pointer',
                  fontSize: 14,
                  padding: 0,
                  lineHeight: 1,
                  opacity: deleting === art.artifact_id ? 0.5 : 1,
                }}
                title="Delete artifact"
              >
                ×
              </button>
            </div>
            <div
              style={{
                fontSize: 12,
                fontWeight: 500,
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
              title={art.name}
            >
              {art.name}
            </div>
            <div style={{ display: 'flex', gap: 8, fontSize: 10, color: 'var(--j-text-dim)', marginTop: 4 }}>
              <span>{art.artifact_type}</span>
              {art.size_bytes != null && <span>{formatSize(art.size_bytes)}</span>}
              <span style={{ marginLeft: 'auto' }}>{timeAgo(art.created_at)}</span>
            </div>
            <div style={{ marginTop: 8, display: 'flex', gap: 6 }}>
              <a
                href={artifacts.downloadUrl(art.artifact_id)}
                download
                style={{
                  fontSize: 11,
                  padding: '2px 8px',
                  borderRadius: 3,
                  background: 'rgba(99, 132, 255, 0.15)',
                  color: '#6384ff',
                  textDecoration: 'none',
                }}
              >
                Download
              </a>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
