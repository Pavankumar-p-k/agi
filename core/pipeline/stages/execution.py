from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.pipeline.base import PipelineStage, StageOutcome, StageResult
from core.pipeline.context import PipelineContext
from core.pipeline.observation import Observation
from core.pipeline.outcome import Outcome

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Provider framework (unchanged)
# ═══════════════════════════════════════════════════════════════════════════════


class ProviderManager:
    def __init__(self) -> None:
        self._providers: list[Provider] = []

    def add_provider(self, provider: Provider, *, position: int | None = None) -> None:
        if position is None:
            self._providers.append(provider)
        else:
            self._providers.insert(position, provider)

    async def execute(self, prompt: str, **kwargs: Any) -> ProviderResult:
        errors: list[str] = []
        for provider in self._providers:
            try:
                return await provider.complete(prompt, **kwargs)
            except Exception as exc:
                logger.warning("Provider %s failed: %s", provider.name, exc)
                errors.append(f"{provider.name}: {exc}")
                continue
        return ProviderResult(
            text="",
            error="All providers failed:\n" + "\n".join(errors),
            provider="none",
        )


@dataclass
class ProviderResult:
    text: str
    error: str | None = None
    provider: str = ""
    tokens: int = 0


class Provider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    async def complete(self, prompt: str, **kwargs: Any) -> ProviderResult:
        ...


# ═══════════════════════════════════════════════════════════════════════════════
# Step executors (Phase 3 agent loop)
# ═══════════════════════════════════════════════════════════════════════════════


class StepExecutor(ABC):
    @abstractmethod
    async def execute(self, step: dict[str, Any], context: PipelineContext) -> dict[str, Any]:
        ...


class LLMStepExecutor(StepExecutor):
    def __init__(self, provider_manager: ProviderManager) -> None:
        self._provider_manager = provider_manager

    async def execute(self, step: dict[str, Any], context: PipelineContext) -> dict[str, Any]:
        objective = step.get("objective", "")
        prompt = f"{objective}\n\nContext:\n{context.raw_input}"
        result = await self._provider_manager.execute(prompt)
        return {
            "text": result.text,
            "provider": result.provider,
            "tokens": result.tokens,
            "step_intent": step.get("intent", ""),
        }


class Runtime:
    def __init__(self, provider_manager: ProviderManager) -> None:
        self._provider_manager = provider_manager
        self._executors: dict[str, type[StepExecutor]] = {}
        self._step_results: list[dict[str, Any]] = []
        self._observations: list[Observation] = []

    @property
    def step_results(self) -> list[dict[str, Any]]:
        return list(self._step_results)

    @property
    def observations(self) -> list[Observation]:
        return list(self._observations)

    def register(self, capability_id: str, executor_cls: type[StepExecutor]) -> None:
        self._executors[capability_id] = executor_cls

    async def execute_plan(
        self,
        plan: dict[str, Any],
        capability_bindings: dict[int, list[Any]],
        context: PipelineContext,
    ) -> str:
        steps = plan.get("steps", [])
        combined_text = ""
        self._step_results.clear()
        self._observations.clear()
        activity_mgr = _get_activity_manager(context)

        for i, step in enumerate(steps):
            step_intent = step.get("intent", "respond")
            step_objective = step.get("objective", "")

            subgoal_node = None
            if activity_mgr is not None and context.activity_id:
                root = activity_mgr.store.get_node(context.activity_id)
                if root:
                    subgoal_node = activity_mgr.create_subgoal(
                        root, step_objective or step_intent,
                        step_name=step_intent,
                    )

            caps = capability_bindings.get(i, [])
            executor = self._build_executor(step_intent, caps)

            if subgoal_node and activity_mgr:
                activity_mgr.store.update_node(subgoal_node)
            tool_node = None
            if subgoal_node and activity_mgr:
                tool_node = activity_mgr.create_tool_call(
                    subgoal_node, f"executor:{type(executor).__name__}",
                    input_data={"step": step},
                )

            result = await executor.execute(step, context)
            self._step_results.append(result)

            # Create Observation for this step
            obs = Observation.new(
                activity_id=context.activity_id or "",
                source="execution",
                type_="tool_output",
                payload=result,
                confidence=None,
                metadata={"step_index": i, "step_intent": step_intent, "executor": type(executor).__name__},
                parent_id=subgoal_node.node_id if subgoal_node else None,
                resource_scope=context.resource_scope,
                services=context.services,
            )
            self._observations.append(obs)

            if tool_node and activity_mgr:
                tool_node.status = _to_activity_status("completed", result.get("error"))
                tool_node.output = result
                tool_node.completed_at = datetime.utcnow()
                activity_mgr.store.update_node(tool_node)

            if subgoal_node and activity_mgr:
                subgoal_node.status = _to_activity_status("completed", result.get("error"))
                subgoal_node.output = result
                subgoal_node.completed_at = datetime.utcnow()
                activity_mgr.store.update_node(subgoal_node)

            if result.get("text"):
                if combined_text:
                    combined_text += "\n\n"
                combined_text += result["text"]

            if result.get("error"):
                logger.warning("Step %d (%s) error: %s", i, step_intent, result["error"])
                break

        return combined_text

    def _build_executor(self, intent: str, capabilities: list[Any]) -> StepExecutor:
        for cap in capabilities:
            cap_id = cap.id if hasattr(cap, "id") else str(cap)
            if cap_id in self._executors:
                return self._executors[cap_id]()
        return LLMStepExecutor(self._provider_manager)


