import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ActiveGoals } from '../components/operations/ActiveGoals';
import type { ActivityNode } from '@jarvis/sdk';

function makeGoal(overrides: Partial<ActivityNode> = {}): ActivityNode {
  return {
    node_id: 'act_test_001',
    activity_id: 'act_test_001',
    node_type: 'goal',
    label: 'Test Goal',
    status: 'RUNNING',
    depth: 0,
    metadata: { progress: 50 },
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  } as ActivityNode;
}

describe('ActiveGoals', () => {
  it('shows empty state when no goals', () => {
    render(<ActiveGoals activities={[]} />);
    expect(screen.getByText('No active goals. Start one to see activity.')).toBeInTheDocument();
  });

  it('renders goal labels', () => {
    const goals = [makeGoal({ label: 'Build app' }), makeGoal({ label: 'Test suite' })];
    render(<ActiveGoals activities={goals} />);
    expect(screen.getByText('Build app')).toBeInTheDocument();
    expect(screen.getByText('Test suite')).toBeInTheDocument();
  });

  it('shows goal count', () => {
    const goals = [makeGoal(), makeGoal({ node_id: 'act_002', activity_id: 'act_002' })];
    render(<ActiveGoals activities={goals} />);
    expect(screen.getByText('(2)')).toBeInTheDocument();
  });

  it('calls onSelect when clicked', () => {
    const onSelect = vi.fn();
    const goal = makeGoal({ label: 'Clickable goal' });
    render(<ActiveGoals activities={[goal]} onSelect={onSelect} />);
    fireEvent.click(screen.getByText('Clickable goal'));
    expect(onSelect).toHaveBeenCalledWith(goal);
  });

  it('renders status text for each goal', () => {
    const goals = [makeGoal({ status: 'RUNNING' }), makeGoal({ node_id: 'act_002', activity_id: 'act_002', status: 'COMPLETED' })];
    render(<ActiveGoals activities={goals} />);
    expect(screen.getByText('RUNNING')).toBeInTheDocument();
    expect(screen.getByText('COMPLETED')).toBeInTheDocument();
  });

  it('filters out non-goal nodes', () => {
    const activities: ActivityNode[] = [
      makeGoal({ node_id: 'act_001', activity_id: 'act_001', label: 'Real goal' }),
      makeGoal({ node_id: 'act_002', activity_id: 'act_002', node_type: 'subgoal', label: 'Sub task' }),
      makeGoal({ node_id: 'act_003', activity_id: 'act_003', node_type: 'tool_call', label: 'A tool call' }),
    ];
    render(<ActiveGoals activities={activities} />);
    expect(screen.getByText('Real goal')).toBeInTheDocument();
    expect(screen.queryByText('Sub task')).not.toBeInTheDocument();
    expect(screen.queryByText('A tool call')).not.toBeInTheDocument();
  });
});
