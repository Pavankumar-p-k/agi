# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
brain/prompt_optimizer.py
Phase 12 — PromptOptimizer

Closes the feedback loop:
  ConstitutionalMemory → FailureAnalyzer → PromptGenerator
  → PromptTester (A/B) → PromptStore → hot-patch AGENT_PROMPTS

Flow:
  DreamingLoop nightly → _step_optimize_prompts()
  → FailureAnalyzer finds top failing criteria per output_type
  → PromptGenerator asks LLM to fix the prompt
  → PromptTester A/B tests old vs new on 5-10 historical queries
  → If new >= +5%: deploy to PromptStore + hot-patch AGENT_PROMPTS

Deployment model:
  Hot-patch at runtime (immediate effect) + persist to disk.
  On restart, lifespan.py loads deployed versions back in.
  24-hour rollback window via /api/system/prompt-rollback/{agent}

Trigger guard:
  Only runs when >= MIN_ENTRIES_PER_TYPE new CM entries since last run.
  Prevents optimizer wasting LLM calls on stale data.

Safety:
  Auto-deploy + rollback endpoint. No manual gate.
  Every change logged to ~/.jarvis/prompt_versions/{agent}/history.json

Dependencies: zero new pip deps.
  sqlite3 (CM DB), brain.reason() (Phase 1), QualityGrader (Phase 5)
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from brain.UnifiedBrain import UnifiedBrain
    from core.quality_grader import QualityGrader, ConstitutionalMemory

logger = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────────────────
MIN_ENTRIES_PER_TYPE  = 50      # minimum new CM entries before optimizing
IMPROVEMENT_THRESHOLD = 0.05    # 5% score gain required to deploy
AB_TEST_QUERIES       = 10      # queries per A/B test
ROLLBACK_WINDOW_HOURS = 24      # hours before a deployed prompt is "locked"
VERSIONS_DIR          = Path.home() / ".jarvis" / "prompt_versions"


# ════════════════════════════════════════════════════════════════════════════
# Dataclasses
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class FailureReport:
    output_type:      str
    total_entries:    int
    new_since_last:   int
    top_failing:      list[dict]   # [{id, description, failure_rate, weight}]
    worst_criterion:  Optional[str] = None   # id of the single worst criterion
    has_enough_data:  bool = False

    def as_prompt_context(self) -> str:
        if not self.top_failing:
            return "No significant failure patterns found."
        lines = [f"Failure analysis for '{self.output_type}' "
                 f"({self.total_entries} total, {self.new_since_last} new):"]
        for c in self.top_failing[:5]:
            lines.append(
                f"  - {c['id']} ({c['description']}): "
                f"{c['failure_rate']:.0%} failure rate (weight {c['weight']})"
            )
        return "\n".join(lines)


@dataclass
class PromptVersion:
    agent:       str
    version:     int
    prompt:      str
    score:       float          # aggregate quality score (0–100)
    deployed:    bool = False
    created_at:  str  = field(default_factory=lambda: datetime.utcnow().isoformat())
    deployed_at: Optional[str] = None
    rollback_of: Optional[int] = None   # set when this is a rollback


@dataclass
class ABTestResult:
    agent:        str
    old_score:    float
    new_score:    float
    improvement:  float    # new - old, normalized 0.0–1.0
    deploy:       bool
    queries_run:  int
    reason:       str      # human-readable decision explanation


# ════════════════════════════════════════════════════════════════════════════
# Component 1 — FailureAnalyzer
# ════════════════════════════════════════════════════════════════════════════

