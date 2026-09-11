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

import json
import logging
import time
from typing import List, Dict, Any, Optional
from datetime import datetime

from core.research.models import ResearchResult, ResearchConfidence, Fact, Claim, Source

logger = logging.getLogger("jarvis.research.benchmark")


class ResearchBenchmark:
    """Benchmarks research quality and efficiency metrics."""

    # Known research tasks with expected outcomes for evaluation
    KNOWN_TASKS: Dict[str, Dict[str, Any]] = {
        "deploy nextjs project": {
            "expected_key_findings": [
                "Next.js framework documentation",
                "Deployment options (Vercel, Netlify)",
                "Required dependencies",
            ],
            "expected_confidence_min": 0.7,
        },
        "python setup tutorial": {
            "expected_key_findings": [
                "Python installation guide",
                "Virtual environment setup",
                "Common package installation",
            ],
            "expected_confidence_min": 0.6,
        },
    }

    def __init__(self):
        self.benchmark_history: List[Dict[str, Any]] = []

    def evaluate(self, result: ResearchResult, task_description: str = "") -> Dict[str, Any]:
        """Evaluate a research result against benchmarks."""
        task_lower = task_description.lower() if task_description else ""

        # Check if this is a known task
        known_task = None
        for task_name, task_spec in self.KNOWN_TASKS.items():
            if task_name in task_lower:
                known_task = task_spec
                break

        # Compute accuracy metrics
        accuracy = self._compute_accuracy(result, known_task)
        completeness = self._compute_completeness(result)
        efficiency = self._compute_efficiency(result)
        source_quality = self._compute_source_quality(result)

        # Overall score
        overall_score = round(
            (accuracy * 0.4) + (completeness * 0.3) + (efficiency * 0.2) + (source_quality * 0.1),
            2,
        )

        # Generate feedback
        feedback = self._generate_feedback(accuracy, completeness, efficiency, source_quality)

        # Store in history
        benchmark_entry = {
            "task_description": task_description,
            "accuracy": accuracy,
            "completeness": completeness,
            "efficiency": efficiency,
            "source_quality": source_quality,
            "overall_score": overall_score,
            "feedback": feedback,
            "timestamp": datetime.now().isoformat(),
        }
        self.benchmark_history.append(benchmark_entry)

        return {
            "accuracy": accuracy,
            "completeness": completeness,
            "efficiency": efficiency,
            "source_quality": source_quality,
            "overall_score": overall_score,
            "feedback": feedback,
            "known_task": known_task is not None,
            "known_task_name": known_task.get("task_name", task_description) if known_task else None,
        }

    def _compute_accuracy(self, result: ResearchResult, known_task: Dict = None) -> float:
        """Compute how accurate the research results are."""
        if not known_task:
            # Without known task, use confidence as proxy
            return result.overall_confidence

        # Check key findings against expected
        expected_findings = known_task.get("expected_key_findings", [])
        actual_findings = result.key_findings if result.key_findings else []

        if not expected_findings:
            return result.overall_confidence

        # Count how many expected findings are present
        found_count = 0
        for expected in expected_findings:
            if any(expected.lower() in str(finding).lower() for finding in actual_findings):
                found_count += 1

        # Accuracy = fraction of expected findings found + confidence weighting
        accuracy = found_count / max(1, len(expected_findings))
        # Weight by confidence
        accuracy = round(accuracy * result.overall_confidence + (1 - accuracy) * 0.3, 2)
        return accuracy

    def _compute_completeness(self, result: ResearchResult) -> float:
        """Compute how complete the research result is."""
        score = 0.0
        total_components = 4  # summary, findings, sources, confidence

        # Check summary
        if result.summary and len(result.summary) > 20:
            score += 1

        # Check key findings
        if result.key_findings and len(result.key_findings) > 0:
            score += 1

        # Check sources
        if result.sources and len(result.sources) > 0:
            score += 1

        # Check confidence
        if result.overall_confidence > 0:
            score += 1

        return round(score / total_components, 2)

    def _compute_efficiency(self, result: ResearchResult) -> float:
        """Compute research efficiency (how quickly good results were obtained)."""
        # Based on rounds completed vs confidence achieved
        if not hasattr(result, 'rounds_completed'):
            return 0.5

        rounds = result.rounds_completed
        confidence = result.overall_confidence

        # Fewer rounds with higher confidence = more efficient
        if rounds == 0:
            return 0.5

        # Efficiency formula: confidence / (rounds / 5 + 1)
        # Normalized to 0-1 range
        efficiency = confidence / (rounds / 5 + 1)
        return round(min(1.0, max(0.0, efficiency)), 2)

    def _compute_source_quality(self, result: ResearchResult) -> float:
        """Compute the quality of sources used."""
        if not result.sources:
            return 0.5  # Neutral if no sources

        # Average credibility from sources
        total_credibility = 0
        count = 0
        for source in result.sources:
            # sources may have credibility attribute or default
            cred = getattr(source, 'credibility', 0.5) if isinstance(source, dict) else 0.5
            total_credibility += cred
            count += 1

        if count > 0:
            return round(total_credibility / count, 2)
        return 0.5

    def _generate_feedback(self, accuracy: float, completeness: float,
                           efficiency: float, source_quality: float) -> str:
        """Generate human-readable feedback based on benchmark results."""
        parts = []

        if accuracy > 0.7:
            parts.append("Good accuracy in findings")
        elif accuracy < 0.4:
            parts.append("Low accuracy — research may need different approach")
        else:
            parts.append("Moderate accuracy — some findings correct")

        if completeness > 0.7:
            parts.append("Research is comprehensive")
        elif completeness < 0.4:
            parts.append("Research is incomplete — more steps needed")
        else:
            parts.append("Research is partially complete")

        if efficiency > 0.7:
            parts.append("Efficient research — few rounds to good result")
        elif efficiency < 0.3:
            parts.append("Inefficient — many rounds for limited gain")
        else:
            parts.append("Moderate efficiency")

        if source_quality > 0.7:
            parts.append("High-quality sources used")
        elif source_quality < 0.4:
            parts.append("Low-quality sources — consider better sources")
        else:
            parts.append("Moderate source quality")

        return ". ".join(parts) + "."

    def record_task_performance(self, task_id: str, result: ResearchResult,
                                task_description: str = "") -> None:
        """Record performance data for a task."""
        entry = {
            "task_id": task_id,
            "description": task_description,
            "result_id": result.id if result else None,
            "accuracy": self._compute_accuracy(result, None),
            "completeness": self._compute_completeness(result),
            "efficiency": self._compute_efficiency(result),
            "source_quality": self._compute_source_quality(result),
            "timestamp": datetime.now().isoformat(),
        }
        self.benchmark_history.append(entry)

    def get_history(self) -> List[Dict[str, Any]]:
        """Get benchmark history."""
        return self.benchmark_history

    def get_statistics(self) -> Dict[str, Any]:
        """Get overall benchmark statistics."""
        if not self.benchmark_history:
            return {"total_tasks": 0}

        total = len(self.benchmark_history)
        avg_accuracy = round(
            sum(b.get("accuracy", 0) for b in self.benchmark_history) / total, 2)
        avg_completeness = round(
            sum(b.get("completeness", 0) for b in self.benchmark_history) / total, 2)
        avg_efficiency = round(
            sum(b.get("efficiency", 0) for b in self.benchmark_history) / total, 2)
        avg_source_quality = round(
            sum(b.get("source_quality", 0) for b in self.benchmark_history) / total, 2)
        avg_overall = round(
            sum(b.get("overall_score", 0) for b in self.benchmark_history) / total, 2)

        return {
            "total_tasks": total,
            "average_accuracy": avg_accuracy,
            "average_completeness": avg_completeness,
            "average_efficiency": avg_efficiency,
            "average_source_quality": avg_source_quality,
            "average_overall_score": avg_overall,
        }