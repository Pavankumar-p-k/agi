'use client';

import { useState } from 'react';
import { motion, type Variants } from 'framer-motion';
import { useOperationsData } from '@/hooks/useOperationsData';
import { ActiveGoals } from '@/components/operations/ActiveGoals';
import { AgentQueue } from '@/components/operations/AgentQueue';
import { ActivityGraph } from '@/components/operations/ActivityGraph';
import { WorkflowTimeline } from '@/components/operations/WorkflowTimeline';
import { RecentArtifacts } from '@/components/operations/RecentArtifacts';
import { ScheduledGoals } from '@/components/operations/ScheduledGoals';
import { KnowledgeExplorer } from '@/components/operations/KnowledgeExplorer';
import { ResearchExplorer } from '@/components/operations/ResearchExplorer';
import { PlannerStudio } from '@/components/operations/PlannerStudio';
import { AgentPerformanceDashboard } from '@/components/operations/AgentPerformanceDashboard';
import { ImprovementPanel } from '@/components/operations/ImprovementPanel';
import { NegotiationPanel } from '@/components/operations/NegotiationPanel';
import { OpportunityPanel } from '@/components/operations/OpportunityPanel';
import { RecoveryFeed } from '@/components/operations/RecoveryFeed';
import type { ActivityNode } from '@jarvis/sdk';

const containerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.06, delayChildren: 0.08 } },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 28 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.62, ease: [0.16, 1, 0.3, 1] } },
};

