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

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from eval.scenario import EvalScenario, ScenarioResult

logger = logging.getLogger(__name__)


@dataclass
class ScenarioScore:
    scenario_id: str
    prompt: str

    tool_call_accuracy: float = 0.0
    pattern_match: float = 0.0
    quality_score: float = 0.0
    efficiency_score: float = 0.0

    tool_call_expected_found: list[str] = field(default_factory=list)
    tool_call_expected_missed: list[str] = field(default_factory=list)
    tool_call_forbidden_called: list[str] = field(default_factory=list)
    patterns_matched: list[str] = field(default_factory=list)
    patterns_missed: list[str] = field(default_factory=list)
    forbidden_patterns_found: list[str] = field(default_factory=list)

    error: str | None = None
    round_count: int = 0
    total_duration: float = 0.0

    aggregate: float = 0.0

    @property
    def passed(self) -> bool:
        return self.aggregate >= 0.7


def score_scenario(
    result: ScenarioResult,
    scenario: EvalScenario,
    quality_grader: Any = None,
) -> ScenarioScore:
    score = ScenarioScore(
        scenario_id=scenario.id,
        prompt=scenario.prompt,
        error=result.error,
        round_count=result.round_count,
        total_duration=result.total_duration,
    )

    tool_names = [tc.get("tool", "") for tc in result.tool_calls]

    if scenario.expected_tools:
        found = [t for t in scenario.expected_tools if t in tool_names]
        missed = [t for t in scenario.expected_tools if t not in tool_names]
        score.tool_call_expected_found = found
        score.tool_call_expected_missed = missed
        score.tool_call_accuracy = len(found) / max(len(scenario.expected_tools), 1)

    if scenario.forbidden_tools:
        called = [t for t in scenario.forbidden_tools if t in tool_names]
        score.tool_call_forbidden_called = called
        if called:
            score.tool_call_accuracy *= 0.5

    if result.full_response and scenario.expected_patterns:
        matched = []
        missed = []
        for pat in scenario.expected_patterns:
            try:
                if re.search(pat, result.full_response, re.IGNORECASE):
                    matched.append(pat)
                else:
                    missed.append(pat)
            except re.error:
                if pat.lower() in result.full_response.lower():
                    matched.append(pat)
                else:
                    missed.append(pat)
        score.patterns_matched = matched
        score.patterns_missed = missed
        score.pattern_match = len(matched) / max(len(scenario.expected_patterns), 1)

    if result.full_response and scenario.forbidden_patterns:
        found = []
        for pat in scenario.forbidden_patterns:
            try:
                if re.search(pat, result.full_response, re.IGNORECASE):
                    found.append(pat)
            except re.error:
                if pat.lower() in result.full_response.lower():
                    found.append(pat)
        score.forbidden_patterns_found = found

    if result.full_response and quality_grader is not None:
        try:
            import asyncio
            grade = asyncio.run(
                quality_grader.grade("response", result.full_response)
            )
            score.quality_score = grade.aggregate_score / 100.0
        except Exception as e:
            logger.warning("Quality grading failed for %s: %s", scenario.id, e)
    else:
        score.quality_score = 0.5

    if scenario.min_rounds > 0 and result.round_count >= scenario.min_rounds:
        score.efficiency_score = 1.0
    else:
        score.efficiency_score = max(0.0, 1.0 - (result.round_count / max(scenario.max_rounds, 1)))

    if result.error:
        score.aggregate = 0.0
    else:
        score.aggregate = (
            score.tool_call_accuracy * 0.25
            + score.pattern_match * 0.25
            + score.quality_score * 0.30
            + score.efficiency_score * 0.20
        )

    return score


def score_all(
    results: list[ScenarioResult],
    scenarios: list[EvalScenario],
    quality_grader: Any = None,
) -> list[ScenarioScore]:
    scenario_map = {s.id: s for s in scenarios}
    scores = []
    for r in results:
        scenario = scenario_map.get(r.scenario_id)
        if scenario:
            scores.append(score_scenario(r, scenario, quality_grader))
    return scores
