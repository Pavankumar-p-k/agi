"""
Module: core.planner.__init__
Planner subsystem re-exports.
"""
from __future__ import annotations
from typing import Any
import logging

logger = logging.getLogger(__name__)

from core.planner.classifier import classify, extract_parameters
from core.planner.decomposer import GoalDecomposer
from core.planner.evidence import (
    FailureEvidence,
    PlannerEvidence,
    ReplanEvidence,
    StrategyComparisonEvidence,
    VerificationEvidence,
    EvidenceSource,
)
from core.planner.executor import PlannerExecutor, ExecutionResult, ExecutionMode
from core.planner.health import PlannerHealth, PlannerHealthReport, PlannerAvailability
from core.planner.outcomes import (
    PlannerOutcome,
    determine_outcome,
)
from core.planner.protocol import Plan, PlanStatus
from core.planner.replan import (
    ReplanDecision,
    Replanner,
    RevisedPlan,
)
from core.planner.state_machine import (
    PlannerStateMachine,
    PlannerStateName,
)
from core.planner.strategies import (
    Strategy,
    StrategyRegistry,
    StrategyStatus,
)
from core.planner.models import ExecutionPlan, SubGoal
from core.planner.templates import TEMPLATES, get_template, list_templates, match_required_tools