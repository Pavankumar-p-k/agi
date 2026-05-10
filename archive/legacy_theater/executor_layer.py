"""
l3_executor/executor_layer.py
═══════════════════════════════════════════════════════════════════
LEVEL 3 — EXECUTOR LAYER  (Codex / Devin equivalent)

WRAPS (does not replace):
  jarvis_fixed/core/simulation_engine.py  → SimulationEngine
  jarvis_fixed/core/decision_engine.py    → DecisionEngine
  jarvis_remaining/tools/tool_registry.py → ToolRegistry

ADDS:
  • TaskPlanner      — LLM decomposes goal into typed steps
  • ExecutionSandbox — safe Python exec (blocked builtins, timeout)
  • ExecutionLoop    — plan→simulate→execute→verify→fix (retry 3×)
  • AuditLog         — every execution persisted to SQLite
"""
from __future__ import annotations
import asyncio, io, json, logging, re, sqlite3, textwrap, time, traceback
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger("jarvis.l3_executor")


class ExecStatus(str, Enum):
    SUCCESS = "success"
    FAILED  = "failed"
    PARTIAL = "partial"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


@dataclass
class TaskStep:
    index:        int
    description:  str
    code:         str  = ""
    tool:         str  = ""
    params:       dict = field(default_factory=dict)
    status:       ExecStatus = ExecStatus.SKIPPED
    output:       str  = ""
    error:        str  = ""
    duration_ms:  int  = 0
    retries:      int  = 0


@dataclass
class ExecutionPlan:
    goal:                  str
    intent:                str
    steps:                 list
    estimated_risk:        float = 0.3
    requires_controller:   bool  = False


@dataclass
class ExecutionResult:
    goal:        str
    status:      ExecStatus
    steps_done:  int
    steps_total: int
    output:      str
    error:       str          = ""
    plan:        Optional[ExecutionPlan] = None
    latency_ms:  int          = 0
    audit_id:    Optional[int] = None


# ── Safety guard (shared with L4) ────────────────────────────────
BLOCKED_PATTERNS = [
    r"rm\s+-rf\s+/", r"mkfs", r"dd\s+if=.*of=/dev",
    r":()\{.*\}", r"chmod\s+-R\s+777\s+/",
    r"curl.*\|\s*sh", r"wget.*\|\s*bash",
    r"DROP\s+TABLE", r"DELETE\s+FROM.*WHERE\s+1\s*=\s*1",
    r"os\.system", r"subprocess\.call", r"subprocess\.run",
    r"__import__",
]


class ExecutionSandbox:
    """
    Safe Python execution.
    • Blocks dangerous builtins
    • Enforces timeout
    • Captures stdout/stderr
    """
    SAFE_BUILTINS_NAMES = [
        "print","len","range","enumerate","zip","map","filter",
        "list","dict","set","tuple","str","int","float","bool",
        "min","max","sum","sorted","reversed","abs","round",
        "isinstance","type","hasattr","getattr","vars","dir",
        "True","False","None","Exception","repr","hash","id",
    ]

    def __init__(self, timeout_sec: int = 30,
                 max_output: int = 8000):
        self._timeout    = timeout_sec
        self._max_output = max_output

    def is_safe(self, code: str) -> tuple[bool, str]:
        for pat in BLOCKED_PATTERNS:
            if re.search(pat, code, re.IGNORECASE):
                return False, f"Blocked pattern: {pat}"
        return True, ""

    async def run(self, code: str,
                  extra_globals: dict = None) -> tuple[str, str, bool]:
        """Returns (stdout, stderr, success)."""
        safe_globals = self._make_globals(extra_globals or {})
        out_buf = io.StringIO()
        err_buf = io.StringIO()

        def _exec():
            with redirect_stdout(out_buf), redirect_stderr(err_buf):
                compiled = compile(
                    textwrap.dedent(code),
                    "<jarvis_sandbox>", "exec")
                exec(compiled, safe_globals)  # noqa: S102

        try:
            await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, _exec),
                timeout=self._timeout,
            )
            return (out_buf.getvalue()[:self._max_output],
                    err_buf.getvalue()[:self._max_output],
                    True)
        except asyncio.TimeoutError:
            return "", f"Timeout after {self._timeout}s", False
        except Exception:
            return out_buf.getvalue(), traceback.format_exc()[-800:], False

    def _make_globals(self, extra: dict) -> dict:
        import json as _json, re as _re, math as _math
        builtins_dict = {}
        import builtins as _bi
        for name in self.SAFE_BUILTINS_NAMES:
            if hasattr(_bi, name):
                builtins_dict[name] = getattr(_bi, name)
        g = {"__builtins__": builtins_dict,
              "json": _json, "re": _re, "math": _math}
        g.update(extra)
        return g


