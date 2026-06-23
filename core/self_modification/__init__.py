"""Self-Modification Engine (Phase 18.0).

Bridges the gap between "what should we improve?" (Phase 17) and
"can we safely change ourselves?" — completing the autonomy loop.

  Principle
      ↓
  Proposal (Phase 14/15)
      ↓
  Patch Plan (Phase 18 — planner)
      ↓
  Apply (Phase 18 — executor)
      ↓
  Test (Phase 18 — safety)
      ↓
  Measure (Phase 18 — metrics)
      ↓
  Promote / Rollback (Phase 18 — executor)
      ↓
  Record (Phase 18 — store)

Constraint: Only predefined recipes. No arbitrary code generation.

Recipes (6):
  - add_retry_loop       — wrap tool in retry logic
  - add_verification_step — add post-execution check
  - increase_timeout     — bump timeout values
  - enable_failure_memory — wire PatternFailureMemory
  - add_calibration_hook — add prediction tracking
  - promote_property     — set registry property (no code change)
"""

from core.self_modification.executor import SelfModificationExecutor
from core.self_modification.models import (
    ModificationMetrics,
    ModificationPlan,
    ModificationRecipe,
    ModificationRecord,
    ModificationStatus,
    ModificationTarget,
)
from core.self_modification.planner import SelfModificationPlanner
from core.self_modification.recipes import (
    apply_recipe,
    get_recipe,
    get_registered_recipes,
    register_recipe,
)
from core.self_modification.safety import (
    SelfModificationSafety,
    DEFAULT_MIN_CONFIDENCE,
    DEFAULT_MIN_IMPROVEMENT,
)
from core.self_modification.store import ModificationStore

__all__ = [
    "DEFAULT_MIN_CONFIDENCE",
    "DEFAULT_MIN_IMPROVEMENT",
    "ModificationMetrics",
    "ModificationPlan",
    "ModificationRecipe",
    "ModificationRecord",
    "ModificationStatus",
    "ModificationStore",
    "ModificationTarget",
    "SelfModificationExecutor",
    "SelfModificationPlanner",
    "SelfModificationSafety",
    "apply_recipe",
    "get_recipe",
    "get_registered_recipes",
    "register_recipe",
]
