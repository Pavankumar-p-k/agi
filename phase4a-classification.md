# Phase 4A: Failure Classification (108 failures)

## Pipeline Reasoning (58 failures)

| Test Class | Count | Root Cause | Category |
|---|---|---|---|
| TestDecisionDataclass | 1 | Decision not imported from pipeline __init__ | Outdated test contract |
| TestReasonerStage | 9 | Tests expect LLM-based reasoning (complexity, requirements, constraints); production ReasonerStage uses PlannerExecutor (goal decomposition) | Outdated test contract |
| TestPlannerStage | 4 | PlannerStage is DynamicStub, no LLM planning impl | Production defect |
| TestPlanValidatorStage | 3 | PlanValidatorStage is DynamicStub | Production defect |
| TestCapabilitySelectionStage | 2 | Intent-to-capability resolution missing certain intents | Production defect (minor) |
| TestEndToEnd | 2 | Full pipeline integration, depends on all stages | Production defect (integration) |
| TestStepExecutor | 2 | Tests `LLMStepExecutor` — obsolete construct | **Obsolete architecture** |
| TestRuntime | 5 | Tests `Runtime` — obsolete construct | **Obsolete architecture** |
| TestExecutionStage | 6 | name property, with_default_providers missing, return type mismatch | Production defect |
| TestVerdict | 3 | Tests `Verdict` dataclass — not in current architecture | **Obsolete architecture** |
| TestSafetyVerifier | 3 | Tests `SafetyVerifier` — verifier pattern not implemented | Production defect |
| TestSchemaVerifier | 4 | Tests `SchemaVerifier` — verifier pattern not implemented | Production defect |
| TestConfidenceVerifier | 3 | Tests `ConfidenceVerifier` — verifier pattern not implemented | Production defect |
| TestVerificationStage | 5 | Tests verifier architecture; production stage uses SPCL-6 outcomes | Outdated test contract |
| TestMemoryStage | 4 | StoreDecision/StoreAction not imported, memory facade unavailable | Production defect (minor) |

**Summary: 10 obsolete, 35 production defects, 13 outdated contracts**

## Tenant Isolation (17 failures)

| Test Class | Count | Root Cause | Category |
|---|---|---|---|
| TestObservationHubTenantIsolation | 2 | ObservationHub not implemented | Production defect |
| TestActivityGraphTenantIsolation | 2 | ActivityNode missing resource_scope field | Production defect |
| TestSchedulerTenantIsolation | 3 | ScheduledActivity missing tenant_id; scheduler routing not impl | Production defect |
| TestMetricsTenantIsolation | 5 | ArchitectureMetrics missing tenant_id, to_dict, from_context | Production defect |
| TestEventBusTenantIsolation | 2 | EventBus publish takes (type,data) not Event; Subscription tenant filter not wired | Production defect (minor) |
| TestStageOwnershipTenant | 1 | TenantResolutionStage not in default pipeline stages | Production defect |
| TestSecurityContextTenant | 2 | SecurityContext not a proper class; security property is dict | Production defect |

**Summary: 0 obsolete, 17 production defects**

## Pipeline Contracts (31 failures)

| Test Name | Root Cause | Category |
|---|---|---|
| test_pipeline_stage_is_abstract | PipelineStage not abstract (no ABCMeta) | Production defect |
| test_process_message_function_exists | process_message returns PipelineContext, not Response | Production defect |
| test_process_message_with_formatter | add_stage chaining OK but FormatterStage missing | Production defect |
| test_process_message_with_error | Same | Production defect |
| test_pipeline_stops_on_fail | Pipeline.execute doesn't set execution_state on context | Production defect |
| test_pipeline_stops_on_short_circuit | Same | Production defect |
| test_pipeline_stops_on_defer | Same | Production defect |
| test_pipeline_merges_stage_metrics | StageResult.metrics not merged into context.metrics | Production defect |
| test_pipeline_without_context_creates_one | Process_message returns PipelineContext not Response with request_id | Production defect |
| test_classify_to_formatter_pipeline | ReceiveStage doesn't set parsed_request; FormatterStage incomplete | Production defect |
| test_receive_stage_parses_input | ReceiveStage doesn't set parsed_request | Production defect |
| test_receive_stage_with_attachments | Same | Production defect |
| test_intent_stage_classifies | IntentStage DynamicStub | Production defect |
| test_intent_stage_empty_input | Same | Production defect |
| test_formatter_stage_builds_response | FormatterStage doesn't set formatted_response | Production defect |
| test_formatter_stage_with_error | Same | Production defect |
| test_metrics_stage_aggregates | MetricsStage DynamicStub | Production defect |
| test_metrics_stage_intelligence_fields | Same | Production defect |
| test_metrics_stage_intelligence_fields_empty | Same | Production defect |
| test_metrics_stage_intelligence_timing | Same | Production defect |
| test_pipeline_retries_on_retry_outcome | No retry logic in Pipeline | Production defect |
| test_pipeline_exhausts_retries | Same | Production defect |
| test_pipeline_retries_on_timeout | Same | Production defect |
| test_pipeline_retries_on_exception | Same | Production defect |
| test_pipeline_exception_exhausts_retries | Same | Production defect |
| test_pipeline_stops_on_cancelled | Cancellation not fully wired | Production defect |
| test_pipeline_external_cancel | Same | Production defect |
| test_process_message_includes_version | process_message returns context not Response | Production defect |
| test_hooks_fire_before_and_after | No hook registry in Pipeline | Production defect |
| test_hook_failure_does_not_crash_pipeline | Same | Production defect |
| test_response_includes_activity_metadata | Same as process_message issue | Production defect |

**Summary: 0 obsolete, 31 production defects**

## Resource Grant (2 failures)

| Test Name | Root Cause | Category |
|---|---|---|
| test_resource_grant_on_context | AuthorizationStage doesn't set resource_grant | Production defect |
| test_resource_grant_in_security_context | security property doesn't include grant correctly | Production defect |

**Summary: 0 obsolete, 2 production defects**

---

## Grand Total

| Category | Count | % |
|---|---|---|
| **Obsolete architecture (Runtime, StepExecutor, Verdict)** | **10** | **9%** |
| **Outdated test contracts** | **13** | **12%** |
| **Production defects** | **85** | **79%** |
| **Total** | **108** | **100%** |
