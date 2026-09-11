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
from typing import List, Dict, Any, Optional
from datetime import datetime

from core.research.models import ResearchResult, ResearchConfidence, Fact, Claim, Source, Hypothesis

logger = logging.getLogger("jarvis.research.research_benchmark")


class ResearchBenchmark:
    """Specialized benchmarks for research AI quality and effectiveness."""

    # Research task categories with quality thresholds
    TASK_THRESHOLDS = {
        "deployment": {"min_confidence": 0.7, "min_findings": 3},
        "documentation": {"min_confidence": 0.6, "min_findings": 2},
        "comparison": {"min_confidence": 0.75, "min_findings": 4},
        "general": {"min_confidence": 0.5, "min_findings": 1},
    }

    def __init__(self):
        self.benchmark_history: List[Dict[str, Any]] = []
        self.task_category_cache: Dict[str, str] = {}

    def classify_task(self, query: str) -> str:
        """Classify a research query into a task category."""
        query_lower = query.lower()

        for category, keywords in self.TASK_THRESHOLDS.items():
            for keyword in self._get_keywords(category):
                if keyword in query_lower:
                    return category
        return "general"

    def _get_keywords(self, category: str) -> List[str]:
        """Get keywords associated with a task category."""
        keywords_map = {
            "deployment": ["deploy", "install", "configure", "setup", "target", "environment"],
            "documentation": ["how to", "tutorial", "guide", "learn", "documentation"],
            "comparison": ["compare", "vs", "versus", "difference between", "alternative"],
            "general": [],
        }
        return keywords_map.get(category, [])

    def evaluate(self, result: ResearchResult, query: str = "") -> Dict[str, Any]:
        """Evaluate research result quality with research-specific metrics."""
        category = self.classify_task(query if query else getattr(result, 'query', '') or '')

        # Get thresholds for this category
        thresholds = self.TASK_THRESHOLDS.get(category, self.TASK_THRESHOLDS["general"])

        # Evaluate individual metrics
        confidence_score = self._score_confidence(result, thresholds)
        findings_score = self._score_findings(result, thresholds)
        source_score = self._score_sources(result)
        coverage_score = self._score_coverage(result, thresholds)

        # Overall research quality score
        overall = round(
            (confidence_score * 0.35)
            + (findings_score * 0.30)
            + (source_score * 0.20)
            + (coverage_score * 0.15),
            2,
        )

        # Generate quality insights
        insights = self._generate_insights(
            confidence_score, findings_score, source_score, coverage_score, category
        )

        # Store in history
        entry = {
            "query": query,
            "category": category,
            "confidence_score": confidence_score,
            "findings_score": findings_score,
            "source_score": source_score,
            "coverage_score": coverage_score,
            "overall_score": overall,
            "insights": insights,
            "timestamp": datetime.now().isoformat(),
        }
        self.benchmark_history.append(entry)

        return {
            "category": category,
            "confidence_score": confidence_score,
            "findings_score": findings_score,
            "source_score": source_score,
            "coverage_score": coverage_score,
            "overall_score": overall,
            "insights": insights,
            "meets_thresholds": (
                confidence_score >= thresholds["min_confidence"]
                and findings_score >= thresholds["min_findings"]
            ),
        }

    def _score_confidence(self, result: ResearchResult, thresholds: Dict) -> float:
        """Score based on confidence and threshold comparison."""
        base = result.overall_confidence
        min_thresh = thresholds.get("min_confidence", 0.5)

        # Score: how well confidence meets threshold
        if base >= min_thresh:
            return round(min(1.0, base), 2)
        else:
            # Partial credit for being close to threshold
            return round(base / min_thresh, 2) if min_thresh > 0 else 0.0

    def _score_findings(self, result: ResearchResult, thresholds: Dict) -> float:
        """Score based on number of key findings vs threshold."""
        min_findings = thresholds.get("min_findings", 1)
        actual_findings = len(result.key_findings) if result.key_findings else 0

        if actual_findings >= min_findings:
            return round(min(1.0, actual_findings / min_findings), 2)
        else:
            return round(actual_findings / min_findings, 2) if min_findings > 0 else 0.0

    def _score_sources(self, result: ResearchResult) -> float:
        """Score based on source quality and diversity."""
        if not result.sources:
            return 0.5  # Neutral score

        # Average credibility
        total_cred = 0
        count = 0
        source_types = set()

        for source in result.sources:
            cred = getattr(source, 'credibility', 0.5) if isinstance(source, dict) else 0.5
            total_cred += cred
            count += 1
            # Extract domain for diversity
            if hasattr(source, 'url') and source.url:
                import re
                domain = re.search(r'https?://[^/]+', source.url)
                if domain:
                    source_types.add(domain.group(0))

        avg_cred = round(total_cred / max(1, count), 2) if count else 0.5

        # Diversity bonus: more different sources = better
        diversity_bonus = round(min(0.3, len(source_types) * 0.1), 2)

        return round(min(1.0, avg_cred + diversity_bonus), 2)

    def _score_coverage(self, result: ResearchResult, thresholds: Dict) -> float:
        """Score based on how well the research covers the topic."""
        # Based on number of claims and their support
        if not result.claims:
            return 0.5

        # Count supported claims
        supported = sum(1 for c in result.claims if c.status == "supported")
        total = len(result.claims)

        # Base score from support ratio
        ratio = supported / max(1, total)

        # Confidence weighting
        avg_conf = 0
        if result.overall_confidence > 0:
            avg_conf = result.overall_confidence
        else:
            # Compute from claims
            confs = [c.confidence for c in result.claims if c.confidence]
            avg_conf = round(sum(confs) / max(1, len(confs)), 2) if confs else 0.5

        return round((ratio * 0.6) + (avg_conf * 0.4), 2)

    def _generate_insights(self, confidence_score: float, findings_score: float,
                           source_score: float, coverage_score: float,
                           category: str) -> Dict[str, Any]:
        """Generate quality insights and recommendations."""
        strengths = []
        weaknesses = []
        recommendations = []

        if confidence_score > 0.7:
            strengths.append("High confidence in results")
        elif confidence_score < 0.4:
            weaknesses.append("Low confidence — results uncertain")

        if findings_score >= 3:
            strengths.append("Good number of key findings")
        elif findings_score < 1:
            weaknesses.append("Few key findings identified")

        if source_score > 0.7:
            strengths.append("High-quality sources")
        elif source_score < 0.4:
            weaknesses.append("Poor source quality — reconsider sources")

        if coverage_score > 0.7:
            strengths.append("Good topic coverage")
        elif coverage_score < 0.4:
            weaknesses.append("Limited topic coverage")

        # Category-specific recommendations
        if category == "deployment":
            if findings_score < 3:
                recommendations.append("For deployment tasks, aim for at least 3 key findings")
            if source_score < 0.6:
                recommendations.append("Prioritize official documentation and reputable tech sites")
        elif category == "comparison":
            if findings_score < 4:
                recommendations.append("For comparison tasks, aim for at least 4 key findings differentiating options")
        
        if not strengths and not weaknesses:
            strengths.append("Research completed with adequate quality")

        return {
            "strengths": strengths,
            "weaknesses": weaknesses,
            "recommendations": recommendations,
        }

    def record_evaluation(self, evaluation: Dict[str, Any]) -> None:
        """Record an evaluation result."""
        self.benchmark_history.append(evaluation)

    def get_history(self) -> List[Dict[str, Any]]:
        """Get evaluation history."""
        return self.benchmark_history

    def get_statistics(self) -> Dict[str, Any]:
        """Get benchmark statistics."""
        if not self.benchmark_history:
            return {"total_evaluations": 0}

        total = len(self.benchmark_history)
        avg_overall = round(
            sum(b.get("overall_score", 0) for b in self.benchmark_history) / total, 2)

        # Count by category
        category_counts: Dict[str, int] = {}
        for b in self.benchmark_history:
            cat = b.get("category", "general")
            category_counts[cat] = category_counts.get(cat, 0) + 1

        return {
            "total_evaluations": total,
            "average_overall_score": avg_overall,
            "category_distribution": category_counts,
            "evaluations_by_category": {
                cat: {
                    "avg_score": round(
                        sum(b.get("overall_score", 0) for b in self.benchmark_history if b.get("category") == cat) / 
                        max(1, sum(1 for b in self.benchmark_history if b.get("category") == cat)),
                        2,
                    )
                }
                for cat in set(category_counts.values())
            },
        }