class FailureAnalyzer:
    """
    Queries ConstitutionalMemory SQLite DB.
    Returns FailureReport per output_type.
    """

    def __init__(self, cm_db_path: Path):
        self.db_path = cm_db_path

    def analyze(self,
                output_type: str,
                since: Optional[datetime] = None) -> FailureReport:
        """
        Returns FailureReport. Never raises — returns empty report on any error.
        """
        if not self.db_path.exists():
            logger.debug("CM DB not found at %s", self.db_path)
            return FailureReport(
                output_type=output_type, total_entries=0,
                new_since_last=0, top_failing=[], has_enough_data=False
            )

        try:
            return self._query(output_type, since)
        except Exception as e:
            logger.warning("FailureAnalyzer query failed: %s", e)
            return FailureReport(
                output_type=output_type, total_entries=0,
                new_since_last=0, top_failing=[], has_enough_data=False
            )

    def _query(self, output_type: str,
               since: Optional[datetime]) -> FailureReport:
        with sqlite3.connect(self.db_path) as conn:
            # Total entries for this output_type
            total = conn.execute(
                "SELECT COUNT(*) FROM grade_history WHERE output_type=?",
                (output_type,)
            ).fetchone()[0]

            # New entries since last optimization run
            since_str = (since or datetime.utcnow() - timedelta(days=7)).isoformat()
            new_count = conn.execute(
                "SELECT COUNT(*) FROM grade_history "
                "WHERE output_type=? AND created_at > ?",
                (output_type, since_str)
            ).fetchone()[0]

            if total < MIN_ENTRIES_PER_TYPE:
                return FailureReport(
                    output_type=output_type, total_entries=total,
                    new_since_last=new_count, top_failing=[],
                    has_enough_data=False
                )

            # Failure rate per criterion (over all time)
            rows = conn.execute("""
                SELECT
                    criterion_id,
                    AVG(CASE WHEN passed=0 THEN 1.0 ELSE 0.0 END) AS failure_rate,
                    COUNT(*) AS n
                FROM grade_history
                WHERE output_type=?
                GROUP BY criterion_id
                HAVING n >= 10
                ORDER BY failure_rate DESC
            """, (output_type,)).fetchall()

        # Load constitution to get descriptions + weights
        constitution = self._load_constitution()
        criteria_map = {
            c["id"]: c
            for c in constitution.get(output_type, [])
        }

        top_failing = []
        for cid, failure_rate, n in rows:
            if failure_rate < 0.20:   # ignore criteria passing >80% of time
                continue
            meta = criteria_map.get(cid, {})
            top_failing.append({
                "id":           cid,
                "description":  meta.get("description", cid),
                "failure_rate": failure_rate,
                "weight":       meta.get("weight", 0.0),
                "n":            n,
            })

        worst = top_failing[0]["id"] if top_failing else None

        return FailureReport(
            output_type     = output_type,
            total_entries   = total,
            new_since_last  = new_count,
            top_failing     = top_failing,
            worst_criterion = worst,
            has_enough_data = new_count >= MIN_ENTRIES_PER_TYPE,
        )

    @staticmethod
    def _load_constitution() -> dict:
        path = Path(__file__).parent.parent / "config" / "quality_constitution.json"
        if path.exists():
            try:
                return json.loads(path.read_text())
            except Exception as e:
                logger.exception("[PromptOpt] load_constitution: %s", e)
        return {}


# ════════════════════════════════════════════════════════════════════════════
# Component 2 — PromptGenerator
# ════════════════════════════════════════════════════════════════════════════

