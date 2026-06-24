'use client';

import { useState, useEffect, useCallback } from 'react';
import { plans } from '@jarvis/sdk';
import type { Plan, PlanNode, NodeEvidence, PlanConfidence, PlanAlternatives, PlanComparison, PlanCandidate, PlanOutcome, PlanAccuracy, PlanHealth, ReplanOptions } from '@jarvis/sdk';

/* ── Helpers ───────────────────────────────────────────────────────────── */

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function countLeaves(node: PlanNode): number {
  if (!node.children || node.children.length === 0) return 1;
  return node.children.reduce((sum, c) => sum + countLeaves(c), 0);
}

function deepCloneNode(node: PlanNode): PlanNode {
  return JSON.parse(JSON.stringify(node));
}

function findNode(root: PlanNode, id: string): PlanNode | null {
  if (root.id === id) return root;
  for (const child of root.children || []) {
    const found = findNode(child, id);
    if (found) return found;
  }
  return null;
}

function removeNode(root: PlanNode, id: string): PlanNode {
  root.children = (root.children || []).filter((c) => c.id !== id);
  for (const child of root.children) {
    removeNode(child, id);
  }
  return root;
}

function addChildTo(root: PlanNode, parentId: string, child: PlanNode): boolean {
  if (root.id === parentId) {
    if (!root.children) root.children = [];
    root.children.push(child);
    return true;
  }
  for (const c of root.children || []) {
    if (addChildTo(c, parentId, child)) return true;
  }
  return false;
}

const STATUS_COLORS: Record<string, string> = {
  pending: '#8b8b8b',
  in_progress: '#00d2ff',
  completed: '#22c55e',
  failed: '#ef4444',
  skipped: '#6b7280',
};

const PLAN_STATUS_COLORS: Record<string, string> = {
  draft: '#8b8b8b',
  approved: '#22c55e',
  rejected: '#ef4444',
  executing: '#00d2ff',
  completed: '#22c55e',
  failed: '#ef4444',
};

/* ── TreeNodeRow ────────────────────────────────────────────────────────── */

function TreeNodeRow({
  node,
  selectedId,
  onSelect,
  onDelete,
  onAddChild,
  depth,
}: {
  node: PlanNode;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onAddChild: (parentId: string) => void;
  depth: number;
}) {
  const [expanded, setExpanded] = useState(true);
  const hasChildren = node.children && node.children.length > 0;
  const isSelected = node.id === selectedId;

  return (
    <>
      <div
        onClick={() => onSelect(node.id)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '5px 8px',
          marginLeft: depth * 18,
          borderRadius: 4,
          cursor: 'pointer',
          background: isSelected ? 'rgba(99,132,255,0.12)' : 'transparent',
          border: 'none',
          fontSize: 12,
          color: 'var(--j-text)',
          transition: 'background 0.15s',
        }}
        onMouseEnter={(e) => { if (!isSelected) (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.04)'; }}
        onMouseLeave={(e) => { if (!isSelected) (e.currentTarget as HTMLElement).style.background = 'transparent'; }}
      >
        {hasChildren && (
          <span
            onClick={(e) => { e.stopPropagation(); setExpanded(!expanded); }}
            style={{ width: 14, textAlign: 'center', cursor: 'pointer', fontSize: 10, color: 'var(--j-text-dim)', flexShrink: 0 }}
          >
            {expanded ? '▾' : '▸'}
          </span>
        )}
        {!hasChildren && <span style={{ width: 14, flexShrink: 0 }} />}
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: STATUS_COLORS[node.status] || '#8b8b8b',
            flexShrink: 0,
          }}
        />
        <span style={{ flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {node.title || node.description.slice(0, 50)}
        </span>
        {node.assigned_agent && (
          <span style={{ fontSize: 10, padding: '1px 5px', borderRadius: 3, background: 'rgba(99,132,255,0.15)', color: '#6384ff', flexShrink: 0 }}>
            {node.assigned_agent}
          </span>
        )}
        <div style={{ display: 'flex', gap: 2, flexShrink: 0, opacity: isSelected ? 1 : 0.3 }}>
          {hasChildren && (
            <button
              onClick={(e) => { e.stopPropagation(); onAddChild(node.id); }}
              title="Add child"
              style={{ background: 'none', border: 'none', color: 'var(--j-text-dim)', cursor: 'pointer', fontSize: 12, padding: '0 3px' }}
            >
              +
            </button>
          )}
          {node.id !== 'root' && (
            <button
              onClick={(e) => { e.stopPropagation(); onDelete(node.id); }}
              title="Delete node"
              style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', fontSize: 12, padding: '0 3px' }}
            >
              ×
            </button>
          )}
        </div>
      </div>
      {expanded && hasChildren && node.children.map((child) => (
        <TreeNodeRow
          key={child.id}
          node={child}
          selectedId={selectedId}
          onSelect={onSelect}
          onDelete={onDelete}
          onAddChild={onAddChild}
          depth={depth + 1}
        />
      ))}
    </>
  );
}

/* ── Node Inspector ─────────────────────────────────────────────────────── */

function NodeInspector({
  node,
  onUpdate,
}: {
  node: PlanNode;
  onUpdate: (patches: Partial<PlanNode>) => void;
}) {
  const [title, setTitle] = useState(node.title);
  const [description, setDescription] = useState(node.description);
  const [agent, setAgent] = useState(node.assigned_agent || '');
  const [priority, setPriority] = useState(String(node.priority));
  const [duration, setDuration] = useState(node.estimated_duration ? String(node.estimated_duration) : '');

  // Sync state when selected node changes
  useEffect(() => {
    setTitle(node.title);
    setDescription(node.description);
    setAgent(node.assigned_agent || '');
    setPriority(String(node.priority));
    setDuration(node.estimated_duration ? String(node.estimated_duration) : '');
  }, [node.id]);

  const commit = useCallback(() => {
    const patch: Partial<PlanNode> = {};
    if (title !== node.title) patch.title = title;
    if (description !== node.description) patch.description = description;
    const agentVal = agent.trim() || null;
    if (agentVal !== node.assigned_agent) patch.assigned_agent = agentVal;
    const prio = parseInt(priority, 10);
    if (!isNaN(prio) && prio !== node.priority) patch.priority = prio;
    const dur = duration ? parseInt(duration, 10) : null;
    if (dur !== node.estimated_duration) patch.estimated_duration = dur;
    if (Object.keys(patch).length > 0) onUpdate(patch);
  }, [title, description, agent, priority, duration, node, onUpdate]);

  return (
    <div style={{ padding: '12px 16px', borderTop: '1px solid var(--j-border)' }}>
      <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--j-text-dim)', marginBottom: 8 }}>
        Node Inspector — {node.id}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div>
          <label style={{ fontSize: 10, color: 'var(--j-text-dim)', display: 'block', marginBottom: 2 }}>Title</label>
          <input value={title} onChange={(e) => setTitle(e.target.value)} style={{ width: '100%', padding: '4px 8px', borderRadius: 3, border: '1px solid var(--j-border)', background: 'var(--j-bg)', color: 'var(--j-text)', fontSize: 12, outline: 'none' }} />
        </div>
        <div>
          <label style={{ fontSize: 10, color: 'var(--j-text-dim)', display: 'block', marginBottom: 2 }}>Description</label>
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} style={{ width: '100%', padding: '4px 8px', borderRadius: 3, border: '1px solid var(--j-border)', background: 'var(--j-bg)', color: 'var(--j-text)', fontSize: 12, resize: 'vertical', outline: 'none' }} />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
          <div>
            <label style={{ fontSize: 10, color: 'var(--j-text-dim)', display: 'block', marginBottom: 2 }}>Agent</label>
            <input value={agent} onChange={(e) => setAgent(e.target.value)} placeholder="auto" style={{ width: '100%', padding: '4px 8px', borderRadius: 3, border: '1px solid var(--j-border)', background: 'var(--j-bg)', color: 'var(--j-text)', fontSize: 12, outline: 'none' }} />
          </div>
          <div>
            <label style={{ fontSize: 10, color: 'var(--j-text-dim)', display: 'block', marginBottom: 2 }}>Priority</label>
            <input value={priority} onChange={(e) => setPriority(e.target.value)} type="number" min="0" max="5" style={{ width: '100%', padding: '4px 8px', borderRadius: 3, border: '1px solid var(--j-border)', background: 'var(--j-bg)', color: 'var(--j-text)', fontSize: 12, outline: 'none' }} />
          </div>
        </div>
        <div>
          <label style={{ fontSize: 10, color: 'var(--j-text-dim)', display: 'block', marginBottom: 2 }}>Est. Duration (s)</label>
          <input value={duration} onChange={(e) => setDuration(e.target.value)} type="number" min="0" style={{ width: '100%', padding: '4px 8px', borderRadius: 3, border: '1px solid var(--j-border)', background: 'var(--j-bg)', color: 'var(--j-text)', fontSize: 12, outline: 'none' }} />
        </div>
        <button
          onClick={commit}
          style={{ marginTop: 4, padding: '5px 12px', borderRadius: 3, border: 'none', background: 'var(--j-sky)', color: '#020406', cursor: 'pointer', fontSize: 11, fontWeight: 500 }}
        >
          Apply Changes
        </button>
      </div>
    </div>
  );
}

