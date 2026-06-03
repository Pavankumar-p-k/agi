"""core/control_loop.py
The heart of JARVIS autonomy.
Interpret → Plan → Build → Validate → Check → Fix/Retry → Done.
Every cycle uses real validation, not LLM opinions.
"""
import asyncio, os, re, json, logging, shlex
from pathlib import Path
from typing import Optional, Callable
from datetime import datetime

logger = logging.getLogger("control_loop")

from core.project_state import ProjectState, ValidationResult, list_projects, PROJECTS_DIR
from core.goal_interpreter import interpret_goal
from core.success_criteria import is_done, get_summary
from core.real_validator import RealValidator
from core.agent_launcher import AgentLauncher
from core.site_planner import plan_site
from core.shared_context import SharedContext
from core.budget_controller import budget_controller
from core.failure_classifier import classify, FailureCategory
from core.conflict_resolver import lock_manager
from core.self_diagnosis import self_diagnosis
from core.quality_scorer import QualityScorer
from core.partial_success import PartialSuccessTracker, ProgressSnapshot
from core.interrupt_override import interrupt_manager
from core.nondet_control import decision_logger, DecisionEntry
from core.checkpoint_manager import checkpoint_manager
from core.system_governor import system_governor, GovernorDecision
from core.plan_evolution import plan_evolution
from core.memory_driven_decisions import memory_router
from core.template_intelligence import template_analyzer
from core.system_identity import system_identity
from core.environment_monitor import environment_monitor
from core.proactive_adaptation import adaptation_engine
from notifications.notifier import notifier

MAX_PARALLEL = 2

quality_scorer = QualityScorer()
partial_tracker = PartialSuccessTracker()

TASK_TEMPLATES = {
    "scaffold": "Create the project scaffold: {description}",
    "frontend": "Build the frontend for: {description}. Create all components and pages.",
    "backend": "Build the backend/API for: {description}. Create all routes and models.",
    "database": "Set up database schema and models for: {description}.",
    "styling": "Apply styling and theming for: {description}. Make it look professional.",
    "auth": "Implement authentication for: {description}. Login, register, sessions.",
    "form": "Build forms for: {description}. Include validation and submission.",
    "deploy": "Set up deployment configuration for: {description}.",
    "test": "Write tests for: {description}. Unit and integration tests.",
    "docs": "Write documentation for: {description}. README, API docs, setup guide.",
    "fix": "Fix the following issues: {description}",
}

_HTML_GEN = str(Path(__file__).resolve().parents[1] / "tools" / "html_generator.py")
_TEMPLATE_APPLIER = str(Path(__file__).resolve().parents[1] / "tools" / "template_applier.py")

SHELL_TASK_TEMPLATES = {
    "scaffold": lambda d, ws: f'python -c "import os; os.makedirs({shlex.quote(ws)}, exist_ok=True); print(\'Scaffold done\')"',
    "frontend": lambda d, ws: f'python {shlex.quote(_HTML_GEN)} --pages {shlex.quote(d)} --output {shlex.quote(ws)} --name {shlex.quote(_extract_site_name(d))}',
    "backend": lambda d, ws: 'python -c "print(\'Backend not needed\')"',
    "database": lambda d, ws: 'python -c "print(\'No database needed\')"',
    "styling": lambda d, ws: 'python -c "print(\'Styling included\')"',
    "auth": lambda d, ws: 'python -c "print(\'Auth not needed\')"',
    "form": lambda d, ws: f'python {shlex.quote(_HTML_GEN)} --pages {shlex.quote(d)} --output {shlex.quote(ws)} --name {shlex.quote(_extract_site_name(d))} --ensure contact',
    "deploy": lambda d, ws: f'python -c "import asyncio; from tools.browser_agent import browser_agent; url=asyncio.run(browser_agent.deploy_to_vercel({shlex.quote(ws)}, {shlex.quote(_extract_site_name(d))})); print(f\'Deployed: {{url}}\')"',
    "test": lambda d, ws: f'python -c "import os; files=[f for f in os.listdir({shlex.quote(ws)}) if f.endswith(\'.html\')]; print(str(len(files)) + \' pages found\')"',
    "docs": lambda d, ws: f'python {shlex.quote(_HTML_GEN)} --pages {shlex.quote(d)} --output {shlex.quote(ws)} --name {shlex.quote(_extract_site_name(d))} --docs-only',
    "fix": lambda d, ws: f'python {shlex.quote(_HTML_GEN)} --pages {shlex.quote(d)} --output {shlex.quote(ws)} --name {shlex.quote(_extract_site_name(d))}',
}


def _esc(s: str) -> str:
    """Escape for Python -c: double backslashes and quotes."""
    return s.replace("\\", "\\\\").replace('"', '\\"')

def _arg(s: str) -> str:
    """Escape for script argument: only escape quotes."""
    return s.replace('"', '\\"')


def _extract_site_name(description: str) -> str:
    """Extract a site name from a task description (which includes the original goal)."""
    desc = description.lower()
    desc = desc.replace("|", " ").replace("--", " ").replace("goal:", " ")
    words = desc.split()
    multi_word = ["book store", "coffee shop", "coffee house", "book shop",
                  "pizza place", "art gallery", "tech startup", "real estate",
                  "fitness center", "music store", "gift shop"]
    for mw in multi_word:
        if mw in desc:
            return mw.title()
    for i, w in enumerate(words):
        if w in ("book", "coffee", "restaurant", "store", "shop", "portfolio",
                 "blog", "saas", "app", "landing", "business", "ecommerce",
                 "pizza", "cafe", "bakery", "hotel", "gym", "salon", "spa"):
            if i + 1 < len(words) and words[i + 1] in ("store", "shop", "site", "house", "cafe", "bar", "place"):
                return f"{w.title()} {words[i+1].title()}"
            return w.title()
    return "Website"