class PromptGenerator:
    """
    Takes current prompt + FailureReport.
    Asks LLM to rewrite the prompt to fix the failures.
    Retries once on LLM failure.
    """

    META_SYSTEM_PROMPT = (
        "You are an expert prompt engineer. Your job is to improve AI system prompts "
        "based on empirical failure data.\n\n"
        "Rules:\n"
        "1. Keep the same role and core constraints as the original prompt\n"
        "2. Only change wording that would plausibly cause the reported failures\n"
        "3. Add specific instructions, examples, or constraints to address each failure\n"
        "4. Do not make the prompt longer than 2x the original\n"
        "5. Output ONLY the new system prompt — no explanation, no preamble, "
        "no markdown fences"
    )

    async def generate(self,
                        agent:    str,
                        current:  str,
                        report:   FailureReport,
                        brain:    "UnifiedBrain") -> Optional[str]:
        """
        Returns improved prompt string, or None on failure.
        """
        if not report.top_failing:
            return None

        prompt = (
            f"Original system prompt for agent '{agent}':\n"
            f"---\n{current}\n---\n\n"
            f"{report.as_prompt_context()}\n\n"
            f"Rewrite the system prompt to reduce these failure rates. "
            f"Focus most on: {report.worst_criterion}. "
            f"Output ONLY the new prompt."
        )

        for attempt in range(1, 3):
            try:
                result = await brain.reason(
                    f"{self.META_SYSTEM_PROMPT}\n\n{prompt}"
                )
                new_prompt = result.answer.strip()

                # Basic sanity checks
                if len(new_prompt) < 20:
                    raise ValueError("Generated prompt too short")
                if len(new_prompt) > len(current) * 3:
                    raise ValueError("Generated prompt too long (>3x original)")
                if new_prompt == current:
                    return None   # LLM returned same prompt — no improvement possible

                return new_prompt

            except Exception as e:
                logger.debug("PromptGenerator attempt %d failed: %s", attempt, e)
                if attempt == 1:
                    prompt += "\n\nNote: Keep the output concise and focused."

        return None


# ════════════════════════════════════════════════════════════════════════════
# Component 3 — PromptTester
# ════════════════════════════════════════════════════════════════════════════

class PromptTester:
    """
    A/B test: runs old vs new prompt on historical queries.
    Grades both via QualityGrader.
    Returns ABTestResult with deploy decision.
    """

    # Domain-specific test queries — expand as JARVIS accumulates real queries
    DOMAIN_QUERIES: dict[str, list[str]] = {
        "response": [
            "What is the capital of France?",
            "Explain how a neural network learns",
            "What are the benefits of local AI models?",
            "How do I reverse a list in Python?",
            "Summarize the key principles of clean code",
            "What is the difference between TCP and UDP?",
            "How does gradient descent work?",
            "What is a REST API?",
            "Explain recursion with a simple example",
            "What is the CAP theorem?",
        ],
        "code": [
            "Write a function to check if a string is a palindrome",
            "Implement a binary search algorithm",
            "Write a decorator that logs function calls",
            "Create a simple rate limiter class",
            "Write a function to flatten a nested list",
        ],
        "website": [
            "Generate hero section content for a restaurant called Spice Garden",
            "Write about us text for a digital marketing agency",
            "Create feature cards for a SaaS project management tool",
        ],
        "email": [
            "Write a follow-up email after a job interview",
            "Draft a project status update to stakeholders",
            "Write a polite payment reminder email",
        ],
    }

    async def test(self,
                   agent:      str,
                   old_prompt: str,
                   new_prompt: str,
                   output_type: str,
                   brain:      "UnifiedBrain",
                   grader:     "QualityGrader") -> ABTestResult:
        """
        Runs AB_TEST_QUERIES queries, grades both prompts.
        Returns ABTestResult with deploy=True if new >= +5%.
        """
        queries = self.DOMAIN_QUERIES.get(
            output_type,
            self.DOMAIN_QUERIES["response"]   # fallback to generic queries
        )[:AB_TEST_QUERIES]

        old_scores: list[float] = []
        new_scores: list[float] = []

        for query in queries:
            try:
                old_out = await self._call_with_prompt(brain, old_prompt, query)
                new_out = await self._call_with_prompt(brain, new_prompt, query)

                old_g = await grader.grade(output_type, old_out)
                new_g = await grader.grade(output_type, new_out)

                old_scores.append(old_g.aggregate_score)
                new_scores.append(new_g.aggregate_score)

            except Exception as e:
                logger.debug("A/B test query failed: %s", e)
                continue   # skip failed queries, don't abort test

        if not old_scores:
            return ABTestResult(
                agent=agent, old_score=0, new_score=0,
                improvement=0, deploy=False,
                queries_run=0,
                reason="All test queries failed — keeping current prompt"
            )

        old_mean = sum(old_scores) / len(old_scores)
        new_mean = sum(new_scores) / len(new_scores)
        improvement = (new_mean - old_mean) / 100.0   # normalize to 0.0–1.0

        if improvement >= IMPROVEMENT_THRESHOLD:
            reason = (f"New prompt scores {new_mean:.1f} vs {old_mean:.1f} "
                      f"(+{improvement:.1%} improvement) — deploying")
            deploy = True
        elif abs(improvement) < 0.01:
            reason = (f"No clear winner (old={old_mean:.1f}, new={new_mean:.1f}) "
                      f"— keeping current prompt")
            deploy = False
        else:
            reason = (f"New prompt scores {new_mean:.1f} vs {old_mean:.1f} "
                      f"(+{improvement:.1%}) — below {IMPROVEMENT_THRESHOLD:.0%} threshold")
            deploy = False

        return ABTestResult(
            agent       = agent,
            old_score   = old_mean,
            new_score   = new_mean,
            improvement = improvement,
            deploy      = deploy,
            queries_run = len(old_scores),
            reason      = reason,
        )

    async def _call_with_prompt(self,
                                  brain:  "UnifiedBrain",
                                  system: str,
                                  user:   str) -> str:
        """Direct LLM call with specific system prompt."""
        from core.llm_router import complete
        result = await complete("chat", [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])
        return result.unwrap_or("")


