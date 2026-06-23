"""Opportunity Discovery Engine (Phase 17.0) — Calibration Integration (Phase 17.1).

Answers: "What should JARVIS improve next?"

Scans four sources to generate improvement opportunities:

  1. Bottleneck Discovery — find tools/systems with low success rates
  2. Ceiling Analysis — compare current vs theoretical capability ceiling
  3. Experiment History — find successful patterns to extend
  4. Principle-Driven Discovery — apply accepted principles to systems
     lacking recommended properties

Each opportunity is scored with a 5-dimensional product formula:

    opportunity_score = impact × headroom × success_probability
                      × confidence × calibration_accuracy

The 5th dimension (calibration_accuracy) comes from tracking predicted vs
actual improvement per discovery source, closing the feedback loop:

    Discover → Predict → Execute → Measure → Learn → Calibrate

All calibration is backward compatible — no calibrator = neutral 1.0.
"""

from core.opportunity.calibration import OpportunityCalibrator
from core.opportunity.engine import OpportunityDiscoveryEngine, DEFAULT_SYSTEM_SCORES
from core.opportunity.models import (
    Opportunity,
    OpportunitySource,
    OpportunityStatus,
)
from core.opportunity.store import OpportunityRecord, OpportunityStore

__all__ = [
    "DEFAULT_SYSTEM_SCORES",
    "Opportunity",
    "OpportunityCalibrator",
    "OpportunityDiscoveryEngine",
    "OpportunityRecord",
    "OpportunitySource",
    "OpportunityStatus",
    "OpportunityStore",
]
