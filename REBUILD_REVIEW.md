# Rebuild Review Request

**Status: implemented, awaiting human review.**
**Reviewer: Pavankumar (repo owner)** — assigned 2026-10-10.

## Scope under review

Commits `46d080a..712aa4f` (7 commits):

| commit | contents |
|---|---|
| `46d080a` | execution: rebuild ExecutionContext (mutable, request_id, stable event timestamp) |
| `5df0204` | execution: rebuild ExecutionManager (engine lifecycle, events, memory recording) |
| `10e4125` | tools: implementations (search/api/browser delegates) + email_utils |
| `b911cee` | tools: cluster 4 — artifact helpers, two-gate RBAC, browser session gate, MCP 2-arg call_tool |
| `cf791ad` | workflow: long_horizon_fsm (state machine, phase validation, loop/timeout guards) |
| `7802267` | architecture: memory facade via `memory` package import, RBAC via `security.authorize_tool_scope` (audit Rules 2 + 17) |
| `712aa4f` | architecture: substring collisions (feature_registry dep -> `core.permission`, special_token_filter docstring) |

Later commits `aac471e..6cf00bf` (2026-10-07/08) are from separate sessions and are NOT part of this review request.

## How to verify

```
python -m pytest tests/architecture -q            # audit rules green
python jarvis.py doctor                           # source diagnostics OK
python scripts/count_stubs.py                     # 5/2580 stubs
python -m pytest tests/unit/test_execution_manager.py tests/unit/test_execution_dispatch.py tests/unit/test_workflow_email.py -q
```

## Review checklist

- [ ] Audit fixes 7802267/712aa4f preserve test contracts (`patch("memory.memory_facade.memory")`, `patch("core.authz.engine.authz_engine.evaluate")`)
- [ ] RBAC path in `core/tools/execution.py` uses `security.authorize_tool_scope` with no restricted substrings
- [ ] No secrets/keys committed
- [ ] Deletions (281 files) remain archived in `rebuild_backlog/`

## Gate

The next priority-list item (`core.browser_manager`) must NOT start until this review is approved.