# ════════════════════════════════════════════════════════════════════════════
# Component 4 — PromptStore
# ════════════════════════════════════════════════════════════════════════════

class PromptStore:
    """
    Version-controlled prompt persistence.
    Saves to ~/.jarvis/prompt_versions/{agent}/history.json
    Hot-patches AGENT_PROMPTS at runtime on deploy.
    """

    def __init__(self):
        VERSIONS_DIR.mkdir(parents=True, exist_ok=True)

    # ── Save ──────────────────────────────────────────────────────────────

    def save_version(self, agent: str,
                      prompt: str,
                      score:  float) -> PromptVersion:
        history = self._load_history(agent)
        version = (max(v["version"] for v in history) + 1) if history else 1
        pv = PromptVersion(
            agent=agent, version=version, prompt=prompt, score=score
        )
        history.append(asdict(pv))
        self._save_history(agent, history)
        logger.info("PromptStore: saved v%d for '%s' (score=%.1f)", version, agent, score)
        return pv

    # ── Deploy ─────────────────────────────────────────────────────────────

    def deploy(self, agent: str, version: int) -> bool:
        """Mark version as deployed + hot-patch AGENT_PROMPTS."""
        history = self._load_history(agent)
        pv      = next((v for v in history if v["version"] == version), None)
        if not pv:
            logger.warning("PromptStore: version %d not found for '%s'", version, agent)
            return False

        # Mark all others as not deployed
        for v in history:
            v["deployed"] = False
        pv["deployed"]    = True
        pv["deployed_at"] = datetime.utcnow().isoformat()
        self._save_history(agent, history)

        # Hot-patch AGENT_PROMPTS immediately
        self._hot_patch(agent, pv["prompt"])
        logger.info("PromptStore: deployed v%d for '%s'", version, agent)
        return True

    # ── Rollback ──────────────────────────────────────────────────────────

    def rollback(self, agent: str) -> Optional[PromptVersion]:
        """
        Rolls back to the previous deployed version.
        Returns the version rolled back to, or None if nothing to roll back to.
        """
        history  = self._load_history(agent)
        deployed = [v for v in history if v["deployed"]]
        if not deployed:
            return None

        current    = deployed[0]
        current_v  = current["version"]

        # Find the version deployed before this one
        previous = [
            v for v in history
            if v["version"] < current_v
        ]
        if not previous:
            logger.info("PromptStore: no previous version to roll back to for '%s'", agent)
            return None

        prev = max(previous, key=lambda v: v["version"])

        # Mark current as not deployed
        current["deployed"] = False
        # Deploy previous
        prev["deployed"]    = True
        prev["deployed_at"] = datetime.utcnow().isoformat()
        prev["rollback_of"] = current_v
        self._save_history(agent, history)

        self._hot_patch(agent, prev["prompt"])
        logger.info("PromptStore: rolled back '%s' from v%d to v%d",
                    agent, current_v, prev["version"])
        return PromptVersion(**prev)

    # ── Query ─────────────────────────────────────────────────────────────

    def get_active(self, agent: str) -> Optional[str]:
        """Returns currently deployed prompt, or None if no deployed version."""
        history = self._load_history(agent)
        for v in history:
            if v.get("deployed"):
                return v["prompt"]
        return None

    def get_history(self, agent: str) -> list[dict]:
        return self._load_history(agent)

    def can_rollback(self, agent: str) -> bool:
        """True if a rollback target exists and current was deployed < 24h ago."""
        history  = self._load_history(agent)
        deployed = [v for v in history if v.get("deployed")]
        if not deployed:
            return False
        deployed_at = deployed[0].get("deployed_at")
        if not deployed_at:
            return True
        try:
            dt    = datetime.fromisoformat(deployed_at)
            age_h = (datetime.utcnow() - dt).total_seconds() / 3600
            return age_h <= ROLLBACK_WINDOW_HOURS
        except Exception as e:
            logger.exception("[PromptOpt] can_rollback: %s", e)
            return True

    # ── Internal ──────────────────────────────────────────────────────────

    def _load_history(self, agent: str) -> list[dict]:
        fp = VERSIONS_DIR / agent / "history.json"
        if not fp.exists():
            return []
        try:
            return json.loads(fp.read_text())
        except Exception as e:
            logger.exception("[PromptOpt] load_history: %s", e)
            return []

    def _save_history(self, agent: str, history: list[dict]) -> None:
        fp = VERSIONS_DIR / agent / "history.json"
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(json.dumps(history, indent=2))

    @staticmethod
    def _hot_patch(agent: str, prompt: str) -> None:
        """Patch AGENT_PROMPTS dict in core.prompts at runtime."""
        try:
            from core.prompts import AGENT_PROMPTS
            AGENT_PROMPTS[agent] = prompt
            logger.debug("PromptStore: hot-patched AGENT_PROMPTS['%s']", agent)
        except Exception as e:
            logger.warning("PromptStore: hot-patch failed for '%s': %s", agent, e)