AGENT_CAPABILITY_MAP = {
    "scaffold": ["codex", "opencode", "gemini", "shell"],
    "frontend": ["opencode", "aider", "codex", "shell"],
    "backend": ["opencode", "aider", "codex", "shell"],
    "database": ["opencode", "aider", "gemini", "shell"],
    "styling": ["aider", "opencode", "codex", "shell"],
    "auth": ["opencode", "aider", "gemini", "shell"],
    "form": ["aider", "opencode", "codex", "shell"],
    "deploy": ["shell", "gh", "opencode"],
    "test": ["gemini", "aider", "opencode", "shell"],
    "docs": ["gemini", "opencode", "aider", "shell"],
    "fix": ["opencode", "aider", "codex", "shell"],
}

TASK_TYPE_ORDER = {
    "scaffold": 0, "database": 1, "backend": 2, "frontend": 3,
    "auth": 4, "form": 5, "styling": 6, "test": 7,
    "deploy": 8, "docs": 9, "fix": 10,
}


class ControlLoop:
    """The main autonomous build loop. Build → Validate → Fix → Repeat."""

    def __init__(self, auto_approve: bool = True, autonomous: bool = False, notify_callback: Optional[Callable] = None):
        self.auto_approve = auto_approve
        self.autonomous = autonomous
        self.notify_callback = notify_callback
        self.running_builds: dict[str, asyncio.Task] = {}
        self._failures_log: Path = Path.cwd() / "failures.jsonl"

    async def _notify(self, project: str, event: str, data: dict):
        try:
            await notifier.notify(project, event, data)
        except Exception as e:
            logger.warning(f"[CONTROL] Notify error: {e}")
        if self.notify_callback:
            try:
                await self.notify_callback(project, event, data)
            except Exception as e:
                logger.warning(f"[CONTROL] Callback error: {e}")

    async def run_build(self, goal: str, workspace: str = "", use_multi_run: bool = False) -> ProjectState:
        """Full control loop for a single goal. Returns final ProjectState."""
        safe_name = re.sub(r'[^a-zA-Z0-9_-]+', '_', goal)[:40].strip("_").lower() or "project"

        # ── MULTI-RUN (Phase 2): run 3 strategies in parallel, pick best ──
        if use_multi_run:
            from core.multi_run import MultiRunExecutor
            logger.info(f"[CONTROL] Multi-run mode: testing 3 strategies for '{goal}'")
            ws_base = Path(workspace) if workspace else Path.cwd()
            mre = MultiRunExecutor()
            best = await mre.execute(goal, workspace_base=str(ws_base))
            if best and best.score and best.score.average >= 5.0:
                logger.info(f"[CONTROL] Multi-run best: {best.strategy} score={best.score.average:.1f}")
                state = ProjectState(project_name=safe_name, goal=goal, status="done")
                state.quality_score = best.score.to_dict() if best.score else None
                state.outputs = {"strategy": best.strategy, "duration": best.duration, "deploy_url": best.deploy_url}
                state.save()
                quality_score = best.score.average if best.score else 0.0
                await self._notify(safe_name, "multi_run_complete", {
                    "strategy": best.strategy, "score": quality_score, "duration": best.duration
                })
                return state
            if best:
                logger.info("[CONTROL] Multi-run best was unusable (%s score=%s), falling back to single run",
                            best.strategy, best.score.average if best.score else 'N/A')
            else:
                logger.info("[CONTROL] Multi-run returned no result, falling back to single run")

        state = ProjectState(project_name=safe_name, goal=goal, status="interpreting")
        state.save()

        ws = Path(workspace) if workspace else Path.cwd() / safe_name
        ws.mkdir(parents=True, exist_ok=True)

        # Phase 3: Initialize seed for deterministic decisions
        import hashlib
        import time
        seed = int(hashlib.sha256(f"{goal}:{time.time()}".encode()).hexdigest()[:8], 16)
        decision_logger.init_project(safe_name, seed)
        decision_logger.set_seed(safe_name, seed)

        ctx = SharedContext(safe_name)

        await self._notify(safe_name, "build_started", {"goal": goal, "project": safe_name})

        # ── STEP 1: INTERPRET ──
        state.status = "interpreting"
        state.save()
        interpreted = await interpret_goal(goal)
        state.interpreted_goal = interpreted
        state.log_event("goal_interpreted", interpreted)
        ctx.write_goal(goal, interpreted)
        await self._notify(safe_name, "goal_interpreted", interpreted)
        logger.info(f"[CONTROL] Interpreted: {interpreted.get('project_type')} "
                         f"pages={interpreted.get('pages')} tech={interpreted.get('tech_stack')}")

        # ── AMBIGUITY CHECK ──
        try:
            from core.ambiguity_resolver import check_ambiguity
            amb_result = check_ambiguity(interpreted)
            if amb_result.ambiguous:
                state.status = "ambiguous"
                state.ambiguous_goal_result = amb_result.to_dict()
                state.log_event("ambiguous_goal", amb_result.to_dict())
                await self._notify(safe_name, "ambiguous_goal", amb_result.to_dict())
                logger.info(f"[CONTROL] Ambiguous goal: {len(amb_result.questions)} question(s) needed")
                state.save()
                return state
        except Exception as e:
            logger.warning(f"[CONTROL] Ambiguity check error: {e}")

        # Reset budget for fresh build
        budget_controller.reset(safe_name)

        # ── SITE PLAN (template selection + structure) ──
        site_plan = plan_site(interpreted)
        state.template_name = site_plan.get("template_name") or ""
        state.template_path = site_plan.get("template_path") or ""
        state.plan = site_plan.get("tasks", [])
        # Phase 4 (D4): Template Intelligence — compose best sections
        try:
            composed = template_analyzer.compose_best(goal, interpreted.get("project_type", "website"))
            if composed.hero_template:
                logger.info(f"[TMPLINTEL] Composed plan: {composed.reason}")
                state.log_event("template_composed", composed.__dict__)
                state.composed_plan = composed.__dict__
        except Exception as e:
            logger.warning(f"[TMPLINTEL] Composition failed: {e}")
        # Phase 4 (D4): Memory-driven strategy selection
        try:
            from memory.decision_memory import decision_memory
            strategy = memory_router.select_strategy(interpreted.get("project_type", "website"), decision_memory, goal)
            logger.info(f"[MDROUTER] Recommended strategy: {strategy}")
        except Exception as e:
            logger.exception("[CONTROL] Strategy selection failed: %s", e)
        state.save()
        logger.info(f"[CONTROL] Site plan: template={state.template_name or 'none'}, "
                     f"{len(state.plan)} tasks")

        # ── STEPS 2-6: CONTROL LOOP ──
        return await self._execute_loop(state, ws, ctx)

    async def resume_build(self, project_name: str) -> Optional[ProjectState]:
        """Resume an interrupted or queued build from its saved state."""
        state = ProjectState.load(project_name)
        if not state:
            logger.warning(f"[CONTROL] Cannot resume {project_name}: no state found")
            return None
        if state.status in ("done", "failed", "cancelled"):
            logger.info(f"[CONTROL] {project_name} already {state.status}")
            return state

        safe_name = state.project_name
        ws = Path.cwd() / safe_name
        ws.mkdir(parents=True, exist_ok=True)
        ctx = SharedContext(safe_name)
        ctx.set_state("resumed", True)

        logger.info(f"[CONTROL] Resuming {project_name} from status={state.status} retry={state.retries}")
        await self._notify(safe_name, "build_resumed", {"status": state.status, "retries": state.retries})
        return await self._execute_loop(state, ws, ctx)

    async def run_pending(self) -> list[str]:
        """Scan for pending/interrupted projects and resume them. Returns resumed names."""
        resumed = []
        if not PROJECTS_DIR.exists():
            return resumed
        for project_dir in sorted(PROJECTS_DIR.iterdir()):
            if not project_dir.is_dir():
                continue
            state_file = project_dir / "state.json"
            if not state_file.exists():
                continue
            try:
                state = ProjectState.load(project_dir.name)
                if not state:
                    continue
                if state.status in ("created", "queued", "interpreting", "planning", "building", "fixing", "validating"):
                    if project_dir.name not in self.running_builds:
                        logger.info(f"[CONTROL] Found pending: {state.project_name} ({state.status})")
                        task = asyncio.create_task(self.resume_build(state.project_name))
                        self.running_builds[project_dir.name] = task
                        resumed.append(project_dir.name)
            except Exception as e:
                logger.warning(f"[CONTROL] Error scanning {project_dir.name}: {e}")
        return resumed

    async def _execute_loop(self, state: ProjectState, ws: Path, ctx: SharedContext) -> ProjectState:
        """Core retry loop: plan → build → validate → check → fix → repeat."""
        safe_name = state.project_name
        goal = state.goal
        interpreted = state.interpreted_goal or {}
        previous_state = None

        while state.retries < state.max_retries:
            # Phase 5 (E1+E2): Environment check + proactive adaptation
            try:
                env_actions = adaptation_engine.assess()
                if env_actions:
                    for a in env_actions:
                        ctx.append(f"[ADAPT] {a['action']}", a['reason'])
                if adaptation_engine.should_pause():
                    state.status = "paused"
                    state.log_event("paused_environment", {"reason": "Critical environment issue"})
                    return state
            except Exception as e:
                logger.warning(f"[CONTROL] Environment check error: {e}")

            # TIER A: Budget check
            within_budget, reason = budget_controller.check_budget(safe_name)
            if not within_budget:
                state.status = "failed"
                state.log_event("budget_exhausted", {"reason": reason})
                logger.error(f"[CONTROL] Budget exhausted for {safe_name}: {reason}")
                await self._notify(safe_name, "budget_exhausted", {"reason": reason})
                return state

            # TIER A: Self-diagnosis
            health_issues = self_diagnosis.check_health(state, previous_state)
            for issue in health_issues:
                ctx.append(f"[DIAGNOSIS] {issue['severity']}", issue['message'])
                if issue['severity'] == 'critical':
                    state.log_event("health_issue", issue)

            previous_state = state

            # Phase 3: Check for interrupt/override signals before each step
            if interrupt_manager.check_and_handle(state):
                return state

            # Phase 3: Fine checkpoint before plan/build
            checkpoint_manager.save_checkpoint(
                safe_name, f"retry_{state.retries}_start",
                description=f"Start of retry {state.retries}",
                workspace=ws, state={"status": state.status, "retries": state.retries}
            )

            # STEP 2: PLAN (use site plan if available, else fallback)
            if not state.plan or state.status == "planning":
                state.status = "planning"
                if not state.plan:
                    from core.site_planner import plan_site
                    site_plan = plan_site(interpreted)
                    state.plan = site_plan.get("tasks", [])
                    if not state.template_name:
                        state.template_name = site_plan.get("template_name") or ""
                    if not state.template_path:
                        state.template_path = site_plan.get("template_path") or ""
                state.save()
                # Phase 3: Log planning decisions
                seed = decision_logger.get_seed(safe_name) or 0
                decision_logger.log(safe_name, DecisionEntry(
                    step="plan", decision_type="plan_step",
                    choices=[t.get("type", "") for t in state.plan],
                    chosen=", ".join([t["id"] for t in state.plan]),
                    rationale=f"Template: {state.template_name or 'none'}",
                    seeded=seed is not None,
                ))
                ctx.set_state("plan", state.plan)
                await self._notify(safe_name, "plan_created", {"tasks": len(state.plan)})
                logger.info(f"[CONTROL] Plan: {len(state.plan)} tasks")

            # Phase 3: Check interrupt before build
            if interrupt_manager.check_and_handle(state):
                return state

            # STEP 3: BUILD (parallel)
            if state.status in ("planning", "building", "fixing"):
                state.status = "building"
                state.save()
                checkpoint_manager.save_checkpoint(
                    safe_name, f"retry_{state.retries}_prebuild",
                    description=f"Before build retry {state.retries}",
                    workspace=ws, state={"status": state.status}
                )
                outputs = await self._execute_plan(state, ws, ctx)
                checkpoint_manager.save_checkpoint(
                    safe_name, f"retry_{state.retries}_postbuild",
                    description=f"After build retry {state.retries}",
                    workspace=ws, state={"status": state.status, "outputs": len(outputs)}
                )
                state.outputs = outputs
                state.log_event("build_complete", {"outputs": len(outputs)})
                state.save()
                # Phase 2: Record partial progress snapshot
                pages_built = [str(p) for p in ws.rglob("*.html")] if ws.exists() else []
                partial_tracker.init_project(safe_name, pages=[Path(p).stem for p in pages_built])
                for p in pages_built:
                    partial_tracker.mark_page(safe_name, Path(p).stem, "done", str(p))
                for tid in outputs:
                    partial_tracker.mark_step(safe_name, tid, True)
                state.partial_progress = partial_tracker.snapshot(safe_name).to_dict() if partial_tracker.snapshot(safe_name) else None
                await self._notify(safe_name, "build_complete", {"outputs": len(outputs)})

            # STEP 4: VALIDATE (real tools)
            state.status = "validating"
            state.save()
            validator = RealValidator(str(ws), template_name=state.template_name)
            results = await validator.validate_all(state, ws)
            state.validation_results = results
            state.save()
            summary = get_summary(state)
            await self._notify(safe_name, "validation_complete", summary)
            logger.info(f"[CONTROL] Validation: {summary['passed']}/{summary['total_checks']} passed")

            # Phase 2: Quality scoring (design, responsiveness, content, nav, code)
            qs = QualityScorer(str(ws))
            score = qs.score_all(safe_name)
            state.quality_score = score.to_dict()
            state.save()
            logger.info(f"[CONTROL] Quality score: {score.average:.1f}/10 "
                         f"(design={score.design_consistency:.1f} resp={score.responsiveness:.1f} "
                         f"content={score.content_quality:.1f} nav={score.navigation_quality:.1f} "
                         f"code={score.code_quality:.1f})")

            # STEP 5: CHECK DONE
            done, failures = is_done(state)
            if done:
                # STEP 5b: DEPLOY (if applicable)
                deploy_url = None
                goal_lower = goal.lower()
                if any(kw in goal_lower for kw in ("deploy", "vercel", "publish", "live", "host")):
                    try:
                        from tools.browser_agent import browser_agent
                        logger.info(f"[CONTROL] Deploying {safe_name} to Vercel...")
                        deploy_url = await browser_agent.deploy_to_vercel(str(ws), safe_name)
                        if deploy_url:
                            state.outputs["deploy_url"] = deploy_url
                            logger.info(f"[CONTROL] Deployed to {deploy_url}")
                            await self._notify(safe_name, "deployed", {"url": deploy_url})
                        else:
                            logger.warning(f"[CONTROL] Deploy returned no URL")
                    except Exception as e:
                        logger.warning(f"[CONTROL] Deploy failed: {e}")

                state.status = "done"
                state.log_event("build_done", {"retries": state.retries, "goal": goal[:60], "deploy_url": deploy_url})
                ctx.set_state("status", "done")
                ctx.set_state("deploy_url", deploy_url)
                await self._notify(safe_name, "build_done", {
                    "retries": state.retries, "goal": goal[:60], "deploy_url": deploy_url
                })
                self._record_outcome(safe_name, goal, state)
                logger.info(f"[CONTROL] BUILD DONE after {state.retries} retries")
                return state

            # Phase 3: Check for interrupt before retry
            if interrupt_manager.check_and_handle(state):
                return state

            # STEP 6: DIAGNOSE + FIX
            state.status = "fixing"
            state.issues = failures
            state.retries += 1
            budget_controller.record_retry(safe_name)

            # Phase 3: Log retry decision
            seed = decision_logger.get_seed(safe_name) or 0
            decision_logger.log(safe_name, DecisionEntry(
                step=f"retry_{state.retries}", decision_type="retry_strategy",
                choices=["continue", "abort"],
                chosen="continue",
                rationale=f"category={classify(' '.join(failures), {}).value if failures else 'none'}",
                seeded=seed is not None,
            ))

            # Phase 2: Record partial success — preserve usable outputs even on failure
            usable_pages = partial_tracker.sum_usable_pages(ws) if ws.exists() else []
            if usable_pages:
                logger.info(f"[CONTROL] {len(usable_pages)} usable pages preserved despite failures")
                state.outputs["usable_pages"] = usable_pages
                snap = partial_tracker.snapshot(safe_name)
                if snap:
                    state.partial_progress = snap.to_dict()

            # Classify failures to pick the right fix strategy
            failure_text = " ".join(failures)
            failure_cat = classify(failure_text, {"tool": state.current_task_id})
            ctx.append("[CLASSIFIER]", f"{failure_cat.value}: {failure_text[:100]}")

            # Phase 4 (D1): System Governor decides the action
            quality_val = state.quality_score.get("average", 0.0) if state.quality_score else None
            has_usable = len(partial_tracker.sum_usable_pages(ws)) > 0 if ws.exists() else False
            gov_decision = system_governor.decide(
                project=safe_name, failures=failures,
                failure_category=failure_cat.value,
                retries=state.retries, max_retries=state.max_retries,
                budget_remaining=budget_controller.budget.get(safe_name, {}).get("remaining", 1.0) if hasattr(budget_controller, "budget") else 1.0,
                quality_score=quality_val,
                score_trend="declining" if state.retries > 1 and quality_val and quality_val < 5.0 else "stable",
                partial_progress=state.partial_progress,
                has_usable_outputs=has_usable,
            )
            ctx.append("[GOVERNOR]", f"{gov_decision.action} ({gov_decision.confidence:.1f}): {gov_decision.reason}")

            if gov_decision.action == "abort":
                if self.autonomous:
                    self._log_autonomous_failure(safe_name, "abort", gov_decision.reason, failures)
                    logger.warning(f"[CONTROL] Autonomous mode: overriding governor abort — continuing")
                    state.plan = self._generate_fix_tasks(failures, interpreted)
                    state.outputs["autonomous_override"] = f"abort→continue: {gov_decision.reason}"
                else:
                    logger.info(f"[CONTROL] Governor: aborting build")
                    state.log_event("governor_abort", {"reason": gov_decision.reason})
                    state.status = "failed"
                    return state
            elif gov_decision.action == "pause":
                if self.autonomous:
                    self._log_autonomous_failure(safe_name, "pause", gov_decision.reason, failures)
                    logger.warning(f"[CONTROL] Autonomous mode: overriding governor pause — continuing")
                    state.plan = self._generate_fix_tasks(failures, interpreted)
                    state.outputs["autonomous_override"] = f"pause→continue: {gov_decision.reason}"
                else:
                    logger.info(f"[CONTROL] Governor: pausing build")
                    state.status = "paused"
                    state.save()
                    return state
            elif gov_decision.action == "replan":
                logger.info(f"[CONTROL] Governor: replanning from goal")
                state.log_event("replan", {"reason": failure_text[:200]})
                new_interpreted = await interpret_goal(state.goal)
                state.interpreted_goal = new_interpreted
                state.plan = self._create_plan(new_interpreted)
            elif gov_decision.action == "switch_tool":
                logger.info(f"[CONTROL] Governor: switching tool")
                state.plan = self._generate_fix_tasks(failures, interpreted)
            elif gov_decision.action == "escalate":
                logger.info(f"[CONTROL] Governor: escalating — usable outputs exist despite declining quality")
                state.plan = self._generate_fix_tasks(failures, interpreted)
                state.outputs["governor_note"] = gov_decision.reason
            else:
                state.plan = self._generate_fix_tasks(failures, interpreted)

            # Phase 4 (D2): Plan Evolution — apply suggested mutations
            suggestions = plan_evolution.suggest_fixes(safe_name, failures, state.plan, state.retries)
            for s in suggestions:
                if s.mutation_type == "insert" and s.new_task:
                    logger.info(f"[PLANEVO] Auto-inserting task: {s.new_task.get('description', '')[:60]}")
                    state.plan.append(s.new_task)

            # Phase 4 (D3): Memory-Driven agent selection for next retry
            try:
                from memory.decision_memory import decision_memory
                for task in state.plan:
                    tt = task.get("type", "")
                    if tt in ("frontend", "backend", "styling", "fix"):
                        best = memory_router.best_agent_for(tt, decision_memory)
                        if best and not memory_router.should_avoid(tt, best, decision_memory):
                            task["preferred_agent"] = best
            except Exception as e:
                logger.exception("[CONTROL] Decision memory agent selection failed: %s", e)

            state.log_event("retry", {"retry": state.retries, "failures": failures,
                                       "category": failure_cat.value, "governor": gov_decision.action})
            ctx.set_state("retries", state.retries)
            ctx.set_state("issues", failures)
            ctx.append(f"Retry {state.retries}/{state.max_retries}",
                       f"Failed: {', '.join(failures)} [{failure_cat.value}] Governor: {gov_decision.action}")
            await self._notify(safe_name, "retry", {"retry": state.retries, "failures": failures,
                                                     "category": failure_cat.value, "governor": gov_decision.action})
            logger.warning(f"[CONTROL] Retry {state.retries}/{state.max_retries}: {failures} [{failure_cat.value}] Gov: {gov_decision.action}")
            state.save()

        # ── FAILED ──
        state.status = "failed"
        # Phase 2: Preserve partial success data on final failure
        usable_pages = partial_tracker.sum_usable_pages(ws) if ws.exists() else []
        if usable_pages:
            state.outputs["usable_pages"] = usable_pages
            logger.info(f"[CONTROL] Build failed but {len(usable_pages)} usable pages preserved")
        snap = partial_tracker.snapshot(safe_name)
        if snap:
            state.partial_progress = snap.to_dict()
        self._record_outcome(safe_name, goal, state)
        state.log_event("build_failed", {"retries": state.retries, "max_retries": state.max_retries})
        ctx.set_state("status", "failed")
        await self._notify(safe_name, "build_failed", {
            "retries": state.retries, "max_retries": state.max_retries
        })
        logger.error(f"[CONTROL] BUILD FAILED after {state.max_retries} retries")
        return state

    def _create_plan(self, interpreted: dict) -> list[dict]:
        """Convert interpreted goal into a task DAG."""
        tasks = []
        task_id = 0

        def add_task(ttype: str, desc: str, deps: list[str] = None):
            nonlocal task_id
            task_id += 1
            tasks.append({
                "id": f"task_{task_id}",
                "type": ttype,
                "description": desc,
                "depends_on": deps or [],
            })

        project_type = interpreted.get("project_type", "website")
        pages = interpreted.get("pages", [])
        tech = interpreted.get("tech_stack", ["html", "css"])

        goal_ctx = interpreted.get("original_goal", "")
        if project_type in ("website", "static") or "html" in tech:
            add_task("scaffold", f"Set up project structure for {project_type}")
            page_list = ", ".join(pages) if pages else "home, about, contact"
            pages_marker = f" [PAGES:{','.join(pages)}]" if pages else ""
            add_task("frontend", f"Goal: {goal_ctx}. Build {project_type} with pages: {page_list}. Tech: {', '.join(tech)}{pages_marker}",
                     deps=["task_1"])
            if "tailwind" in tech or "bootstrap" in tech or len(pages) > 2:
                add_task("styling", f"Apply consistent styling across all pages", deps=[f"task_{task_id}"])
            if "contact" in pages:
                add_task("form", f"Build contact form with validation", deps=[f"task_{task_id}"])

        elif project_type == "webapp":
            add_task("scaffold", f"Set up {project_type} project. Tech: {', '.join(tech)}")
            add_task("frontend", f"Build UI components and pages: {', '.join(pages)}",
                     deps=["task_1"])
            if any(t in tech for t in ("fastapi", "flask", "django", "node")):
                add_task("backend", f"Build API backend with {', '.join(tech)}",
                         deps=["task_1"])
            if any(k in interpreted.get("original_goal", "").lower() for k in ("auth", "login", "user")):
                add_task("auth", "Implement authentication", deps=["task_2"])
            add_task("styling", "Apply theming and responsive design", deps=["task_2"])

        elif project_type == "api":
            add_task("scaffold", f"Scaffold API project. Tech: {', '.join(tech)}")
            add_task("backend", f"Build API endpoints and business logic",
                     deps=["task_1"])
            if any(k in interpreted.get("original_goal", "").lower() for k in ("db", "database", "sql", "postgres")):
                add_task("database", "Set up database models and migrations",
                         deps=["task_1"])
            add_task("test", "Write API endpoint tests", deps=["task_2"])

        else:
            goal_text = interpreted.get("original_goal", "")[:60]
            add_task("scaffold", f"Set up project for {goal_text}")
            add_task("frontend", "Build UI", deps=["task_1"])
            add_task("styling", "Apply styling", deps=["task_2"])

        goal_text = interpreted.get("original_goal", "")
        if "deploy" in goal_text.lower() or "docker" in goal_text.lower() or "ci" in goal_text.lower():
            add_task("deploy", "Set up deployment configuration", deps=[f"task_{task_id}"])
        if "doc" in goal_text.lower() or "readme" in goal_text.lower():
            add_task("docs", "Write project documentation", deps=[f"task_{task_id}"])

        tasks.sort(key=lambda t: TASK_TYPE_ORDER.get(t["type"], 99))
        return tasks

    def _generate_fix_tasks(self, failures: list[str], interpreted: dict) -> list[dict]:
        """Generate repair tasks from validation failures."""
        fix_tasks = []
        original_goal = interpreted.get("original_goal", "")
        for failure in failures:
            check = failure.split(":")[0] if ":" in failure else failure
            if check == "all_pages_exist":
                pages = interpreted.get("pages", [])
                pages_marker = f" [PAGES:{','.join(pages)}]" if pages else ""
                fix_tasks.append({
                    "id": "fix_pages", "type": "fix",
                    "description": f"{original_goal or 'Create all missing pages'}{pages_marker}",
                    "depends_on": [],
                })
            elif check == "no_broken_links":
                fix_tasks.append({
                    "id": "fix_links", "type": "fix",
                    "description": "Fix all broken links and missing referenced files",
                    "depends_on": ["fix_pages"] if fix_tasks and fix_tasks[-1]["id"] == "fix_pages" else [],
                })
            elif check == "no_placeholders":
                fix_tasks.append({
                    "id": "fix_placeholders", "type": "fix",
                    "description": "Replace all placeholder text, TODO markers, and template variables with real content",
                    "depends_on": [],
                })
            elif check == "nav_consistent":
                fix_tasks.append({
                    "id": "fix_nav", "type": "fix",
                    "description": "Make navigation consistent across all pages",
                    "depends_on": [],
                })
            elif check == "html_valid":
                fix_tasks.append({
                    "id": "fix_html", "type": "fix",
                    "description": "Fix HTML syntax errors in all pages",
                    "depends_on": [],
                })
            elif check == "visual_quality":
                msg = failure.split(":", 1)[1] if ":" in failure else failure
                issues = []
                if "issues:" in msg:
                    issues_part = msg.split("issues:", 1)[1]
                    issues = [i.strip() for i in issues_part.split(";") if i.strip()]
                if not issues:
                    issues = ["visual_score_below_threshold"]
                for issue in issues:
                    issue_lower = issue.lower()
                    if any(kw in issue_lower for kw in ("content", "text", "message", "headline", "copy")):
                        fix_tasks.append({
                            "id": f"fix_vis_content_{len(fix_tasks)}", "type": "fix",
                            "description": f"Regenerate page content: {issue}",
                            "depends_on": [],
                        })
                    elif any(kw in issue_lower for kw in ("brand", "logo", "name", "identity")):
                        fix_tasks.append({
                            "id": f"fix_vis_brand_{len(fix_tasks)}", "type": "fix",
                            "description": f"Fix branding mismatch: {issue}",
                            "depends_on": [],
                        })
                    elif any(kw in issue_lower for kw in ("image", "icon", "placeholder", "img", "photo")):
                        fix_tasks.append({
                            "id": f"fix_vis_images_{len(fix_tasks)}", "type": "fix",
                            "description": f"Fix missing or broken images: {issue}",
                            "depends_on": [],
                        })
                    elif any(kw in issue_lower for kw in ("layout", "spacing", "alignment", "responsive", "mobile")):
                        fix_tasks.append({
                            "id": f"fix_vis_layout_{len(fix_tasks)}", "type": "fix",
                            "description": f"Fix layout issues: {issue}",
                            "depends_on": [],
                        })
                    elif any(kw in issue_lower for kw in ("element", "broken", "error", "missing")):
                        fix_tasks.append({
                            "id": f"fix_vis_element_{len(fix_tasks)}", "type": "fix",
                            "description": f"Fix broken elements: {issue}",
                            "depends_on": [],
                        })
                    else:
                        fix_tasks.append({
                            "id": f"fix_vis_other_{len(fix_tasks)}", "type": "fix",
                            "description": f"Fix visual issue: {issue}",
                            "depends_on": [],
                        })
            elif check == "reasoning_quality":
                fix_tasks.append({
                    "id": "fix_reasoning", "type": "fix",
                    "description": "Regenerate content with better reasoning, structure, and relevance",
                    "depends_on": [],
                })
        if not fix_tasks:
            fix_tasks.append({
                "id": "fix_general", "type": "fix",
                "description": f"Fix validation failures: {', '.join(failures)}",
                "depends_on": [],
            })
        return fix_tasks

    async def _execute_plan(self, state: ProjectState, workspace: Path, ctx: SharedContext) -> dict[str, str]:
        """Execute plan tasks in parallel respecting dependencies."""
        tasks = state.plan
        if not tasks:
            return {}

        launcher = AgentLauncher(workspace=str(workspace), auto_approve=self.auto_approve)
        outputs = {}
        completed = set()
        failed = set()

        async def progress_handler(agent: str, line: str, is_stderr: bool):
            if is_stderr:
                ctx.append(f"[{agent}] stderr", line)
            else:
                ctx.append(f"[{agent}] stdout", line)

        while len(completed | failed) < len(tasks):
            ready = []
            task_map = {t["id"]: t for t in tasks}
            for t in tasks:
                tid = t["id"]
                if tid in completed or tid in failed:
                    continue
                deps = [d for d in t.get("depends_on", []) if d in task_map]
                if all(d in completed for d in deps):
                    ready.append(t)

            if not ready and len(completed | failed) < len(tasks):
                break

            running = []
            for t in ready[:MAX_PARALLEL]:
                agent = self._assign_agent(t, launcher)
                task_type = t.get("type", "scaffold")
                if agent == "shell":
                    fn = SHELL_TASK_TEMPLATES.get(task_type, lambda d, ws: f'python -c "print(\'{d}\')"')
                    prompt = fn(t.get("description", ""), str(workspace))
                    if task_type in ("frontend", "form") and state.composed_plan:
                        import json as _json
                        cp = _json.dumps(state.composed_plan).replace('"', '\\"')
                        prompt += f' --compose "{cp}"'
                else:
                    template = TASK_TEMPLATES.get(task_type, "Work on: {description}")
                    prompt = template.format(description=t.get("description", ""))
                state.current_task_id = t["id"]
                state.log_agent(agent, t["id"], "started")
                ctx.append(f"Starting {t['id']}", f"Agent: {agent}\n{prompt}")

                async def run_one(task=t, a=agent, p=prompt):
                    # Acquire workspace lock for write-type tasks
                    task_type = task.get("type", "")
                    needs_lock = task_type not in ("test", "docs", "deploy")
                    if needs_lock:
                        lock_manager.acquire(a, str(workspace))
                    try:
                        result = await launcher.launch(a, p, timeout=600, progress_callback=progress_handler)
                    finally:
                        if needs_lock:
                            lock_manager.release(a, str(workspace))
                    return task, result

                running.append(asyncio.create_task(run_one(t, agent, prompt)))

            if not running:
                break

            done_set, pending = await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
            for fut in done_set:
                task_obj, result = fut.result()
                tid = task_obj["id"]
                if result.exit_code == 0 and not result.timed_out:
                    completed.add(tid)
                    outputs[tid] = result.stdout[-500:]
                    state.log_agent(result.agent, tid, "completed", result.stdout[-200:])
                    ctx.mark_task_complete(tid, result.stdout[-500:])
                else:
                    failed.add(tid)
                    state.log_agent(result.agent, tid, "failed", result.stderr[-200:])

            running = list(pending)

        state.log_event("execution_complete", {
            "completed": len(completed), "failed": len(failed)
        })
        return outputs

    def _assign_agent(self, task: dict, launcher: AgentLauncher) -> str:
        task_type = task.get("type", "scaffold")
        preferred = AGENT_CAPABILITY_MAP.get(task_type, ["shell"])
        # Prefer shell directly for static HTML generation (no API keys needed)
        if task_type in ("scaffold", "frontend", "styling", "form", "test", "docs", "fix"):
            return "shell"
        for agent_name in preferred:
            if launcher.is_available(agent_name):
                return agent_name
        return "shell"

    def _record_outcome(self, project: str, goal: str, state: ProjectState):
        """Record build outcome to decision_memory for future learning."""
        try:
            from memory.decision_memory import decision_memory
            visual_score = None
            reasoning_score = None
            if state.quality_score:
                visual_score = state.quality_score.get("average")  # QualityScorer average
            if state.validation_results:
                for r in state.validation_results:
                    if hasattr(r, "check") and r.check == "visual_quality" and not r.passed:
                        pass
                    if hasattr(r, "check") and r.check == "reasoning_quality" and not r.passed:
                        pass
            amb_resolved = state.ambiguous_goal_result is not None
            decision_memory.record(
                goal=goal,
                task="build",
                agents_tried=["shell"],
                winner="shell" if state.status == "done" else None,
                duration_s=0,
                success=state.status == "done",
                error="; ".join(state.issues) if state.issues else "",
                keys_rotated=0,
                visual_score=visual_score,
                reasoning_score=reasoning_score,
                ambiguity_resolved=amb_resolved,
                fix_applied=None,
            )
        except Exception as e:
            logger.warning(f"[CONTROL] Outcome recording skipped: {e}")

    def _log_autonomous_failure(self, project: str, action: str, reason: str, failures: list[str]):
        """Log a persistent failure to failures.jsonl instead of blocking the build."""
        import json, time
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "project": project,
            "action": action,
            "reason": reason,
            "failures": failures,
        }
        try:
            with open(self._failures_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
            logger.info(f"[CONTROL] Autonomous failure logged: {project} {action}")
        except Exception as e:
            logger.warning(f"[CONTROL] Failed to write autonomous failure log: {e}")

    def get_status(self, project_name: str) -> Optional[dict]:
        state = ProjectState.load(project_name)
        if state:
            return {
                "name": state.project_name,
                "status": state.status,
                "goal": state.goal[:80],
                "retries": state.retries,
                "max_retries": state.max_retries,
                "issues": len(state.issues),
                "validation": get_summary(state) if state.validation_results else None,
                "quality_score": state.quality_score,
                "partial_progress": state.partial_progress,
            }
        return None

    def list_projects(self) -> list[dict]:
        return list_projects()

    def cancel_build(self, project_name: str) -> bool:
        state = ProjectState.load(project_name)
        if state:
            if state.status in ("building", "fixing", "validating", "planning", "interpreting", "paused"):
                interrupt_manager.signal_cancel(project_name)
                logger.info(f"[CONTROL] Cancel signaled for {project_name}")
                return True
            state.status = "cancelled"
            state.log_event("cancelled", {})
            state.save()
            return True
        return False

    def pause_build(self, project_name: str) -> bool:
        interrupt_manager.signal_pause(project_name)
        return True

    def override_build(self, project_name: str, overrides: dict) -> bool:
        state = ProjectState.load(project_name)
        if state:
            if state.status in ("building", "fixing", "validating", "planning"):
                interrupt_manager.signal_override(project_name, overrides)
                return True
            for k, v in overrides.items():
                if hasattr(state, k):
                    setattr(state, k, v)
            state.log_event("overridden", overrides)
            state.save()
            return True
        return False

    def resume_paused(self, project_name: str) -> bool:
        state = ProjectState.load(project_name)
        if state and state.status == "paused":
            state.status = "building"
            state.save()
            task = asyncio.create_task(self.resume_build(project_name))
            self.running_builds[project_name] = task
            return True
        return False

    async def request_fix(self, failures: list[str],
                           project_dir: str,
                           interpreted: dict | None = None) -> list[str]:
        """Public entry point for external components (eg real_validator)
        to request self-correction.  Returns list of fix task IDs executed."""
        fix_tasks = self._generate_fix_tasks(
            failures, interpreted or {"original_goal": "Fix validation issues"}
        )
        if not fix_tasks:
            return []
        from core.agent_launcher import AgentLauncher
        launcher = AgentLauncher(workspace=project_dir, auto_approve=self.auto_approve)
        executed = []
        for task in fix_tasks:
            try:
                result = await launcher.launch(
                    "shell" if task.get("type") == "shell" else "build",
                    task.get("description", ""),
                    timeout=300,
                )
                executed.append(task["id"])
            except Exception as e:
                logger.warning(f"[FIX] Task {task['id']} failed: {e}")
        return executed


control_loop = ControlLoop()
