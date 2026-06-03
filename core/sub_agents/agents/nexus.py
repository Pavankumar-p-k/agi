import logging
import time
from typing import Optional
from core.sub_agents.base_agent import SubAgent, AgentResult

logger = logging.getLogger("jarvis.agents.nexus")

RESEARCH_TRIGGERS = [
    "research", "find out", "deep dive", "investigate", "what is the latest",
    "summarize everything about", "report on", "analyze", "comprehensive",
    "analyze deeply", "find everything", "full analysis"
]

def _should_use_deep_research(query: str) -> bool:
    q = query.lower()
    return any(trigger in q for trigger in RESEARCH_TRIGGERS)

NEXUS_PROMPTS = {
    "research": (
        "You are NEXUS, a deep research sub-agent inside Jarvis — a personal AI OS built by Pavan, "
        "an independent developer in India. Your role: conduct exhaustive, structured research on any topic. "
        "Always output: 1) Executive Summary (2-3 sentences), 2) Key Findings (numbered, dense), "
        "3) Critical Gaps or Caveats, 4) Recommended Next Steps. "
        "Be precise, cite reasoning chains, use technical depth. No fluff. Think like a research scientist."
    ),
    "synthesize": (
        "You are NEXUS running in Synthesis Mode inside Jarvis — Pavan's personal AI OS. "
        "Your role: take any input topic or set of concepts and synthesize a coherent, multi-layered understanding. "
        "Output: 1) Core Synthesis (the unified insight), 2) Tension Points (where ideas conflict), "
        "3) Emergent Patterns, 4) Synthesis Confidence score (0-100). Think like a systems theorist."
    ),
    "compare": (
        "You are NEXUS running in Comparative Analysis Mode inside Jarvis — Pavan's personal AI OS. "
        "Your role: rigorously compare two or more entities, approaches, or ideas. "
        "Output structured markdown: Header, Comparison Matrix (dimensions vs subjects), "
        "Winner per dimension with reasoning, Overall Verdict. Be ruthlessly objective."
    ),
    "brief": (
        "You are NEXUS running in Intelligence Brief Mode inside Jarvis — Pavan's personal AI OS. "
        "Your role: produce concise, high-signal intelligence briefs. "
        "Format: [BRIEF] header, 5 bullet points max, each under 20 words, "
        "one critical risk or opportunity at the end. "
        "Imagine you're briefing a technical founder who has 60 seconds."
    ),
}

class NexusAgent(SubAgent):
    NAME = "NEXUS"
    DESCRIPTION = "Deep research, synthesis, comparison, and intelligence briefs"
    DEFAULT_MODE = "research"
    AVAILABLE_MODES = ["research", "synthesize", "compare", "brief"]
    MODEL_GROUP = "analysis"
    MAX_TOKENS = 2000

    def get_system_prompt(self, mode: str) -> str:
        return NEXUS_PROMPTS.get(mode, NEXUS_PROMPTS["research"])

    async def run(self, task: str, mode: Optional[str] = None, **kwargs) -> AgentResult:
        user_id = kwargs.get("user_id") or "default"
        
        # 1. Retrieve relevant memories
        from memory.mem0_adapter import mem0_memory
        relevant_memories = mem0_memory.search(task, user_id=user_id, limit=3)
        memory_context = mem0_memory.format_context(relevant_memories)
        
        # Add memory context to task if it exists
        enhanced_task = task
        if memory_context:
            enhanced_task = f"{memory_context}\n\nUser Task: {task}"

        # 2. Check for Deep Research trigger
        if _should_use_deep_research(task):
            self.status = "running"
            start_time = time.time()
            from tools.deep_research import deep_research
            
            try:
                logger.info(f"[{self.NAME}:{self.id}] Triggering Deep Research for: {task[:60]}...")
                result = await deep_research(task, rounds=8, max_sources=12)
                
                # Format as agent response
                response_text = f"""# Research Report: {task}

## Summary
{result.get('summary', 'No summary available')}

## Key Findings
{chr(10).join(f"- {f}" for f in result.get('key_findings', []))}

## Sources ({len(result.get('sources', []))} found)
{chr(10).join(f"- {s.get('url', s.get('title', 'Unknown'))}" for s in result.get('sources', [])[:8])}

*Confidence: {result.get('confidence', 0):.0%} | Rounds: {result.get('rounds_completed', 0)}*"""

                self._result = AgentResult(
                    agent_id=self.id,
                    agent_name=self.NAME,
                    mode=mode or self.DEFAULT_MODE,
                    input=task,
                    output=response_text,
                    success=True,
                    duration_s=time.time() - start_time,
                    token_estimate=0,
                )
                self.status = "done"
            except Exception as e:
                logger.error(f"[{self.NAME}:{self.id}] Deep Research failed: {e}")
                self._result = AgentResult(
                    agent_id=self.id, agent_name=self.NAME, mode=mode or self.DEFAULT_MODE,
                    input=task, output="", success=False,
                    duration_s=time.time() - start_time, token_estimate=0, error=str(e),
                )
                self.status = "failed"
        else:
            # Standard LLM call via base class
            self._result = await super().run(enhanced_task, mode=mode, **kwargs)
            # Restore original input in result for consistency
            if self._result:
                self._result.input = task

        # 3. Store the exchange in memory
        if self._result and self._result.success:
            mem0_memory.add(
                [{"role": "user", "content": task}, {"role": "assistant", "content": self._result.output}],
                user_id=user_id,
            )

        return self._result