# ════════════════════════════════════════════════════════════════════════════
# PromptOptimizer — orchestrates all 4 components
# ════════════════════════════════════════════════════════════════════════════

class PromptOptimizer:
    """
    Main class. Called from DreamingLoop._step_optimize_prompts().
    Also callable manually via POST /api/system/prompt-optimize.

    Usage:
        optimizer = PromptOptimizer(brain=unified_brain, grader=quality_grader)
        results   = await optimizer.run_cycle()

    Per-agent usage:
        result = await optimizer.optimize_agent("chat", output_type="response")
    """

    # Map agent name → output_type for CM lookup
    AGENT_OUTPUT_TYPE: dict[str, str] = {
        "chat":            "response",
        "coder":           "code",
        "researcher":      "response",
        "website_builder": "website",
        "critic":          "response",
        "grader":          "response",
        "orchestrator":    "response",
    }

    def __init__(self,
                 brain:  "UnifiedBrain",
                 grader: "QualityGrader",
                 cm:     "ConstitutionalMemory"):
        from pathlib import Path
        self.brain    = brain
        self.grader   = grader
        self.cm       = cm

        self.analyzer  = FailureAnalyzer(cm.DB_PATH)
        self.generator = PromptGenerator()
        self.tester    = PromptTester()
        self.store     = PromptStore()

        # Track last optimization time per output_type
        self._last_run: dict[str, datetime] = {}

    # ── Full cycle ────────────────────────────────────────────────────────

    async def run_cycle(self) -> list[dict]:
        """
        Run optimization cycle for all agents.
        Returns list of result dicts (one per agent attempted).
        Called from DreamingLoop._step_optimize_prompts().
        """
        results = []
        for agent, output_type in self.AGENT_OUTPUT_TYPE.items():
            try:
                result = await self.optimize_agent(agent, output_type)
                results.append(result)
            except Exception as e:
                logger.warning("PromptOptimizer: agent '%s' failed: %s", agent, e)
                results.append({
                    "agent":  agent,
                    "status": "error",
                    "reason": str(e)
                })
        return results

    # ── Single agent ──────────────────────────────────────────────────────

    async def optimize_agent(self,
                               agent:       str,
                               output_type: str) -> dict:
        """
        Full optimization pipeline for one agent.
        Returns status dict for logging.
        """
        from core.prompts import get_prompt

        # Step 1: Check if enough new data
        since    = self._last_run.get(output_type)
        report   = self.analyzer.analyze(output_type, since=since)

        if not report.has_enough_data:
            return {
                "agent":      agent,
                "status":     "skipped",
                "reason":     f"Only {report.new_since_last} new entries "
                              f"(need {MIN_ENTRIES_PER_TYPE})",
                "entries":    report.total_entries,
            }

        self._last_run[output_type] = datetime.utcnow()

        # Step 2: Get current prompt (PromptStore first, then hardcoded)
        current = self.store.get_active(agent) or get_prompt(agent)

        # Step 3: Generate improved prompt
        new_prompt = await self.generator.generate(
            agent=agent, current=current, report=report, brain=self.brain
        )
        if not new_prompt:
            return {
                "agent":  agent,
                "status": "skipped",
                "reason": "PromptGenerator returned no improvement",
            }

        # Step 4: A/B test
        ab = await self.tester.test(
            agent=agent, old_prompt=current, new_prompt=new_prompt,
            output_type=output_type, brain=self.brain, grader=self.grader
        )

        # Step 5: Deploy if winner
        if ab.deploy:
            pv = self.store.save_version(agent, new_prompt, ab.new_score)
            self.store.deploy(agent, pv.version)
            status = "deployed"
        else:
            status = "no_improvement"

        result = {
            "agent":       agent,
            "status":      status,
            "old_score":   round(ab.old_score, 2),
            "new_score":   round(ab.new_score, 2),
            "improvement": round(ab.improvement * 100, 2),
            "queries_run": ab.queries_run,
            "reason":      ab.reason,
            "top_failures":report.top_failing[:3],
        }
        logger.info("PromptOptimizer: %s → %s (%s)", agent, status, ab.reason)
        return result

    # ── Rollback ──────────────────────────────────────────────────────────

    def rollback_agent(self, agent: str) -> dict:
        if not self.store.can_rollback(agent):
            return {
                "agent":  agent,
                "status": "error",
                "reason": f"Rollback window ({ROLLBACK_WINDOW_HOURS}h) expired "
                          f"or no previous version exists"
            }
        pv = self.store.rollback(agent)
        if not pv:
            return {"agent": agent, "status": "error", "reason": "No rollback target"}
        return {
            "agent":   agent,
            "status":  "rolled_back",
            "version": pv.version,
            "score":   pv.score,
        }


# ── Singleton ──────────────────────────────────────────────────────────────
# Created in lifespan.py after brain + grader are initialized:
#   from brain.prompt_optimizer import PromptOptimizer
#   prompt_optimizer = PromptOptimizer(brain=unified_brain,
#                                       grader=quality_grader,
#                                       cm=constitutional_memory)
