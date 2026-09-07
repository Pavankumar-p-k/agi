import { describe, it, expect, beforeEach, vi } from 'vitest';
import { activity } from '../activity';

function mockFetch(data: unknown, ok = true) {
  return vi.fn().mockResolvedValueOnce({
    ok,
    status: ok ? 200 : 500,
    statusText: ok ? 'OK' : 'Internal Server Error',
    json: () => Promise.resolve(data),
    text: () => Promise.resolve(ok ? '' : 'error'),
  });
}

const MOCK_NODE = {
  node_id: 'act_test123',
  activity_id: 'act_test123',
  node_type: 'goal',
  label: 'Test activity',
  status: 'RUNNING',
  depth: 0,
  parent_id: null,
  agent_id: null,
  origin_node_id: null,
  artifacts: {},
  workflow_id: null,
  started_at: '2026-06-25T10:00:00',
  completed_at: null,
  created_at: '2026-06-25T10:00:00',
  metadata: {},
};

const MOCK_COUNTS = { total: 5, running: 2, pending: 3, completed: 10, failed: 1, suspended: 0, cancelled: 1 };

const MOCK_TREE = {
  nodes: [MOCK_NODE, { ...MOCK_NODE, node_id: 'sg_child1', parent_id: 'act_test123', node_type: 'subgoal', depth: 1, label: 'Subgoal 1' }],
  edges: [{ edge_id: 'ed_1', from_node_id: 'act_test123', to_node_id: 'sg_child1', edge_type: 'depends_on', created_at: '2026-06-25T10:00:00' }],
};

const MOCK_SUMMARY = {
  activity_id: 'act_test123',
  goal: 'Test activity',
  status: 'RUNNING',
  total_nodes: 2,
  by_status: { RUNNING: 2 },
  by_type: { goal: 1, subgoal: 1 },
  depth: 1,
  agents_used: [],
  created_at: '2026-06-25T10:00:00',
};

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('activity.list', () => {
  it('returns list of active activities', async () => {
    globalThis.fetch = mockFetch({ activities: [MOCK_NODE] });
    const result = await activity.list();
    expect(result).toEqual([MOCK_NODE]);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/activity'),
      expect.any(Object),
    );
  });

  it('throws on server error', async () => {
    globalThis.fetch = mockFetch(null, false);
    await expect(activity.list()).rejects.toThrow();
  });
});

describe('activity.counts', () => {
  it('returns aggregate counts', async () => {
    globalThis.fetch = mockFetch(MOCK_COUNTS);
    const result = await activity.counts();
    expect(result).toEqual(MOCK_COUNTS);
  });
});

describe('activity.get', () => {
  it('returns a single activity node', async () => {
    globalThis.fetch = mockFetch(MOCK_NODE);
    const result = await activity.get('act_test123');
    expect(result).toEqual(MOCK_NODE);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/activity/act_test123'),
      expect.any(Object),
    );
  });

  it('encodes the activity ID', async () => {
    globalThis.fetch = mockFetch(MOCK_NODE);
    await activity.get('act with spaces');
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining(encodeURIComponent('act with spaces')),
      expect.any(Object),
    );
  });
});

describe('activity.tree', () => {
  it('returns full activity tree', async () => {
    globalThis.fetch = mockFetch(MOCK_TREE);
    const result = await activity.tree('act_test123');
    expect(result).toEqual(MOCK_TREE);
    expect(result.nodes).toHaveLength(2);
    expect(result.edges).toHaveLength(1);
  });
});

describe('activity.timeline', () => {
  it('returns timeline array', async () => {
    globalThis.fetch = mockFetch({ timeline: [MOCK_NODE] });
    const result = await activity.timeline('act_test123');
    expect(result).toHaveLength(1);
    expect(result[0]).toEqual(MOCK_NODE);
  });
});

describe('activity.summary', () => {
  it('returns activity summary', async () => {
    globalThis.fetch = mockFetch(MOCK_SUMMARY);
    const result = await activity.summary('act_test123');
    expect(result).toEqual(MOCK_SUMMARY);
  });
});

describe('activity.resumePoint', () => {
  it('returns resume context (GET)', async () => {
    const ctx = { activity_id: 'act_test123', target_node: MOCK_NODE, ancestors: [], accumulated_artifacts: {}, accumulated_input: {} };
    globalThis.fetch = mockFetch(ctx);
    const result = await activity.resumePoint('act_test123');
    expect(result).toEqual(ctx);
  });
});

describe('activity.resume', () => {
  it('resumes an activity (POST)', async () => {
    const ctx = { activity_id: 'act_test123', target_node: MOCK_NODE, ancestors: [], accumulated_artifacts: {}, accumulated_input: {} };
    globalThis.fetch = mockFetch(ctx);
    const result = await activity.resume('act_test123');
    expect(result).toEqual(ctx);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/activity/act_test123/resume'),
      expect.objectContaining({ method: 'POST' }),
    );
  });
});

describe('activity.pause', () => {
  it('pauses a running activity', async () => {
    globalThis.fetch = mockFetch({ status: 'paused' });
    const result = await activity.pause('act_test123');
    expect(result).toEqual({ status: 'paused' });
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/activity/act_test123/pause'),
      expect.objectContaining({ method: 'POST' }),
    );
  });
});

describe('activity.cancel', () => {
  it('cancels an activity', async () => {
    globalThis.fetch = mockFetch({ status: 'cancelled' });
    const result = await activity.cancel('act_test123');
    expect(result).toEqual({ status: 'cancelled' });
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/activity/act_test123/cancel'),
      expect.objectContaining({ method: 'POST' }),
    );
  });
});

describe('activity.search', () => {
  it('searches activities by label', async () => {
    globalThis.fetch = mockFetch({ results: [MOCK_NODE] });
    const result = await activity.search('test');
    expect(result).toEqual([MOCK_NODE]);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('q=test'),
      expect.any(Object),
    );
  });
});

describe('activity.byAgent', () => {
  it('returns nodes by agent', async () => {
    globalThis.fetch = mockFetch({ nodes: [MOCK_NODE] });
    const result = await activity.byAgent('agent_1');
    expect(result).toEqual([MOCK_NODE]);
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/activity/by-agent/agent_1'),
      expect.any(Object),
    );
  });
});
