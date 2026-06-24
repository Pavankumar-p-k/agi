'use client';

import { useState, useEffect, useCallback } from 'react';
import { scheduler } from '@jarvis/sdk';
import type { Schedule } from '@jarvis/sdk';

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

function nextRun(dateStr: string | null | undefined): string {
  if (!dateStr) return '—';
  const d = new Date(dateStr);
  const now = Date.now();
  const diff = d.getTime() - now;
  if (diff < 0) return 'overdue';
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `in ${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `in ${hrs}h`;
  return d.toLocaleDateString();
}

function intervalLabel(s: Schedule): string {
  if (s.cron) return `Cron: ${s.cron}`;
  if (s.interval_seconds) {
    if (s.interval_seconds < 60) return `Every ${s.interval_seconds}s`;
    if (s.interval_seconds < 3600) return `Every ${Math.floor(s.interval_seconds / 60)}min`;
    return `Every ${Math.floor(s.interval_seconds / 3600)}h`;
  }
  return 'Manual';
}

interface Props {
  onCreate?: () => void;
}

export function ScheduledGoals({ onCreate }: Props) {
  const [scheduleList, setScheduleList] = useState<Schedule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actioning, setActioning] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [newInterval, setNewInterval] = useState('3600');

  const load = useCallback(() => {
    setLoading(true);
    scheduler
      .list()
      .then((r) => {
        setScheduleList(r.schedules);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load schedules'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const handlePause = async (id: string) => {
    setActioning(id);
    try {
      await scheduler.pause(id);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to pause');
    } finally {
      setActioning(null);
    }
  };

  const handleResume = async (id: string) => {
    setActioning(id);
    try {
      await scheduler.resume(id);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to resume');
    } finally {
      setActioning(null);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this schedule?')) return;
    setActioning(id);
    try {
      await scheduler.delete(id);
      setScheduleList((prev) => prev.filter((s) => s.id !== id));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete');
    } finally {
      setActioning(null);
    }
  };

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setActioning('__create__');
    try {
      await scheduler.create({
        name: newName.trim(),
        interval_seconds: parseInt(newInterval, 10) || undefined,
      });
      setNewName('');
      setShowCreate(false);
      onCreate?.();
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create schedule');
    } finally {
      setActioning(null);
    }
  };

  if (loading && scheduleList.length === 0) {
    return (
      <div className="hud-panel" style={{ padding: 24 }}>
        <h2 className="hud-title">Scheduled Goals</h2>
        <div style={{ textAlign: 'center', padding: 16, color: 'var(--j-text-dim)', fontSize: 13 }}>Loading...</div>
      </div>
    );
  }

  return (
    <div className="hud-panel" style={{ padding: 24 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2 className="hud-title" style={{ margin: 0 }}>
          Scheduled Goals
          {scheduleList.length > 0 && (
            <span style={{ fontSize: 12, marginLeft: 8, opacity: 0.6 }}>({scheduleList.length})</span>
          )}
        </h2>
        <button
          onClick={() => setShowCreate(!showCreate)}
          style={{
            padding: '4px 12px',
            borderRadius: 4,
            border: '1px solid var(--j-border)',
            background: 'var(--j-surface)',
            color: 'var(--j-sky)',
            cursor: 'pointer',
            fontSize: 12,
          }}
        >
          {showCreate ? 'Cancel' : '+ Schedule'}
        </button>
      </div>

      {error && (
        <div style={{ fontSize: 12, color: '#f55', marginBottom: 8 }}>{error}</div>
      )}

      {/* Create form */}
      {showCreate && (
        <div
          style={{
            padding: 12,
            borderRadius: 4,
            background: 'var(--j-surface)',
            border: '1px solid var(--j-border)',
            marginBottom: 12,
            display: 'flex',
            flexDirection: 'column',
            gap: 8,
          }}
        >
          <input
            placeholder="Schedule name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
            style={{
              padding: '6px 10px',
              borderRadius: 4,
              border: '1px solid var(--j-border)',
              background: 'var(--j-bg)',
              color: 'var(--j-text)',
              fontSize: 12,
              outline: 'none',
            }}
          />
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <span style={{ fontSize: 11, color: 'var(--j-text-dim)' }}>Interval:</span>
            <select
              value={newInterval}
              onChange={(e) => setNewInterval(e.target.value)}
              style={{
                padding: '4px 8px',
                borderRadius: 4,
                border: '1px solid var(--j-border)',
                background: 'var(--j-bg)',
                color: 'var(--j-text)',
                fontSize: 11,
                flex: 1,
              }}
            >
              <option value="300">Every 5 min</option>
              <option value="900">Every 15 min</option>
              <option value="3600">Every hour</option>
              <option value="21600">Every 6 hours</option>
              <option value="86400">Daily</option>
            </select>
            <button
              onClick={handleCreate}
              disabled={actioning === '__create__' || !newName.trim()}
              style={{
                padding: '4px 12px',
                borderRadius: 4,
                border: 'none',
                background: 'var(--j-sky)',
                color: '#020406',
                cursor: 'pointer',
                fontSize: 11,
                fontWeight: 500,
                opacity: actioning === '__create__' || !newName.trim() ? 0.6 : 1,
              }}
            >
              Create
            </button>
          </div>
        </div>
      )}

      {/* Empty state */}
      {scheduleList.length === 0 && !showCreate && (
        <div style={{ textAlign: 'center', padding: '24px 0', color: 'var(--j-text-dim)', fontSize: 13 }}>
          No schedules. Create one to automate recurring work.
        </div>
      )}

      {/* Schedule list */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {scheduleList.map((s) => (
          <div
            key={s.id}
            style={{
              padding: '10px 12px',
              borderRadius: 4,
              background: 'var(--j-surface)',
              border: '1px solid var(--j-border)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  background:
                    s.status === 'active' ? '#22c55e'
                    : s.status === 'paused' ? '#f5c842'
                    : s.status === 'failed' ? '#ef4444'
                    : '#6b7280',
                }}
              />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {s.name}
                </div>
                <div style={{ fontSize: 10, color: 'var(--j-text-dim)', marginTop: 2 }}>
                  {intervalLabel(s)}
                  {s.next_run_at && ` · Next: ${nextRun(s.next_run_at)}`}
                  {s.last_run_at && ` · Last: ${timeAgo(s.last_run_at)}`}
                </div>
              </div>
              <div style={{ display: 'flex', gap: 4 }}>
                {s.status === 'active' && (
                  <button
                    onClick={() => handlePause(s.id)}
                    disabled={actioning === s.id}
                    style={{
                      padding: '2px 8px',
                      borderRadius: 3,
                      border: '1px solid #f5c842',
                      background: 'rgba(245,200,66,0.1)',
                      color: '#f5c842',
                      cursor: 'pointer',
                      fontSize: 10,
                      opacity: actioning === s.id ? 0.6 : 1,
                    }}
                  >
                    Pause
                  </button>
                )}
                {s.status === 'paused' && (
                  <button
                    onClick={() => handleResume(s.id)}
                    disabled={actioning === s.id}
                    style={{
                      padding: '2px 8px',
                      borderRadius: 3,
                      border: '1px solid #22c55e',
                      background: 'rgba(34,197,94,0.1)',
                      color: '#22c55e',
                      cursor: 'pointer',
                      fontSize: 10,
                      opacity: actioning === s.id ? 0.6 : 1,
                    }}
                  >
                    Resume
                  </button>
                )}
                <button
                  onClick={() => handleDelete(s.id)}
                  disabled={actioning === s.id}
                  style={{
                    padding: '2px 8px',
                    borderRadius: 3,
                    border: '1px solid #ef4444',
                    background: 'rgba(239,68,68,0.1)',
                    color: '#ef4444',
                    cursor: 'pointer',
                    fontSize: 10,
                    opacity: actioning === s.id ? 0.6 : 1,
                  }}
                >
                  Delete
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
