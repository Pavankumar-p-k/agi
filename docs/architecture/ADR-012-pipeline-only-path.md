# ADR-012: Canonical Pipeline as the Sole Request Path

**Status:** Accepted (previously ADR-007, now expanded with implementation detail)  
**Date:** 2026-07-09  
**Phase:** 2  

## Context

The REQUEST_PIPELINE_AUDIT identified two parallel request-processing architectures:

1. **Canonical pipeline** (19 stages): primary, well-structured, used by HTTP and some MCP paths
2. **RuntimePipeline** (legacy, 10 phases): deprecated but still functional, used by CLI, daemon, WebSocket, and some internal callers

The RuntimePipeline has no RateLimitStage, no CapabilitySelectionStage, and a different error-handling model. Bugs fixed in the canonical pipeline reappear in RuntimePipeline. Development effort is split between two paths.

The EXECUTION_ARCHITECTURE_AUDIT confirmed that `core/tools/execution.py` (3,024 lines) is the execution backbone for both pipelines, but the entry points and stage processing differ.

## Decision

**The 19-stage canonical pipeline is the single request-processing path for all entry points.**

1. All entry points (HTTP, WebSocket, MCP, CLI, daemon, internal calls) must go through `Pipeline.execute()`.
2. The `RuntimePipeline` class and its 10-phase state machine are removed after all callers are migrated.
3. Code paths that directly call execution stages (e.g., `execute_tool_block()` from non-pipeline code) must be refactored to go through the pipeline.
4. The pipeline entry adapter pattern (`core/entry/manager.py`) is used to normalize different transport protocols into `PipelineContext`.

## Consequences

**Positive:**
- Single code path for all requests — bugs fixed once, security enforced once
- Rate limiting, auth, capability selection, and memory storage apply uniformly
- Reduces maintenance burden by ~10% (one pipeline vs two)

**Negative:**
- Migration requires auditing every caller of RuntimePipeline and every bypass of the canonical pipeline
- Some internal callers (e.g., control_loop.py) may see latency increase from going through all 19 stages — short-circuit paths may be needed for stage subsets
- CLI and daemon entry points must be refactored to build PipelineContext from stdin/env instead of HTTP request data
