"""parallel_agents.py — Demo of JARVIS sub-agent system.

Simulates parallel agent dispatch without needing real LLM calls.
Shows the orchestration pattern: a task is analyzed, split, dispatched
to specialized agents, and results are merged.

Usage:
    python -m demo.parallel_agents
"""
from __future__ import annotations

import asyncio
import time


async def agent_nexus(task: str) -> dict:
    await asyncio.sleep(0.3)
    return {"agent": "nexus", "result": f"Integrated dependencies for: {task}"}


async def agent_forge(task: str) -> dict:
    await asyncio.sleep(0.5)
    return {"agent": "forge", "result": f"Generated code skeleton for: {task}"}


async def agent_atlas(task: str) -> dict:
    await asyncio.sleep(0.4)
    return {"agent": "atlas", "result": f"Researched background for: {task}"}


async def agent_oracle(task: str) -> dict:
    await asyncio.sleep(0.2)
    return {"agent": "oracle", "result": f"Planned execution steps for: {task}"}


async def main() -> None:
    task = "Build a REST API for a todo app"

    print("=" * 60)
    print("  JARVIS Parallel Sub-Agent Demo")
    print("=" * 60)
    print(f"\n  Task: \"{task}\"")
    print(f"  Dispatching to 4 agents in parallel...\n")

    start = time.time()

    results = await asyncio.gather(
        agent_nexus(task),
        agent_forge(task),
        agent_atlas(task),
        agent_oracle(task),
    )

    elapsed = time.time() - start

    for r in results:
        print(f"  [{r['agent'].upper()}] {r['result']}")

    print(f"\n  All {len(results)} agents completed in {elapsed:.2f}s")
    print(f"  (Sequential would take ~1.4s — parallel is {1.4/elapsed:.1f}x faster)")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
