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
from typing import List, Dict, Any, Optional
from datetime import datetime

from core.research.models import ResearchResult, ResearchConfidence, Fact, Claim, Hypothesis

logger = logging.getLogger("jarvis.research.reflection")


class ResearchReflection:
    """Research reflection and learning from previous research experiences."""

    def __init__(self, evidence_tracker=None, graph_store=None):
        self.evidence_tracker = evidence_tracker or EvidenceTracker()
        self.graph_store = graph_store or GraphStore()
        self.learned_patterns: Dict[str, Any] = {}
        self.research_history: List[ResearchResult] = []
    
    def record_research(self, result: ResearchResult) -> None:
        """Record a completed research result for future learning."""
        self.research_history.append(result)
        
        # Extract patterns from this research
        patterns = self._extract_patterns(result)
        self._update_learned_patterns(patterns)
    
    def _extract_patterns(self, result: ResearchResult) -> Dict[str, Any]:
        """Extract learnings from a research result."""
        patterns = {
            "query": result.sub_questions[0] if result.sub_questions else "",
            "success": result.status == "completed",
            "fact_count": len(result.claims) if result.claims else 0,
            "confidence": result.overall_confidence,
            "key_findings": result.key_findings,
            "sources_used": len(result.sources) if result.sources else 0,
        }
        
        # Determine what worked well
        if result.overall_confidence > 0.7:
            patterns["what_worked"] = "High-confidence sources and clear evidence chains"
        elif result.overall_confidence > 0.4:
            patterns["what_worked"] = "Moderate-confidence evidence with some gaps"
        else:
            patterns["what_worked"] = "Low confidence — areas for improvement"
        
        # Determine what didn't work
        if result.status == "failed":
            patterns["what_failed"] = "Research pipeline failed to complete"
        elif result.overall_confidence < 0.3:
            patterns["what_failed"] = "Insufficient evidence or poor source quality"
        else:
            patterns["what_failed"] = ""
        
        return patterns
    
    def _update_learned_patterns(self, patterns: Dict[str, Any]) -> None:
        """Update the learned patterns store."""
        query_pattern = patterns.get("query", "")
        if query_pattern not in self.learned_patterns:
            self.learned_patterns[query_pattern] = []
        
        # Append this pattern's results
        self.learned_patterns[query_pattern].append({
            "confidence": patterns.get("confidence", 0),
            "success": patterns.get("success", False),
            "fact_count": patterns.get("fact_count", 0),
            "what_worked": patterns.get("what_worked", ""),
        })
        
        # Keep only recent patterns (limit per query)
        if len(self.learned_patterns[query_pattern]) > 10:
            self.learned_patterns[query_pattern] = self.learned_patterns[query_pattern][-10:]
    
    def get_learned_patterns(self, query: str = "") -> Dict[str, Any]:
        """Get learned patterns, optionally filtered by query."""
        if query:
            return self.learned_patterns.get(query, {})
        return self.learned_patterns
    
    def get_pattern_insights(self, query: str) -> Dict[str, Any]:
        """Get insights from learned patterns for a specific query."""
        patterns = self.get_learned_patterns(query)
        
        if not patterns:
            return {
                "patterns_found": 0,
                "insights": "No previous research found for this query type",
                "recommendations": "Start with a fresh research approach",
            }
        
        # Analyze patterns
        total = len(patterns)
        successful = sum(1 for p in patterns if p.get("success", False))
        avg_confidence = sum(p.get("confidence", 0) for p in patterns) / max(1, total)
        
        # Find common what_worked themes
        what_worked_freq = {}
        for p in patterns:
            pw = p.get("what_worked", "")
            if pw:
                # Simple keyword extraction
                for word in pw.lower().split():
                    if len(word) > 3:
                        what_worked_freq[word] = what_worked_freq.get(word, 0) + 1
        
        top_insights = sorted(what_worked_freq.items(), key=lambda x: x[1], reverse=True)[:3]
        
        recommendations = []
        if successful / total > 0.6 if total > 0 else False:
            recommendations.append("Previous research successful — similar approach may work")
        if avg_confidence > 0.6:
            recommendations.append("High confidence pattern detected — can increase ambition")
        if avg_confidence < 0.3:
            recommendations.append("Low success rate — consider different strategy")
        
        return {
            "patterns_found": total,
            "success_rate": round(successful / total, 2) if total > 0 else 0,
            "average_confidence": round(avg_confidence, 2),
            "top_insights": [w for w, _ in top_insights],
            "recommendations": recommendations,
        }
    
    def suggest_strategy(self, query: str) -> Dict[str, Any]:
        """Suggest a research strategy based on learned patterns."""
        patterns = self.get_pattern_insights(query)
        
        strategy = {
            "approach": "standard",
            "max_sources": 10,
            "rounds": 5,
            "confidence_threshold": 0.5,
        }
        
        if patterns.get("patterns_found", 0) > 0:
            success_rate = patterns.get("success_rate", 0)
            avg_conf = patterns.get("average_confidence", 0)
            
            if success_rate > 0.7 and avg_confidence > 0.6:
                strategy = {
                    "approach": "accelerated",
                    "max_sources": 15,
                    "rounds": 8,
                    "confidence_threshold": 0.6,
                }
            elif success_rate < 0.3:
                strategy = {
                    "approach": "conservative",
                    "max_sources": 5,
                    "rounds": 3,
                    "confidence_threshold": 0.4,
                }
        
        return strategy
    
    def clear_history(self) -> None:
        """Clear research history and learned patterns."""
        self.research_history.clear()
        self.learned_patterns.clear()


# Singleton
research_reflection = ResearchReflection()