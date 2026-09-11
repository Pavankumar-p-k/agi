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

from core.research.models import ResearchResult, ResearchReport, Source, Claim, Fact, Hypothesis, ResearchConfidence

logger = logging.getLogger("jarvis.research.synthesizer")


class Synthesizer:
    """Synthesizes research findings into structured reports and conclusions."""

    def synthesize(self, topic: str, facts: List[Fact],
                   claims: List[Claim] = None,
                   sources: List[Source] = None,
                   hypotheses: List[Hypothesis] = None) -> ResearchReport:
        """Synthesize research findings into a structured report."""
        
        # Analyze facts
        fact_summary = self._summarize_facts(facts)
        
        # Analyze claims
        claim_summary = self._summarize_claims(claims) if claims else {"total": 0, "supported": 0, "contradicted": 0}
        
        # Analyze sources
        source_summary = self._summarize_sources(sources) if sources else {"total": 0, "formatted": []}
        
        # Analyze hypotheses
        hyp_summary = self._summarize_hypotheses(hypotheses) if hypotheses else {"total": 0, "supported": 0}
        
        # Compute overall confidence
        confidence = self._compute_confidence(facts, claims, hypotheses)
        
        # Generate summary
        summary = self._generate_summary(topic, fact_summary, claim_summary, confidence)
        
        # Generate key findings
        key_findings = self._generate_key_findings(facts, claims)
        
        # Format sources
        formatted_sources = self._format_sources(sources)
        
        # Generate conclusion
        conclusion = self._generate_conclusion(facts, claims, hypotheses)
        
        return ResearchReport(
            summary=summary,
            key_findings=key_findings,
            sources=formatted_sources,
            claims=self._format_claims(claims),
            overall_confidence=confidence,
            status="completed",
            generated_at=datetime.now(),
        )
    
    def _summarize_facts(self, facts: List[Fact]) -> Dict[str, Any]:
        """Summarize extracted facts."""
        if not facts:
            return {"total": 0, "by_confidence": {}, "themes": []}
        
        # Group by confidence range
        by_confidence = {}
        for fact in facts:
            conf_key = f"{int(fact.confidence * 10)}0"
            by_confidence.setdefault(conf_key, []).append({
                "text": fact.text[:100],
                "confidence": fact.confidence,
                "source": fact.source_url,
            })
        
        # Simple theme extraction (keywords from facts)
        all_text = " ".join(f.text for f in facts)
        words = [w.lower() for w in all_text.split() if w.isalpha()]
        # Get most common words (simple approach)
        word_freq = {}
        for w in words:
            if len(w) > 3:
                word_freq[w] = word_freq.get(w, 0) + 1
        top_themes = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:5]
        themes = [w for w, _ in top_themes]
        
        return {
            "total": len(facts),
            "by_confidence": {k: len(v) for k, v in by_confidence.items()},
            "themes": themes,
        }
    
    def _summarize_claims(self, claims: List[Claim]) -> Dict[str, Any]:
        """Summarize claims by status."""
        if not claims:
            return {"total": 0, "supported": 0, "contradicted": 0, "unverified": 0}
        
        supported = sum(1 for c in claims if c.status == "supported")
        contradicted = sum(1 for c in claims if c.status == "contradicted")
        unverified = sum(1 for c in claims if c.status == "unverified")
        
        return {
            "total": len(claims),
            "supported": supported,
            "contradicted": contradicted,
            "unverified": unverified,
        }
    
    def _summarize_sources(self, sources: List[Source]) -> Dict[str, Any]:
        """Summarize sources."""
        if not sources:
            return {"total": 0, "by_credibility": {}, "formatted": []}
        
        by_credibility = {}
        for source in sources:
            cred_key = f"{int(source.credibility * 10)}0"
            by_credibility.setdefault(cred_key, []).append({
                "url": source.url,
                "title": source.title,
            })
        
        return {
            "total": len(sources),
            "by_credibility": {k: len(v) for k, v in by_credibility.items()},
            "formatted": [{"url": s.url, "title": s.title} for s in sources[:5]],
        }
    
    def _summarize_hypotheses(self, hypotheses: List[Hypothesis]) -> Dict[str, Any]:
        """Summarize hypotheses."""
        if not hypotheses:
            return {"total": 0, "supported": 0, "refuted": 0}
        
        supported = sum(1 for h in hypotheses if h.status in ["supported", "partially_supported"])
        refuted = sum(1 for h in hypotheses if h.status in ["refuted", "unsubstantiated"])
        
        return {
            "total": len(hypotheses),
            "supported": supported,
            "refuted": refuted,
        }
    
    def _compute_confidence(self, facts: List[Fact], claims: List[Claim],
                           hypotheses: List[Hypothesis]) -> float:
        """Compute overall confidence in the research results."""
        scores = []
        
        # Factor 1: Fact confidence
        if facts:
            avg_fact_conf = sum(f.confidence for f in facts) / len(facts)
            scores.append(avg_fact_conf)
        
        # Factor 2: Claim support
        if claims:
            supported = sum(1 for c in claims if c.status == "supported")
            claim_ratio = supported / max(1, len(claims))
            scores.append(claim_ratio)
        
        # Factor 3: Hypothesis support
        if hypotheses:
            supported = sum(1 for h in hypotheses if h.status in ["supported", "partially_supported"])
            hyp_ratio = supported / max(1, len(hypotheses))
            scores.append(hyp_ratio)
        
        # Combine scores
        if scores:
            overall = sum(scores) / len(scores)
        else:
            overall = 0.5
        
        return round(min(1.0, max(0.0, overall)), 2)
    
    def _generate_summary(self, topic: str, fact_summary: Dict,
                          claim_summary: Dict, confidence: float) -> str:
        """Generate the report summary paragraph."""
        total_facts = fact_summary.get("total", 0)
        total_claims = claim_summary.get("total", 0)
        supported_claims = claim_summary.get("supported", 0)
        
        # Build summary
        parts = [f"Research on: {topic}"]
        
        if total_facts > 0:
            parts.append(f"{total_facts} factual statements extracted")
        
        if total_claims > 0:
            parts.append(f"{supported_claims} of {total_total_claims} claims supported" 
                        if total_claims > 0 else "")
        
        if confidence > 0.5:
            parts.append(f"Overall confidence: {confidence:.0%}")
        else:
            parts.append(f"Low confidence: {confidence:.0%} — further research recommended")
        
        return ". ".join(p for p in parts if p) + "."
    
    def _generate_key_findings(self, facts: List[Fact], claims: List[Claim]) -> List[str]:
        """Generate key findings from facts and claims."""
        findings = []
        
        if facts:
            # Top themes from facts
            all_text = " ".join(f.text for f in facts[:10])
            findings.append(f"Analyzed {len(facts)} source documents")
        
        if claims:
            supported = [c for c in claims if c.status == "supported"]
            if supported:
                findings.append(f"{len(supported)} claims are well-supported by evidence")
            contradicted = [c for c in claims if c.status == "contradicted"]
            if contradicted:
                findings.append(f"{len(contradicted)} claims have contradicting evidence")
        
        # Add confidence-based finding
        if facts:
            avg_conf = sum(f.confidence for f in facts) / len(facts)
            if avg_conf > 0.7:
                findings.append("High-confidence evidence found")
            elif avg_conf < 0.4:
                findings.append("Low-confidence evidence — verification recommended")
        
        return findings[:5]  # Limit to 5 findings
    
    def _format_sources(self, sources: List[Source]) -> List[Dict[str, Any]]:
        """Format sources for the report."""
        if not sources:
            return []
        
        formatted = []
        for i, source in enumerate(sources[:10], 1):
            formatted.append({
                "index": i,
                "url": source.url,
                "title": source.title or f"Source {i}",
                "credibility": source.credibility,
                "relevance": getattr(source, 'relevance', 0.5),
            })
        return formatted
    
    def _format_claims(self, claims: List[Claim]) -> List[Dict[str, Any]]:
        """Format claims for the report."""
        if not claims:
            return []
        
        formatted = []
        for claim in claims[:10]:
            formatted.append({
                "text": claim.text[:200] if claim.text else "",
                "status": claim.status,
                "confidence": claim.confidence,
                "evidence_count": len(claim.evidence_ids) if claim.evidence_ids else 0,
            })
        return formatted
    
    def _generate_conclusion(self, facts: List[Fact], claims: List[Claim],
                             hypotheses: List[Hypothesis]) -> str:
        """Generate the conclusion string."""
        conclusion_parts = []
        
        # Based on supported claims
        supported_claims = [c for c in claims if c.status == "supported"] if claims else []
        
        if supported_claims:
            conclusion_parts.append(
                f"{len(supported_claims)} key finding(s) are well-supported by evidence"
            )
        
        # Based on confidence
        if facts:
            avg_conf = sum(f.confidence for f in facts) / len(facts)
            if avg_conf > 0.7:
                conclusion_parts.append("High overall confidence in findings")
            elif avg_conf < 0.4:
                conclusion_parts.append("Low confidence — results should be treated as preliminary")
        
        # Based on hypotheses
        if hypotheses:
            supported_hyp = [h for h in hypotheses if h.status in ["supported", "partially_supported"]]
            if supported_hyp:
                conclusion_parts.append(
                    f"{len(supported_hyp)} hypothesis(es) best supported by evidence"
                )
        
        # Final statement
        if not conclusion_parts:
            conclusion_parts.append("Research completed — additional investigation recommended")
        
        return ". ".join(conclusion_parts) + "."