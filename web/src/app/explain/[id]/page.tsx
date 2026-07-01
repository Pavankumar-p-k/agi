'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { api, type ReplayDAG, type ReplayNode, type TimelineEvent, type DecisionTrace, type CandidateScore } from '@/lib/api';



/* ── Pipeline stage definitions ── */

const PIPELINE_STAGES = [
  { key: 'goal', label: 'Goal', icon: '🎯' },
  { key: 'planner', label: 'Planner', icon: '📋' },
  { key: 'capability', label: 'Capability', icon: '⚡' },
  { key: 'provider', label: 'Provider', icon: '🔌' },
  { key: 'permission', label: 'Permission', icon: '🛡️' },
  { key: 'execution', label: 'Execution', icon: '⚙️' },
  { key: 'learning', label: 'Learning', icon: '🧠' },
] as const;

/* ── Helpers ── */

function fmtDuration(seconds: number | null | undefined): string {
  if (seconds == null) return '--';
  if (seconds < 1) return `${(seconds * 1000).toFixed(0)}ms`;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${Math.floor(seconds / 60)}m ${(seconds % 60).toFixed(0)}s`;
}

function fmtTime(ts: number): string {
  return new Date(ts * 1000).toLocaleString();
}

function statusColor(status: string): string {
  if (['completed', 'success', 'running'].includes(status)) return 'var(--j-green)';
  if (['failed', 'error'].includes(status)) return '#ff4757';
  if (status === 'running') return 'var(--j-gold)';
  return 'var(--j-text-dim)';
}

function nodeTypeIcon(type: string): string {
  switch (type) {
    case 'goal': return '🎯';
    case 'subgoal': return '📌';
    case 'agent_call': return '🤖';
    case 'tool_call': return '🔧';
    case 'artifact': return '📦';
    case 'milestone': return '🏁';
    default: return '•';
  }
}

/* ── Sub-components ── */

function PipelineVisualization({ dag }: { dag: ReplayDAG }) {
  const activeStages = new Set<string>();
  for (const n of Object.values(dag.all_nodes)) {
    if (n.node_type === 'goal') activeStages.add('goal');
    if (n.node_type === 'subgoal') activeStages.add('planner');
    if (n.provider) activeStages.add('provider');
    if (n.tool) activeStages.add('execution');
  }
  if (dag.decisions.length > 0) activeStages.add('capability');
  if (dag.knowledge && dag.knowledge.length > 0) activeStages.add('learning');

  return (
    <div
      className="flex items-center gap-0 overflow-hidden"
      style={{
        border: '1px solid var(--j-border)',
        borderRadius: 'var(--j-radius-md)',
      }}
    >
      {PIPELINE_STAGES.map((stage, i) => {
        const active = activeStages.has(stage.key);
        return (
          <div
            key={stage.key}
            className="flex-1 flex flex-col items-center gap-1.5 px-3 py-4 text-center transition-all"
            style={{
              background: active ? 'rgba(var(--j-sky-rgb),0.06)' : 'transparent',
              borderRight: i < PIPELINE_STAGES.length - 1 ? '1px solid var(--j-border)' : 'none',
              opacity: active ? 1 : 0.4,
            }}
          >
            <span style={{ fontSize: 18, lineHeight: 1 }}>{stage.icon}</span>
            <span
              className="text-[9px] font-mono uppercase tracking-[0.12em] whitespace-nowrap"
              style={{ color: active ? 'var(--j-sky)' : 'var(--j-text-dim)' }}
            >
              {stage.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function SummaryCard({ dag }: { dag: ReplayDAG }) {
  const metrics = [
    { label: 'Total Nodes', value: `${dag.total_nodes}` },
    { label: 'Failed Nodes', value: `${dag.failed_nodes}`, color: dag.failed_nodes > 0 ? '#ff4757' : undefined },
    { label: 'Duration', value: fmtDuration(dag.total_duration_seconds) },
    { label: 'Tools Used', value: `${dag.unique_tools.length}` },
    { label: 'Providers', value: `${dag.unique_providers.length}` },
    { label: 'Retries', value: `${dag.total_retries}` },
    { label: 'Cost', value: dag.total_cost > 0 ? `$${dag.total_cost.toFixed(4)}` : '--' },
  ];

  return (
    <div
      className="grid grid-cols-4 md:grid-cols-7 gap-px"
      style={{
        border: '1px solid var(--j-border)',
        borderRadius: 'var(--j-radius-md)',
        overflow: 'hidden',
      }}
    >
      {metrics.map(m => (
        <div
          key={m.label}
          className="px-3 py-3 text-center"
          style={{ background: 'rgba(var(--j-bg-rgb),0.4)' }}
        >
          <div className="text-[9px] font-mono uppercase tracking-[0.12em]" style={{ color: 'var(--j-text-dim)' }}>
            {m.label}
          </div>
          <div
            className="text-sm font-mono mt-1"
            style={{ color: m.color || 'var(--j-text)' }}
          >
            {m.value}
          </div>
        </div>
      ))}
    </div>
  );
}

function UniqueToolsChips({ tools, providers }: { tools: string[]; providers: string[] }) {
  return (
    <div className="space-y-3">
      {tools.length > 0 && (
        <div>
          <div className="text-[9px] font-mono uppercase tracking-[0.12em] mb-2" style={{ color: 'var(--j-text-dim)' }}>
            Tools
          </div>
          <div className="flex flex-wrap gap-1.5">
            {tools.map(t => (
              <span
                key={t}
                className="px-2 py-1 text-[10px] font-mono"
                style={{
                  border: '1px solid var(--j-border)',
                  borderRadius: 'var(--j-radius-sm)',
                  background: 'rgba(var(--j-sky-rgb),0.06)',
                  color: 'var(--j-sky)',
                }}
              >
                {t}
              </span>
            ))}
          </div>
        </div>
      )}
      {providers.length > 0 && (
        <div>
          <div className="text-[9px] font-mono uppercase tracking-[0.12em] mb-2" style={{ color: 'var(--j-text-dim)' }}>
            Providers
          </div>
          <div className="flex flex-wrap gap-1.5">
            {providers.map(p => (
              <span
                key={p}
                className="px-2 py-1 text-[10px] font-mono"
                style={{
                  border: '1px solid var(--j-border)',
                  borderRadius: 'var(--j-radius-sm)',
                  background: 'rgba(var(--j-green-rgb),0.06)',
                  color: 'var(--j-green)',
                }}
              >
                {p}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function TimelineSection({ events }: { events: TimelineEvent[] }) {
  if (events.length === 0) return null;

  return (
    <div className="space-y-0">
      {events.map((ev, i) => (
        <div key={ev.node_id + i} className="flex gap-3 group">
          {/* Timeline line */}
          <div className="flex flex-col items-center shrink-0" style={{ width: 20 }}>
            <div
              className="w-2 h-2 rounded-full mt-1.5 shrink-0"
              style={{ background: statusColor(ev.status) }}
            />
            {i < events.length - 1 && (
              <div className="w-px flex-1 mt-1" style={{ background: 'var(--j-border)' }} />
            )}
          </div>
          {/* Content */}
          <div className="pb-4 flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span style={{ fontSize: 12 }}>{nodeTypeIcon(ev.node_type)}</span>
              <span className="text-xs font-mono" style={{ color: 'var(--j-text)' }}>
                {ev.label}
              </span>
              {ev.duration_seconds != null && (
                <span className="text-[10px] font-mono ml-auto shrink-0" style={{ color: 'var(--j-text-dim)' }}>
                  {fmtDuration(ev.duration_seconds)}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-[10px]" style={{ color: 'var(--j-text-dim)' }}>
                {fmtTime(ev.timestamp)}
              </span>
              <span
                className="text-[9px] font-mono uppercase tracking-[0.08em]"
                style={{ color: statusColor(ev.status) }}
              >
                {ev.status}
              </span>
            </div>
            {ev.detail && (
              <div
                className="mt-1 text-[11px] font-mono leading-relaxed"
                style={{ color: 'var(--j-text-muted)' }}
              >
                {ev.detail}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function CandidateScoreBar({ score, label, maxScore }: { score: number; label: string; maxScore: number }) {
  const pct = maxScore > 0 ? (score / maxScore) * 100 : 0;
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] font-mono w-28 shrink-0 text-right" style={{ color: 'var(--j-text-dim)' }}>
        {label}
      </span>
      <div className="flex-1 h-3 rounded-sm overflow-hidden" style={{ background: 'rgba(var(--j-bg-rgb),0.5)' }}>
        <div
          className="h-full rounded-sm transition-all"
          style={{ width: `${pct}%`, background: 'var(--j-sky)' }}
        />
      </div>
      <span className="text-[10px] font-mono w-10 text-right" style={{ color: 'var(--j-text)' }}>
        {score.toFixed(2)}
      </span>
    </div>
  );
}

function CandidateCard({ candidate, isSelected }: { candidate: CandidateScore; isSelected: boolean }) {
  const maxScore = Math.max(candidate.total_score, 0.01);
  const dimensions: { label: string; value: number }[] = [
    { label: 'Priority', value: candidate.priority_score },
    { label: 'Historical', value: candidate.historical_score },
    { label: 'Benchmark', value: candidate.benchmark_score },
    { label: 'Health', value: candidate.health_score },
    { label: 'Latency', value: candidate.latency_score },
    { label: 'Cost', value: candidate.cost_score },
    { label: 'Budget', value: candidate.budget_score },
    { label: 'Offline', value: candidate.offline_score },
    { label: 'Calibration', value: candidate.calibration_adjustment },
  ];

  return (
    <div
      className="px-4 py-3 transition-all"
      style={{
        border: isSelected ? '1px solid var(--j-sky)' : '1px solid var(--j-border)',
        borderRadius: 'var(--j-radius-md)',
        background: isSelected ? 'rgba(var(--j-sky-rgb),0.06)' : 'transparent',
      }}
    >
      <div className="flex items-center gap-2 mb-2">
        <span className="text-xs font-mono" style={{ color: 'var(--j-text)' }}>
          {candidate.provider_id}
        </span>
        {isSelected && (
          <span
            className="px-1.5 py-0.5 text-[8px] font-mono uppercase tracking-[0.08em]"
            style={{
              background: 'var(--j-sky)',
              color: '#000',
              borderRadius: 'var(--j-radius-sm)',
            }}
          >
            Selected
          </span>
        )}
        <span className="text-xs font-mono ml-auto" style={{ color: 'var(--j-sky)' }}>
          {candidate.total_score.toFixed(2)}
        </span>
      </div>
      <div className="space-y-0.5">
        {dimensions.map(d => d.value !== 0 && (
          <CandidateScoreBar key={d.label} label={d.label} score={d.value} maxScore={maxScore} />
        ))}
      </div>
    </div>
  );
}

function DecisionSection({ decisions }: { decisions: DecisionTrace[] }) {
  if (decisions.length === 0) return null;

  return (
    <div className="space-y-4">
      {decisions.map(d => (
        <div key={d.decision_id}>
          <div className="flex items-center gap-2 mb-3">
            <span className="text-xs font-mono" style={{ color: 'var(--j-sky)' }}>
              {d.capability}
            </span>
            <span className="text-[10px]" style={{ color: 'var(--j-text-dim)' }}>→</span>
            <span className="text-xs font-mono" style={{ color: 'var(--j-green)' }}>
              {d.selected_provider}
            </span>
            {d.outcome && (
              <span
                className={`text-[9px] font-mono uppercase tracking-[0.08em] ml-auto ${d.outcome.success ? '' : ''}`}
                style={{ color: d.outcome.success ? 'var(--j-green)' : '#ff4757' }}
              >
                {d.outcome.success ? '✓ Success' : '✗ Failed'} · {fmtDuration(d.outcome.duration_ms / 1000)}
              </span>
            )}
          </div>

          {d.reasons.length > 0 && (
            <div className="mb-3 space-y-0.5">
              {d.reasons.map((r, i) => (
                <div key={i} className="flex items-start gap-2">
                  <span className="text-[10px] mt-px" style={{ color: 'var(--j-text-dim)' }}>→</span>
                  <span className="text-[11px]" style={{ color: 'var(--j-text-muted)' }}>{r}</span>
                </div>
              ))}
            </div>
          )}

          <div className="space-y-2">
            {d.candidates.map(c => (
              <CandidateCard key={c.provider_id} candidate={c} isSelected={c.provider_id === d.selected_provider} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function KnowledgeSection({ knowledge }: { knowledge: Record<string, unknown>[] }) {
  if (!knowledge || knowledge.length === 0) return null;

  return (
    <div className="space-y-2">
      {knowledge.map((item, i) => (
        <div
          key={i}
          className="px-4 py-3"
          style={{
            border: '1px solid var(--j-border)',
            borderRadius: 'var(--j-radius-md)',
          }}
        >
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] font-mono uppercase tracking-[0.08em]" style={{ color: 'var(--j-sky)' }}>
              {item.category as string}
            </span>
            {(item.confidence as number) != null && (
              <span
                className="text-[9px] font-mono ml-auto"
                style={{ color: (item.confidence as number) > 0.7 ? 'var(--j-green)' : 'var(--j-gold)' }}
              >
                {(item.confidence as number).toFixed(2)} confidence
              </span>
            )}
          </div>
          <div className="text-[11px] font-mono leading-relaxed" style={{ color: 'var(--j-text-muted)' }}>
            {item.claim as string}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ── Node Tree ── */

function NodeTree({ node, depth }: { node: ReplayNode; depth?: number }) {
  const [expanded, setExpanded] = useState(true);
  const d = depth ?? 0;
  const hasChildren = node.children && node.children.length > 0;

  return (
    <div>
      <div
        className="flex items-center gap-2 py-1.5 px-2 rounded-sm cursor-pointer hover:bg-[rgba(var(--j-sky-rgb),0.04)] transition-colors"
        style={{ paddingLeft: 8 + d * 16 }}
        onClick={() => setExpanded(!expanded)}
        role="treeitem"
        aria-expanded={hasChildren ? expanded : undefined}
      >
        {hasChildren ? (
          <span className="text-[10px] w-3 shrink-0" style={{ color: 'var(--j-text-dim)' }}>
            {expanded ? '▼' : '▶'}
          </span>
        ) : (
          <span className="w-3 shrink-0" />
        )}
        <span style={{ fontSize: 12 }}>{nodeTypeIcon(node.node_type)}</span>
        <span className="text-[11px] font-mono truncate flex-1" style={{ color: 'var(--j-text)' }}>
          {node.label}
        </span>
        <span
          className="text-[9px] font-mono uppercase tracking-[0.08em] shrink-0"
          style={{ color: statusColor(node.status) }}
        >
          {node.status}
        </span>
        {node.duration_seconds != null && (
          <span className="text-[9px] font-mono shrink-0" style={{ color: 'var(--j-text-dim)' }}>
            {fmtDuration(node.duration_seconds)}
          </span>
        )}
        {node.tool && (
          <span
            className="px-1.5 py-0.5 text-[8px] font-mono shrink-0"
            style={{
              border: '1px solid var(--j-border)',
              borderRadius: 'var(--j-radius-sm)',
              color: 'var(--j-sky)',
            }}
          >
            {node.tool}
          </span>
        )}
      </div>

      {expanded && hasChildren && (
        <div>
          {node.children.map(c => (
            <NodeTree key={c.node_id} node={c} depth={d + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Main Page ── */

export default function ExplainPage() {
  const params = useParams();
  const activityId = params?.id as string;
  const [dag, setDag] = useState<ReplayDAG | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!activityId) return;
    setLoading(true);
    api.activity.replay(activityId)
      .then(setDag)
      .catch(err => setError(err instanceof Error ? err.message : 'Failed to load task explanation'))
      .finally(() => setLoading(false));
  }, [activityId]);

  if (loading) {
    return (
      <div className="mx-auto max-w-4xl py-12">
        <div className="flex items-center justify-center py-20">
          <div
            className="w-2 h-2 rounded-full animate-pulse"
            style={{ background: 'var(--j-sky)' }}
          />
        </div>
      </div>
    );
  }

  if (error || !dag) {
    return (
      <div className="mx-auto max-w-4xl py-12">
        <div className="text-center py-20">
          <p className="text-sm font-mono" style={{ color: '#ff4757' }}>{error || 'No data found'}</p>
        </div>
      </div>
    );
  }

  const rootNode = dag.root_id ? dag.all_nodes[dag.root_id] : null;

  return (
    <div className="mx-auto max-w-4xl space-y-8 pb-12">

      {/* ── Header ── */}
      <div>
        <h1 className="text-xs font-mono uppercase tracking-[0.12em]" style={{ color: 'var(--j-text-dim)' }}>
          Task Explanation
        </h1>
        <h2 className="text-sm font-mono mt-1" style={{ color: 'var(--j-text)' }}>
          {rootNode?.label || dag.activity_id}
        </h2>
        <p className="text-[10px] font-mono mt-1" style={{ color: 'var(--j-text-muted)' }}>
          {dag.activity_id}
        </p>
      </div>

      {/* ── Pipeline Visualization ── */}
      <section>
        <div className="flex items-center gap-2 mb-3">
          <h2 className="text-[9px] font-mono uppercase tracking-[0.12em]" style={{ color: 'var(--j-text-dim)' }}>Pipeline</h2>
          <span className="h-px flex-1" style={{ background: 'var(--j-border)' }} />
        </div>
        <PipelineVisualization dag={dag} />
      </section>

      {/* ── Summary Metrics ── */}
      <section>
        <div className="flex items-center gap-2 mb-3">
          <h2 className="text-[9px] font-mono uppercase tracking-[0.12em]" style={{ color: 'var(--j-text-dim)' }}>Summary</h2>
          <span className="h-px flex-1" style={{ background: 'var(--j-border)' }} />
        </div>
        <SummaryCard dag={dag} />
        <div className="mt-4">
          <UniqueToolsChips tools={dag.unique_tools} providers={dag.unique_providers} />
        </div>
      </section>

      {/* ── Timeline ── */}
      {dag.timeline.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-3">
            <h2 className="text-[9px] font-mono uppercase tracking-[0.12em]" style={{ color: 'var(--j-text-dim)' }}>Timeline</h2>
            <span className="h-px flex-1" style={{ background: 'var(--j-border)' }} />
          </div>
          <TimelineSection events={dag.timeline} />
        </section>
      )}

      {/* ── Decision Traces ── */}
      {dag.decisions.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-3">
            <span className="text-[8px]">🔌</span>
            <h2 className="text-[9px] font-mono uppercase tracking-[0.12em]" style={{ color: 'var(--j-text-dim)' }}>
              Provider Routing ({dag.decisions.length})
            </h2>
            <span className="h-px flex-1" style={{ background: 'var(--j-border)' }} />
          </div>
          <DecisionSection decisions={dag.decisions} />
        </section>
      )}

      {/* ── Knowledge ── */}
      {dag.knowledge && dag.knowledge.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-3">
            <span className="text-[8px]">🧠</span>
            <h2 className="text-[9px] font-mono uppercase tracking-[0.12em]" style={{ color: 'var(--j-text-dim)' }}>
              Knowledge ({dag.knowledge.length})
            </h2>
            <span className="h-px flex-1" style={{ background: 'var(--j-border)' }} />
          </div>
          <KnowledgeSection knowledge={dag.knowledge} />
        </section>
      )}

      {/* ── Execution Tree ── */}
      {rootNode && (
        <section>
          <div className="flex items-center gap-2 mb-3">
            <h2 className="text-[9px] font-mono uppercase tracking-[0.12em]" style={{ color: 'var(--j-text-dim)' }}>
              Execution Tree ({dag.total_nodes} nodes)
            </h2>
            <span className="h-px flex-1" style={{ background: 'var(--j-border)' }} />
          </div>
          <div
            role="tree"
            aria-label="Execution tree"
            style={{
              border: '1px solid var(--j-border)',
              borderRadius: 'var(--j-radius-md)',
              overflow: 'hidden',
            }}
          >
            <NodeTree node={rootNode} />
          </div>
        </section>
      )}

    </div>
  );
}
