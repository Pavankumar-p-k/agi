"""Phase 15.2 — Resource-Constrained Strategic Reasoning Layer.

Phase 15.1:
    Proposals + Goals + State → Candidate Strategies → Outcome Prediction
    → Tradeoff Analysis → Utility Scoring → Strategic Decision → Execution → Outcome → Learning

Phase 15.2:
    ↓ + Resource Budget → Portfolio Optimizer → Selected (execute now) + Deferred (queue later)

This answers:
    "Which improvements should I make, given I have limited time/resources?"

Components:
    models.py        — StrategyCandidate, TradeoffAnalysis, StrategicDecision,
                       ResourceBudget, PortfolioAllocation
    planner.py       — Generates candidate strategies from proposals
    predictor.py     — Predicts time horizons and improvement ranges
    tradeoffs.py     — Multi-attribute utility analysis with opportunity cost
    evaluator.py     — Sorts candidates by net utility
    selector.py      — Selects best strategy with rationale
    executor.py      — Bridges decision → ProposalExecutor (closed-loop execution)
    portfolio.py     — Resource-constrained knapsack optimization
    memory_adapter.py— Queries PrincipleStore for open proposals
"""

from core.strategy_v2.executor import StrategyExecutor
from core.strategy_v2.evaluator import StrategicEvaluator
from core.strategy_v2.memory_adapter import StrategyMemoryAdapter
from core.strategy_v2.models import (
    ImpactDimension,
    PortfolioAllocation,
    ResourceBudget,
    StrategicDecision,
    StrategyCandidate,
    StrategyStatus,
    TimeHorizon,
    TradeoffAnalysis,
)
from core.strategy_v2.planner import StrategicPlanner
from core.strategy_v2.portfolio import PortfolioOptimizer
from core.strategy_v2.predictor import OutcomePredictor
from core.strategy_v2.selector import StrategicSelector
from core.strategy_v2.tradeoffs import TradeoffEngine

__all__ = [
    "StrategicPlanner",
    "OutcomePredictor",
    "TradeoffEngine",
    "StrategicEvaluator",
    "StrategicSelector",
    "StrategyExecutor",
    "PortfolioOptimizer",
    "StrategyMemoryAdapter",
    "StrategyCandidate",
    "TradeoffAnalysis",
    "StrategicDecision",
    "ResourceBudget",
    "PortfolioAllocation",
    "TimeHorizon",
    "ImpactDimension",
    "StrategyStatus",
]
