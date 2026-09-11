"""
Module: core.research.__init__
Research AI internal components and specialist interface.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from core.research.models import (
    ResearchTask,
    ResearchPlan,
    ResearchStep,
    Source,
    Evidence,
    Claim,
    Fact,
    Hypothesis,
    ResearchResult,
    ResearchReport,
    ResearchConfidence,
    ResearchError,
    Belief,
    BeliefState,
    Conclusion,
    CounterHypothesis,
)

from core.research.graph_models import (
    GraphNode,
    GraphEdge,
    EdgeType,
    KnowledgeGraph,
)

from core.research.extractor import Extractor

from core.research.evidence_tracker import EvidenceTracker

from core.research.linker import Linker

from core.research.planner import ResearchPlanner, ResearchPlan, ResearchStep, uuid4

from core.research.reasoner import FactReasoner, ComparisonEngine

from core.research.reasoning import (
    ReasoningEngine,
    BeliefStateTracker,
    ArgumentMapper,
)

from core.research.hypothesis import Hypothesis, HypothesisGenerator

from core.research.knowledge_graph import KnowledgeGraphManager

from core.research.graph_store import GraphStore

from core.research.synthesizer import Synthesizer, FactSynthesizer, ResearchReport

from core.research.reflection import ResearchReflection

from core.research.storage import ResearchStorage

from core.research.retriever import Retriever

from core.research.benchmark import ResearchBenchmark

from core.research.research_benchmark import ResearchBenchmark as ResearchBench

__all__ = [
    "ResearchTask",
    "ResearchPlan",
    "ResearchStep",
    "Source",
    "Evidence",
    "Claim",
    "Fact",
    "Hypothesis",
    "ResearchResult",
    "ResearchReport",
    "ResearchConfidence",
    "ResearchError",
    "Belief",
    "BeliefState",
    "Conclusion",
    "CounterHypothesis",
    "GraphNode",
    "GraphEdge",
    "EdgeType",
    "KnowledgeGraph",
    "KnowledgeGraphManager",
    "Extractor",
    "EvidenceTracker",
    "Linker",
    "ResearchPlanner",
    "FactReasoner",
    "ComparisonEngine",
    "ReasoningEngine",
    "BeliefStateTracker",
    "ArgumentMapper",
    "Hypothesis",
    "HypothesisGenerator",
    "Synthesizer",
    "FactSynthesizer",
    "ResearchReport",
    "ResearchReflection",
    "ResearchStorage",
    "Retriever",
    "ResearchBenchmark",
    "ResearchBench",
]


# Research AI public interface class
class ResearchAI:
    """Main specialist interface for Research AI capability.
    
    Provides a unified interface for the Super-Brain to access research capabilities
    without needing to understand the internal 22-module architecture.
    """
    
    def __init__(self):
        self.storage = ResearchStorage()
        self.reflection = ResearchReflection()
        self.benchmark = ResearchBenchmark()
        self._synthesizer = Synthesizer()
        self._extractor = Extractor()
        self._retriever = Retriever()
        self._linker = Linker()
        self._planner = ResearchPlanner()
        self._reasoner = FactReasoner()
        self._knowledge_graph = KnowledgeGraphManager()
        self._graph_store = GraphStore()
    
    def research(self, query: str, task_description: str = "",
                 max_sources: int = 15, max_rounds: int = 8) -> Dict[str, Any]:
        """Perform research on a given query or task.
        
        Args:
            query: The research question or goal
            task_description: Optional detailed task description
            max_sources: Maximum number of sources to gather
            max_rounds: Maximum research rounds/iterations
        
        Returns:
            Dictionary with research results including summary, findings, sources, confidence
        """
        import asyncio
        
        # Run the async research pipeline
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If already running, create task
                task = loop.create_task(
                    self._aresearch(query, task_description, max_sources, max_rounds)
                )
                # We'll return a pending result for now
                return {
                    "status": "research_in_progress",
                    "query": query,
                    "message": "Research started asynchronously"
                }
            else:
                return loop.run_until_complete(
                    self._aresearch(query, task_description, max_sources, max_rounds)
        except Exception as e:
            logger.error(f"Research AI error: {e}", exc_info=True)
            return {
                "status": "error",
                "query": query,
                "error": str(e),
                "overall_confidence": 0.0,
            }
    
    async def _aresearch(self, query: str, task_description: str,
                         max_sources: int, max_rounds: int) -> Dict[str, Any]:
        """Async research pipeline."""
        from core.llm_core import complete_text
        
        # Step 1: Plan - break into sub-questions
        plan_prompt = (
            f"You are a research planner. Break this question into 3-5 specific, diverse sub-questions "
            f"that will help provide a comprehensive answer: {query}\n"
            "Return a simple bulleted list of questions."
        )
        res = await complete_text(plan_prompt, model="ollama/qwen2.5-coder:3b")
        if res.is_err():
            raise res.unwrap_err()
        plan_text = res.unwrap()
        sub_questions = []
        for line in plan_text.split('\n'):
            import re
            q_match = re.search(r"[-*•]\s*(.*)", line)
            if q_match:
                sub_questions.append(q_match.group(1).strip())
        
        if not sub_questions:
            sub_questions = [query]
        
        # Step 2: Retrieve - gather sources
        retrieval_result = await self._retriever.research(
            query, max_sources=max_sources, max_rounds=max_rounds
        )
        
        # Step 3: Extract - extract facts from sources
        all_facts = []
        raw_pages = retrieval_result.get("raw_pages", [])
        for page_content in raw_pages[:10]:
            if not page_content or len(page_content) < 50:
                continue
            facts = self._extractor.extract_from_text(
                page_content, 
                retrieval_result.get("sources", [{}])[0].get("url", ""),
                retrieval_result.get("sources", [{}])[0].get("title", ""),
                query
            )
            all_facts.extend(facts)
        
        # Step 4: Create claims from facts
        claims = []
        for fact in all_facts[:20]:  # Limit to top 20 facts
            claim = Claim(
                text=fact.text[:200],
                source_url=fact.source_url,
                source_title=fact.source_title,
                confidence=fact.confidence,
            )
            claims.append(claim)
            self._linker.link_facts_to_claims([fact], claim_text=fact.text)
        
        # Step 5: Evaluate claims
        for claim in claims:
            self._reasoner.evaluate_evidence(claim)
        
        # Step 6: Synthesize report
        report = self._synthesizer.synthesize(
            topic=query,
            facts=all_facts[:10],  # Top 10 facts
            claims=claims,
            sources=retrieval_result.get("sources", []),
        )
        
        # Step 7: Reflect and learn
        research_result = ResearchResult(
            id=f"res_{query[:50]}",
            query=query,
            summary=report.summary,
            key_findings=report.key_findings,
            sources=report.sources,
            claims=report.claims,
            overall_confidence=report.overall_confidence,
            status="completed",
        )
        
        self.storage.save_result(research_result)
        self.reflection.record_research(research_result)
        
        return {
            "status": "completed",
            "summary": report.summary,
            "key_findings": report.key_findings,
            "sources": report.sources,
            "claims": [
                {"text": c.text, "status": c.status, "confidence": c.confidence}
                for c in report.claims
            ],
            "overall_confidence": report.overall_confidence,
            "confidence": report.overall_confidence,
        }