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

// ─── Knowledge Store ───────────────────────────────────────────────────────

export interface KnowledgeItem {
  knowledge_id: string;
  category: 'pattern' | 'principle' | 'heuristic' | 'factoid' | 'warning';
  claim: string;
  confidence: number;
  evidence_count: number;
  source_activity_ids: string[];
  source_pattern_keys: string[];
  tags: string[];
  created_at: string | null;
  last_validated: string | null;
  metadata: Record<string, unknown>;
}

export interface Experience {
  activity_id: string;
  goal: string;
  domain: string;
  status: string;
  node_count: number;
  agent_ids: string[];
  tools_used: string[];
  artifacts_produced: string[];
  success: boolean;
  error_summary: string | null;
  duration_seconds: number | null;
  outcome_quality: number | null;
  created_at: string | null;
}

export interface KnowledgeStatistics {
  total_knowledge_items: number;
  total_experiences: number;
  knowledge_by_category: Record<string, number>;
  domains: string[];
  total_patterns: number;
  total_failures: number;
}

export interface KnowledgeSearchResponse {
  knowledge: KnowledgeItem[];
  total: number;
  query: string;
}

export interface KnowledgeListResponse {
  knowledge: KnowledgeItem[];
  total: number;
}

export interface ExperienceListResponse {
  experiences: Experience[];
  total: number;
}

export interface PatternEntry {
  pattern: string;
  regex: string;
  count: number;
  first_seen: string;
  last_seen: string;
  exemplar: string;
  best_strategy: string | null;
  strategies: Record<string, { success_count: number; failure_count: number; success_rate: number; last_used: string }>;
}