/* ── Evidence Panel ────────────────────────────────────────────────────── */

function EvidencePanel({
  nodeEvidence,
}: {
  nodeEvidence: NodeEvidence | null;
}) {
  if (!nodeEvidence) {
    return (
      <div style={{ padding: 16, fontSize: 11, color: 'var(--j-text-dim)', textAlign: 'center' }}>
        Select a node to view evidence
      </div>
    );
  }

  const conf = nodeEvidence.confidence;
  const confColor = conf >= 0.7 ? '#22c55e' : conf >= 0.4 ? '#f5c842' : '#ef4444';
  const criticalRisks = nodeEvidence.risks.filter((r) => r.severity === 'critical');
  const warningRisks = nodeEvidence.risks.filter((r) => r.severity === 'warning');
  const infoRisks = nodeEvidence.risks.filter((r) => r.severity === 'info');

  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--j-text-dim)', marginBottom: 8 }}>
        Node Evidence
      </div>

      {/* Confidence bar */}
      <div style={{ marginBottom: 10 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, marginBottom: 3 }}>
          <span style={{ color: 'var(--j-text-dim)' }}>Confidence</span>
          <span style={{ fontWeight: 600, color: confColor }}>{Math.round(conf * 100)}%</span>
        </div>
        <div style={{ height: 5, borderRadius: 3, background: 'var(--j-surface)', overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${conf * 100}%`, borderRadius: 3, background: confColor, transition: 'width 0.4s ease' }} />
        </div>
        <div style={{ display: 'flex', gap: 10, marginTop: 4, fontSize: 10, color: 'var(--j-text-dim)' }}>
          <span>{nodeEvidence.evidence_count} evidence items</span>
          <span>{nodeEvidence.risk_count} risks</span>
        </div>
      </div>

      {/* Evidence by type */}
      {['experience', 'pattern', 'principle', 'heuristic', 'factoid'].map((type) => {
        const items = nodeEvidence.evidence.filter((e) => e.type === type);
        if (items.length === 0) return null;
        const typeLabels: Record<string, string> = {
          experience: 'Past Experiences',
          pattern: 'Patterns',
          principle: 'Principles',
          heuristic: 'Heuristics',
          factoid: 'Facts',
        };
        const typeColors: Record<string, string> = {
          experience: '#6384ff',
          pattern: '#a78bfa',
          principle: '#22c55e',
          heuristic: '#f5c842',
          factoid: '#8b8b8b',
        };
        return (
          <div key={type} style={{ marginBottom: 8 }}>
            <div style={{ fontSize: 10, fontWeight: 600, color: typeColors[type] || 'var(--j-text-dim)', marginBottom: 4 }}>
              {typeLabels[type] || type} ({items.length})
            </div>
            {items.slice(0, 5).map((item, i) => (
              <div key={i} style={{ fontSize: 10, padding: '4px 6px', marginBottom: 2, borderRadius: 3, background: 'rgba(255,255,255,0.03)' }}>
                <div style={{ color: 'var(--j-text)', lineHeight: 1.4 }}>{item.summary.slice(0, 80)}</div>
                <div style={{ color: 'var(--j-text-dim)', marginTop: 1 }}>
                  {item.relevance !== undefined && `relevance: ${item.relevance} · `}
                  {item.confidence !== undefined && `conf: ${Math.round(item.confidence * 100)}% · `}
                  {item.success !== undefined && (item.success ? 'success' : 'failed')}
                  {item.id && ` · ${item.id}`}
                </div>
              </div>
            ))}
            {items.length > 5 && (
              <div style={{ fontSize: 10, color: 'var(--j-text-dim)', paddingLeft: 6 }}>+{items.length - 5} more</div>
            )}
          </div>
        );
      })}

      {/* No evidence */}
      {nodeEvidence.evidence.length === 0 && (
        <div style={{ fontSize: 10, color: 'var(--j-text-dim)', marginBottom: 10 }}>No evidence found for this node</div>
      )}

      {/* Risks */}
      {nodeEvidence.risks.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <div style={{ fontSize: 10, fontWeight: 600, color: '#ef4444', marginBottom: 4 }}>
            Risks ({nodeEvidence.risks.length})
          </div>
          {criticalRisks.map((risk, i) => (
            <div key={i} style={{ fontSize: 10, padding: '4px 6px', marginBottom: 2, borderRadius: 3, background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)' }}>
              <strong>Critical:</strong> {risk.detail || risk.pattern || risk.type}
            </div>
          ))}
          {warningRisks.map((risk, i) => (
            <div key={i} style={{ fontSize: 10, padding: '4px 6px', marginBottom: 2, borderRadius: 3, background: 'rgba(245,200,66,0.08)', border: '1px solid rgba(245,200,66,0.2)' }}>
              <strong>Warning:</strong> {risk.detail || risk.pattern || risk.type}
              {risk.success_rate !== undefined && ` (${Math.round(risk.success_rate * 100)}% success rate)`}
            </div>
          ))}
        </div>
      )}

      {nodeEvidence.evidence.length === 0 && nodeEvidence.risks.length === 0 && (
        <div style={{ fontSize: 10, color: 'var(--j-text-dim)' }}>No evidence or risks — try replanning or adding more context</div>
      )}
    </div>
  );
}

/* ── Confidence Overview ───────────────────────────────────────────────── */

function ConfidenceOverview({
  confidence,
  allNodes,
}: {
  confidence: PlanConfidence | null;
  allNodes: NodeEvidence[];
}) {
  if (!confidence || allNodes.length === 0) {
    return null;
  }

  const ov = confidence.overall;
  const ovConf = ov.confidence;
  const ovColor = ovConf >= 0.7 ? '#22c55e' : ovConf >= 0.4 ? '#f5c842' : '#ef4444';

  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--j-text-dim)', marginBottom: 8 }}>
        Confidence Overview
      </div>

      {/* Overall */}
      <div style={{ marginBottom: 8 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, marginBottom: 2 }}>
          <span style={{ color: 'var(--j-text-dim)' }}>Overall</span>
          <span style={{ fontWeight: 600, color: ovColor }}>{Math.round(ovConf * 100)}%</span>
        </div>
        <div style={{ height: 4, borderRadius: 2, background: 'var(--j-surface)', overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${ovConf * 100}%`, borderRadius: 2, background: ovColor, transition: 'width 0.4s ease' }} />
        </div>
        <div style={{ display: 'flex', gap: 8, marginTop: 3, fontSize: 9, color: 'var(--j-text-dim)' }}>
          <span>{ov.total_nodes} nodes</span>
          <span>{ov.total_evidence} evidence</span>
          <span style={{ color: ov.critical_risks > 0 ? '#ef4444' : 'var(--j-text-dim)' }}>
            {ov.total_risks} risks ({ov.critical_risks} critical)
          </span>
        </div>
      </div>

      {/* Per-node confidence bars */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        {allNodes.map((n) => {
          const c = n.confidence;
          const color = c >= 0.7 ? '#22c55e' : c >= 0.4 ? '#f5c842' : '#ef4444';
          return (
            <div key={n.node_id} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{
                fontSize: 9, color: 'var(--j-text-dim)', width: 60, overflow: 'hidden',
                textOverflow: 'ellipsis', whiteSpace: 'nowrap', flexShrink: 0,
              }}>
                {n.title.slice(0, 12)}
              </span>
              <div style={{ flex: 1, height: 3, borderRadius: 2, background: 'var(--j-surface)', overflow: 'hidden' }}>
                <div style={{ height: '100%', width: `${c * 100}%`, borderRadius: 2, background: color }} />
              </div>
              <span style={{ fontSize: 9, color: 'var(--j-text-dim)', width: 24, textAlign: 'right' }}>
                {Math.round(c * 100)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ── Alternatives Panel ────────────────────────────────────────────────── */

function AlternativesPanel({
  alternatives,
  nodeId,
}: {
  alternatives: PlanAlternatives | null;
  nodeId: string | null;
}) {
  if (!alternatives || !nodeId) {
    return (
      <div style={{ padding: 16, fontSize: 11, color: 'var(--j-text-dim)', textAlign: 'center' }}>
        Select a node to view alternatives
      </div>
    );
  }

  const nodeAlts = alternatives.nodes.find((n) => n.node_id === nodeId);
  if (!nodeAlts || nodeAlts.alternatives.length === 0) {
    return (
      <div style={{ padding: 16, fontSize: 11, color: 'var(--j-text-dim)', textAlign: 'center' }}>
        No alternatives found for this node
      </div>
    );
  }

  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--j-text-dim)', marginBottom: 8 }}>
        Alternatives ({nodeAlts.alternatives.length})
      </div>
      {nodeAlts.alternatives.map((alt, i) => (
        <div
          key={i}
          style={{
            fontSize: 10, padding: '6px 8px', marginBottom: 4, borderRadius: 4,
            border: '1px solid var(--j-border)', background: 'rgba(255,255,255,0.02)',
          }}
        >
          <div style={{ fontWeight: 600, color: 'var(--j-text)', marginBottom: 2 }}>
            {alt.approach}
          </div>
          <div style={{ color: 'var(--j-text-dim)', marginBottom: 3 }}>
            {alt.description}
          </div>
          {alt.pros.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, marginBottom: 2 }}>
              {alt.pros.map((p, j) => (
                <span key={j} style={{
                  fontSize: 9, padding: '1px 4px', borderRadius: 2,
                  background: 'rgba(34,197,94,0.12)', color: '#22c55e',
                }}>
                  +{p}
                </span>
              ))}
            </div>
          )}
          {alt.cons.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
              {alt.cons.map((c, j) => (
                <span key={j} style={{
                  fontSize: 9, padding: '1px 4px', borderRadius: 2,
                  background: 'rgba(239,68,68,0.12)', color: '#ef4444',
                }}>
                  -{c}
                </span>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

/* ── Compare Plans View ───────────────────────────────────────────────── */

function ScoreBar({ value, color }: { value: number; color: string }) {
  return (
    <div style={{ height: 4, borderRadius: 2, background: 'rgba(255,255,255,0.08)', overflow: 'hidden', width: 60 }}>
      <div style={{ height: '100%', width: `${Math.round(value * 100)}%`, borderRadius: 2, background: color }} />
    </div>
  );
}

function ComparePlansView({
  goal,
  onGoalChange,
  onCompare,
  comparison,
  comparing,
  selectedCandidate,
  onSelectCandidate,
  onAcceptCandidate,
  error,
}: {
  goal: string;
  onGoalChange: (g: string) => void;
  onCompare: () => void;
  comparison: PlanComparison | null;
  comparing: boolean;
  selectedCandidate: PlanCandidate | null;
  onSelectCandidate: (c: PlanCandidate | null) => void;
  onAcceptCandidate: (c: PlanCandidate) => void;
  error: string | null;
}) {
  return (
    <div style={{ padding: 24 }}>
      {/* Goal input + compare button */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <input
          value={goal}
          onChange={(e) => onGoalChange(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') onCompare(); }}
          placeholder="Enter a goal to compare strategies..."
          style={{ flex: 1, padding: '8px 12px', borderRadius: 4, border: '1px solid var(--j-border)', background: 'var(--j-bg)', color: 'var(--j-text)', fontSize: 13, outline: 'none' }}
        />
        <button
          onClick={onCompare}
          disabled={comparing || !goal.trim()}
          style={{
            padding: '8px 20px', borderRadius: 4, border: 'none',
            background: comparing || !goal.trim() ? 'var(--j-border)' : 'var(--j-sky)',
            color: comparing || !goal.trim() ? 'var(--j-text-dim)' : '#020406',
            cursor: comparing || !goal.trim() ? 'default' : 'pointer',
            fontSize: 12, fontWeight: 500,
          }}
        >
          {comparing ? 'Comparing...' : 'Compare'}
        </button>
      </div>

      {error && (
        <div style={{ marginBottom: 12, padding: '6px 12px', borderRadius: 4, background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', color: '#ef4444', fontSize: 12 }}>
          {error}
        </div>
      )}

      {!comparison && !comparing && (
        <div style={{ textAlign: 'center', padding: 32, color: 'var(--j-text-dim)', fontSize: 13 }}>
          Enter a goal and click Compare to see strategy alternatives.
        </div>
      )}

      {comparing && (
        <div style={{ textAlign: 'center', padding: 32, color: 'var(--j-text-dim)', fontSize: 13 }}>
          Generating candidate plans...
        </div>
      )}

      {/* Results table */}
      {comparison && !selectedCandidate && (
        <>
          <div style={{ marginBottom: 4, fontSize: 11, color: 'var(--j-text-dim)' }}>
            {comparison.total_candidates} strategies compared
          </div>
          <div style={{ border: '1px solid var(--j-border)', borderRadius: 4, overflow: 'hidden' }}>
            {/* Header */}
            <div style={{ display: 'grid', gridTemplateColumns: '140px 60px 60px 60px 60px 60px 50px 60px', gap: 0, background: 'var(--j-surface)', borderBottom: '1px solid var(--j-border)', fontSize: 10, fontWeight: 600, color: 'var(--j-text-dim)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              {['Strategy', 'Score', 'Conf', 'History', 'Duration', 'Risk', 'Cost', 'Evidence'].map((h) => (
                <div key={h} style={{ padding: '7px 6px' }}>{h}</div>
              ))}
            </div>
            {/* Rows */}
            {comparison.candidates.map((c) => {
              const isRecommended = comparison.recommended?.strategy_key === c.strategy_key;
              const scoreColor = c.overall_score >= 0.7 ? '#22c55e' : c.overall_score >= 0.5 ? '#f5c842' : '#ef4444';
              return (
                <div
                  key={c.strategy_key}
                  onClick={() => onSelectCandidate(c)}
                  style={{
                    display: 'grid', gridTemplateColumns: '140px 60px 60px 60px 60px 60px 50px 60px', gap: 0,
                    borderBottom: '1px solid var(--j-border)', fontSize: 11, cursor: 'pointer',
                    background: isRecommended ? 'rgba(34,197,94,0.06)' : 'transparent',
                  }}
                >
                  <div style={{ padding: '7px 6px', fontWeight: 500 }}>
                    {c.strategy_label}
                    {isRecommended && <span style={{ marginLeft: 4, fontSize: 9, color: '#22c55e' }}>★</span>}
                  </div>
                  <div style={{ padding: '7px 6px', fontWeight: 600, color: scoreColor }}>{Math.round(c.overall_score * 100)}</div>
                  <div style={{ padding: '7px 6px' }}>{Math.round(c.dimensions.confidence * 100)}</div>
                  <div style={{ padding: '7px 6px' }}>{Math.round(c.dimensions.historical_success * 100)}</div>
                  <div style={{ padding: '7px 6px' }}>{c.estimated_duration_days}d</div>
                  <div style={{ padding: '7px 6px' }}>{Math.round(c.dimensions.risk * 100)}</div>
                  <div style={{ padding: '7px 6px', fontSize: 10 }}>{c.estimated_cost}</div>
                  <div style={{ padding: '7px 6px' }}>{c.total_evidence}</div>
                </div>
              );
            })}
          </div>

          {/* Recommendation */}
          {comparison.recommended && (
            <div style={{ marginTop: 12, padding: '10px 14px', borderRadius: 4, background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.2)', fontSize: 11, color: 'var(--j-text)' }}>
              <strong>Recommended: {comparison.recommended.strategy_label}</strong>
              <div style={{ marginTop: 4, color: 'var(--j-text-dim)', fontSize: 10 }}>{comparison.recommended.reasoning}</div>
            </div>
          )}
        </>
      )}

      {/* Candidate detail view */}
      {selectedCandidate && (
        <div>
          <button onClick={() => onSelectCandidate(null)} style={{ background: 'none', border: 'none', color: 'var(--j-sky)', cursor: 'pointer', fontSize: 12, marginBottom: 12 }}>&larr; Back to comparison</button>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <h3 style={{ fontSize: 13, fontWeight: 600, margin: '0 0 8px' }}>{selectedCandidate.strategy_label}</h3>
              <div style={{ fontSize: 11, color: 'var(--j-text-dim)', marginBottom: 8 }}>{selectedCandidate.strategy_description}</div>
              <div style={{ display: 'flex', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 10, padding: '3px 8px', borderRadius: 3, background: 'rgba(255,255,255,0.06)', color: 'var(--j-text-dim)' }}>
                  Score: {Math.round(selectedCandidate.overall_score * 100)}
                </span>
                <span style={{ fontSize: 10, padding: '3px 8px', borderRadius: 3, background: 'rgba(255,255,255,0.06)', color: 'var(--j-text-dim)' }}>
                  {selectedCandidate.estimated_duration_days}d
                </span>
                <span style={{ fontSize: 10, padding: '3px 8px', borderRadius: 3, background: 'rgba(255,255,255,0.06)', color: 'var(--j-text-dim)' }}>
                  {selectedCandidate.estimated_cost}
                </span>
              </div>
              {/* Pros/Cons */}
              {selectedCandidate.pros.length > 0 && (
                <div style={{ marginBottom: 8 }}>
                  <div style={{ fontSize: 10, fontWeight: 600, color: '#22c55e', marginBottom: 4 }}>Pros</div>
                  {selectedCandidate.pros.map((p, i) => <div key={i} style={{ fontSize: 10, color: 'var(--j-text-dim)', paddingLeft: 8 }}>+ {p}</div>)}
                </div>
              )}
              {selectedCandidate.cons.length > 0 && (
                <div style={{ marginBottom: 8 }}>
                  <div style={{ fontSize: 10, fontWeight: 600, color: '#ef4444', marginBottom: 4 }}>Cons</div>
                  {selectedCandidate.cons.map((c, i) => <div key={i} style={{ fontSize: 10, color: 'var(--j-text-dim)', paddingLeft: 8 }}>- {c}</div>)}
                </div>
              )}
            </div>
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 6 }}>Dimension Scores</div>
              {Object.entries(selectedCandidate.dimensions).map(([key, val]) => {
                const colors: Record<string, string> = { confidence: '#6384ff', historical_success: '#22c55e', duration: '#a78bfa', risk: '#f5c842', evidence_strength: '#8b8b8b' };
                const labels: Record<string, string> = { confidence: 'Confidence', historical_success: 'History', duration: 'Duration', risk: 'Risk', evidence_strength: 'Evidence' };
                return (
                  <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4, fontSize: 10 }}>
                    <span style={{ width: 70, color: 'var(--j-text-dim)' }}>{labels[key] || key}</span>
                    <ScoreBar value={val as number} color={colors[key] || '#8b8b8b'} />
                    <span style={{ width: 30, textAlign: 'right', fontWeight: 500 }}>{Math.round((val as number) * 100)}</span>
                  </div>
                );
              })}
            </div>
          </div>
          <button
            onClick={() => onAcceptCandidate(selectedCandidate)}
            style={{ marginTop: 12, padding: '8px 20px', borderRadius: 4, border: 'none', background: '#22c55e', color: '#020406', cursor: 'pointer', fontSize: 12, fontWeight: 500 }}
          >
            Accept & Create Plan
          </button>
        </div>
      )}
    </div>
  );
}

/* ── Main Component ────────────────────────────────────────────────────── */

export function PlannerStudio() {
  const [mode, setMode] = useState<'plans' | 'compare'>('plans');
  const [planList, setPlanList] = useState<Plan[]>([]);
  const [selectedPlan, setSelectedPlan] = useState<Plan | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [goalInput, setGoalInput] = useState('');
  const [planEvidence, setPlanEvidence] = useState<NodeEvidence[] | null>(null);
  const [planAlternatives, setPlanAlternatives] = useState<PlanAlternatives | null>(null);
  const [planConfidence, setPlanConfidence] = useState<PlanConfidence | null>(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Compare state
  const [compareGoal, setCompareGoal] = useState('');
  const [comparison, setComparison] = useState<PlanComparison | null>(null);
  const [comparing, setComparing] = useState(false);
  const [selectedCandidate, setSelectedCandidate] = useState<PlanCandidate | null>(null);

  // Outcome state
  const [planOutcome, setPlanOutcome] = useState<PlanOutcome | null>(null);
  const [planAccuracy, setPlanAccuracy] = useState<PlanAccuracy | null>(null);
  const [outcomeLoading, setOutcomeLoading] = useState(false);

  // Health & Replan state
  const [planHealth, setPlanHealth] = useState<PlanHealth | null>(null);
  const [replanOptions, setReplanOptions] = useState<ReplanOptions | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);
  const [replanning, setReplanning] = useState(false);

  const loadPlans = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await plans.list();
      setPlanList(res.plans);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadPlans(); }, []);

  const handleCompare = useCallback(async () => {
    if (!compareGoal.trim()) return;
    setComparing(true);
    setError(null);
    setSelectedCandidate(null);
    try {
      const result = await plans.compare(compareGoal.trim());
      setComparison(result);
    } catch (e) {
      setError(String(e));
    } finally {
      setComparing(false);
    }
  }, [compareGoal]);

  const handleAcceptCandidate = useCallback(async (candidate: PlanCandidate) => {
    setError(null);
    try {
      const plan = await plans.create(candidate.strategy_description || compareGoal);
      setMode('plans');
      setSelectedPlan(plan);
      setSelectedNodeId('root');
      await loadPlans();
    } catch (e) {
      setError(String(e));
    }
  }, [compareGoal, loadPlans]);

  const selectPlan = useCallback((plan: Plan) => {
    setSelectedPlan(plan);
    setSelectedNodeId('root');
  }, []);

  const selectedNode = selectedPlan && selectedNodeId
    ? findNode(selectedPlan.root_node, selectedNodeId)
    : null;

  // Fetch evidence + alternatives + confidence when plan is selected
  useEffect(() => {
    if (!selectedPlan) { setPlanEvidence(null); setPlanAlternatives(null); setPlanConfidence(null); return; }
    setEvidenceLoading(true);
    const pid = selectedPlan.id;
    Promise.all([
      plans.evidence(pid),
      plans.alternatives(pid),
      plans.confidence(pid),
    ])
      .then(([ev, alts, conf]) => {
        setPlanEvidence(ev.nodes);
        setPlanAlternatives(alts);
        setPlanConfidence(conf);
      })
      .catch(() => {
        setPlanEvidence(null);
        setPlanAlternatives(null);
        setPlanConfidence(null);
      })
      .finally(() => setEvidenceLoading(false));
  }, [selectedPlan?.id]);

  // Fetch outcome + accuracy when plan is selected
  useEffect(() => {
    if (!selectedPlan) { setPlanOutcome(null); setPlanAccuracy(null); return; }
    setOutcomeLoading(true);
    const pid = selectedPlan.id;
    Promise.all([
      plans.outcome(pid).catch(() => null),
      plans.accuracy(pid).catch(() => null),
    ])
      .then(([outcome, accuracy]) => {
        setPlanOutcome(outcome);
        setPlanAccuracy(accuracy);
      })
      .finally(() => setOutcomeLoading(false));
  }, [selectedPlan?.id]);

  // Fetch health + replan options when plan is selected
  useEffect(() => {
    if (!selectedPlan) { setPlanHealth(null); setReplanOptions(null); return; }
    setHealthLoading(true);
    const pid = selectedPlan.id;
    Promise.all([
      plans.health(pid).catch(() => null),
      plans.replanOptions(pid).catch(() => null),
    ])
      .then(([health, opts]) => {
        setPlanHealth(health);
        setReplanOptions(opts);
      })
      .finally(() => setHealthLoading(false));
  }, [selectedPlan?.id]);

  const selectedNodeEvidence = planEvidence
    ? planEvidence.find((n) => n.node_id === selectedNodeId) || null
    : null;

  const handleCreate = useCallback(async () => {
    if (!goalInput.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const plan = await plans.create(goalInput.trim());
      setGoalInput('');
      setSelectedPlan(plan);
      setSelectedNodeId('root');
      await loadPlans();
    } catch (e) {
      setError(String(e));
    } finally {
      setCreating(false);
    }
  }, [goalInput, loadPlans]);

  const handleAction = useCallback(async (action: string, fn: () => Promise<Plan>) => {
    setActionLoading(action);
    setError(null);
    try {
      const updated = await fn();
      setSelectedPlan(updated);
      await loadPlans();
    } catch (e) {
      setError(String(e));
    } finally {
      setActionLoading(null);
    }
  }, [loadPlans]);

  const handleUpdateNode = useCallback(async (patches: Partial<PlanNode>) => {
    if (!selectedPlan || !selectedNodeId) return;
    setError(null);
    try {
      const updated = await plans.updateNode(selectedPlan.id, selectedNodeId, patches);
      setSelectedPlan(updated);
    } catch (e) {
      setError(String(e));
    }
  }, [selectedPlan, selectedNodeId]);

  const handleDeleteNode = useCallback(async (nodeId: string) => {
    if (!selectedPlan) return;
    if (nodeId === 'root') return;
    const newRoot = deepCloneNode(selectedPlan.root_node);
    removeNode(newRoot, nodeId);
    setError(null);
    try {
      const updated = await plans.updateNode(selectedPlan.id, 'root', { children: newRoot.children });
      setSelectedPlan(updated);
      if (selectedNodeId === nodeId) setSelectedNodeId('root');
    } catch (e) {
      setError(String(e));
    }
  }, [selectedPlan, selectedNodeId]);

  const handleAddChild = useCallback(async (parentId: string) => {
    if (!selectedPlan) return;
    const childId = `node_${Date.now()}`;
    const newChild: PlanNode = {
      id: childId,
      title: 'New Task',
      description: '',
      assigned_agent: null,
      estimated_duration: null,
      priority: 0,
      status: 'pending',
      children: [],
    };
    const newRoot = deepCloneNode(selectedPlan.root_node);
    addChildTo(newRoot, parentId, newChild);
    setError(null);
    try {
      const updated = await plans.updateNode(selectedPlan.id, 'root', { children: newRoot.children });
      setSelectedPlan(updated);
      setSelectedNodeId(childId);
    } catch (e) {
      setError(String(e));
    }
  }, [selectedPlan]);

  // ── Initial view (no plan selected) ──────────────────────────────────

  if (!selectedPlan) {
    if (mode === 'compare') {
      return (
        <div className="hud-panel" style={{ padding: 0 }}>
          {/* Mode header */}
          <div style={{ padding: 20, paddingBottom: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <h2 className="hud-title" style={{ margin: 0 }}>Planner Studio</h2>
            <button
              onClick={() => { setMode('plans'); setComparison(null); setSelectedCandidate(null); }}
              style={{ padding: '5px 12px', borderRadius: 4, border: '1px solid var(--j-border)', background: 'var(--j-surface)', color: 'var(--j-text)', cursor: 'pointer', fontSize: 11 }}
            >
              Single Plan Mode
            </button>
          </div>
          <ComparePlansView
            goal={compareGoal}
            onGoalChange={setCompareGoal}
            onCompare={handleCompare}
            comparison={comparison}
            comparing={comparing}
            selectedCandidate={selectedCandidate}
            onSelectCandidate={setSelectedCandidate}
            onAcceptCandidate={handleAcceptCandidate}
            error={error}
          />
        </div>
      );
    }

    return (
      <div className="hud-panel" style={{ padding: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <h2 className="hud-title" style={{ margin: 0 }}>Planner Studio</h2>
          <button
            onClick={() => setMode('compare')}
            style={{ padding: '5px 12px', borderRadius: 4, border: '1px solid var(--j-border)', background: 'var(--j-surface)', color: 'var(--j-text)', cursor: 'pointer', fontSize: 11 }}
          >
            Compare Plans
          </button>
        </div>

        {/* Create new plan */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
          <input
            value={goalInput}
            onChange={(e) => setGoalInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleCreate(); }}
            placeholder="Enter a goal to create a plan..."
            style={{ flex: 1, padding: '8px 12px', borderRadius: 4, border: '1px solid var(--j-border)', background: 'var(--j-bg)', color: 'var(--j-text)', fontSize: 13, outline: 'none' }}
          />
          <button
            onClick={handleCreate}
            disabled={creating || !goalInput.trim()}
            style={{
              padding: '8px 20px',
              borderRadius: 4,
              border: 'none',
              background: creating || !goalInput.trim() ? 'var(--j-border)' : 'var(--j-sky)',
              color: creating || !goalInput.trim() ? 'var(--j-text-dim)' : '#020406',
              cursor: creating || !goalInput.trim() ? 'default' : 'pointer',
              fontSize: 12,
              fontWeight: 500,
            }}
          >
            {creating ? 'Creating...' : 'Create Plan'}
          </button>
        </div>

        {error && (
          <div style={{ marginBottom: 12, padding: '6px 12px', borderRadius: 4, background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', color: '#ef4444', fontSize: 12 }}>
            {error}
          </div>
        )}

        {/* Plan list */}
        {loading && <div style={{ textAlign: 'center', padding: 20, color: 'var(--j-text-dim)', fontSize: 13 }}>Loading...</div>}

        {!loading && planList.length === 0 && (
          <div style={{ textAlign: 'center', padding: 32, color: 'var(--j-text-dim)', fontSize: 13 }}>
            No plans yet. Enter a goal above to create one.
          </div>
        )}

        {planList.map((plan) => (
          <div
            key={plan.id}
            onClick={() => selectPlan(plan)}
            style={{
              padding: '12px 14px',
              borderRadius: 4,
              background: 'var(--j-surface)',
              border: '1px solid var(--j-border)',
              marginBottom: 4,
              cursor: 'pointer',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ width: 10, height: 10, borderRadius: '50%', background: PLAN_STATUS_COLORS[plan.status] || '#8b8b8b', flexShrink: 0 }} />
              <span style={{ flex: 1, fontSize: 13, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {plan.goal.slice(0, 80)}
              </span>
              <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 3, background: 'rgba(255,255,255,0.06)', color: 'var(--j-text-dim)' }}>
                {plan.status}
              </span>
              <span style={{ fontSize: 10, color: 'var(--j-text-dim)' }}>
                {countLeaves(plan.root_node)} tasks
              </span>
              <span style={{ fontSize: 10, color: 'var(--j-text-dim)' }}>
                {timeAgo(plan.created_at)}
              </span>
            </div>
          </div>
        ))}
      </div>
    );
  }

  // ── Plan detail view ─────────────────────────────────────────────────

  const plan = selectedPlan;
  const leaves = countLeaves(plan.root_node);

  return (
    <div className="hud-panel" style={{ padding: 24 }}>
      {/* ── Header ──────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <button onClick={() => { setSelectedPlan(null); setSelectedNodeId(null); }} style={{ background: 'none', border: 'none', color: 'var(--j-sky)', cursor: 'pointer', fontSize: 13 }}>&larr; All Plans</button>
        <h2 className="hud-title" style={{ margin: 0, fontSize: 16, flex: 1 }}>Plan: {plan.goal.slice(0, 60)}</h2>
        <span style={{ fontSize: 10, padding: '3px 8px', borderRadius: 3, background: 'rgba(255,255,255,0.06)', color: 'var(--j-text-dim)', border: '1px solid var(--j-border)' }}>
          {plan.id.slice(0, 16)}
        </span>
        <span style={{ width: 10, height: 10, borderRadius: '50%', background: PLAN_STATUS_COLORS[plan.status] || '#8b8b8b', flexShrink: 0 }} />
        <span style={{ fontSize: 12, fontWeight: 500 }}>{plan.status}</span>
        {planHealth && (
          <span style={{ fontSize: 10, padding: '3px 8px', borderRadius: 3, border: '1px solid var(--j-border)', background: planHealth.status === 'healthy' ? 'rgba(34,197,94,0.1)' : planHealth.status === 'watch' ? 'rgba(245,200,66,0.1)' : 'rgba(239,68,68,0.1)', color: planHealth.status === 'healthy' ? '#22c55e' : planHealth.status === 'watch' ? '#f5c842' : '#ef4444' }}>
            Health: {planHealth.status.replace(/_/g, ' ')}
          </span>
        )}
      </div>

      {error && (
        <div style={{ marginBottom: 12, padding: '6px 12px', borderRadius: 4, background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', color: '#ef4444', fontSize: 12 }}>
          {error}
        </div>
      )}

      {/* ── Stats bar ───────────────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(100px, 1fr))', gap: 6, marginBottom: 12 }}>
        {[
          { label: 'Tasks', value: leaves, color: '#6384ff' },
          { label: 'Status', value: plan.status, color: PLAN_STATUS_COLORS[plan.status] || '#8b8b8b' },
          { label: 'Created', value: timeAgo(plan.created_at), color: 'var(--j-text-dim)' },
        ].map((s) => (
          <div key={s.label} style={{ padding: '7px 10px', borderRadius: 4, background: 'var(--j-surface)', border: '1px solid var(--j-border)', textAlign: 'center' }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: s.color }}>{s.value}</div>
            <div style={{ fontSize: 10, color: 'var(--j-text-dim)', marginTop: 1 }}>{s.label}</div>
          </div>
        ))}
      </div>

      {/* ── Action bar ──────────────────────────────────────────────── */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 16, flexWrap: 'wrap' }}>
        {plan.status === 'draft' && (
          <button
            onClick={() => handleAction('approve', () => plans.approve(plan.id))}
            disabled={actionLoading !== null}
            style={{ padding: '6px 14px', borderRadius: 4, border: 'none', background: actionLoading === 'approve' ? 'var(--j-border)' : '#22c55e', color: '#020406', cursor: actionLoading ? 'default' : 'pointer', fontSize: 12, fontWeight: 500 }}
          >
            {actionLoading === 'approve' ? '...' : 'Approve'}
          </button>
        )}
        {plan.status === 'draft' && (
          <button
            onClick={() => handleAction('reject', () => plans.reject(plan.id))}
            disabled={actionLoading !== null}
            style={{ padding: '6px 14px', borderRadius: 4, border: '1px solid #ef4444', background: 'transparent', color: '#ef4444', cursor: actionLoading ? 'default' : 'pointer', fontSize: 12 }}
          >
            {actionLoading === 'reject' ? '...' : 'Reject'}
          </button>
        )}
        {plan.status === 'draft' && (
          <button
            onClick={() => handleAction('replan', () => plans.replan(plan.id))}
            disabled={actionLoading !== null}
            style={{ padding: '6px 14px', borderRadius: 4, border: '1px solid var(--j-border)', background: 'var(--j-surface)', color: 'var(--j-text)', cursor: actionLoading ? 'default' : 'pointer', fontSize: 12 }}
          >
            {actionLoading === 'replan' ? '...' : 'Replan'}
          </button>
        )}
        {plan.status === 'approved' && (
          <button
            onClick={() => handleAction('execute', () => plans.execute(plan.id))}
            disabled={actionLoading !== null}
            style={{ padding: '6px 14px', borderRadius: 4, border: 'none', background: actionLoading === 'execute' ? 'var(--j-border)' : '#00d2ff', color: '#020406', cursor: actionLoading ? 'default' : 'pointer', fontSize: 12, fontWeight: 500 }}
          >
            {actionLoading === 'execute' ? '...' : 'Execute'}
          </button>
        )}
        <button
          onClick={() => handleAction('delete', async () => { await plans.delete(plan.id); setSelectedPlan(null); setSelectedNodeId(null); await loadPlans(); return plan; })}
          disabled={actionLoading !== null}
          style={{ padding: '6px 14px', borderRadius: 4, border: '1px solid #ef4444', background: 'transparent', color: '#ef4444', cursor: actionLoading ? 'default' : 'pointer', fontSize: 12, marginLeft: 'auto' }}
        >
          {actionLoading === 'delete' ? '...' : 'Delete'}
        </button>
      </div>

      {/* ── Tree + Inspector + Evidence layout ──────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px 300px', gap: 12, minHeight: 300 }}>
        {/* Tree panel */}
        <div style={{ borderRadius: 4, border: '1px solid var(--j-border)', background: 'var(--j-bg)', overflow: 'auto', padding: '8px 0' }}>
          <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--j-text-dim)', padding: '0 12px 8px', borderBottom: '1px solid var(--j-border)', marginBottom: 4 }}>
            Plan Tree
          </div>
          <div style={{ padding: '0 4px' }}>
            <TreeNodeRow
              node={plan.root_node}
              selectedId={selectedNodeId}
              onSelect={setSelectedNodeId}
              onDelete={handleDeleteNode}
              onAddChild={handleAddChild}
              depth={0}
            />
          </div>
          {!plan.root_node.children || plan.root_node.children.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 20, color: 'var(--j-text-dim)', fontSize: 12 }}>
              Empty plan — add nodes or replan
            </div>
          ) : null}
        </div>

        {/* Inspector column */}
        <div style={{ borderRadius: 4, border: '1px solid var(--j-border)', background: 'var(--j-bg)', display: 'flex', flexDirection: 'column' }}>
          {selectedNode ? (
            <>
              <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--j-border)' }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--j-text)' }}>{selectedNode.title}</div>
                {selectedNode.description && (
                  <div style={{ fontSize: 11, color: 'var(--j-text-dim)', marginTop: 2 }}>{selectedNode.description.slice(0, 100)}</div>
                )}
                <div style={{ display: 'flex', gap: 4, marginTop: 4, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 10, padding: '1px 5px', borderRadius: 3, background: 'rgba(255,255,255,0.06)', color: 'var(--j-text-dim)' }}>
                    {selectedNode.status}
                  </span>
                  {selectedNode.assigned_agent && (
                    <span style={{ fontSize: 10, padding: '1px 5px', borderRadius: 3, background: 'rgba(99,132,255,0.15)', color: '#6384ff' }}>
                      {selectedNode.assigned_agent}
                    </span>
                  )}
                  <span style={{ fontSize: 10, padding: '1px 5px', borderRadius: 3, background: 'rgba(255,255,255,0.06)', color: 'var(--j-text-dim)' }}>
                    p{selectedNode.priority}
                  </span>
                </div>
              </div>
              <NodeInspector node={selectedNode} onUpdate={handleUpdateNode} />
            </>
          ) : (
            <div style={{ padding: 24, textAlign: 'center', color: 'var(--j-text-dim)', fontSize: 12 }}>
              Select a node to inspect
            </div>
          )}
        </div>

        {/* Evidence column */}
        <div style={{ borderRadius: 4, border: '1px solid var(--j-border)', background: 'var(--j-bg)', display: 'flex', flexDirection: 'column', overflow: 'auto' }}>
          <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--j-text-dim)', padding: '10px 16px', borderBottom: '1px solid var(--j-border)' }}>
            Evidence
          </div>
          {evidenceLoading && (
            <div style={{ padding: 16, fontSize: 11, color: 'var(--j-text-dim)', textAlign: 'center' }}>Loading...</div>
          )}
          {!evidenceLoading && (
            <div style={{ padding: '12px 16px' }}>
              <ConfidenceOverview confidence={planConfidence} allNodes={planEvidence || []} />
              <EvidencePanel nodeEvidence={selectedNodeEvidence} />
              <AlternativesPanel alternatives={planAlternatives} nodeId={selectedNodeId} />
            </div>
          )}
        </div>
      </div>

      {/* ── Prediction Accuracy / Outcome ───────────────────────────── */}
      {!outcomeLoading && (planOutcome || planAccuracy) && (
        <div style={{ marginTop: 16 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
            {/* Prediction card */}
            {planOutcome && (
              <div style={{ borderRadius: 4, border: '1px solid var(--j-border)', background: 'var(--j-bg)', padding: '12px 16px' }}>
                <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--j-text-dim)', marginBottom: 8 }}>Prediction</div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4, fontSize: 11 }}>
                  <span style={{ color: 'var(--j-text-dim)' }}>Confidence</span><span>{Math.round(planOutcome.predicted_confidence * 100)}%</span>
                  <span style={{ color: 'var(--j-text-dim)' }}>Duration</span><span>{planOutcome.predicted_duration_days}d</span>
                  <span style={{ color: 'var(--j-text-dim)' }}>Risk</span><span>{Math.round(planOutcome.predicted_risk_score * 100)}%</span>
                  <span style={{ color: 'var(--j-text-dim)' }}>Cost</span><span>{planOutcome.predicted_cost}</span>
                </div>
              </div>
            )}

            {/* Actual outcome card */}
            {planOutcome && (
              <div style={{ borderRadius: 4, border: '1px solid var(--j-border)', background: 'var(--j-bg)', padding: '12px 16px' }}>
                <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--j-text-dim)', marginBottom: 8 }}>Actual Outcome</div>
                {planOutcome.actual_success !== null ? (
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4, fontSize: 11 }}>
                    <span style={{ color: 'var(--j-text-dim)' }}>Success</span>
                    <span style={{ color: planOutcome.actual_success ? '#22c55e' : '#ef4444' }}>{planOutcome.actual_success ? 'Yes' : 'No'}</span>
                    {planOutcome.actual_duration_seconds !== null && (
                      <>
                        <span style={{ color: 'var(--j-text-dim)' }}>Duration</span>
                        <span>{Math.round(planOutcome.actual_duration_seconds / 3600 / 8 * 10) / 10}d</span>
                      </>
                    )}
                    {planOutcome.actual_failures !== null && (
                      <>
                        <span style={{ color: 'var(--j-text-dim)' }}>Failures</span>
                        <span style={{ color: planOutcome.actual_failures > 0 ? '#f5c842' : '#22c55e' }}>{planOutcome.actual_failures}</span>
                      </>
                    )}
                    <span style={{ color: 'var(--j-text-dim)' }}>Cost</span><span>{planOutcome.actual_cost || planOutcome.predicted_cost}</span>
                    <span style={{ color: 'var(--j-text-dim)' }}>Completed</span>
                    <span style={{ fontSize: 10 }}>{planOutcome.completed_at ? new Date(planOutcome.completed_at).toLocaleDateString() : (planOutcome.executed_at ? 'Running' : 'Pending')}</span>
                  </div>
                ) : (
                  <div style={{ fontSize: 11, color: 'var(--j-text-dim)' }}>
                    {planOutcome.executed_at ? 'Awaiting completion...' : 'Not yet executed'}
                  </div>
                )}
              </div>
            )}

            {/* Accuracy card */}
            {planAccuracy && planAccuracy.has_actuals && (
              <div style={{ borderRadius: 4, border: '1px solid var(--j-border)', background: 'var(--j-bg)', padding: '12px 16px' }}>
                <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--j-text-dim)', marginBottom: 8 }}>Accuracy</div>
                <div style={{ textAlign: 'center', marginBottom: 8 }}>
                  <span style={{ fontSize: 28, fontWeight: 700, color: planAccuracy.overall_accuracy >= 0.7 ? '#22c55e' : planAccuracy.overall_accuracy >= 0.4 ? '#f5c842' : '#ef4444' }}>
                    {Math.round(planAccuracy.overall_accuracy * 100)}%
                  </span>
                  <div style={{ fontSize: 10, color: 'var(--j-text-dim)' }}>Overall</div>
                </div>
                <div style={{ fontSize: 11 }}>
                  {Object.entries(planAccuracy.dimensions).map(([key, dim]: [string, any]) => (
                    <div key={key} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                      <span style={{ color: 'var(--j-text-dim)' }}>{key}</span>
                      <span style={{ fontWeight: 500, color: dim.score >= 0.7 ? '#22c55e' : dim.score >= 0.4 ? '#f5c842' : '#ef4444' }}>
                        {Math.round(dim.score * 100)}%
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Health Signals & Replan ──────────────────────────────────── */}
      {!healthLoading && replanOptions && (
        <div style={{ marginTop: 16 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            {/* Health signals */}
            <div style={{ borderRadius: 4, border: '1px solid var(--j-border)', background: 'var(--j-bg)', padding: '12px 16px' }}>
              <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--j-text-dim)', marginBottom: 8 }}>Health Signals</div>
              {planHealth && planHealth.signals.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 11 }}>
                  {planHealth.signals.map((s) => (
                    <div key={s.name} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{
                        width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
                        background: s.weight_multiplier >= 0.85 ? '#22c55e' : s.weight_multiplier >= 0.55 ? '#f5c842' : '#ef4444',
                      }} />
                      <span style={{ flex: 1, color: 'var(--j-text-dim)' }}>{s.label}</span>
                      <span style={{ fontWeight: 500 }}>{s.detail}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ fontSize: 11, color: 'var(--j-text-dim)' }}>No signals</div>
              )}
              {planHealth && (
                <div style={{ marginTop: 10, fontSize: 10, color: 'var(--j-text-dim)', textAlign: 'right' }}>
                  Score: {Math.round(planHealth.health_score * 100)}/100
                </div>
              )}
            </div>

            {/* Replan options */}
            <div style={{ borderRadius: 4, border: '1px solid var(--j-border)', background: 'var(--j-bg)', padding: '12px 16px' }}>
              <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--j-text-dim)', marginBottom: 8 }}>Replan Options</div>
              {replanOptions.options && replanOptions.options.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <div style={{ fontSize: 11, color: 'var(--j-text-dim)' }}>
                    Current: <strong>{replanOptions.current_strategy}</strong> ({replanOptions.current_score}/100)
                  </div>
                  {replanOptions.options.slice(0, 3).map((opt) => (
                    <div key={opt.strategy} style={{ borderRadius: 3, border: '1px solid var(--j-border)', padding: '8px 10px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                        <span style={{ fontSize: 12, fontWeight: 600 }}>{opt.strategy.replace(/_/g, ' ')}</span>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <span style={{ fontSize: 12, fontWeight: 600, color: opt.delta.overall_change > 0 ? '#22c55e' : '#f5c842' }}>
                            {Math.round(opt.score)}/100
                          </span>
                          {opt.delta.score_change > 0 && (
                            <span style={{ fontSize: 10, color: '#22c55e' }}>+{Math.round(opt.delta.score_change)}</span>
                          )}
                        </div>
                      </div>
                      <div style={{ fontSize: 10, color: 'var(--j-text-dim)', marginBottom: 4 }}>
                        {opt.description.slice(0, 100)}
                      </div>
                      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 6 }}>
                        {opt.delta.expected_improvements.filter(i => i !== 'neutral').map((imp) => (
                          <span key={imp} style={{ fontSize: 9, padding: '1px 5px', borderRadius: 2, background: 'rgba(34,197,94,0.1)', color: '#22c55e' }}>
                            {imp}
                          </span>
                        ))}
                      </div>
                      <button
                        onClick={async () => {
                          setReplanning(true);
                          try {
                            const updated = await plans.replanWithStrategy(plan.id, opt.strategy);
                            setSelectedPlan(updated);
                            await loadPlans();
                          } catch (e) { setError(String(e)); }
                          finally { setReplanning(false); }
                        }}
                        disabled={replanning}
                        style={{ padding: '4px 10px', fontSize: 10, borderRadius: 3, border: '1px solid var(--j-border)', background: 'var(--j-surface)', color: 'var(--j-text)', cursor: 'pointer', width: '100%' }}
                      >
                        {replanning ? 'Replanning...' : 'Apply This Strategy'}
                      </button>
                    </div>
                  ))}
                  {/* Auto-replan button */}
                  <button
                    onClick={async () => {
                      setReplanning(true);
                      try {
                        const result = await plans.autoReplan(plan.id);
                        if (result.plan) setSelectedPlan(result.plan);
                        await loadPlans();
                        const freshHealth = await plans.health(plan.id).catch(() => null);
                        if (freshHealth) setPlanHealth(freshHealth);
                      } catch (e) { setError(String(e)); }
                      finally { setReplanning(false); }
                    }}
                    disabled={replanning}
                    style={{ padding: '6px 10px', fontSize: 11, borderRadius: 3, border: '1px solid transparent', background: planHealth?.status === 'replan_required' ? 'rgba(239,68,68,0.15)' : 'rgba(34,197,94,0.1)', color: planHealth?.status === 'replan_required' ? '#ef4444' : '#22c55e', cursor: 'pointer', fontWeight: 600 }}
                  >
                    {replanning ? 'Replanning...' : planHealth?.status === 'replan_required' ? 'Auto-Replan Required' : planHealth?.status === 'replan_recommended' ? 'Auto-Replan Recommended' : 'Auto-Replan'}
                  </button>
                </div>
              ) : (
                <div style={{ fontSize: 11, color: 'var(--j-text-dim)' }}>
                  {replanning ? 'Generating options...' : 'No alternative strategies available'}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
