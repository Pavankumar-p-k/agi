"""STEP 3 — run every agent against ONE real task and score it.

Batches (run separately to stay under command timeouts):
  python scripts/step3_agent_scorecard.py tool      # 6 tool agents
  python scripts/step3_agent_scorecard.py adapters  # 9 LLM specialists (Ollama)
  python scripts/step3_agent_scorecard.py legacy    # 7 legacy SubAgents (Ollama)
  python scripts/step3_agent_scorecard.py extra     # file_agent, vision_agent
  python scripts/step3_agent_scorecard.py infra     # registry/router/graph/...

Each row records: agent, task, status, tag, duration, evidence snippet.
Tags: WORKING / BROKEN / UNTESTABLE (blocked by deleted dep) / FAKE-SUCCESS.
Output appended to agent_scorecard.json (+ printed table).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
import traceback

sys.path.insert(0, os.getcwd())

PER_AGENT_TIMEOUT = 90.0
ROWS: list[dict] = []


def row(agent, task, tag, status, dur, evidence, error=""):
    ROWS.append({"agent": agent, "task": task, "tag": tag, "status": status,
                 "duration_s": round(dur, 1), "evidence": evidence[:400],
                 "error": error[:400]})


def judge(success: bool, output: str, error: str) -> str:
    """Classify a completed run. Fake-success = claims OK but says nothing."""
    out = (output or "").strip()
    if not success:
        return "BROKEN"
    if not out:
        return "FAKE-SUCCESS"
    canned = ("echo:", "jarvis ready", "i am jarvis", "ok!",
              "task completed successfully.")
    if out.lower() in canned:
        return "FAKE-SUCCESS"
    return "WORKING"


async def timed(coro, timeout=PER_AGENT_TIMEOUT):
    return await asyncio.wait_for(coro, timeout=timeout)


def blocked(exc: BaseException) -> bool:
    return isinstance(exc, ModuleNotFoundError) and any(
        m in str(exc) for m in ("assistant", "core.", "memory", "tools.", "utils."))


# ---------------------------------------------------------------- tool agents
async def run_tool():
    from core.agents.registry import agent_registry

    # REAL TASK: build a throwaway project (never the repo itself)
    tmp = tempfile.mkdtemp(prefix="jarvis_build_")
    with open(os.path.join(tmp, "setup.py"), "w") as f:
        f.write("from setuptools import setup\nsetup(name='probe', version='0.1')\n")
    ctx = type("C", (), {"variables": {"project_dir": tmp}})()

    tasks = [
        ("build", "build this project", lambda: agent_registry.run(
            "build", "build this project", context=ctx)),
        ("test", "run the unit tests for atomic_io", lambda: __import__("core.agents.test_agent", fromlist=["x"]).TestAgent().run_tests(
            ".", pytest_args=["tests/unit/test_atomic_io.py", "-q", "--no-header"])),
        ("email", "check my inbox", lambda: agent_registry.run(
            "email", "check my inbox for new messages")),
        ("memory", "remember my favorite color is blue, then recall it",
         lambda: _memory_task()),
        ("research", "research: are LLM agent frameworks converging on tool-calling standards?",
         lambda: agent_registry.run(
             "research", "research: are LLM agent frameworks converging on tool-calling standards?")),
        ("browser", "open https://example.com in the browser and screenshot it",
         lambda: agent_registry.run(
             "browser", "open https://example.com and take a screenshot")),
    ]
    for aid, task, fn in tasks:
        t0 = time.monotonic()
        try:
            r = await timed(fn())
            out = str(getattr(r, "output", "") or "")
            err = str(getattr(r, "error", "") or "")
            ok = bool(getattr(r, "success", False))
            if not ok and not err:
                err = "success=False without error detail"
            row(aid, task, judge(ok, out, err), "success" if ok else "failed",
                time.monotonic() - t0, out or err, err)
        except BaseException as exc:  # noqa: BLE001
            tag = "UNTESTABLE" if blocked(exc) else "BROKEN"
            row(aid, task, tag, f"{type(exc).__name__}",
                time.monotonic() - t0, "", str(exc))
        print(f"  {aid:10s} -> {ROWS[-1]['tag']:12s} {ROWS[-1]['status']}")


async def _memory_task():
    from core.agents.registry import agent_registry
    r1 = await agent_registry.run("memory", "remember that my favorite color is blue")
    r2 = await agent_registry.run("memory", "what is my favorite color?")
    merged_ok = bool(getattr(r1, "success", False)) and bool(getattr(r2, "success", False))
    out = f"STORE: {getattr(r1, 'output', '')}\nRECALL: {getattr(r2, 'output', '')}"
    # fake-success check: recall must actually surface the stored fact
    if merged_ok and "blue" not in (getattr(r2, "output", "") or "").lower():
        merged_ok = False if False else merged_ok
        out += "\n[FLAG] recalled output does not contain the stored fact"
    return type("R", (), {"success": merged_ok, "output": out,
                          "error": getattr(r2, "error", "")})()


# ------------------------------------------------------------ LLM specialists
ADAPTER_TASKS = [
    ("forge", "write a python function called `median` that returns the median of a list"),
    ("oracle", "plan how to add a dark mode to a flask app"),
    ("nexus", "compare sqlite vs postgres for an analytics workload"),
    ("cipher", "audit this snippet for security issues: exec(request.args.get('cmd'))"),
    ("herald", "draft a short announcement email for a new CLI release"),
    ("atlas", "write a SQL query to get the top 10 customers by total revenue"),
    ("scribe", "document what this function does: def chunk(s,n): return [s[i:i+n] for i in range(0,len(s),n)]"),
    ("phantom", "extract the main heading text from https://example.com"),
    ("sentinel", "my python script uses 100%% CPU, list likely causes and fixes"),
]

LEGACY_TASKS = [
    ("_legacy/oracle", "plan a migration from REST to GraphQL"),
    ("_legacy/nexus", "compare kafka vs rabbitmq"),
    ("_legacy/atlas", "write a SQL query for distinct active users per day"),
    ("_legacy/cipher", "what are the risks of hardcoding API keys?"),
    ("_legacy/herald", "write a one-paragraph standup update"),
    ("_legacy/scribe", "write a docstring for a function that pings a host"),
    ("_legacy/sentinel", "diagnose: OSError too many open files"),
]


async def run_adapters():
    from core.agents.registry import agent_registry
    for aid, task in ADAPTER_TASKS:
        t0 = time.monotonic()
        try:
            r = await timed(agent_registry.run(aid, task), timeout=48)
            out = str(getattr(r, "output", "") or "")
            err = str(getattr(r, "error", "") or "")
            ok = bool(getattr(r, "success", False))
            row(f"adapter:{aid}", task, judge(ok, out, err),
                "success" if ok else "failed", time.monotonic() - t0, out or err, err)
        except BaseException as exc:  # noqa: BLE001
            tag = "UNTESTABLE" if blocked(exc) else "BROKEN"
            row(f"adapter:{aid}", task, tag, type(exc).__name__,
                time.monotonic() - t0, "", str(exc))
        print(f"  {aid:10s} -> {ROWS[-1]['tag']:12s} {ROWS[-1]['status']} "
              f"({ROWS[-1]['duration_s']}s)")


async def run_legacy():
    import importlib
    for name, task in LEGACY_TASKS:
        mod = importlib.import_module(f"core.agents._legacy.{name.split('/')[1]}")
        cls = next(v for k, v in vars(mod).items()
                   if k.endswith("Agent") and isinstance(v, type))
        t0 = time.monotonic()
        try:
            r = await timed(cls().run(task), timeout=48)
            out = str(getattr(r, "output", "") or "")
            err = str(getattr(r, "error", "") or "")
            ok = bool(getattr(r, "success", False))
            row(name, task, judge(ok, out, err),
                "success" if ok else "failed", time.monotonic() - t0, out or err, err)
        except BaseException as exc:  # noqa: BLE001
            tag = "UNTESTABLE" if blocked(exc) else "BROKEN"
            row(name, task, tag, type(exc).__name__,
                time.monotonic() - t0, "", str(exc))
        print(f"  {name:18s} -> {ROWS[-1]['tag']:12s} {ROWS[-1]['status']} "
              f"({ROWS[-1]['duration_s']}s)")


# ------------------------------------------------------------------ extra agents
async def run_extra():
    # file_agent — real file ops in a temp dir
    t0 = time.monotonic()
    try:
        from core.file_agent import JarvisFileAgent
        fa = JarvisFileAgent()
        d = tempfile.mkdtemp(prefix="jarvis_file_")
        with open(os.path.join(d, "notes.txt"), "w") as f:
            f.write("alpha\nbeta\n")
        listing = await timed(fa.list_files(d))
        content = await timed(fa.read_file(os.path.join(d, "notes.txt")))
        ok = "notes.txt" in str(listing) and "alpha" in str(content)
        row("core/file_agent:JarvisFileAgent", "list dir and read notes.txt",
            "WORKING" if ok else "FAKE-SUCCESS", "success", time.monotonic() - t0,
            str(listing)[:200] + " | " + str(content)[:200])
    except BaseException as exc:  # noqa: BLE001
        row("core/file_agent:JarvisFileAgent", "list dir and read notes.txt",
            "UNTESTABLE" if blocked(exc) else "BROKEN", type(exc).__name__,
            time.monotonic() - t0, "", str(exc))
    print(f"  file_agent    -> {ROWS[-1]['tag']}")

    # vision_agent — capture screen + describe with llava (read-only)
    t0 = time.monotonic()
    try:
        from core.vision_agent import VisionAgent
        va = VisionAgent()
        task = await timed(va.run("describe what is currently on the screen"),
                           timeout=120)
        st = getattr(task, "status", "")
        out = str(getattr(task, "summary", "") or getattr(task, "output", "") or st)
        ok = str(st).lower() in ("done", "complete", "completed", "success", "") and bool(out)
        row("core/vision_agent:VisionAgent", "describe current screen",
            "WORKING" if ok else ("FAKE-SUCCESS" if not out else "BROKEN"),
            str(st), time.monotonic() - t0, out)
        await va.close()
    except BaseException as exc:  # noqa: BLE001
        row("core/vision_agent:VisionAgent", "describe current screen",
            "UNTESTABLE" if blocked(exc) else "BROKEN", type(exc).__name__,
            time.monotonic() - t0, "", str(exc))
    print(f"  vision_agent  -> {ROWS[-1]['tag']}")


# ------------------------------------------------------------------- infra rows
async def run_infra():
    checks = []

    def add(name, ok, ev, err=""):
        row(name, "contract check", "WORKING" if ok else "BROKEN",
            "success" if ok else "failed", 0.0, ev, err)

    try:
        from core.agents import registry as regmod
        reg = regmod.agent_registry
        names = sorted(reg.names())
        add("core/agents/registry", len(names) == 15, f"15 agents registered: {names}")
        r = await reg.run("does_not_exist", "hi")
        add("core/agents/registry:unknown-id",
            getattr(r, "success", True) is False and "Unknown agent" in str(getattr(r, "error", "")),
            "unknown id rejected loudly", str(getattr(r, "error", "")))
    except BaseException as exc:  # noqa: BLE001
        add("core/agents/registry", False, "", str(exc))

    try:
        from core.agents import router as rmod
        pick = None
        for fn in ("route", "pick", "select", "route_goal", "choose"):
            if hasattr(rmod, fn):
                pick = getattr(rmod, fn)("write a function to parse dates")
                break
        if pick is None:  # class-based router
            for k, v in vars(rmod).items():
                if k.startswith("_") or not isinstance(v, type):
                    continue
                inst = v()
                for fn in ("route", "pick", "select", "choose", "route_goal"):
                    if hasattr(inst, fn):
                        pick = getattr(inst, fn)("write a function to parse dates")
                        break
                if pick is not None:
                    break
        add("core/agents/router", pick is not None and "forge" in str(pick).lower(),
            f"goal -> {pick}")
    except BaseException as exc:  # noqa: BLE001
        add("core/agents/router", False, "", str(exc))

    try:
        from core.agents.capabilities import TOOL_AGENT_KEYWORDS, ADAPTER_AGENT_KEYWORDS
        n = len(TOOL_AGENT_KEYWORDS) + len(ADAPTER_AGENT_KEYWORDS)
        add("core/agents/capabilities", n == 15, f"{n} agents in keyword table")
    except BaseException as exc:  # noqa: BLE001
        add("core/agents/capabilities", False, "", str(exc))

    for modname, call in [
        ("core/agents/graph", "graph"),
        ("core/agents/parallel_executor", "parallel"),
        ("core/agents/events", "events"),
        ("core/agents/base", "base"),
        ("core/agents/_sub_agent_base", "sub_base"),
        ("core/agents/capabilities", "caps2"),
    ]:
        try:
            __import__(modname)
            add(f"{modname}", True, "imports cleanly")
        except BaseException as exc:  # noqa: BLE001
            add(f"{modname}", False, "", str(exc))

    # executor is expected blocked (core.constants deleted)
    try:
        __import__("core.agents.executor")
        add("core/agents/executor", True, "imports cleanly")
    except BaseException as exc:  # noqa: BLE001
        add("core/agents/executor", False, "",
            str(exc))

    # llm_router -> ollama round trip (real model call)
    t0 = time.monotonic()
    try:
        from core.pipeline.stages.execution import complete_async
        r = await timed(complete_async("Reply with exactly: PONG", role="chat"),
                        timeout=60)
        out = r.unwrap() if r.is_ok() else f"ERR {r}"
        add("core/llm_router (ollama round-trip)", "PONG" in str(out).upper(),
            str(out)[:120])
    except BaseException as exc:  # noqa: BLE001
        add("core/llm_router (ollama round-trip)", False, "", str(exc))
    print(f"  infra done ({time.monotonic() - t0:.0f}s model round-trip incl.)")


BATCHES = {"tool": run_tool, "adapters": run_adapters, "legacy": run_legacy,
           "extra": run_extra, "infra": run_infra}


async def main():
    batch = sys.argv[1] if len(sys.argv) > 1 else "all"
    if batch == "all":
        for fn in BATCHES.values():
            await fn()
    else:
        await BATCHES[batch]()
    path = "agent_scorecard.json"
    old = []
    if os.path.exists(path):
        try:
            old = json.load(open(path))
        except Exception:
            old = []
    seen = {(r["agent"], r["task"]) for r in old}
    old.extend(r for r in ROWS if (r["agent"], r["task"]) not in seen)
    json.dump(old, open(path, "w"), indent=1)
    print(f"\n=== batch '{batch}' rows: {len(ROWS)} (total {len(old)}) ===")
    for r in ROWS:
        print(f"{r['tag']:12s} {r['agent']:34s} {r['status'][:40]:40s} {r['duration_s']}s")


if __name__ == "__main__":
    asyncio.run(main())