export interface FailureEntry {
  pattern: string;
  fix_strategy: string;
  count: number;
  last_seen: string;
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

// ─── Research Memory ───────────────────────────────────────────────────────

export interface ResearchFact {
  fact_id: string;
  source_url: string;
  claim: string;
  confidence: number;
  category: string;
  tags: string[];
  timestamp: string | null;
  activity_id: string | null;
  node_id: string | null;
  metadata: Record<string, unknown>;
}

export interface ResearchSession {
  activity_id: string;
  fact_count: number;
  sources: string[];
  categories: string[];
  avg_confidence: number;
  first_fact_at: string | null;
  last_fact_at: string | null;
}

export interface ResearchContradiction {
  entity: string;
  attribute: string;
  values: string[];
  sources: string[];
  confidence: number;
  summary: string;
}

export interface ResearchAgreement {
  entity: string;
  attribute: string;
  value: string;
  sources: string[];
  confidence: number;
  summary: string;
}

export interface ResearchSessionDetail {
  session: ResearchSession;
  facts: ResearchFact[];
  contradictions: ResearchContradiction[];
  agreements: ResearchAgreement[];
  syntheses: string[];
}

export interface ResearchStatistics {
  total_facts: number;
  fact_count_by_category: Record<string, number>;
  fact_count_by_source: Record<string, number>;
  total_sessions: number;
}

export interface ResearchFactListResponse {
  facts: ResearchFact[];
  total: number;
}

export interface ResearchSessionListResponse {
  sessions: ResearchSession[];
  total: number;
}

export interface ResearchSearchResponse {
  facts: ResearchFact[];
  total: number;
  query: string;
}

export interface ResearchContradictionsResponse {
  contradictions: ResearchContradiction[];
  total: number;
}

// ─── Planner / Plan ─────────────────────────────────────────────────────────

export interface PlanNode {
  id: string;
  title: string;
  description: string;
  assigned_agent: string | null;
  estimated_duration: number | null;
  priority: number;
  status: string;
  children: PlanNode[];
}

export interface Plan {
  id: string;
  goal: string;
  status: 'draft' | 'approved' | 'rejected' | 'executing' | 'completed' | 'failed';
  root_node: PlanNode;
  created_at: string;
  updated_at: string;
}

export interface PlanListResponse {
  plans: Plan[];
  total: number;
}

// ─── Plan Evidence ──────────────────────────────────────────────────────────

export interface EvidenceItem {
  type: string;
  id: string;
  summary: string;
  relevance?: number;
  success?: boolean;
  duration?: number | null;
  confidence?: number;
  evidence_count?: number;
}

export interface RiskItem {
  severity: 'critical' | 'warning' | 'info';
  type: string;
  detail?: string;
  pattern?: string;
  success_rate?: number;
  strategy?: string;
}

export interface AlternativeItem {
  approach: string;
  description: string;
  pros: string[];
  cons: string[];
}

export interface NodeEvidence {
  node_id: string;
  title: string;
  confidence: number;
  evidence: EvidenceItem[];
  evidence_count: number;
  risks: RiskItem[];
  risk_count: number;
}

export interface PlanEvidence {
  plan_id: string;
  overall: {
    confidence: number;
    total_nodes: number;
    total_evidence: number;
    total_risks: number;
    nodes_with_risks: number;
    critical_risks: number;
    warning_risks: number;
  };
  nodes: NodeEvidence[];
}

export interface PlanRisks {
  plan_id: string;
  total_risks: number;
  risks: (RiskItem & { node_id: string })[];
  critical_count: number;
  warning_count: number;
  info_count: number;
}

export interface PlanAlternatives {
  plan_id: string;
  total_alternatives: number;
  nodes: {
    node_id: string;
    node_title: string;
    alternatives: AlternativeItem[];
  }[];
}

export interface PlanConfidence {
  plan_id: string;
  overall: {
    confidence: number;
    total_nodes: number;
    total_evidence: number;
    total_risks: number;
    nodes_with_risks: number;
    critical_risks: number;
    warning_risks: number;
  };
  nodes: {
    node_id: string;
    confidence: number;
    evidence_count: number;
    risk_count: number;
  }[];
}

// ─── Plan Comparison ────────────────────────────────────────────────────────

export interface PlanCandidate {
  strategy_key: string;
  strategy_label: string;
  strategy_description: string;
  overall_score: number;
  dimensions: {
    confidence: number;
    historical_success: number;
    duration: number;
    risk: number;
    evidence_strength: number;
  };
  estimated_duration_days: number;
  estimated_cost: 'low' | 'medium' | 'high';
  total_nodes: number;
  total_evidence: number;
  total_risks: number;
  critical_risks: number;
  warning_risks: number;
  pros: string[];
  cons: string[];
  root_node: PlanNode;
}

export interface PlanComparison {
  goal: string;
  total_candidates: number;
  candidates: PlanCandidate[];
  recommended: {
    strategy_key: string;
    strategy_label: string;
    overall_score: number;
    reasoning: string;
  } | null;
}

// ─── Plan Outcome & Prediction ─────────────────────────────────────────────

export interface PlanOutcome {
  plan_id: string;
  predicted_confidence: number;
  predicted_success_rate: number;
  predicted_duration_days: number;
  predicted_risk_score: number;
  predicted_cost: string;
  actual_success: boolean | null;
  actual_duration_seconds: number | null;
  actual_failures: number | null;
  actual_cost: string | null;
  executed_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PlanPrediction {
  plan_id: string;
  predicted_confidence: number;
  predicted_success_rate: number;
  predicted_duration_days: number;
  predicted_risk_score: number;
  predicted_cost: string;
  executed_at: string | null;
  completed_at: string | null;
}

export interface PlanAccuracy {
  plan_id: string;
  has_actuals: boolean;
  dimensions: Record<string, {
    predicted?: unknown;
    actual?: unknown;
    correct?: boolean;
    score: number;
    [key: string]: unknown;
  }>;
  overall_accuracy: number;
}

// ── Plan Health & Replan ──────────────────────────────────────────────────

export interface PlanHealthSignal {
  name: string;
  label: string;
  value: number | null;
  baseline: number;
  delta: number;
  weight_multiplier: number;
  detail: string;
}

export interface PlanHealth {
  plan_id: string;
  health_score: number;
  status: 'healthy' | 'watch' | 'replan_recommended' | 'replan_required' | 'unknown';
  signals: PlanHealthSignal[];
  weights: Record<string, number>;
  evaluated_at: string;
}

export interface ReplanOptionDelta {
  overall_change: number;
  score_change: number;
  confidence_change: number;
  expected_improvements: string[];
}

export interface ReplanOption {
  strategy: string;
  description: string;
  pros: string[];
  cons: string[];
  score: number;
  delta: ReplanOptionDelta;
}

export interface ReplanOptions {
  plan_id: string;
  goal: string;
  current_strategy: string;
  current_score: number;
  current_health: string;
  health_score: number;
  options: ReplanOption[];
  option_count: number;
  evaluated_at: string;
}

export interface AutoReplanResult {
  status: string;
  action: string;
  strategy?: string;
  expected_improvement?: ReplanOptionDelta;
  plan?: Plan;
  health?: PlanHealth;
  health_before?: PlanHealth;
  message?: string;
}

// ── Analytics & Performance ──────────────────────────────────────────────

export interface StrategyWinRate {
  strategy: string;
  total: number;
  successful: number;
  failed: number;
  win_rate: number;
}

export interface AccuracyTrendPoint {
  plan_id: string;
  accuracy: number;
  completed_at: string;
}

export interface AccuracyTrend {
  direction: string;
  early_avg: number;
  recent_avg: number;
  recent: AccuracyTrendPoint[];
}

export interface CalibrationBucket {
  bucket: string;
  total: number;
  predicted_center: number;
  actual_success_rate: number;
  error: number;
}

export interface ConfidenceCalibration {
  status: string;
  avg_calibration_error: number | null;
  buckets: CalibrationBucket[];
}

export interface DurationAccuracy {
  status: string;
  avg_duration_error: number;
  plans_with_duration_data: number;
  significantly_wrong: number;
}

export interface RiskAccuracy {
  high_risk_plans: number;
  low_risk_plans: number;
  high_risk_failure_rate: number;
  low_risk_failure_rate: number;
  risk_discrimination: number;
  discrimination_quality: string;
}

export interface ReplanMetrics {
  total_plans: number;
  replanned_count: number;
  replan_rate: number;
  improved_after_replan: number;
  avg_replans_per_plan: number;
}

export interface FailurePattern {
  plan_id: string;
  predicted_confidence: number;
  predicted_risk: number;
  predicted_duration_days: number;
  actual_failures: number;
  reasons: string[];
}

export interface FailureAnalysis {
  total_failures: number;
  patterns: FailurePattern[];
  common_reasons: { reason: string; count: number }[];
}

export interface OverallPlannerPerformance {
  total_plans: number;
  completed_plans: number;
  successful: number;
  failed: number;
  success_rate: number;
  avg_prediction_accuracy: number | null;
}

export interface PlannerPerformance {
  overall: OverallPlannerPerformance;
  strategy_win_rates: StrategyWinRate[];
  accuracy_trend: AccuracyTrend;
  confidence_calibration: ConfidenceCalibration;
  duration_accuracy: DurationAccuracy;
  risk_accuracy: RiskAccuracy;
  replan_metrics: ReplanMetrics;
  failure_analysis: FailureAnalysis;
  computed_at: string;
}

// ── Improvement System ──────────────────────────────────────────────────

export interface ImprovementOpportunity {
  id: string;
  type: string;
  strategy: string | null;
  description: string;
  current_value: number;
  target_value: number;
  expected_gain: number;
  impact: string;
  recommended_action: string;
  recommended_change: string;
  evidence: string;
  detected_at: string;
  status: string;
}

export interface PlannerExperiment {
  id: string;
  opportunity_id: string;
  title: string;
  description: string;
  type: string;
  status: string;
  config_before: Record<string, unknown> | null;
  config_after: Record<string, unknown> | null;
  metrics_before: Record<string, unknown> | null;
  metrics_after: Record<string, unknown> | null;
  result: { overall?: string; changes?: Record<string, number>; improved?: boolean; } | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

// ── Negotiation System ──────────────────────────────────────────────────

export interface AgentOpinion {
  agent_name: string;
  position: string;
  confidence: number;
  reasoning: string;
  evidence_sources: string[];
  metadata: Record<string, unknown>;
}

export interface ConsensusResult {
  decision: string;
  confidence: number;
  reasoning: string;
  dissent: string[];
  individual_scores: Record<string, number>;
}

export interface NegotiationSession {
  id: string;
  goal: string;
  status: string;
  opinions: AgentOpinion[];
  consensus: ConsensusResult;
  created_at: string;
  resolved_at: string | null;
}

// ── Opportunity Discovery System ───────────────────────────────────────────

export interface Opportunity {
  id: string;
  target_system: string;
  improvement_description: string;
  source: string;
  bottleneck_impact: number;
  improvement_headroom: number;
  success_probability: number;
  confidence: number;
  calibration_accuracy: number;
  opportunity_score: number;
  rationale: string;
  evidence: string[];
  status: string;
  created_at: string | null;
}

export interface RoadmapPhase {
  name: string;
  item_count: number;
  total_priority: number;
  items: RoadmapItem[];
  rationale: string;
}

export interface RoadmapItem {
  system: string;
  priority: number;
  depth: number;
  dependencies: string[];
  unlocks: string[];
  current_score: number;
  expected_gain: number;
  rationale: string;
}

export interface Bottleneck {
  subsystem: string;
  local_impact: number;
  propagated_impact: number;
  total_constrained_value: number;
  confidence: number;
  affected_systems: string[];
}

export interface ForecastedOpportunity {
  system: string;
  current_score: number;
  predicted_score: number;
  confidence: number;
  horizon: string;
  trend: string;
  velocity: number;
  unlock_value: number;
  bottleneck_pressure: number;
  rationale: string;
}

export interface GraphNode {
  system_name: string;
  base_score: number;
  unlock_value: number;
  compounded_score: number;
  has_opportunity: boolean;
}

export interface GraphEdge {
  source: string;
  target: string;
  confidence: number;
  source_type: string;
}

export interface OpportunityGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

// ─── API Response Wrappers ────────────────────────────────────────────────

export interface ListResponse<T> {
  activities?: T[];
  nodes?: T[];
  results?: T[];
  timeline?: T[];
}
