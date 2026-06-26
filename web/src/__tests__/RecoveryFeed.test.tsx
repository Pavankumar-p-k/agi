import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import {
  RecoveryFeed,
  isUpdated,
  isCompleted,
  isResumed,
  getEventIcon,
  getEventColor,
  getEventDescription,
  formatTimestamp,
} from '../components/operations/RecoveryFeed';
import type { ActivityEvent } from '@jarvis/sdk';

describe('RecoveryFeed type guards', () => {
  const updated: ActivityEvent = { event: 'activity_updated', activity_id: 'act_1' };
  const completed: ActivityEvent = { event: 'activity_completed', activity_id: 'act_1', status: 'COMPLETED' };
  const resumed: ActivityEvent = { event: 'activity_resumed', activity_id: 'act_1', node_id: 'n1' };

  it('detects activity_updated', () => {
    expect(isUpdated(updated)).toBe(true);
    expect(isUpdated(completed)).toBe(false);
  });

  it('detects activity_completed', () => {
    expect(isCompleted(completed)).toBe(true);
    expect(isCompleted(updated)).toBe(false);
  });

  it('detects activity_resumed', () => {
    expect(isResumed(resumed)).toBe(true);
    expect(isResumed(updated)).toBe(false);
  });
});

describe('RecoveryFeed event helpers', () => {
  it('getEventIcon returns correct icons', () => {
    const completeOk: ActivityEvent = { event: 'activity_completed', activity_id: 'a1', status: 'COMPLETED' };
    const completeFail: ActivityEvent = { event: 'activity_completed', activity_id: 'a1', status: 'FAILED' };
    const resumed: ActivityEvent = { event: 'activity_resumed', activity_id: 'a1', node_id: 'n1' };
    const updatedRunning: ActivityEvent = { event: 'activity_updated', activity_id: 'a1', status: 'RUNNING' };
    const updated: ActivityEvent = { event: 'activity_updated', activity_id: 'a1' };
    const triggered: ActivityEvent = { event: 'schedule_triggered', activity_id: '', schedule_id: 's1' };
    const failed: ActivityEvent = { event: 'schedule_failed', activity_id: '', schedule_id: 's1', error: 'err' };

    expect(getEventIcon(completeOk)).toBe('✓');
    expect(getEventIcon(completeFail)).toBe('⚠');
    expect(getEventIcon(resumed)).toBe('▶');
    expect(getEventIcon(updatedRunning)).toBe('⚡');
    expect(getEventIcon(updated)).toBe('○');
    expect(getEventIcon(triggered)).toBe('⏰');
    expect(getEventIcon(failed)).toBe('⛔');
  });

  it('getEventColor returns correct colors', () => {
    const completeOk: ActivityEvent = { event: 'activity_completed', activity_id: 'a1', status: 'COMPLETED' };
    const completeFail: ActivityEvent = { event: 'activity_completed', activity_id: 'a1', status: 'FAILED' };
    const resumed: ActivityEvent = { event: 'activity_resumed', activity_id: 'a1', node_id: 'n1' };
    const triggered: ActivityEvent = { event: 'schedule_triggered', activity_id: '', schedule_id: 's1' };
    const failed: ActivityEvent = { event: 'schedule_failed', activity_id: '', schedule_id: 's1', error: 'err' };

    expect(getEventColor(completeOk)).toBe('#22c55e');
    expect(getEventColor(completeFail)).toBe('#ef4444');
    expect(getEventColor(resumed)).toBe('#00d2ff');
    expect(getEventColor(triggered)).toBe('#22c55e');
    expect(getEventColor(failed)).toBe('#ef4444');
  });

  it('getEventDescription returns correct text', () => {
    const completeOk: ActivityEvent = { event: 'activity_completed', activity_id: 'act_test_123456', status: 'COMPLETED' };
    const completeErr: ActivityEvent = { event: 'activity_completed', activity_id: 'act_test_123456', status: 'FAILED', error: 'timeout' };
    const resumed: ActivityEvent = { event: 'activity_resumed', activity_id: 'act_test_123456', node_id: 'node_target_1' };
    const updated: ActivityEvent = { event: 'activity_updated', activity_id: 'act_test_123456', status: 'RUNNING' };
    const triggered: ActivityEvent = { event: 'schedule_triggered', activity_id: '', schedule_id: 'sched_target_1' };
    const failed: ActivityEvent = { event: 'schedule_failed', activity_id: '', schedule_id: 'sched_target_1', error: 'disk full' };

    expect(getEventDescription(completeOk)).toContain('completed');
    expect(getEventDescription(completeOk)).toContain('act_test_123');
    expect(getEventDescription(completeErr)).toContain('timeout');
    expect(getEventDescription(resumed)).toContain('resumed');
    expect(getEventDescription(resumed)).toContain('node_target');
    expect(getEventDescription(updated)).toContain('RUNNING');
    expect(getEventDescription(triggered)).toContain('triggered');
    expect(getEventDescription(triggered)).toContain('sched_target');
    expect(getEventDescription(failed)).toContain('disk full');
  });

  it('formatTimestamp handles relative time', () => {
    const now = new Date().toISOString();
    expect(formatTimestamp(now)).toBe('just now');

    const fiveMinAgo = new Date(Date.now() - 5 * 60 * 1000).toISOString();
    expect(formatTimestamp(fiveMinAgo)).toMatch(/m ago/);

    const twoHAgo = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();
    expect(formatTimestamp(twoHAgo)).toMatch(/h ago/);
  });
});

describe('RecoveryFeed component', () => {
  it('returns null when empty', () => {
    const { container } = render(<RecoveryFeed events={[]} />);
    expect(container.innerHTML).toBe('');
  });

  it('renders completed event', () => {
    const events: ActivityEvent[] = [
      { event: 'activity_completed', activity_id: 'act_123', status: 'COMPLETED' },
    ];
    render(<RecoveryFeed events={events} />);
    expect(screen.getByText(/completed/)).toBeInTheDocument();
  });

  it('renders multiple events', () => {
    const events: ActivityEvent[] = [
      { event: 'activity_updated', activity_id: 'act_1', status: 'RUNNING' },
      { event: 'activity_completed', activity_id: 'act_2', status: 'COMPLETED' },
      { event: 'activity_resumed', activity_id: 'act_3', node_id: 'n_1' },
    ];
    render(<RecoveryFeed events={events} />);
    expect(screen.getByText('Event Feed')).toBeInTheDocument();
    expect(screen.getByText('(3)')).toBeInTheDocument();
  });

  it('respects max prop', () => {
    const events: ActivityEvent[] = Array.from({ length: 10 }, (_, i) => ({
      event: 'activity_updated' as const,
      activity_id: `act_${i}`,
      status: 'RUNNING',
    }));
    render(<RecoveryFeed events={events} max={3} />);
    const items = screen.getAllByText(/RUNNING/);
    expect(items.length).toBe(3);
  });
});
