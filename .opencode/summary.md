## Context
Precision Provider Router — deterministic evidence-based capability routing through ProviderRouter + ProviderMemory, with time-decay-weighted Bayesian scoring and confidence-gated exploration.

## Goal
Complete the capability layer so every execution path enters through a uniform evidence-based provider router. ProviderMemory is a learning evidence service that adapts scoring to new data (time-decay) and balances exploration vs exploitation (confidence-gated).

## Constraints & Preferences
- ProviderRouter weights are configurable for self-improvement tuning
- Backward compatible: all existing tests pass
- EvidenceRecord uses Bayesian Beta-Binomial posterior (10th percentile lower bound)
- Time decay: exponential half-life (30 days), rolling execution log (200 entries), effective sample size via Kish's formula
- Exploration: greedy at confidence>0.95, epsilon-greedy (10%) at <0.60, active explore (30%) at <0.30

## Progress
### Done
- **Phase 2A**: ProviderRouter `_score()` evaluates 8 dimensions against configurable weights (historical_success 0.20, benchmark_quality 0.15, health 0.15, latency 0.15, cost 0.10, budget 0.10, offline_availability 0.05, priority 0.10)
- **Phase 2B**: MessagingProvider wraps MCP email + channels/controller (Telegram/Slack/Discord)
- **Phase 2C**: DeploymentProvider wraps Docker, git, Vercel, Railway, Netlify
- **EvidenceRecord**: Bayesian Beta-Binomial scoring, failure-reason histogram, rolling execution log with exponential time decay (half-life 30 days, 200 entry cap), Kish's effective sample size, `_weighted_counts()` for time-decayed posterior
- **Confidence-gated exploration** in `ProviderRouter.select()`: confidence>0.95 greedy, <0.60 epsilon-greedy (10% pick second-ranked), <0.30 active explore (30% pick from top 3), `len(scored)<2` always greedy
- **Scoring**: historical_success dimension uses `get_performance_score()` (Bayesian conservative lower bound); ScoreBreakdown extended with health/latency/cost/budget/offline fields
- **Dev**: 248 tests, 0 warnings

### In Progress
- (none)

### Blocked
- (none)

## Next Steps
1. Benchmark integration — feed benchmark results into the same EvidenceRecord model
2. Online recalibration — background recomputation of aggregate scores and confidence intervals
3. Multi-model benchmark to confirm model-independent exploration behavior

## Critical Context
- 248 provider tests pass, 0 warnings
- Evidence key fallback: `(pid,cap,task_type,model,lang)` → `(pid,cap,"","","")` → `(pid,"","","","")`
- Time decay constants: `DECAY_HALF_LIFE_DAYS=30`, `MAX_EXECUTION_LOG=200`
- Exploration: `random.seed(42)` in tests for deterministic greedy behavior
- Architecture maturity: Planner ✅, Decision Engine ✅, Capability Registry ✅, Provider Adapters ✅ (6/6), Provider Router ✅ (evidence-based + exploration), Provider Memory ✅ (learning-based + time-decay), Workflow Engine ✅, Activity Graph ✅, Learning Loop ✅, Improvement Loop ✅

## Relevant Files
- `core/providers/router.py`: MODIFIED — confidence-gated exploration in `select()`
- `core/providers/memory.py`: MODIFIED — `EvidenceRecord._execution_log`, `_weighted_counts()`, Kish's `effective_sample_size`, time-decayed `_recompute_posterior()`
- `tests/unit/test_provider_ecosystem.py`: MODIFIED — 6 new tests (execution_log_sized, time_decay_weights_recent, time_decay_ages_old_entries, confidence_scales_with_evidence, exploration_high_confidence_greedy, exploration_low_confidence_epsilon_greedy)
