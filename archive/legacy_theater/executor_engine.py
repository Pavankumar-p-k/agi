"""
l3_executor/executor_engine.py
═══════════════════════════════════════════════════════════════════
LEVEL 3 — EXECUTOR ENGINE (Codex equivalent)

The autonomous task execution layer.
Takes a goal from L1 Brain, decomposes it into steps,
executes each step, verifies, fixes failures, retries.

EXECUTION LOOP:
    while not done:
        step = plan.next()
        sim  = simulate(step, world_state)
        if sim.should_proceed():
            result = sandbox.run(step)
            if verify(result):
                advance()
            else:
                fix(result)   # ask L1 Brain for correction
                retry()       # max MAX_RETRIES times
        else:
            log("skipped — simulation says risky")

SAFETY:
    • All commands run through SafetyGuard (L4)
    • Timeout per step (default 30s)
    • Max retries per step (default 3)
    • Full audit log in SQLite
═══════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import asyncio, json, logging, os, sqlite3, subprocess, time, traceback
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("jarvis.l3")

MAX_RETRIES    = 3
STEP_TIMEOUT_S = 60
LOG_DB         = Path(os.getenv("JARVIS_DB", "database.db"))


# ─────────────────────────────────────────────────────────────────
#  DATA CLASSES
# ─────────────────────────────────────────────────────────────────

class StepStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    DONE      = "done"
    FAILED    = "failed"
    SKIPPED   = "skipped"
    RETRYING  = "retrying"

@dataclass
class ExecutionStep:
    step:       int
    action:     str
    tool:       str        # code|terminal|browser|adb|file|api|python
    command:    str        # actual command / code to run
    expected:   str        # human-readable expected output
    status:     StepStatus = StepStatus.PENDING
    result:     str        = ""
    error:      str        = ""
    retries:    int        = 0
    started_at: float      = 0.0
    done_at:    float      = 0.0
    duration_ms: int       = 0

@dataclass
class ExecutionPlan:
    goal:       str
    steps:      List[ExecutionStep]
    plan_id:    str        = ""
    created_at: float      = field(default_factory=time.time)
    done:       bool       = False
    success:    bool       = False
    summary:    str        = ""

    def __post_init__(self):
        if not self.plan_id:
            import hashlib
            self.plan_id = hashlib.md5(
                f"{self.goal}{self.created_at}".encode()).hexdigest()[:10]

    @property
    def current_step(self) -> Optional[ExecutionStep]:
        for s in self.steps:
            if s.status == StepStatus.PENDING:
                return s
        return None

    @property
    def progress(self) -> str:
        done  = sum(1 for s in self.steps if s.status == StepStatus.DONE)
        total = len(self.steps)
        return f"{done}/{total}"

@dataclass
class ExecutionResult:
    plan_id:    str
    goal:       str
    success:    bool
    steps_done: int
    steps_fail: int
    output:     str
    error:      str      = ""
    duration_ms: int     = 0
    logs:       List[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────
#  EXECUTION SANDBOX — safe subprocess runner
# ─────────────────────────────────────────────────────────────────

class ExecutionSandbox:
    """
    Safe command/code execution with:
    • Timeout enforcement
    • Output capture
    • Working directory isolation
    • Environment variable control
    """

    def __init__(self, working_dir: str = ".", timeout: int = STEP_TIMEOUT_S):
        self.working_dir = Path(working_dir).resolve()
        self.timeout     = timeout

    async def run(self, step: ExecutionStep) -> tuple[bool, str, str]:
        """
        Execute a step based on its tool type.
        Returns (success, stdout, stderr).
        """
        tool = step.tool.lower()

        if tool == "terminal":
            return await self._run_shell(step.command)
        elif tool == "python":
            return await self._run_python(step.command)
        elif tool == "file":
            return await self._run_file_op(step.command)
        elif tool == "api":
            return await self._run_api(step.command)
        elif tool == "code":
            # code tool = write code then maybe execute
            return await self._run_code_write(step.command)
        else:
            # Unknown tool — try as shell command
            return await self._run_shell(step.command)

    async def _run_shell(self, command: str) -> tuple[bool, str, str]:
        if not command.strip():
            return True, "", ""
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir),
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self.timeout)
                success = proc.returncode == 0
                return success, stdout.decode(errors="replace"), stderr.decode(errors="replace")
            except asyncio.TimeoutError:
                proc.kill()
                return False, "", f"Timeout after {self.timeout}s"
        except Exception as e:
            return False, "", str(e)

    async def _run_python(self, code: str) -> tuple[bool, str, str]:
        """Execute Python code string in subprocess."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w",
                                         delete=False) as f:
            f.write(code)
            tmp = f.name
        try:
            return await self._run_shell(f"python {tmp}")
        finally:
            try:
                os.unlink(tmp)
            except Exception:
                pass

    async def _run_file_op(self, command: str) -> tuple[bool, str, str]:
        """
        File operations encoded as JSON:
        {"op":"write","path":"file.py","content":"..."}
        {"op":"read","path":"file.py"}
        {"op":"delete","path":"file.py"}
        """
        try:
            op = json.loads(command)
            path = Path(self.working_dir / op["path"])

            if op["op"] == "write":
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(op.get("content", ""))
                return True, f"Written: {path}", ""
            elif op["op"] == "read":
                return True, path.read_text(), ""
            elif op["op"] == "delete":
                path.unlink(missing_ok=True)
                return True, f"Deleted: {path}", ""
            else:
                return False, "", f"Unknown op: {op['op']}"
        except Exception as e:
            return False, "", str(e)

    async def _run_api(self, command: str) -> tuple[bool, str, str]:
        """HTTP API call encoded as JSON: {"method":"POST","url":"...","body":{}}"""
        try:
            import httpx
            op = json.loads(command)
            async with httpx.AsyncClient(timeout=30) as c:
                method = op.get("method", "GET").upper()
                url    = op["url"]
                body   = op.get("body", {})
                if method == "GET":
                    r = await c.get(url)
                elif method == "POST":
                    r = await c.post(url, json=body)
                else:
                    r = await c.request(method, url, json=body)
                return r.status_code < 400, r.text, ""
        except Exception as e:
            return False, "", str(e)

    async def _run_code_write(self, command: str) -> tuple[bool, str, str]:
        """
        Code tool: parse {"file":"path","content":"...","run":bool}
        Write file, optionally execute it.
        """
        try:
            op = json.loads(command)
        except Exception:
            # Plain string = python code to eval
            return await self._run_python(command)

        path = Path(self.working_dir / op.get("file","output.py"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(op.get("content", ""))

        if op.get("run", False):
            return await self._run_shell(f"python {path}")

        return True, f"File written: {path}", ""


# ─────────────────────────────────────────────────────────────────
#  EXECUTION LOGGER
# ─────────────────────────────────────────────────────────────────

class ExecutionLogger:
    """Persists every execution step to SQLite for audit + learning."""

    def __init__(self, db_path: Path = LOG_DB):
        self._db = db_path
        self._ensure_table()

    def _ensure_table(self):
        try:
            with sqlite3.connect(str(self._db)) as con:
                con.execute("""
                    CREATE TABLE IF NOT EXISTS execution_log (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        plan_id     TEXT,
                        goal        TEXT,
                        step_num    INTEGER,
                        action      TEXT,
                        tool        TEXT,
                        command     TEXT,
                        status      TEXT,
                        result      TEXT,
                        error       TEXT,
                        retries     INTEGER,
                        duration_ms INTEGER,
                        created_at  REAL
                    )
                """)
                con.commit()
        except Exception as e:
            logger.warning("[L3] Logger DB init failed: %s", e)

    def log_step(self, plan_id: str, goal: str, step: ExecutionStep):
        try:
            with sqlite3.connect(str(self._db)) as con:
                con.execute("""
                    INSERT INTO execution_log
                    (plan_id,goal,step_num,action,tool,command,status,
                     result,error,retries,duration_ms,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, (plan_id, goal, step.step, step.action, step.tool,
                      step.command[:500], step.status.value,
                      step.result[:500], step.error[:200],
                      step.retries, step.duration_ms, time.time()))
                con.commit()
        except Exception as e:
            logger.debug("[L3] Log step failed: %s", e)

    def get_history(self, plan_id: str = None, limit: int = 50) -> list:
        try:
            with sqlite3.connect(str(self._db)) as con:
                con.row_factory = sqlite3.Row
                if plan_id:
                    rows = con.execute(
                        "SELECT * FROM execution_log WHERE plan_id=? ORDER BY id DESC LIMIT ?",
                        (plan_id, limit)).fetchall()
                else:
                    rows = con.execute(
                        "SELECT * FROM execution_log ORDER BY id DESC LIMIT ?",
                        (limit,)).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []


# ─────────────────────────────────────────────────────────────────
#  EXECUTOR ENGINE — main entry point
# ─────────────────────────────────────────────────────────────────

class ExecutorEngine:
    """
    L3 Executor main entry point.

    USAGE:
        executor = ExecutorEngine(sandbox, safety_guard, simulation, brain_ext)
        result   = await executor.run(plan)
    """

    def __init__(self,
                 sandbox:        ExecutionSandbox,
                 safety_guard,   # L4 SafetyGuard
                 simulation,     # existing SimulationEngine
                 brain_ext,      # L1 BrainExtension (for fix generation)
                 world_state):   # WorldState
        self.sandbox    = sandbox
        self.safety     = safety_guard
        self.simulation = simulation
        self.brain      = brain_ext
        self.world      = world_state
        self.logger     = ExecutionLogger()
        logger.info("[L3] ExecutorEngine ready")

    # ── Main execution loop ───────────────────────────────────────

    async def run(self, plan: ExecutionPlan,
                  on_progress: Optional[Callable] = None) -> ExecutionResult:
        """
        Execute plan with plan→execute→verify→fix retry loop.
        """
        t0      = time.time()
        logs    = []
        success = True

        logger.info("[L3] Starting plan '%s' | steps=%d",
                    plan.goal[:60], len(plan.steps))

        for step in plan.steps:
            log_entry = f"Step {step.step}: {step.action}"
            logs.append(log_entry)
            logger.info("[L3] %s", log_entry)

            step.status = StepStatus.RUNNING
            step.started_at = time.time()

            # ── Safety check ──────────────────────────────────────
            if not self.safety.check(step.command, step.tool):
                step.status = StepStatus.SKIPPED
                step.error  = "Blocked by SafetyGuard"
                logs.append(f"  → BLOCKED: {step.command[:60]}")
                self.logger.log_step(plan.plan_id, plan.goal, step)
                continue

            # ── Simulation check ──────────────────────────────────
            snap   = self.world.snapshot()
            sim    = self.simulation.simulate_generic(step.action, snap)
            if sim.risk_flag and sim.risk_level == "high":
                step.status = StepStatus.SKIPPED
                step.error  = f"Skipped by simulation: {sim.predicted_outcome}"
                logs.append(f"  → SIMULATION SKIP: risk={sim.risk_level}")
                self.logger.log_step(plan.plan_id, plan.goal, step)
                continue

            # ── Execute with retry loop ───────────────────────────
            step_ok = False
            for attempt in range(MAX_RETRIES + 1):
                if attempt > 0:
                    step.status  = StepStatus.RETRYING
                    step.retries = attempt
                    logs.append(f"  → Retry {attempt}/{MAX_RETRIES}")
                    logger.info("[L3]   Retry %d/%d for step %d",
                                attempt, MAX_RETRIES, step.step)

                ok, stdout, stderr = await self.sandbox.run(step)
                step.result = stdout[:1000] if stdout else ""
                step.error  = stderr[:500]  if stderr else ""

                if ok and await self._verify(step):
                    step.status = StepStatus.DONE
                    step_ok = True
                    logs.append(f"  ✓ Done: {stdout[:80] if stdout else 'ok'}")
                    break
                else:
                    if attempt < MAX_RETRIES:
                        # Ask brain to generate a fix
                        fixed_cmd = await self._fix(step)
                        if fixed_cmd:
                            step.command = fixed_cmd
                            logs.append(f"  → Fix applied: {fixed_cmd[:60]}")
                    else:
                        step.status = StepStatus.FAILED
                        logs.append(f"  ✗ Failed after {MAX_RETRIES} retries")
                        success = False

            step.done_at     = time.time()
            step.duration_ms = int((step.done_at - step.started_at) * 1000)
            self.logger.log_step(plan.plan_id, plan.goal, step)

            if on_progress:
                await on_progress(step, plan.progress)

            # Stop plan if critical step fails
            if not step_ok and step.step <= 2:
                logs.append("  ⛔ Critical step failed — aborting plan")
                success = False
                break

        plan.done    = True
        plan.success = success

        steps_done = sum(1 for s in plan.steps if s.status == StepStatus.DONE)
        steps_fail = sum(1 for s in plan.steps if s.status == StepStatus.FAILED)
        duration   = int((time.time() - t0) * 1000)

        summary = (f"{'✓' if success else '✗'} Plan complete: "
                   f"{steps_done}/{len(plan.steps)} steps done "
                   f"in {duration}ms")
        plan.summary = summary
        logs.append(summary)

        logger.info("[L3] %s", summary)

        return ExecutionResult(
            plan_id    = plan.plan_id,
            goal       = plan.goal,
            success    = success,
            steps_done = steps_done,
            steps_fail = steps_fail,
            output     = "\n".join(s.result for s in plan.steps if s.result),
            duration_ms = duration,
            logs       = logs,
        )

    # ── Verify step output ────────────────────────────────────────

    async def _verify(self, step: ExecutionStep) -> bool:
        """
        Check if step result matches expected output.
        Returns True if step should be marked done.
        """
        # Fatal error signals
        fatal = ["error:", "exception:", "traceback", "permission denied",
                 "command not found", "no such file", "syntax error"]
        err_lower = step.error.lower()
        if any(f in err_lower for f in fatal):
            return False

        # Expected output check (if specified)
        if step.expected and step.result:
            exp_lower = step.expected.lower()
            res_lower = step.result.lower()
            # Check key words from expected appear in result
            keywords = [w for w in exp_lower.split() if len(w) > 4]
            if keywords:
                matches = sum(1 for k in keywords if k in res_lower)
                if matches < len(keywords) * 0.3:  # 30% match threshold
                    return False

        return True

    # ── Fix step using L1 Brain ───────────────────────────────────

    async def _fix(self, step: ExecutionStep) -> Optional[str]:
        """
        Ask L1 Brain to suggest a fix for a failed step.
        Returns new command string or None.
        """
        try:
            from jarvis_brain.orchestrator.brain import Message as BMsg
            prompt = (
                f"A command failed. Suggest a corrected command.\n"
                f"Tool: {step.tool}\n"
                f"Original command: {step.command}\n"
                f"Error: {step.error}\n"
                f"Expected: {step.expected}\n\n"
                f"Return ONLY the corrected command, nothing else."
            )
            result = await self.brain.brain.think(BMsg(text=prompt))
            fixed  = result.reply.strip().strip("`").strip()
            if fixed and fixed != step.command:
                return fixed
        except Exception as e:
            logger.debug("[L3] Fix generation failed: %s", e)
        return None

    def from_steps(self, goal: str, steps: list) -> ExecutionPlan:
        """Convert raw step dicts from L1 decomposer into ExecutionPlan."""
        exec_steps = []
        for i, s in enumerate(steps):
            exec_steps.append(ExecutionStep(
                step    = s.get("step", i+1),
                action  = s.get("action", ""),
                tool    = s.get("tool", "terminal"),
                command = s.get("command", ""),
                expected= s.get("expected", ""),
            ))
        return ExecutionPlan(goal=goal, steps=exec_steps)

    def get_history(self, limit: int = 20) -> list:
        return self.logger.get_history(limit=limit)
