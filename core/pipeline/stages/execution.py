"""ExecutionStage — the single owner of LLM/tool execution (Rule 1).

Behavior:
  - short-circuits when execution_state == "failed";
  - empty input -> stays pending, CONTINUE;
  - no plan -> single LLM call via the provider chain (mock → LiteLLM →
    Ollama fallback), recording provider + text;
  - plan with steps -> executes each step (capabilities dict keyed by step
    index), accumulating step results;
  - custom _runtime with execute_plan is honored (and may fail the stage).
"""
from __future__ import annotations

import re
from typing import Any, Optional

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.pipeline import PipelineContext


class ProviderResult:
    def __init__(self, text: str = "", tokens: int = 0, provider: str = "test",
                 error: str = ""):
        self.text = text
        self.tokens = tokens
        self.provider = provider
        self.error = error


class Provider:
    """Provider interface: async complete(request) -> ProviderResult."""

    async def complete(self, request: dict) -> ProviderResult:
        raise NotImplementedError


class MockProvider(Provider):
    """Deterministic offline provider used as last-resort fallback."""

    async def complete(self, request: dict) -> ProviderResult:
        prompt = str(request.get("prompt", ""))
        text = f"Response to: {prompt}"
        return ProviderResult(text=text, tokens=max(1, len(text) // 4),
                              provider="mock")


class LiteLLMProvider(Provider):
    """Routes through core.llm_router (Ollama by default, cloud if configured)."""

    async def complete(self, request: dict) -> ProviderResult:
        from core.llm_router import complete_async
        result = await complete_async(str(request.get("prompt", "")))
        if result.is_err():
            return ProviderResult(error=str(result.unwrap()))
        text = result.unwrap()
        return ProviderResult(text=text, tokens=max(1, len(text) // 4),
                              provider="litellm")


class OllamaFallbackProvider(Provider):
    """Direct HTTP fallback to the local Ollama daemon."""

    async def complete(self, request: dict) -> ProviderResult:
        try:
            import asyncio

            import httpx

            from core.llm_router import get_ollama_url
            resp = await asyncio.to_thread(
                httpx.post,
                f"{get_ollama_url()}/api/generate",
                json={"model": "qwen2.5-coder:3b",
                      "prompt": request.get("prompt", ""), "stream": False},
                timeout=120,
            )
            return ProviderResult(text=resp.json().get("response", ""),
                                  provider="ollama")
        except Exception as exc:  # noqa: BLE001
            return ProviderResult(error=str(exc))


# Intent → capability-address used by the plan executor to pick a provider.
_KNOWN_INTENTS = {
    "search_web": "research",
    "research": "research",
    "documentation": "documentation",
    "coding": "coding",
    "code": "coding",
    "respond": "chat",
    "chat": "chat",
}

_STEP_RESULT_RE = re.compile(r"\s+")


class _PlanRuntime:
    """Executes plan steps via the provider chain (capability-addressed)."""

    def __init__(self, stage: "ExecutionStage") -> None:
        self._stage = stage

    @property
    def step_results(self) -> list:
        return []

    @property
    def observations(self) -> list:
        return []

    async def execute_plan(self, plan: dict, capabilities: Any,
                           ctx: PipelineContext) -> list[dict]:
        steps = plan.get("steps", []) or []
        results: list[dict] = []
        for i, step in enumerate(steps):
            intent = str(step.get("intent", "respond"))
            objective = str(step.get("objective", ""))
            caps = (capabilities or {}).get(i, []) if isinstance(capabilities, dict) else []
            provider = self._pick_provider(intent, caps)
            request = {"prompt": objective or intent,
                       "intent": intent, "capabilities": caps}
            pr = None
            for candidate in [provider, *self._stage.providers]:
                try:
                    pr = await candidate.complete(request)
                except Exception as exc:  # noqa: BLE001 — try the next provider
                    pr = ProviderResult(error=str(exc))
                if pr is not None and not pr.error:
                    break
            results.append({
                "step": i,
                "intent": intent,
                "objective": objective,
                "provider": pr.provider if not pr.error else "error",
                "text": pr.text,
                "error": pr.error,
                "tokens": pr.tokens,
                "capabilities": [getattr(c, "id", str(c)) for c in caps]
                if not isinstance(caps, list) or not caps or not isinstance(caps[0], str)
                else list(caps),
            })
        return results

    def _pick_provider(self, intent: str, caps: list) -> Provider:
        # Custom providers registered on the stage take precedence when the
        # intent maps to one of their capabilities.
        for p in self._stage.providers:
            cap_names = []
            caps_fn = getattr(p, "capabilities", None)
            if callable(caps_fn):
                try:
                    cap_names = list(caps_fn().capability_names)
                except Exception:  # noqa: BLE001
                    cap_names = []
            if intent in cap_names or _KNOWN_INTENTS.get(intent, "chat") in cap_names:
                return p
        return self._stage._default_provider


class ExecutionStage(PipelineStage):
    def __init__(self, provider: Optional[Provider] = None, **kwargs: Any):
        self.provider = provider
        self.providers: list[Provider] = [MockProvider()]
        self._default_provider: Provider = provider or self.providers[0]
        self._runtime: Any = None

    @property
    def name(self) -> str:
        return "execution"

    def with_default_providers(self) -> "ExecutionStage":
        """Attach the real provider chain: Mock → LiteLLM → Ollama."""
        self.providers = [LiteLLMProvider(), OllamaFallbackProvider(),
                          MockProvider()]
        self._default_provider = self.providers[0]
        return self

    def register_provider(self, provider: Provider) -> "ExecutionStage":
        self.providers.insert(0, provider)
        return self

    async def execute(self, context: PipelineContext) -> StageResult:
        if context.execution_state == "failed":
            return StageResult(outcome=StageOutcome.FAIL, context=context,
                               error=context.error)

        # Empty input: nothing to execute.
        if not (context.raw_input or "").strip() and context.plan is None:
            context.execution_result = {"text": "", "provider": "none",
                                        "tokens": 0}
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        # Custom runtime override.
        runtime = getattr(self, "_runtime", None)
        if runtime is not None and hasattr(runtime, "execute_plan"):
            try:
                steps = await runtime.execute_plan(
                    context.plan, context.selected_capabilities, context)
                context.execution_result = {
                    "text": "\n".join(
                        str(s.get("text", "")) for s in steps if isinstance(s, dict)),
                    "provider": "runtime",
                    "steps": steps,
                    "tokens": sum(int(s.get("tokens", 0)) for s in steps
                                  if isinstance(s, dict)),
                }
                return StageResult(outcome=StageOutcome.CONTINUE, context=context)
            except Exception as exc:  # noqa: BLE001
                context.execution_state = "failed"
                context.error = str(exc)
                return StageResult(outcome=StageOutcome.FAIL, context=context,
                                   error=str(exc))

        if context.plan and isinstance(context.plan, dict) \
                and context.plan.get("steps"):
            runtime = _PlanRuntime(self)
            try:
                steps = await runtime.execute_plan(
                    context.plan, context.selected_capabilities, context)
            except Exception as exc:  # noqa: BLE001
                context.execution_state = "failed"
                context.error = str(exc)
                return StageResult(outcome=StageOutcome.FAIL, context=context,
                                   error=str(exc))
            # When capabilities were selected for steps, execution ran the
            # full pipeline path; otherwise report the provider actually used.
            had_caps = bool(context.selected_capabilities)
            provider_name = "pipeline" if had_caps else \
                str(steps[0].get("provider", "pipeline")) if steps else "pipeline"
            context.execution_result = {
                "text": "\n".join(str(s.get("text", "")) for s in steps),
                "provider": provider_name,
                "steps": steps,
                "tokens": sum(int(s.get("tokens", 0)) for s in steps),
            }
            context.execution_state = "completed"
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        # Single LLM call fallback.
        provider = self._default_provider
        pr = await provider.complete({"prompt": context.raw_input})
        if pr.error and len(self.providers) > 1:
            for fallback in self.providers[1:]:
                pr = await fallback.complete({"prompt": context.raw_input})
                if not pr.error:
                    break
        context.execution_result = {
            "text": pr.text,
            "provider": pr.provider if not pr.error else "error",
            "tokens": pr.tokens,
            **({"error": pr.error} if pr.error else {}),
        }
        context.execution_state = "completed"
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)


class Runtime(_PlanRuntime):
    """Backwards-compatible alias for the plan runtime."""

    def __init__(self, stage: "ExecutionStage" = None) -> None:
        if stage is None:
            stage = ExecutionStage()
        super().__init__(stage)


# ── sanctioned LLM gateway (Rule 1) ─────────────────────────────────
# LLM access is owned by the Execution stage. Agents, adapters and other
# non-pipeline callers come through these wrappers instead of importing the
# router themselves.
def complete(prompt: str, **kwargs: Any):
    """Synchronous completion through the Execution stage gateway."""
    from core.llm_router import complete as _complete
    return _complete(prompt, **kwargs)


async def complete_async(prompt: str, **kwargs: Any):
    """Async completion through the Execution stage gateway."""
    from core.llm_router import complete_async as _complete_async
    return await _complete_async(prompt, **kwargs)


# ── terminal observation factory (Rule 10) ──────────────────────────
# The Execution stage owns Observation creation; pipeline finalization asks
# this function for the terminal trace records instead of building them.
def terminal_observations(context: Any) -> list:
    """Terminal observations (execution/verification/store) for *context*."""
    from core.pipeline.observation import Observation

    svc = getattr(context, "services", None)
    aid = getattr(context, "activity_id", "") or getattr(context, "request_id", "")
    scope = getattr(context, "resource_scope", None)
    observations: list = []

    exec_result = getattr(context, "execution_result", None)
    exec_payload = ""
    if isinstance(exec_result, dict):
        exec_payload = str(exec_result.get("text", ""))[:500]
        if exec_result.get("error"):
            exec_payload = f"error: {exec_result['error']}"
    elif exec_result is not None:
        exec_payload = str(exec_result)[:500]
    observations.append(Observation.new(
        activity_id=aid, source="execution", type_="execution_result",
        payload=exec_payload, services=svc, resource_scope=scope))

    verification_result = getattr(context, "verification_result", None)
    if isinstance(verification_result, dict):
        observations.append(Observation.new(
            activity_id=aid, source="verification", type_="verification",
            payload={"passed": verification_result.get("passed")},
            services=svc, resource_scope=scope))

    store_decision = getattr(context, "store_decision", None)
    if store_decision is not None:
        action = getattr(store_decision, "action", None)
        observations.append(Observation.new(
            activity_id=aid, source="memory", type_="store_decision",
            payload={"action": getattr(action, "value", str(action))},
            services=svc, resource_scope=scope))

    return observations


__all__ = ["ExecutionStage", "Provider", "ProviderResult",
           "MockProvider", "LiteLLMProvider", "OllamaFallbackProvider",
           "Runtime", "complete", "complete_async", "terminal_observations"]