def _to_activity_status(outcome: str, error: str | None) -> Any:
    from core.activity.models import ActivityStatus

    if error:
        return ActivityStatus.FAILED
    return ActivityStatus.COMPLETED


def _get_activity_manager(context: PipelineContext) -> Any | None:
    from core.activity.manager import ActivityManager

    return ActivityManager()


# ═══════════════════════════════════════════════════════════════════════════════
# ExecutionStage
# ═══════════════════════════════════════════════════════════════════════════════


class ExecutionStage(PipelineStage):
    def __init__(self) -> None:
        self.provider_manager = ProviderManager()
        self._runtime: Runtime | None = None

    @property
    def runtime(self) -> Runtime:
        if self._runtime is None:
            self._runtime = Runtime(self.provider_manager)
        return self._runtime

    @property
    def name(self) -> str:
        return "execution"

    def with_default_providers(self) -> ExecutionStage:
        try:
            self.provider_manager.add_provider(LiteLLMProvider())
        except Exception as exc:
            logger.warning("LiteLLM provider unavailable: %s", exc)
        try:
            self.provider_manager.add_provider(OllamaFallbackProvider())
        except Exception as exc:
            logger.warning("Ollama fallback provider unavailable: %s", exc)
        return self

    async def execute(self, context: PipelineContext) -> StageResult:
        raw_input = context.raw_input or ""
        plan = context.plan
        capabilities = context.selected_capabilities or {}

        if not raw_input.strip():
            return StageResult(outcome=StageOutcome.CONTINUE, context=context)

        if self._has_plan(plan, capabilities):
            return await self._execute_plan(context, plan, capabilities)

        return await self._execute_simple(context, raw_input)

    def _has_plan(self, plan: Any, capabilities: dict[int, Any]) -> bool:
        if plan is None:
            return False
        steps = plan.get("steps", [])
        return len(steps) > 0 and len(capabilities) > 0

    async def _execute_plan(
        self, context: PipelineContext, plan: dict[str, Any],
        capabilities: dict[int, list[Any]],
    ) -> StageResult:
        try:
            text = await self.runtime.execute_plan(plan, capabilities, context)
        except Exception as exc:
            logger.exception("Plan execution failed")
            context.execution_state = "failed"
            er = {
                "text": "",
                "provider": "runtime",
                "tokens": 0,
                "steps": self.runtime.step_results,
            }
            context.execution_result = er
            context.outcome = Outcome(
                success=False,
                outputs={"text": ""},
                tool_results=self.runtime.step_results,
                observations=self.runtime.observations,
                metrics={"provider": "runtime", "tokens": 0},
                activity_id=context.activity_id,
                errors=[f"Plan execution failed: {exc}"],
                resource_scope=context.resource_scope,
            )
            return StageResult(
                outcome=StageOutcome.FAIL, context=context,
                error=f"Plan execution failed: {exc}",
            )

        tokens = sum(s.get("tokens", 0) for s in self.runtime.step_results)
        context.execution_state = "completed"
        er = {
            "text": text,
            "provider": "pipeline",
            "tokens": tokens,
            "steps": self.runtime.step_results,
        }
        context.execution_result = er
        context.outcome = Outcome(
            success=True,
            outputs={"text": text},
            tool_results=self.runtime.step_results,
            observations=self.runtime.observations,
            metrics={"provider": "pipeline", "tokens": tokens},
            activity_id=context.activity_id,
            resource_scope=context.resource_scope,
        )
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)

    async def _execute_simple(self, context: PipelineContext, raw_input: str) -> StageResult:
        result = await self.provider_manager.execute(raw_input)
        er = {
            "text": result.text,
            "provider": result.provider,
            "tokens": result.tokens,
        }
        context.execution_result = er
        obs = Observation.new(
            activity_id=context.activity_id or "",
            source="execution",
            type_="text",
            payload={"text": result.text},
            confidence=None,
            metadata={"provider": result.provider, "tokens": result.tokens},
            resource_scope=context.resource_scope,
            services=context.services,
        )
        context.outcome = Outcome(
            success=result.error is None,
            outputs={"text": result.text},
            observations=[obs],
            metrics={"provider": result.provider, "tokens": result.tokens},
            activity_id=context.activity_id,
            errors=[result.error] if result.error else [],
            resource_scope=context.resource_scope,
        )
        if result.error:
            context.error = result.error
            context.execution_state = "failed"
            return StageResult(outcome=StageOutcome.FAIL, context=context, error=result.error)
        context.execution_state = "completed"
        return StageResult(outcome=StageOutcome.CONTINUE, context=context)