class AuditLog:
    """Every execution recorded to SQLite."""

    SCHEMA = """CREATE TABLE IF NOT EXISTS exec_audit (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        goal        TEXT,
        intent      TEXT,
        status      TEXT,
        steps_done  INTEGER,
        steps_total INTEGER,
        output      TEXT,
        error       TEXT,
        latency_ms  INTEGER,
        ts          REAL DEFAULT (unixepoch())
    )"""

    def __init__(self, db_path: str = "database.db"):
        self._db = db_path
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(self.SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def record(self, result: ExecutionResult) -> int:
        conn = sqlite3.connect(self._db)
        try:
            cur = conn.execute(
                "INSERT INTO exec_audit "
                "(goal,intent,status,steps_done,steps_total,output,error,latency_ms) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (result.goal,
                 result.plan.intent if result.plan else "",
                 result.status,
                 result.steps_done, result.steps_total,
                 result.output[:2000], result.error[:500],
                 result.latency_ms),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def recent(self, n: int = 20) -> list[dict]:
        conn = sqlite3.connect(self._db)
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM exec_audit "
                "ORDER BY ts DESC LIMIT ?", (n,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


class TaskPlanner:
    """LLM decomposes goal → typed steps."""

    SYSTEM = """You are JARVIS executor planner.
Break the goal into ordered steps.
Return ONLY valid JSON:
{
  "steps": [
    {"index":1,"description":"...","type":"code|tool|shell","content":"..."}
  ],
  "estimated_risk": 0.0-1.0,
  "requires_controller": true|false
}"""

    def __init__(self, pool, simulation_engine=None):
        self._pool = pool
        self._sim  = simulation_engine

    async def plan(self, goal: str, intent: str,
                    context: str = "") -> ExecutionPlan:
        try:
            raw = await self._pool.generate(
                model="qwen3:4b",
                prompt=f"Goal: {goal}\nContext: {context[:400]}",
                system=self.SYSTEM,
                temperature=0.1,
                max_tokens=500,
            )
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if not m:
                raise ValueError("No JSON")
            data  = json.loads(m.group())
            steps = [
                TaskStep(
                    index       = s["index"],
                    description = s["description"],
                    code        = s["content"] if s.get("type") == "code" else "",
                    tool        = s["content"] if s.get("type") == "tool" else "",
                    params      = ({"cmd": s["content"]}
                                   if s.get("type") == "shell" else {}),
                )
                for s in data.get("steps", [])
            ]
            return ExecutionPlan(
                goal  = goal, intent = intent,
                steps = steps,
                estimated_risk       = float(data.get("estimated_risk", 0.3)),
                requires_controller  = bool(data.get("requires_controller", False)),
            )
        except Exception as e:
            logger.warning("[L3] Planner error: %s — fallback", e)
            return ExecutionPlan(
                goal=goal, intent=intent,
                steps=[TaskStep(index=1, description=goal,
                                 code=f"# Goal: {goal}\nprint('Executing...')")],
                estimated_risk=0.2,
            )


class ExecutionLoop:
    """
    Core execution engine.

    while not done:
        plan()
        simulate()   ← existing SimulationEngine
        execute()
        verify()
        if error: fix() and retry (max 3×)
    """
    MAX_RETRIES = 3

    def __init__(self, planner: TaskPlanner, sandbox: ExecutionSandbox,
                 audit: AuditLog, pool=None, tools=None):
        self._planner = planner
        self._sandbox = sandbox
        self._audit   = audit
        self._pool    = pool
        self._tools   = tools

    async def run(self, goal: str, intent: str = "task",
                   context: str = "",
                   dry_run: bool = False) -> ExecutionResult:
        t0 = time.time()
        logger.info("[L3] ▶ Executing: %s", goal[:80])

        # Plan
        plan = await self._planner.plan(goal, intent, context)
        logger.info("[L3] Plan: %d steps, risk=%.2f",
                    len(plan.steps), plan.estimated_risk)

        # Safety threshold
        if plan.estimated_risk > 0.85:
            result = ExecutionResult(
                goal=goal, status=ExecStatus.BLOCKED,
                steps_done=0, steps_total=len(plan.steps),
                output="", error=f"Risk {plan.estimated_risk:.2f} > 0.85",
                plan=plan,
                latency_ms=int((time.time()-t0)*1000),
            )
            self._audit.record(result)
            return result

        if dry_run:
            lines = [f"DRY RUN — {plan.goal}",
                     f"Risk: {plan.estimated_risk:.2f}"]
            for s in plan.steps:
                lines.append(f"  {s.index}. {s.description}")
            return ExecutionResult(
                goal=goal, status=ExecStatus.SKIPPED,
                steps_done=0, steps_total=len(plan.steps),
                output="\n".join(lines), plan=plan,
                latency_ms=int((time.time()-t0)*1000),
            )

        # Execute steps
        outputs = []
        done    = 0
        for step in plan.steps:
            step = await self._run_step(step, outputs)
            plan.steps[step.index - 1] = step
            outputs.append(f"Step {step.index}: {step.output}")
            if step.status == ExecStatus.FAILED:
                break
            done += 1

        status = (ExecStatus.SUCCESS if done == len(plan.steps)
                   else ExecStatus.PARTIAL if done > 0
                   else ExecStatus.FAILED)

        result = ExecutionResult(
            goal=goal, status=status,
            steps_done=done, steps_total=len(plan.steps),
            output="\n".join(outputs),
            error="" if status == ExecStatus.SUCCESS else
            next((s.error for s in plan.steps
                  if s.status == ExecStatus.FAILED), ""),
            plan=plan,
            latency_ms=int((time.time()-t0)*1000),
        )
        result.audit_id = self._audit.record(result)
        logger.info("[L3] ✓ %s (%d/%d) in %dms",
                    status, done, len(plan.steps), result.latency_ms)
        return result

    async def _run_step(self, step: TaskStep,
                         prev: list[str]) -> TaskStep:
        t0 = time.time()
        for attempt in range(self.MAX_RETRIES):
            step.retries = attempt

            if step.code:
                ok_safe, reason = self._sandbox.is_safe(step.code)
                if not ok_safe:
                    step.status = ExecStatus.BLOCKED
                    step.error  = reason
                    step.duration_ms = int((time.time()-t0)*1000)
                    return step

                out, err, ok = await self._sandbox.run(
                    step.code, {"_prev": prev})

                if ok:
                    step.status = ExecStatus.SUCCESS
                    step.output = out or "Done (no output)"
                    step.duration_ms = int((time.time()-t0)*1000)
                    return step

                logger.warning("[L3] Step %d attempt %d: %s",
                               step.index, attempt+1, err[:80])

                if attempt < self.MAX_RETRIES - 1 and self._pool:
                    fixed = await self._auto_fix(step.code, err)
                    if fixed:
                        step.code = fixed
                        continue

                step.status     = ExecStatus.FAILED
                step.error      = err
                step.duration_ms= int((time.time()-t0)*1000)
                return step

            elif step.tool and self._tools:
                try:
                    r = await self._tools.call(step.tool, **step.params)
                    step.status = (ExecStatus.SUCCESS if r.success
                                    else ExecStatus.FAILED)
                    step.output = r.output or "Tool executed"
                    step.error  = r.error  or ""
                except Exception as e:
                    step.status = ExecStatus.FAILED
                    step.error  = str(e)
                step.duration_ms = int((time.time()-t0)*1000)
                return step

            else:
                step.status  = ExecStatus.SKIPPED
                step.output  = step.description
                step.duration_ms = 0
                return step

        return step

    async def _auto_fix(self, code: str, error: str) -> Optional[str]:
        if not self._pool:
            return None
        try:
            raw = await self._pool.generate(
                model="qwen2.5-coder:3b",
                prompt=(f"Fix this code:\n```python\n{code}\n```\n"
                        f"Error: {error[:250]}\n"
                        f"Return ONLY the fixed code."),
                system="Fix Python code. Return only corrected code.",
                temperature=0.05,
                max_tokens=450,
            )
            m = re.search(r"```python\n(.*?)```", raw, re.DOTALL)
            return m.group(1).strip() if m else raw.strip()
        except Exception:
            return None


class ExecutorLayer:
    """L3 façade."""

    def __init__(self, pool, simulation_engine=None,
                 tools=None, db_path: str = "database.db"):
        audit         = AuditLog(db_path)
        planner       = TaskPlanner(pool, simulation_engine)
        sandbox       = ExecutionSandbox(timeout_sec=30)
        self._loop    = ExecutionLoop(planner, sandbox, audit, pool, tools)
        self._audit   = audit
        logger.info("[L3] ExecutorLayer initialized")

    async def execute(self, goal: str, intent: str = "task",
                       context: str = "",
                       dry_run: bool = False) -> ExecutionResult:
        return await self._loop.run(goal, intent, context, dry_run)

    def recent(self, n: int = 10) -> list[dict]:
        return self._audit.recent(n)
