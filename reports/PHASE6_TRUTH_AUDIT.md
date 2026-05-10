# PHASE6 TRUTH AUDIT

Generated: 2026-05-04T07:40:47.383646+00:00

## Scope
- `jarvis_os`
- `brain`
- `runtime`
- `governance`
- `autonomy`

Files scanned: `153`

## Theater Findings
- autonomy/l2_assistant/assistant_engine.py: contains theater token
- governance/MetaGovernor.py: contains theater token
- jarvis_os/control_plane/scheduler.py: contains theater token
- jarvis_os/daemon/supervisor.py: contains theater token
- jarvis_os/memory/vector_store.py: contains theater token
- jarvis_os/self_improvement.py: contains theater token

## Weak Governance Findings
- None

## Parse Errors
- runtime/ModelRuntimeManager.py:90:expected 'except' or 'finally' block
