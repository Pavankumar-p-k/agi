'use client';

import type { Agent } from '@jarvis/sdk';
import { StatusDot } from '@jarvis/ui';

interface Props {
  agents: Agent[];
  onRun?: (agent: Agent) => void;
}

type Column = {
  key: string;
  label: string;
  statuses: string[];
};

const COLUMNS: Column[] = [
  { key: 'running', label: 'Running', statuses: ['running'] },
  { key: 'queued', label: 'Queued', statuses: ['idle', 'pending'] },
  { key: 'failed', label: 'Failed', statuses: ['failed'] },
  { key: 'paused', label: 'Paused', statuses: ['paused'] },
];

function groupByStatus(agents: Agent[], statuses: string[]): Agent[] {
  return agents.filter((a) => statuses.includes(a.status));
}

export function AgentQueue({ agents: agentList, onRun }: Props) {
  return (
    <div className="hud-panel" style={{ padding: 24 }}>
      <h2 className="hud-title" style={{ marginBottom: 16 }}>
        Agent Queue
        <span style={{ fontSize: 12, marginLeft: 8, opacity: 0.6 }}>({agentList.length})</span>
      </h2>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
        {COLUMNS.map((col) => {
          const group = groupByStatus(agentList, col.statuses);
          return (
            <div key={col.key} style={{ minWidth: 0 }}>
              <div style={{ fontSize: 11, color: 'var(--j-text-dim)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                {col.label}
                <span style={{ marginLeft: 4 }}>({group.length})</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {group.map((agent) => (
                  <div
                    key={agent.name}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      padding: '8px 12px',
                      borderRadius: 4,
                      background: 'var(--j-surface)',
                      border: '1px solid var(--j-border)',
                      cursor: onRun ? 'pointer' : 'default',
                    }}
                    onClick={() => onRun?.(agent)}
                  >
                    <StatusDot status={agent.status} size={8} pulse={agent.status === 'running'} />
                    <span style={{ fontSize: 12, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {agent.display_name || agent.name}
                    </span>
                  </div>
                ))}
                {group.length === 0 && (
                  <div style={{ fontSize: 11, color: 'var(--j-text-dim)', padding: '8px 0', textAlign: 'center' }}>
                    —
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
