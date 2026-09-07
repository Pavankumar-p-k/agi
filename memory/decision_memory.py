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
"""memory/decision_memory.py
Action→outcome learning for JARVIS.
Stores every action + outcome and uses it to make better decisions.
"""
import os, re, json, logging, statistics
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger("decision_memory")

MEMORY_PATH = Path.home() / ".jarvis" / "decision_memory.json"


class DecisionMemory:
    """Stores and learns from past actions and outcomes."""

    def __init__(self):
        self.entries: list[dict] = []
        self._rules: dict[str, str] = {}
        self._load()

    def _load(self):
        if MEMORY_PATH.exists():
            try:
                data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
                self.entries = data.get("entries", [])
                self._rules = data.get("rules", {})
            except Exception as e:
                logger.error(f"[DECISION] Load error: {e}")

    def _save(self):
        MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {"entries": self.entries, "rules": self._rules}
        MEMORY_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def record(self, goal: str, task: str, agents_tried: list[str], winner: Optional[str],
               duration_s: float, success: bool, error: str = "", keys_rotated: int = 0,
               visual_score: Optional[float] = None, reasoning_score: Optional[float] = None,
               ambiguity_resolved: bool = False, fix_applied: Optional[str] = None):
        """Record an action and its outcome.

        Args:
            visual_score: Vision LLM quality score (0-100) after fix, if applicable.
            reasoning_score: Reasoning engine quality score (0-10), if applicable.
            ambiguity_resolved: Whether an ambiguity question was asked & answered.
            fix_applied: The fix type that was applied (e.g. 'fix_vis_content', 'fix_nav').
        """
        entry: dict[str, object] = {
            "goal": goal[:100],
            "task": task[:100],
            "agents_tried": agents_tried,
            "winner": winner,
            "duration_s": round(duration_s, 1),
            "success": success,
            "error": error[:200],
            "keys_rotated": keys_rotated,
            "timestamp": datetime.now().isoformat(),
        }
        if visual_score is not None:
            entry["visual_score"] = round(visual_score, 1)
        if reasoning_score is not None:
            entry["reasoning_score"] = round(reasoning_score, 1)
        if ambiguity_resolved:
            entry["ambiguity_resolved"] = True
        if fix_applied:
            entry["fix_applied"] = fix_applied
        self.entries.append(entry)
        self._derive_rules(entry)
        self._save()
        logger.info(f"[DECISION] Recorded: {task[:40]}... {'OK' if success else 'FAIL'} via {winner or 'none'}")

    def _derive_rules(self, entry: dict):
        """Derive learning rules from this entry."""
        if entry["success"] and entry["winner"]:
            task_type = self._classify_task(entry["task"])
            self._rules[f"agent_{task_type}"] = entry["winner"]

        if not entry["success"]:
            task_type = self._classify_task(entry["task"])
            for agent in entry["agents_tried"]:
                self._rules[f"avoid_{task_type}_{agent}"] = "true"

        if entry["keys_rotated"] > 0:
            for agent in entry["agents_tried"]:
                if agent != "shell":
                    self._rules[f"rotate_keys_for_{agent}"] = "true"

    def _classify_task(self, task: str) -> str:
        tl = task.lower()
        if "scaffold" in tl: return "scaffold"
        if "frontend" in tl or "ui" in tl: return "frontend"
        if "backend" in tl or "api" in tl: return "backend"
        if "styling" in tl or "css" in tl or "theme" in tl: return "styling"
        if "deploy" in tl: return "deploy"
        if "test" in tl: return "test"
        if "fix" in tl: return "fix"
        if "doc" in tl: return "docs"
        if "database" in tl or "schema" in tl: return "database"
        if "auth" in tl or "login" in tl: return "auth"
        return "general"

    def best_agent_for(self, task_type: str) -> Optional[str]:
        """Return the best agent for a task type based on past success."""
        rule = self._rules.get(f"agent_{task_type}")
        if rule:
            return rule

        candidates = [e for e in self.entries if task_type in e.get("task", "").lower() and e["success"]]
        if not candidates:
            return None

        agent_scores = {}
        for entry in candidates:
            agent = entry.get("winner") or entry["agents_tried"][0] if entry["agents_tried"] else None
            if agent:
                score = 1.0 / (entry["duration_s"] + 1)
                agent_scores[agent] = agent_scores.get(agent, 0) + score

        if agent_scores:
            return max(agent_scores, key=agent_scores.get)
        return None

    def worst_agents_for(self, task_type: str) -> list[str]:
        """Return agents that have failed for this task type."""
        bad = []
        for key in self._rules:
            if key.startswith(f"avoid_{task_type}_"):
                bad.append(key.replace(f"avoid_{task_type}_", ""))
        return bad

    def has_pattern(self, task_type: str, error: str) -> Optional[str]:
        """Check if we've seen this error before and return the fix."""
        for entry in self.entries:
            if task_type in entry.get("task", "").lower():
                if error.lower() in entry.get("error", "").lower():
                    if entry["success"]:
                        return entry.get("winner") or "shell"
        return None

    def best_fix_for(self, issue_type: str) -> Optional[str]:
        """Return the fix type that most reliably resolved this issue type in the past.

        issue_type examples: 'visual_quality', 'reasoning_quality', 'all_pages_exist', 'nav_consistent'
        Returns the fix_applied value (e.g. 'fix_vis_content', 'fix_nav') or None.
        """
        candidates = [
            e for e in self.entries
            if e.get("fix_applied") and e.get("success")
            and issue_type in e.get("task", "")
        ]
        if not candidates:
            return None
        fix_counts: dict[str, list[float]] = {}
        for entry in candidates:
            fa = entry["fix_applied"]
            if fa not in fix_counts:
                fix_counts[fa] = []
            fix_counts[fa].append(1.0)
            # Boost score if visual quality improved significantly
            vs = entry.get("visual_score")
            if vs is not None and vs >= 85:
                fix_counts[fa][-1] += 0.5
        best_fix = max(fix_counts, key=lambda f: sum(fix_counts[f]) / len(fix_counts[f]))
        return best_fix

    def fix_success_rate(self, fix_type: str) -> float:
        """Return the success rate (0.0-1.0) for a given fix type across all entries."""
        total = [e for e in self.entries if e.get("fix_applied") == fix_type]
        if not total:
            return 0.0
        succeeded = sum(1 for e in total if e["success"])
        return succeeded / len(total)

    def get_stats(self) -> dict:
        """Return summary stats."""
        total = len(self.entries)
        succeeded = sum(1 for e in self.entries if e["success"])
        if not total:
            return {"total": 0, "success_rate": 0, "avg_duration": 0, "rules": 0}

        durations = [e["duration_s"] for e in self.entries if e["success"]]
        agent_counts = {}
        for e in self.entries:
            for a in e["agents_tried"]:
                agent_counts[a] = agent_counts.get(a, 0) + 1

        return {
            "total": total,
            "success_rate": round(succeeded / total * 100, 1),
            "avg_duration": round(statistics.mean(durations), 1) if durations else 0,
            "agents_used": len(agent_counts),
            "agent_breakdown": agent_counts,
            "rules": len(self._rules),
        }

    def clear(self):
        self.entries.clear()
        self._rules.clear()
        self._save()


decision_memory = DecisionMemory()
