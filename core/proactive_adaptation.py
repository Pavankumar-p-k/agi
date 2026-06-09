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
"""core/proactive_adaptation.py
Phase 5 (E2): Proactive Adaptation.
Uses environment monitor data to anticipate issues and switch strategies preemptively.
"""
import logging

from core.environment_monitor import environment_monitor

logger = logging.getLogger(__name__)


class AdaptationEngine:
    """Reads environment health and proactively adjusts system behavior."""
    def __init__(self):
        self._rules_triggered: dict[str, int] = {}

    def assess(self) -> list[dict]:
        snap = environment_monitor.check()
        actions = []

        # Rule: If Ollama down, force shell-only mode
        if not snap.ollama_available:
            actions.append({
                "action": "force_shell_mode",
                "reason": "Ollama unavailable",
                "severity": "warning",
                "details": "Falling back to shell-only agent execution",
            })
            self._rules_triggered["force_shell_mode"] = self._rules_triggered.get("force_shell_mode", 0) + 1

        # Rule: If disk low, reduce max_parallel
        if snap.disk_free_gb < 5.0:
            actions.append({
                "action": "reduce_parallelism",
                "reason": f"Low disk ({snap.disk_free_gb:.1f} GB)",
                "severity": "warning",
                "details": "Reducing max parallel builds to 1",
            })
            self._rules_triggered["reduce_parallelism"] = self._rules_triggered.get("reduce_parallelism", 0) + 1

        # Rule: If disk critically low, pause builds
        if snap.disk_free_gb < 1.0:
            actions.append({
                "action": "pause_builds",
                "reason": f"Critical disk ({snap.disk_free_gb:.1f} GB)",
                "severity": "critical",
                "details": "Pausing all builds until disk space recovered",
            })
            self._rules_triggered["pause_builds"] = self._rules_triggered.get("pause_builds", 0) + 1

        # Rule: If network down, skip deploy tasks
        if not snap.network_reachable:
            actions.append({
                "action": "skip_deploy",
                "reason": "Network unreachable",
                "severity": "warning",
                "details": "Skipping deploy tasks in build plans",
            })
            self._rules_triggered["skip_deploy"] = self._rules_triggered.get("skip_deploy", 0) + 1

        # Rule: If memory low, reduce parallel tasks and increase timeouts
        if snap.memory_free_mb < 500:
            actions.append({
                "action": "reduce_memory_load",
                "reason": f"Low memory ({snap.memory_free_mb:.0f} MB free)",
                "severity": "warning",
                "details": "Reducing task parallelism, increasing timeouts",
            })
            self._rules_triggered["reduce_memory_load"] = self._rules_triggered.get("reduce_memory_load", 0) + 1

        # Rule: If critical services missing
        for s_name, s_health in snap.services.items():
            if s_health.status == "down" and s_name == "templates":
                actions.append({
                    "action": "regenerate_templates",
                    "reason": "Template library missing",
                    "severity": "warning",
                    "details": "Will generate templates from scratch instead",
                })
                self._rules_triggered["regenerate_templates"] = self._rules_triggered.get("regenerate_templates", 0) + 1

        if actions:
            for a in actions:
                logger.warning(f"[ADAPT] {a['action']}: {a['reason']}")

        return actions

    def adapt_config(self, config: dict) -> dict:
        """Modify a config dict based on environment assessment."""
        actions = self.assess()
        adapted = dict(config)

        for a in actions:
            if a["action"] == "force_shell_mode":
                adapted["max_parallel"] = 1
                adapted["prefer_shell"] = True
            elif a["action"] == "reduce_parallelism":
                adapted["max_parallel"] = min(adapted.get("max_parallel", 2), 1)
            elif a["action"] == "pause_builds":
                adapted["paused"] = True
            elif a["action"] == "skip_deploy":
                adapted["skip_deploy"] = True
            elif a["action"] == "reduce_memory_load":
                adapted["max_parallel"] = min(adapted.get("max_parallel", 2), 1)
                adapted["task_timeout"] = adapted.get("task_timeout", 600) + 120
            elif a["action"] == "regenerate_templates":
                adapted["template_fallback"] = True

        return adapted

    def should_pause(self) -> bool:
        actions = self.assess()
        return any(a["action"] == "pause_builds" for a in actions)

    def get_rules_triggered(self) -> dict:
        return dict(self._rules_triggered)

    def reset_counters(self):
        self._rules_triggered.clear()


adaptation_engine = AdaptationEngine()
