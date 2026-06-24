'use client';

import { StatusDot, ProgressBar } from '@jarvis/ui';
import type { ActivityNode } from '@jarvis/sdk';

interface Props {
  activities: ActivityNode[];
  onSelect?: (activity: ActivityNode) => void;
}

export function ActiveGoals({ activities, onSelect }: Props) {
  const goals = activities.filter((a) => a.node_type === 'goal');
  if (goals.length === 0) {
    return (
      <div className="hud-panel" style={{ padding: 24 }}>
        <h2 className="hud-title" style={{ marginBottom: 16 }}>Active Goals</h2>
        <div style={{ textAlign: 'center', padding: '32px 0', color: 'var(--j-text-dim)', fontSize: 13 }}>
          No active goals. Start one to see activity.
        </div>
      </div>
    );
  }

  return (
    <div className="hud-panel" style={{ padding: 24 }}>
      <h2 className="hud-title" style={{ marginBottom: 16 }}>
        Active Goals
        <span style={{ fontSize: 12, marginLeft: 8, opacity: 0.6 }}>({goals.length})</span>
      </h2>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {goals.map((goal) => (
          <div
            key={goal.node_id}
            onClick={() => onSelect?.(goal)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              padding: '12px 16px',
              borderRadius: 6,
              background: 'var(--j-surface)',
              border: '1px solid var(--j-border)',
              cursor: onSelect ? 'pointer' : 'default',
              transition: 'background 0.15s',
            }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'var(--j-surface-hover)'; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = 'var(--j-surface)'; }}
          >
            <StatusDot status={goal.status} pulse={goal.status === 'RUNNING'} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {goal.label}
              </div>
              <div style={{ marginTop: 4 }}>
                <ProgressBar
                  value={goal.metadata?.progress as number ?? 0}
                  label={`${goal.metadata?.progress ?? 0}%`}
                  height={4}
                />
              </div>
            </div>
            <span style={{ fontSize: 11, color: 'var(--j-text-dim)' }}>
              {goal.status}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
