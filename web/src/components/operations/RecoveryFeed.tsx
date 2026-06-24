'use client';

import type { ActivityEvent, ActivityUpdatedEvent, ActivityCompletedEvent, ActivityResumedEvent, ScheduleTriggeredEvent, ScheduleFailedEvent } from '@jarvis/sdk';

interface Props {
  events: ActivityEvent[];
  max?: number;
}

function isUpdated(e: ActivityEvent): e is ActivityUpdatedEvent {
  return e.event === 'activity_updated';
}

function isCompleted(e: ActivityEvent): e is ActivityCompletedEvent {
  return e.event === 'activity_completed';
}

function isResumed(e: ActivityEvent): e is ActivityResumedEvent {
  return e.event === 'activity_resumed';
}

function isScheduleTriggered(e: ActivityEvent): e is ScheduleTriggeredEvent {
  return e.event === 'schedule_triggered';
}

function isScheduleFailed(e: ActivityEvent): e is ScheduleFailedEvent {
  return e.event === 'schedule_failed';
}

function getEventIcon(event: ActivityEvent): string {
  if (isCompleted(event)) {
    return event.status === 'FAILED' || event.status === 'CANCELLED' ? '⚠' : '✓';
  }
  if (isResumed(event)) return '▶';
  if (isUpdated(event)) return event.status === 'RUNNING' ? '⚡' : '○';
  if (isScheduleTriggered(event)) return '⏰';
  if (isScheduleFailed(event)) return '⛔';
  return '•';
}

function getEventColor(event: ActivityEvent): string {
  if (isCompleted(event)) {
    return event.status === 'FAILED' || event.status === 'CANCELLED' ? '#ef4444' : '#22c55e';
  }
  if (isResumed(event)) return '#00d2ff';
  if (isScheduleTriggered(event)) return '#22c55e';
  if (isScheduleFailed(event)) return '#ef4444';
  return 'var(--j-text-dim)';
}

function formatTimestamp(ts: string): string {
  try {
    const d = new Date(ts);
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    if (diff < 60000) return 'just now';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    return d.toLocaleDateString();
  } catch {
    return ts;
  }
}

function getEventDescription(event: ActivityEvent): string {
  if (isCompleted(event)) {
    if (event.error) return `Activity ${event.activity_id.slice(0, 12)} — ${event.error}`;
    return `Activity ${event.activity_id.slice(0, 12)} completed`;
  }
  if (isResumed(event)) {
    return `Activity ${event.activity_id.slice(0, 12)} resumed at node ${event.node_id.slice(0, 12)}`;
  }
  if (isUpdated(event)) {
    return `Activity ${event.activity_id.slice(0, 12)} → ${event.status}`;
  }
  if (isScheduleTriggered(event)) {
    return `Schedule ${event.schedule_id.slice(0, 12)} triggered`;
  }
  if (isScheduleFailed(event)) {
    return `Schedule ${event.schedule_id.slice(0, 12)} failed: ${event.error}`;
  }
  return event.event;
}

export function RecoveryFeed({ events, max = 50 }: Props) {
  const displayed = events.slice(0, max);

  if (displayed.length === 0) {
    return null;
  }

  return (
    <div className="hud-panel" style={{ padding: 24 }}>
      <h2 className="hud-title" style={{ marginBottom: 16 }}>
        Event Feed
        <span style={{ fontSize: 12, marginLeft: 8, opacity: 0.6 }}>({events.length})</span>
      </h2>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 200, overflowY: 'auto' }}>
        {displayed.map((event, idx) => (
          <div
            key={`${event.event}-${(event as any).activity_id}-${idx}`}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '4px 8px',
              borderRadius: 3,
              fontSize: 12,
              animation: 'fadeIn 0.2s ease',
            }}
          >
            <span style={{ color: getEventColor(event), flexShrink: 0 }}>{getEventIcon(event)}</span>
            <span style={{ flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {getEventDescription(event)}
            </span>
            <span style={{ color: 'var(--j-text-dim)', fontSize: 10, flexShrink: 0 }}>
              {formatTimestamp((event as any).timestamp || '')}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
