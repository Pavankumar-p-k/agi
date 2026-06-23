# JARVIS Architecture Decisions

> Major architectural principles discovered during development.
> These explain *why* the architecture looks the way it does.

---

## 1. Planner Authority > Model Size

The single highest-leverage architectural finding. A weak planner with enforcement authority outperforms a strong model without it.

**Before:** LLM decides what to do. Model may or may not execute. 50% benchmark pass rate on qwen2.5:7b.

**After:** Planner decides what to do. LLM fills parameters. Executor runs. 100% pass rate on the same model.

**Principle:** Never let the LLM veto a required workflow step. Own the sequence architecturally; delegate only parameterization.

---

## 2. Confidence Must Be Decomposed

A single confidence score hides too much. The formula evolved through five phases:

- **Phase 12:** Single confidence score
- **Phase 16:** `source_quality × evidence_strength × prediction_accuracy × freshness × consensus`
- **Phase 17:** 5-dimensional opportunity scoring: `impact × headroom × success_probability × confidence × calibration_accuracy`
- **Phase 19:** 6-dimensional: added `unlock_value`
- **Phase 20:** Edge confidence now includes `lift` (statistical signal vs noise)

**Principle:** Every subsystem that produces a score must expose the dimensions that produced it. Composite scores are for ranking; decomposed scores are for debugging.

---

## 3. Learned Graph Edges Require Statistical Promotion

A mined edge `A → B` is not a fact. It is a hypothesis. Phase 20 enforces three gates before admitting an edge:

- `support ≥ 5` — enough observations
- `confidence ≥ 0.6` — strong conditional probability
- `lift ≥ 1.2` — better than random

Without lift as a gate, high-frequency nodes (like `long_term_memory`, which appears in every activity) would create spurious edges to everything.

**Principle:** Default edges bootstrap the graph. Learned edges replace them only when statistics exceed the default's confidence. The graph converges toward empirical truth without ever being empty.

---

## 4. Self-Modification Must Be Reversible

Phase 18's strongest design choice was mandatory snapshot-before-write. Every modification creates a `ModificationRollbackSnapshot` that can restore the original file byte-for-byte.

**Principle:** If the system cannot undo a change, it should not make that change. Rollback from a promoted state (Phase 18.1) is the acceptable gap — but even that is constrained to recipe-based modifications, not arbitrary rewrites.

---

## 5. Opportunity Value Must Include Unlock Value

A standalone improvement of 0.8 that unlocks nothing is less valuable than an improvement of 0.5 that unlocks four future improvements worth 2.0 combined.

Phase 19 formalized this as `compounded_score = base_score × unlock_value`, where `unlock_value` is computed via forward BFS reachability with `0.5^(depth-1)` discount.

**Principle:** Local optimization (pick the highest-scored opportunity) is strictly worse than graph optimization (pick the opportunity that maximizes future leverage). The graph is the optimizer's state, not the scoring function.

---

## 6. Principle Discovery Requires Causal Filtering

Phase 14's validator gates (sample size, domain diversity, support rate, discrimination, confidence) prevent the system from mistaking correlation for causation. The critical gate is `lift`—a property must meaningfully separate successful from unsuccessful outcomes.

**Without causal filtering:** The system learns "systems with `retry_capable=true` succeed more often" and promotes it universally.

**With causal filtering:** The system learns "`retry_capable` predicts success in build domains (discrimination=0.33, confidence=0.89)" but does not promote it to domains without evidence.

**Principle:** A principle without a confidence interval and discrimination score is not a principle — it is an opinion.

---

## 7. Feedback Loops Must Be Closed in the Infrastructure, Not the Model

Every loop in the architecture (learning, improvement, strategy, self-modification) is closed by deterministic infrastructure, not by LLM reasoning. The model participates in parameterization; the infrastructure owns the decision.

- **Learning loop:** ExperienceExtractor → KnowledgeSynthesizer → Consolidator (deterministic)
- **Improvement loop:** Detector → ProposalEngine → ExperimentRunner → SafePromotion (deterministic)
- **Self-modification loop:** Planner → Executor → Safety gates → Rollback (deterministic)

**Principle:** Any loop that depends on the model to decide whether to close will eventually fail to close. The infrastructure must guarantee loop closure; the model only influences loop quality.

---

## 8. Bottleneck Analysis Must Be Graph-Propagated, Not Local

Phase 17's bottleneck discovery looked at per-tool failure rates. Phase 22 changed this to graph propagation: a subsystem with moderate local impact but high centrality (many downstream dependents) can be a more valuable improvement target than a severely broken subsystem with no dependents.

The algorithm: `total_constrained_value = local_impact + propagated_impact`, where propagated impact is the sum of downstream local impacts weighted by path confidence and depth discount.

**Principle:** A bottleneck is not defined by how broken a subsystem is. It is defined by how much downstream damage that brokenness causes.

---

## 9. Roadmaps Are a Scheduling Problem Over a Learned Graph

Phase 23 does not use AI to generate roadmaps. It uses topological sort over the learned dependency graph, weighted by compounded priority and bottleneck impact. The output is deterministic and explainable.

**Principle:** Roadmap generation is a scheduling/portfolio problem on a learned graph, not a creative planning problem. The creativity is in the graph; the planning is in the sort.

---

## 10. Forecasting Is the Last Architecture Gap Because It Requires Everything Else

Phase 21 remains unimplemented because forecasting quality depends on:
- Maturity curves from belief quality (Phase 16)
- Improvement velocity from historical data
- Bottleneck propagation (Phase 22)
- Roadmap structure (Phase 23)

Attempting forecasting before these existed would produce trend extrapolation, not causal forecasting.

**Principle:** Forecasting is the ceiling of an autonomous improvement architecture. Build the backward-looking and present-state systems first. Only then does forward-looking prediction become tractable.
