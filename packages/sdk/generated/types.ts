/* ───────────────────────────────────────────────────────────────────────────
 * @jarvis/sdk — Generated Types
 *
 * These types are auto-generated from the backend FastAPI OpenAPI schema.
 * To regenerate:
 *   curl http://localhost:8000/openapi.json > generated/schema.json
 *   npx openapi-typescript generated/schema.json -o generated/types.ts
 *
 * Manual source-of-truth version. Update when backend endpoints change.
 * ─────────────────────────────────────────────────────────────────────────── */

// ── Activity Graph ────────────────────────────────────────────────────────

export interface ActivityNode {
  node_id: string;
  activity_id: string;
  node_type: 'goal' | 'subgoal' | 'agent_call' | 'tool_call' | 'artifact' | 'milestone';
  label: string;
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'SUSPENDED' | 'CANCELLED';
  depth: number;
  parent_id: string | null;
  agent_id: string | null;
  origin_node_id: string | null;
  artifacts: Record<string, string>;
  workflow_id: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string | null;
  metadata: Record<string, unknown>;
}

export interface ActivityEdge {
  edge_id: string;
  from_node_id: string;
  to_node_id: string;
  edge_type: 'depends_on' | 'produces' | 'triggers' | 'references';
  created_at: string | null;
}

export interface ActivityTree {
  nodes: ActivityNode[];
  edges: ActivityEdge[];
}

export interface ActivitySummary {
  activity_id: string;
  goal: string | null;
  status: string | null;
  total_nodes: number;
  by_status: Record<string, number>;
  by_type: Record<string, number>;
  depth: number;
  agents_used: string[];
  created_at: string | null;
}

export interface ActivityCounts {
  total: number;
  running: number;
  pending: number;
  completed: number;
  failed: number;
  suspended: number;
  cancelled: number;
}

export interface ResumeContext {
  activity_id: string;
  target_node: ActivityNode;
  ancestors: ActivityNode[];
  accumulated_artifacts: Record<string, string>;
  accumulated_input: Record<string, unknown>;
}

// ── Agents ────────────────────────────────────────────────────────────────

export interface Agent {
  name: string;
  display_name?: string;
  description?: string;
  status: 'idle' | 'running' | 'paused' | 'failed' | 'offline';
  modes?: string[];
  default_mode?: string;
  current_task?: string;
  last_active?: string;
}

// ── Artifacts ─────────────────────────────────────────────────────────────

export interface Artifact {
  artifact_id: string;
  workflow_id: string;
  name: string;
  artifact_type: 'screenshot' | 'html_snapshot' | 'apk' | 'aab' | 'build_log' | 'report' | 'coverage' | 'test_result' | 'email_sent' | 'file';
  path: string;
  size_bytes: number;
  checksum: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

// ── Workflows (legacy — prefer WorkflowSummary / WorkflowDetail) ──────────

export interface Workflow {
  workflow_id: string;
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'COMPENSATING' | 'COMPENSATED';
  goal?: string;
  current_step?: string;
  progress?: number;
  created_at: string;
  updated_at?: string;
}

// ── WebSocket Events ──────────────────────────────────────────────────────

export interface ActivityUpdatedEvent {
  event: 'activity_updated';
  activity_id: string;
  node_id?: string;
  status: string;
  progress?: number;
  timestamp: string;
}

export interface ActivityCompletedEvent {
  event: 'activity_completed';
  activity_id: string;
  status: 'COMPLETED' | 'FAILED' | 'CANCELLED';
  error?: string;
  timestamp: string;
}

export interface ActivityResumedEvent {
  event: 'activity_resumed';
  activity_id: string;
  node_id: string;
  status: 'RUNNING';
  timestamp: string;
}

// ─── Schedule Events ────────────────────────────────────────────────────

export interface ScheduleTriggeredEvent {
  event: 'schedule_triggered';
  schedule_id: string;
  activity_id?: string;
  workflow_id?: string;
  timestamp: string;
}

export interface ScheduleFailedEvent {
  event: 'schedule_failed';
  schedule_id: string;
  error: string;
  timestamp: string;
}

export type ActivityEvent =
  | ActivityUpdatedEvent
  | ActivityCompletedEvent
  | ActivityResumedEvent
  | ScheduleTriggeredEvent
  | ScheduleFailedEvent
  | { event: 'subscribed'; activity_id: string };

// ─── Artifact Responses ────────────────────────────────────────────────────

export interface ArtifactListResponse {
  artifacts: Artifact[];
  total: number;
  offset: number;
  limit: number;
}

export interface ArtifactSearchResponse {
  artifacts: Artifact[];
  total: number;
}

// ─── Workflow Responses ───────────────────────────────────────────────────

export interface WorkflowListResponse {
  workflows: WorkflowSummary[];
  total: number;
}

export interface WorkflowSummary {
  workflow_id: string;
  workflow_type: string;
  status: string;
  current_step: number;
  total_steps: number;
  progress: string;
  created_at: string | null;
  updated_at: string | null;
  owner: string;
  artifacts: unknown[];
}

export interface WorkflowDetail extends WorkflowSummary {
  steps: WorkflowStepDetail[];
  last_heartbeat: string | null;
  session_id: string;
  timeout_seconds: number | null;
  retry_count: number;
  retry_budget: number;
  parent_workflow_id: string | null;
  execution_context: Record<string, unknown>;
}

export interface WorkflowStepDetail {
  step_id: string;
  tool_name: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  retry_count: number;
}

// ─── Schedules ─────────────────────────────────────────────────────────────

export interface Schedule {
  id: string;
  name: string;
  activity_id?: string;
  workflow_id?: string;
  cron?: string;
  interval_seconds?: number;
  next_run_at?: string;
  last_run_at?: string;
  status: 'active' | 'paused' | 'completed' | 'failed';
  created_at?: string;
}

export interface ScheduleListResponse {
  schedules: Schedule[];
  total: number;
}

// ─── API Response Wrappers ────────────────────────────────────────────────

export interface ListResponse<T> {
  activities?: T[];
  nodes?: T[];
  results?: T[];
  timeline?: T[];
}
