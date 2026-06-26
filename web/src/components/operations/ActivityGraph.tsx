'use client';

import { useState, useEffect } from 'react';
import { activity } from '@jarvis/sdk';
import type { ActivityNode, ActivityEdge, ActivityTree } from '@jarvis/sdk';
import { StatusDot } from '@jarvis/ui';

interface Props {
  activityId: string;
  onClose?: () => void;
}

const NODE_COLORS: Record<string, string> = {
  goal: '#00d2ff',
  subgoal: '#7ddcff',
  agent_call: '#f5c842',
  tool_call: '#8b8b8b',
  artifact: '#22c55e',
  milestone: '#a78bfa',
};

function buildTree(
  nodes: ActivityNode[],
): { node: ActivityNode; children: { node: ActivityNode; children: ActivityNode[] }[] } | null {
  if (nodes.length === 0) return null;
  const root = nodes.find((n) => n.depth === 0);
  if (!root) return null;
  const children = nodes.filter((n) => n.parent_id === root.node_id);
  return {
    node: root,
    children: children.map((c) => ({
      node: c,
      children: nodes.filter((n) => n.parent_id === c.node_id),
    })),
  };
}

export function ActivityGraph({ activityId, onClose }: Props) {
  const [tree, setTree] = useState<ActivityTree | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    activity
      .tree(activityId)
      .then(setTree)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load tree'))
      .finally(() => setLoading(false));
  }, [activityId]);

  if (loading) {
    return (
      <div className="hud-panel" style={{ padding: 24, height: 300, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ color: 'var(--j-text-dim)', fontSize: 13 }}>Loading activity graph...</span>
      </div>
    );
  }

  if (error || !tree) {
    return (
      <div className="hud-panel" style={{ padding: 24, height: 300, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ color: '#ef4444', fontSize: 13 }}>{error || 'No data'}</span>
      </div>
    );
  }

  const depthTree = buildTree(tree.nodes);

  return (
    <div className="hud-panel" style={{ padding: 24 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2 className="hud-title" style={{ margin: 0 }}>
          Activity Graph
          <span style={{ fontSize: 12, marginLeft: 8, opacity: 0.6 }}>({tree.nodes.length} nodes)</span>
        </h2>
        {onClose && (
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--j-text-dim)', cursor: 'pointer', fontSize: 16 }}>
            ✕
          </button>
        )}
      </div>

      <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
        {Object.entries(NODE_COLORS).map(([type, color]) => (
          <span key={type} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10, color: 'var(--j-text-dim)' }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: color }} />
            {type}
          </span>
        ))}
      </div>

      {depthTree && (
        <div style={{ padding: '8px 0' }}>
          <TreeNodeView node={depthTree.node} depth={0} />
          <div style={{ marginLeft: 24, borderLeft: '1px solid var(--j-border)', paddingLeft: 16 }}>
            {depthTree.children.map((child) => (
              <div key={child.node.node_id} style={{ marginBottom: 8 }}>
                <TreeNodeView node={child.node} depth={1} />
                {child.children.length > 0 && (
                  <div style={{ marginLeft: 24, borderLeft: '1px solid var(--j-border)', paddingLeft: 16, marginTop: 6 }}>
                    {child.children.map((gc) => (
                      <div key={gc.node_id} style={{ marginBottom: 4 }}>
                        <TreeNodeView node={gc} depth={2} />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      <div style={{ marginTop: 16, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {tree.edges.slice(0, 10).map((edge) => (
          <span
            key={edge.edge_id}
            style={{
              fontSize: 10,
              padding: '2px 8px',
              borderRadius: 4,
              background: 'var(--j-surface)',
              border: '1px solid var(--j-border)',
              color: 'var(--j-text-dim)',
            }}
          >
            {edge.edge_type}: {edge.from_node_id.slice(0, 8)} → {edge.to_node_id.slice(0, 8)}
          </span>
        ))}
      </div>
    </div>
  );
}

function TreeNodeView({ node, depth }: { node: ActivityNode; depth: number }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px', borderRadius: 4 }}>
      <div style={{ width: 20, textAlign: 'center' }}>
        <span style={{ width: 10, height: 10, borderRadius: '50%', display: 'inline-block', backgroundColor: NODE_COLORS[node.node_type] || '#666' }} />
      </div>
      <StatusDot status={node.status} size={8} pulse={node.status === 'RUNNING'} />
      <span style={{ fontSize: 12, fontWeight: node.node_type === 'goal' ? 600 : 400, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 300 }}>
        {node.label}
      </span>
      {node.agent_id && (
        <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 3, background: 'rgba(245,200,66,0.15)', color: '#f5c842' }}>
          {node.agent_id}
        </span>
      )}
      <span style={{ fontSize: 10, color: 'var(--j-text-dim)', marginLeft: 'auto' }}>{node.status}</span>
    </div>
  );
}
