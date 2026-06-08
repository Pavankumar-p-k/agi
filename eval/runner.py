from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass

from eval.scenario import EvalScenario, ScenarioResult

logger = logging.getLogger(__name__)


@dataclass
class RunConfig:
    endpoint_url: str = ""
    model: str = ""
    headers: dict | None = None
    temperature: float = 0.3
    max_tokens: int = 4096
    max_rounds: int = 10
    max_tool_calls: int = 0
    context_length: int = 0
    session_id: str | None = None
    owner: str | None = None
    timeout: float = 300.0


async def run_scenario(
    scenario: EvalScenario,
    config: RunConfig,
) -> ScenarioResult:
    """Run a single eval scenario through the agent loop and capture its full trace."""
    from core.agent_loop import stream_agent_loop

    messages = [{"role": "user", "content": scenario.prompt}]

    effective_model = scenario.model_override or config.model
    effective_max_rounds = min(scenario.max_rounds, config.max_rounds)

    events: list[str] = []
    tool_calls: list[dict] = []
    full_response = ""
    metrics: dict | None = None
    error: str | None = None
    round_count = 0
    start = time.time()

    loop_kwargs = dict(
        endpoint_url=config.endpoint_url,
        model=effective_model,
        messages=messages,
        headers=config.headers or {},
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        max_rounds=effective_max_rounds,
        max_tool_calls=config.max_tool_calls,
        context_length=config.context_length,
        session_id=config.session_id,
        owner=config.owner,
    )
    loop_kwargs.update(scenario.extra_params)

    try:
        async for event in stream_agent_loop(**loop_kwargs):
            events.append(event)
            if event.startswith("data: ") and not event.startswith("data: [DONE]"):
                try:
                    data = json.loads(event[6:])
                    if data.get("type") == "tool_output":
                        tool_calls.append({
                            "tool": data.get("tool"),
                            "command": data.get("command"),
                            "output": data.get("output", ""),
                            "exit_code": data.get("exit_code"),
                        })
                    elif data.get("type") == "agent_step":
                        round_count = data.get("round", round_count)
                    elif data.get("type") == "metrics":
                        metrics = data.get("data")
                    elif data.get("type") == "error":
                        error = data.get("error")
                    elif "delta" in data:
                        pass
                except json.JSONDecodeError:
                    pass
    except asyncio.TimeoutError:
        error = f"Timed out after {config.timeout}s"
    except Exception as e:
        error = str(e)
        logger.exception("Eval scenario %s failed: %s", scenario.id, e)

    total_duration = time.time() - start

    for event in events:
        if not event.startswith("data: ") or event.startswith("data: [DONE]"):
            continue
        try:
            data = json.loads(event[6:])
            if "delta" in data:
                full_response += data["delta"]
        except (json.JSONDecodeError, IndexError):
            pass

    logger.info(
        "Scenario %s: %d rounds, %d tool calls, %.1fs, error=%s",
        scenario.id, round_count, len(tool_calls), total_duration, error or "none",
    )

    return ScenarioResult(
        scenario_id=scenario.id,
        prompt=scenario.prompt,
        full_response=full_response,
        tool_calls=tool_calls,
        round_count=round_count,
        total_duration=total_duration,
        events=events,
        error=error,
        metrics=metrics,
    )


async def run_scenarios(
    scenarios: list[EvalScenario],
    config: RunConfig,
    concurrency: int = 1,
) -> list[ScenarioResult]:
    """Run multiple scenarios, optionally with concurrency."""
    sem = asyncio.Semaphore(concurrency)

    async def _run_one(s: EvalScenario) -> ScenarioResult:
        async with sem:
            return await run_scenario(s, config)

    tasks = [_run_one(s) for s in scenarios]
    return await asyncio.gather(*tasks, return_exceptions=False)
