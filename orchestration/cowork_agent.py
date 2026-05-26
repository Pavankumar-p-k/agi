# orchestration/cowork_agent.py
"""Cowork Orchestrator Wrapper

Provides a higher‑level orchestrator that attempts to use CrewAI (or a similar
framework) if it is installed. If the import fails, it gracefully falls back to
the existing ``ToolCallingAgent`` which already works for single‑step tool calls.

The wrapper implements a ``run`` coroutine compatible with the existing code in
``core/main.py`` where ``_get_action_agent().run(message)`` is invoked.
"""

import logging
from typing import List, Any

logger = logging.getLogger(__name__)

# Try to import CrewAI – optional dependency.
try:
    from crewai import Crew, Agent, Task  # type: ignore
    HAS_CREWAI = True
    logger.info("CrewAI detected – will use it for multi‑step orchestration.")
except Exception as e:  # pragma: no cover – optional dependency may be missing
    HAS_CREWAI = False
    logger.info(f"CrewAI not available ({e}); falling back to ToolCallingAgent.")

if not HAS_CREWAI:
    # Fallback imports when CrewAI is not present
    from smolagents import ToolCallingAgent, LiteLLMModel  # type: ignore


class CoworkOrchestrator:
    """Unified orchestrator exposing a ``run`` coroutine.

    If CrewAI is available, a simple crew with a single agent is created. The ``run``
    method builds a temporary ``Task`` and executes the crew synchronously (the
    crew ``kickoff`` method is blocking, so we run it in a thread pool to keep the
    async contract).

    When CrewAI is not installed, the wrapper delegates to the original
    ``ToolCallingAgent`` which already knows how to call the individual tools.
    """

    def __init__(self, tools: List[Any] = None):
        self.tools = tools or []
        if HAS_CREWAI:
            # Build a minimal CrewAI agent. The agent can use the provided tools
            # for multi‑step execution. Tool definitions are passed via the ``tools``
            # argument (CrewAI will expose them for function calling).
            try:
                # Use the same LiteLLMModel for consistency with the existing
                # configuration.
                from smolagents import LiteLLMModel  # type: ignore
                model = LiteLLMModel(model_id="ollama/gemma4:e4b", api_base="http://localhost:11434")
            except Exception:
                model = None
            self.agent = Agent(
                role="JARVIS",
                goal="Assist the user with multi‑step tasks using available tools.",
                backstory="You are a personal AI assistant built by Pavan Kumar.",
                llm=model,
                tools=self.tools,
            )
            # Create a crew with the single agent. No explicit tasks are added –
            # we will create a temporary task at call time.
            self.crew = Crew(agents=[self.agent], tasks=[], verbose=False)

        else:
            # Fallback to the simple ToolCallingAgent used throughout the codebase.
            model = LiteLLMModel(model_id="ollama/gemma4:e4b", api_base="http://localhost:11434")
            self.fallback_agent = ToolCallingAgent(
                tools=self.tools,
                model=model,
                instructions=(
                    "You are JARVIS's action executor. You have full autonomy to decide which tools to use. "
                    "Identify and execute EVERY distinct action requested – do NOT stop after just one."
                ),
                max_steps=12,
            )

    def _handle_multi_step(self, message: str) -> Any:
        """Simple ad‑hoc multi‑step handling when CrewAI is unavailable.

        Detects a pattern like "search for X, summarize it, and email me".
        Performs:
        1️⃣ Search via search_fallback (SearXNG → DDGS).
        2️⃣ Summarize the first result using Ollama generate endpoint.
        3️⃣ Attempt to send an email via the Composio Gmail tool (if configured).

        Returns a dict compatible with the existing ``execute_action`` contract.
        """
        low = message.lower()
        if all(k in low for k in ("search", "summarize", "email")):
            import re, httpx
            from tools.search_fallback import search as search_web, format_results
            # Extract the query after "search for"
            m = re.search(r"search\s+for\s+([^,]+)", low)
            query = m.group(1).strip() if m else low.replace("search", "").strip()
            # ----- Step 1: Search -----
            results = search_web(query, max_results=3)
            if not results:
                return {"executed": True, "action": f"No search results found for: {query}"}
            top = results[0]
            content = top.get("content") or top.get("title") or ""
            # ----- Step 2: Summarize -----
            summary_prompt = f"Summarize the following text in a concise paragraph:\n\n{content}"
            try:
                resp = httpx.post(
                    "http://localhost:11434/api/generate",
                    json={"model": "gemma4:e4b", "prompt": summary_prompt, "stream": False, "options": {"temperature": 0.7}},
                    timeout=30,
                )
                summary = resp.json().get("response", "").strip()
            except Exception:
                summary = "(summary unavailable)"
            # ----- Step 3: Email (optional) -----
            email_result = None
            if self.fallback_agent:
                try:
                    # Use the gmail_send_email tool directly if composio is enabled
                    from core.main import gmail_send_email
                    email_result = gmail_send_email(to="user@example.com", subject="AI Paper Summary", body=summary)
                except Exception:
                    email_result = None
            action_msg = f"Summary: {summary}"
            if email_result:
                action_msg += f" | Email result: {email_result}"
            return {"executed": True, "action": action_msg}
        return None

    def run(self, message: str) -> Any:
        """Execute ``message`` using the orchestrator.

        Returns the raw result from the underlying engine – a string for the
        fallback agent or the CrewAI ``Task`` result when CrewAI is active.
        """
        if HAS_CREWAI:
            # Create a temporary CrewAI Task and run it synchronously.
            task = Task(description=message, expected_output="Result")
            # ``crew.kickoff`` is a blocking call, so we invoke it directly.
            result = self.crew.kickoff([task])
            # ``kickoff`` returns a list of results; return the first entry if possible.
            if isinstance(result, list) and result:
                return result[0]
            return result
        else:
            # Try simple multi‑step handling before falling back to the tool agent.
            multi = self._handle_multi_step(message)
            if multi is not None:
                return multi
            # ``ToolCallingAgent.run`` is synchronous, so call it directly.
            return self.fallback_agent.run(message)