# ═══════════════════════════════════════════════════════════════════════════════
# Concrete provider implementations (unchanged)
# ═══════════════════════════════════════════════════════════════════════════════


class LiteLLMProvider(Provider):
    @property
    def name(self) -> str:
        return "litellm"

    async def complete(self, prompt: str, **kwargs: Any) -> ProviderResult:
        from core.llm_router import get_router, route_request

        model, tier, processed_query = route_request(prompt)
        model_group = "cloud" if model == "cloud" else "chat"

        messages = [
            {"role": "system", "content": "You are JARVIS, your AI assistant. Be concise."},
            {"role": "user", "content": processed_query},
        ]
        resp = await get_router().acompletion(
            model=model_group,
            messages=messages,
            timeout=kwargs.get("timeout", 60),
        )
        text = resp.choices[0].message.content if hasattr(resp, "choices") else str(resp)
        return ProviderResult(text=text, provider="litellm", tokens=0)


class OllamaFallbackProvider(Provider):
    @property
    def name(self) -> str:
        return "ollama_fallback"

    async def complete(self, prompt: str, **kwargs: Any) -> ProviderResult:
        import httpx

        from core.llm_router import get_ollama_url, model_for_role

        model_obj = model_for_role("chat")
        url = get_ollama_url(model_obj)
        payload = {
            "model": url.split("/")[-1].split(":")[0] if "/" in url else "llama3.1",
            "messages": [
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {
                "num_predict": 1024,
                "temperature": 0.7,
            },
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
            text = data.get("message", {}).get("content", "")
            return ProviderResult(text=text, provider="ollama", tokens=0)