export default function OperationsCenter() {
  const {
    activities,
    agentList,
    events,
    counts,
    loading,
    error,
    pauseActivity,
    resumeActivity,
    cancelActivity,
    refresh,
  } = useOperationsData();

  const [selectedActivity, setSelectedActivity] = useState<ActivityNode | null>(null);
  const [showGraph, setShowGraph] = useState(true);

  const rootGoal = activities.find((a) => a.node_type === 'goal');

  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      className="hud-page"
      style={{ padding: '24px 32px', maxWidth: 1400, margin: '0 auto' }}
    >
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <motion.div variants={itemVariants} style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <h1 className="hud-title" style={{ fontSize: 28, margin: 0 }}>Operations Center</h1>
            <p style={{ margin: '4px 0 0', fontSize: 13, color: 'var(--j-text-dim)' }}>
              Active goals · Agent queue · Workflow timeline · Live events
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <button
              onClick={refresh}
              style={{
                padding: '8px 16px',
                borderRadius: 4,
                border: '1px solid var(--j-border)',
                background: 'var(--j-surface)',
                color: 'var(--j-text)',
                cursor: 'pointer',
                fontSize: 12,
              }}
            >
              Refresh
            </button>
            {showGraph && rootGoal && (
              <button
                onClick={() => setShowGraph(false)}
                style={{
                  padding: '8px 16px',
                  borderRadius: 4,
                  border: '1px solid var(--j-border)',
                  background: 'var(--j-surface)',
                  color: 'var(--j-text)',
                  cursor: 'pointer',
                  fontSize: 12,
                }}
              >
                Close Graph
              </button>
            )}
          </div>
        </div>
        {Object.keys(counts).length > 0 && (
          <div style={{ display: 'flex', gap: 16, marginTop: 12, fontSize: 12 }}>
            {Object.entries(counts).map(([status, count]) => (
              <span key={status} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: '50%',
                    display: 'inline-block',
                    backgroundColor:
                      status === 'RUNNING' ? '#00d2ff'
                      : status === 'COMPLETED' ? '#22c55e'
                      : status === 'FAILED' ? '#ef4444'
                      : status === 'SUSPENDED' ? '#f5c842'
                      : status === 'CANCELLED' ? '#6b7280'
                      : '#8b8b8b',
                  }}
                />
                {status}: {count}
              </span>
            ))}
          </div>
        )}
        {error && (
          <div
            style={{
              marginTop: 8,
              padding: '8px 16px',
              borderRadius: 4,
              background: 'rgba(239,68,68,0.1)',
              border: '1px solid rgba(239,68,68,0.3)',
              color: '#ef4444',
              fontSize: 12,
            }}
          >
            {error}
            <button onClick={refresh} style={{ marginLeft: 12, textDecoration: 'underline', background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer' }}>
              Retry
            </button>
          </div>
        )}
      </motion.div>

      {/* ── Planner Studio ──────────────────────────────────────────────── */}
      {!loading && (
        <motion.div variants={itemVariants} style={{ marginBottom: 16 }}>
          <PlannerStudio />
        </motion.div>
      )}

      {/* ── Loading state ───────────────────────────────────────────────── */}
      {loading && (
        <motion.div variants={itemVariants}>
          <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: 16 }}>
            <div className="hud-panel" style={{ height: 200 }}>
              <div className="hud-skeleton" style={{ width: '60%', height: 16, margin: 24 }} />
              <div className="hud-skeleton" style={{ width: '90%', height: 48, margin: '8px 24px' }} />
              <div className="hud-skeleton" style={{ width: '90%', height: 48, margin: '8px 24px' }} />
            </div>
            <div className="hud-panel" style={{ height: 200 }}>
              <div className="hud-skeleton" style={{ width: '40%', height: 16, margin: 24 }} />
              <div className="hud-skeleton" style={{ width: '95%', height: 120, margin: '8px 24px' }} />
            </div>
          </div>
        </motion.div>
      )}

      {/* ── Main grid ───────────────────────────────────────────────────── */}
      {!loading && (
        <motion.div variants={itemVariants} style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: 16, marginBottom: 16 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <ActiveGoals
              activities={activities}
              onSelect={(goal) => {
                setSelectedActivity(goal);
                setShowGraph(true);
              }}
            />
            <ScheduledGoals />
          </div>
          <AgentQueue agents={agentList} />
        </motion.div>
      )}

      {/* ── Activity Graph + Workflow Timeline ──────────────────────────── */}
      {!loading && showGraph && selectedActivity && (
        <motion.div
          variants={itemVariants}
          style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}
        >
          <ActivityGraph
            activityId={selectedActivity.activity_id}
            onClose={() => setShowGraph(false)}
          />
          <WorkflowTimeline workflowId={selectedActivity.workflow_id || undefined} />
        </motion.div>
      )}

      {/* ── No selection state ──────────────────────────────────────────── */}
      {!loading && !selectedActivity && activities.length > 0 && (
        <motion.div
          variants={itemVariants}
          className="hud-panel"
          style={{ padding: 32, textAlign: 'center', color: 'var(--j-text-dim)', marginBottom: 16 }}
        >
          Select a goal from the Active Goals panel to see its activity graph and timeline.
        </motion.div>
      )}

      {/* ── Workflows ───────────────────────────────────────────────────── */}
      {!loading && (
        <motion.div variants={itemVariants} style={{ marginBottom: 16 }}>
          <WorkflowTimeline />
        </motion.div>
      )}

      {/* ── Recent Artifacts ────────────────────────────────────────────── */}
      {!loading && (
        <motion.div variants={itemVariants} style={{ marginBottom: 16 }}>
          <RecentArtifacts />
        </motion.div>
      )}

      {/* ── Knowledge Explorer ──────────────────────────────────────────── */}
      {!loading && (
        <motion.div variants={itemVariants} style={{ marginBottom: 16 }}>
          <KnowledgeExplorer />
        </motion.div>
      )}

      {/* ── Research Explorer ──────────────────────────────────────────── */}
      {!loading && (
        <motion.div variants={itemVariants} style={{ marginBottom: 16 }}>
          <ResearchExplorer />
        </motion.div>
      )}

      {/* ── Agent Performance Dashboard ────────────────────────────────── */}
      {!loading && (
        <motion.div variants={itemVariants} style={{ marginBottom: 16 }}>
          <AgentPerformanceDashboard />
        </motion.div>
      )}

      {/* ── Improvement System ──────────────────────────────────────────── */}
      {!loading && (
        <motion.div variants={itemVariants} style={{ marginBottom: 16 }}>
          <ImprovementPanel />
        </motion.div>
      )}

      {/* ── Negotiations ─────────────────────────────────────────────────── */}
      {!loading && (
        <motion.div variants={itemVariants} style={{ marginBottom: 16 }}>
          <NegotiationPanel />
        </motion.div>
      )}

      {/* ── Opportunity Discovery ────────────────────────────────────────── */}
      {!loading && (
        <motion.div variants={itemVariants} style={{ marginBottom: 16 }}>
          <OpportunityPanel />
        </motion.div>
      )}

      {/* ── Recovery Feed ───────────────────────────────────────────────── */}
      {!loading && (
        <motion.div variants={itemVariants}>
          <RecoveryFeed events={events} />
        </motion.div>
      )}

      {/* ── Empty state ─────────────────────────────────────────────────── */}
      {!loading && activities.length === 0 && (
        <motion.div
          variants={itemVariants}
          className="hud-panel"
          style={{
            padding: 64,
            textAlign: 'center',
            color: 'var(--j-text-dim)',
          }}
        >
          <div style={{ fontSize: 32, marginBottom: 16, opacity: 0.4 }}>○</div>
          <h2 style={{ fontSize: 18, fontWeight: 500, margin: '0 0 8px' }}>No Active Operations</h2>
          <p style={{ fontSize: 13, maxWidth: 400, margin: '0 auto' }}>
            Start a goal, run an agent, or trigger a build. Activity will appear here automatically.
          </p>
          <div style={{ marginTop: 24, display: 'flex', gap: 12, justifyContent: 'center' }}>
            <a
              href="/chat"
              style={{
                padding: '10px 24px',
                borderRadius: 4,
                background: 'var(--j-sky)',
                color: '#020406',
                textDecoration: 'none',
                fontWeight: 500,
                fontSize: 13,
              }}
            >
              Start Chat
            </a>
            <a
              href="/build"
              style={{
                padding: '10px 24px',
                borderRadius: 4,
                border: '1px solid var(--j-border)',
                color: 'var(--j-text)',
                textDecoration: 'none',
                fontSize: 13,
              }}
            >
              Start Build
            </a>
          </div>
        </motion.div>
      )}

      {/* ── Activity actions ────────────────────────────────────────────── */}
      {selectedActivity && (selectedActivity.status === 'RUNNING' || selectedActivity.status === 'SUSPENDED') && (
        <motion.div
          variants={itemVariants}
          style={{
            position: 'fixed',
            bottom: 24,
            right: 24,
            display: 'flex',
            gap: 8,
            padding: '12px 16px',
            borderRadius: 8,
            background: 'var(--j-surface)',
            border: '1px solid var(--j-border)',
            backdropFilter: 'blur(12px)',
            zIndex: 50,
          }}
        >
          <span style={{ fontSize: 12, display: 'flex', alignItems: 'center', marginRight: 8 }}>
            {selectedActivity.label.slice(0, 30)}
          </span>
          {selectedActivity.status === 'RUNNING' && (
            <button
              onClick={() => pauseActivity(selectedActivity.activity_id)}
              style={{
                padding: '6px 14px',
                borderRadius: 4,
                border: '1px solid #f5c842',
                background: 'rgba(245,200,66,0.1)',
                color: '#f5c842',
                cursor: 'pointer',
                fontSize: 12,
              }}
            >
              Pause
            </button>
          )}
          {selectedActivity.status === 'SUSPENDED' && (
            <button
              onClick={() => resumeActivity(selectedActivity.activity_id)}
              style={{
                padding: '6px 14px',
                borderRadius: 4,
                border: '1px solid #00d2ff',
                background: 'rgba(0,210,255,0.1)',
                color: '#00d2ff',
                cursor: 'pointer',
                fontSize: 12,
              }}
            >
              Resume
            </button>
          )}
          <button
            onClick={() => cancelActivity(selectedActivity.activity_id)}
            style={{
              padding: '6px 14px',
              borderRadius: 4,
              border: '1px solid #ef4444',
              background: 'rgba(239,68,68,0.1)',
              color: '#ef4444',
              cursor: 'pointer',
              fontSize: 12,
            }}
          >
            Cancel
          </button>
        </motion.div>
      )}
    </motion.div>
  );
}
