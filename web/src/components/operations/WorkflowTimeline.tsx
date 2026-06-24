'use client';

import { useState, useEffect } from 'react';
import { workflows } from '@jarvis/sdk';
import type { WorkflowDetail, WorkflowSummary } from '@jarvis/sdk';
import { StatusDot } from '@jarvis/ui';

interface Props {
  /** Show workflow list if undefined, or a specific workflow if ID is given. */
  workflowId?: string;
  onStatusChange?: () => void;
}

const STATUS_GROUPS: Record<string, string> = {
  RUNNING: 'Running',
  FAILED: 'Failed',
  PENDING: 'Queued',
  COMPLETED: 'Completed',
  CANCELLED: 'Cancelled',
  COMPENSATING: 'Rolling back',
  COMPENSATED: 'Rolled back',
};

export function WorkflowTimeline({ workflowId, onStatusChange }: Props) {
  const [workflow, setWorkflow] = useState<WorkflowDetail | null>(null);
  const [workflowList, setWorkflowList] = useState<WorkflowSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actioning, setActioning] = useState<string | null>(null);

  const loadDetail = () => {
    if (!workflowId) return;
    setLoading(true);
    workflows
      .get(workflowId)
      .then((w) => {
        setWorkflow(w);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load workflow'))
      .finally(() => setLoading(false));
  };

  const loadList = () => {
    if (workflowId) return;
    setLoading(true);
    workflows
      .list()
      .then((r) => {
        setWorkflowList(r.workflows);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load workflows'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (workflowId) loadDetail();
    else loadList();
  }, [workflowId]);

  const handleResume = async (id: string) => {
    setActioning(id);
    try {
      await workflows.resume(id);
      onStatusChange?.();
      loadDetail();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to resume');
    } finally {
      setActioning(null);
    }
  };

  const handleCancel = async (id: string) => {
    if (!confirm('Cancel this workflow?')) return;
    setActioning(id);
    try {
      await workflows.cancel(id);
      onStatusChange?.();
      loadDetail();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to cancel');
    } finally {
      setActioning(null);
    }
  };

  // ── Workflow list view ─────────────────────────────────────────────────

  if (!workflowId) {
    if (loading && workflowList.length === 0) {
      return (
        <div className="hud-panel" style={{ padding: 24 }}>
          <h2 className="hud-title">Workflows</h2>
          <div style={{ textAlign: 'center', padding: 16, color: 'var(--j-text-dim)', fontSize: 13 }}>Loading...</div>
        </div>
      );
    }

    if (workflowList.length === 0) {
      return null;
    }

    return (
      <div className="hud-panel" style={{ padding: 24 }}>
        <h2 className="hud-title" style={{ marginBottom: 16 }}>
          Workflows
          <span style={{ fontSize: 12, marginLeft: 8, opacity: 0.6 }}>({workflowList.length})</span>
        </h2>
        {error && <div style={{ fontSize: 12, color: '#f55', marginBottom: 8 }}>{error}</div>}
        {workflowList.map((w) => (
          <div
            key={w.workflow_id}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              padding: '10px 12px',
              borderRadius: 4,
              background: 'var(--j-surface)',
              border: '1px solid var(--j-border)',
              marginBottom: 6,
            }}
          >
            <StatusDot status={w.status as any} size={10} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {w.workflow_type}
              </div>
              <div style={{ fontSize: 10, color: 'var(--j-text-dim)', marginTop: 2 }}>
                {STATUS_GROUPS[w.status] || w.status} — {w.progress} steps
              </div>
            </div>
            <div style={{ fontSize: 10, color: 'var(--j-text-dim)', whiteSpace: 'nowrap' }}>
              {w.created_at ? new Date(w.created_at).toLocaleString() : ''}
            </div>
          </div>
        ))}
      </div>
    );
  }

  // ── Single workflow detail view ────────────────────────────────────────

  if (loading && !workflow) {
    return (
      <div className="hud-panel" style={{ padding: 24 }}>
        <h2 className="hud-title">Workflow Timeline</h2>
        <div style={{ textAlign: 'center', padding: 16, color: 'var(--j-text-dim)', fontSize: 13 }}>Loading...</div>
      </div>
    );
  }

  if (!workflow) {
    return null;
  }

  return (
    <div className="hud-panel" style={{ padding: 24 }}>
      <h2 className="hud-title" style={{ marginBottom: 16 }}>
        Workflow Timeline
        <span style={{ fontSize: 12, marginLeft: 8, opacity: 0.6 }}>({workflow.steps.length} steps)</span>
      </h2>

      {error && <div style={{ fontSize: 12, color: '#f55', marginBottom: 8 }}>{error}</div>}

      {/* Workflow header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '8px 12px',
        marginBottom: 12,
        borderRadius: 4,
        background: 'var(--j-surface)',
        border: '1px solid var(--j-border)',
      }}>
        <StatusDot status={workflow.status as any} size={12} pulse={workflow.status === 'RUNNING'} />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 12, fontWeight: 500 }}>{workflow.workflow_type}</div>
          <div style={{ fontSize: 11, color: 'var(--j-text-dim)', marginTop: 2 }}>
            {STATUS_GROUPS[workflow.status] || workflow.status} — {workflow.progress}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          {(workflow.status === 'FAILED' || workflow.status === 'PENDING') && (
            <button
              onClick={() => handleResume(workflow.workflow_id)}
              disabled={actioning === workflow.workflow_id}
              style={{
                fontSize: 11,
                padding: '3px 10px',
                borderRadius: 3,
                border: 'none',
                background: '#2d7a3a',
                color: '#fff',
                cursor: 'pointer',
                opacity: actioning === workflow.workflow_id ? 0.6 : 1,
              }}
            >
              Resume
            </button>
          )}
          {workflow.status === 'RUNNING' && (
            <button
              onClick={() => handleCancel(workflow.workflow_id)}
              disabled={actioning === workflow.workflow_id}
              style={{
                fontSize: 11,
                padding: '3px 10px',
                borderRadius: 3,
                border: 'none',
                background: '#7a2d2d',
                color: '#fff',
                cursor: 'pointer',
                opacity: actioning === workflow.workflow_id ? 0.6 : 1,
              }}
            >
              Cancel
            </button>
          )}
        </div>
      </div>

      {/* Step timeline */}
      <div style={{ position: 'relative', paddingLeft: 24 }}>
        <div style={{ position: 'absolute', left: 11, top: 4, bottom: 4, width: 1, background: 'var(--j-border)' }} />

        {workflow.steps.map((step, idx) => (
          <div key={step.step_id} style={{ position: 'relative', paddingBottom: 12 }}>
            <div style={{ position: 'absolute', left: -19, top: 3 }}>
              <StatusDot status={step.status as any} size={10} />
            </div>
            <div
              style={{
                padding: '8px 12px',
                borderRadius: 4,
                background: 'var(--j-surface)',
                border: '1px solid var(--j-border)',
                marginBottom: 4,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 11, fontWeight: 500 }}>
                  {idx + 1}. {step.tool_name}
                </span>
                <span style={{ fontSize: 10, color: 'var(--j-text-dim)', marginLeft: 'auto' }}>
                  {step.status}
                </span>
              </div>
              {step.started_at && (
                <div style={{ fontSize: 10, color: 'var(--j-text-dim)', marginTop: 2 }}>
                  {new Date(step.started_at).toLocaleTimeString()}
                  {step.completed_at && ` → ${new Date(step.completed_at).toLocaleTimeString()}`}
                </div>
              )}
              {step.error && (
                <div style={{ fontSize: 10, color: '#f55', marginTop: 4, whiteSpace: 'pre-wrap' }}>
                  {step.error}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
