import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { ActivityGraph } from '../components/operations/ActivityGraph';
import type { ActivityNode, ActivityTree } from '@jarvis/sdk';

// Mock @jarvis/sdk before any imports from the component
vi.mock('@jarvis/sdk', () => ({
  activity: {
    tree: vi.fn(),
  },
}));

import { activity } from '@jarvis/sdk';
const mockedTree = activity.tree as ReturnType<typeof vi.fn>;

function makeNode(overrides: Partial<ActivityNode> = {}): ActivityNode {
  return {
    node_id: 'n1',
    activity_id: 'act_1',
    node_type: 'goal',
    label: 'Root',
    status: 'RUNNING',
    depth: 0,
    ...overrides,
  } as ActivityNode;
}

const emptyTree: ActivityTree = { nodes: [], edges: [] };

const sampleTree: ActivityTree = {
  nodes: [
    { node_id: 'n1', activity_id: 'act_1', node_type: 'goal', label: 'Root', status: 'RUNNING', depth: 0 },
    { node_id: 'n2', activity_id: 'act_1', node_type: 'subgoal', label: 'Sub A', status: 'PENDING', depth: 1, parent_id: 'n1' },
    { node_id: 'n3', activity_id: 'act_1', node_type: 'agent_call', label: 'Agent 1', status: 'RUNNING', depth: 2, parent_id: 'n2', agent_id: 'builder' },
    { node_id: 'n4', activity_id: 'act_1', node_type: 'subgoal', label: 'Sub B', status: 'COMPLETED', depth: 1, parent_id: 'n1' },
  ],
  edges: [
    { edge_id: 'e1', from_node_id: 'n1', to_node_id: 'n2', edge_type: 'contains' },
    { edge_id: 'e2', from_node_id: 'n1', to_node_id: 'n4', edge_type: 'contains' },
  ],
};

describe('ActivityGraph component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows loading state', () => {
    mockedTree.mockReturnValue(new Promise(() => {})); // never resolves
    render(<ActivityGraph activityId="act_1" />);
    expect(screen.getByText('Loading activity graph...')).toBeInTheDocument();
  });

  it('shows error when fetch fails', async () => {
    mockedTree.mockRejectedValue(new Error('Network error'));
    render(<ActivityGraph activityId="act_1" />);
    expect(await screen.findByText('Network error')).toBeInTheDocument();
  });

  it('shows error when tree is empty', async () => {
    mockedTree.mockResolvedValue(emptyTree);
    render(<ActivityGraph activityId="act_1" />);
    expect(await screen.findByText('No data')).toBeInTheDocument();
  });

  it('renders tree nodes', async () => {
    mockedTree.mockResolvedValue(sampleTree);
    render(<ActivityGraph activityId="act_1" />);
    expect(await screen.findByText('Root')).toBeInTheDocument();
    expect(screen.getByText('Sub A')).toBeInTheDocument();
    expect(screen.getByText('Agent 1')).toBeInTheDocument();
    expect(screen.getByText('Sub B')).toBeInTheDocument();
  });

  it('shows node count', async () => {
    mockedTree.mockResolvedValue(sampleTree);
    render(<ActivityGraph activityId="act_1" />);
    expect(await screen.findByText('(4 nodes)')).toBeInTheDocument();
  });

  it('renders edge badges', async () => {
    mockedTree.mockResolvedValue(sampleTree);
    render(<ActivityGraph activityId="act_1" />);
    expect(await screen.findByText(/contains/)).toBeInTheDocument();
  });

  it('renders color legend', async () => {
    mockedTree.mockResolvedValue(sampleTree);
    render(<ActivityGraph activityId="act_1" />);
    expect(await screen.findByText('goal')).toBeInTheDocument();
    expect(screen.getByText('subgoal')).toBeInTheDocument();
    expect(screen.getByText('agent_call')).toBeInTheDocument();
    expect(screen.getByText('tool_call')).toBeInTheDocument();
    expect(screen.getByText('artifact')).toBeInTheDocument();
    expect(screen.getByText('milestone')).toBeInTheDocument();
  });

  it('calls onClose when close button clicked', async () => {
    mockedTree.mockResolvedValue(sampleTree);
    const onClose = vi.fn();
    render(<ActivityGraph activityId="act_1" onClose={onClose} />);
    expect(await screen.findByText('✕')).toBeInTheDocument();
    screen.getByText('✕').click();
    expect(onClose).toHaveBeenCalled();
  });
});
