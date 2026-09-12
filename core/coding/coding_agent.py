"""Coding AI specialist entry point.

This module orchestrates repository intelligence, change planning, refactoring,
and test verification. It implements the standard SpecialistModule protocol for
the Capability AI and Super-Brain architecture.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Optional

from core.coding.architecture_map import ArchitectureMapper
from core.coding.change_planner import ChangePlan, ChangePlanner, ChangeType, FileChange
from core.coding.change_simulation import ChangeSimulation
from core.coding.coding_state import (
    CodingAction,
    CodingCapabilityContract,
    CodingConstraints,
    CodingResult,
    CodingStatus,
)
from core.coding.dependency_graph import DependencyGraph
from core.coding.impact_analyzer import ImpactAnalyzer
from core.coding.refactor_safety import RefactorSafetyEngine
from core.coding.refactoring_engine import RefactoringEngine
from core.coding.repository_indexer import RepositoryIndexer
from core.coding.tool_broker import CodingToolBroker
from core.coding.verification import CodingVerifier
from core.specialist import SpecialistModule, SpecialistResult
from tools.base_tool import (
    CapabilityDefinition,
    CapabilityHealth,
    CapabilityStatus as CapStatus,
    CapabilityType,
    RiskTier,
    VerificationSpec,
)

logger = logging.getLogger(__name__)

Implementer = Callable[[ChangePlan], list[dict[str, Any]]]


class CodingAI(SpecialistModule):
    """Repository-focused coding specialist for future Super-Brain delegation."""

    def __init__(
        self,
        repository: str | Path = ".",
        *,
        memory: Any = None,
        event_bus: Any = None,
        task_graph_factory: Any = None,
        tool_registry: Any = None,
        verifier: CodingVerifier | None = None,
    ):
        self.repository = Path(repository).resolve()
        self.memory = memory
        self.event_bus = event_bus
        self.task_graph_factory = task_graph_factory
        self.tool_registry = tool_registry
        self.contract = CodingCapabilityContract()
        self.indexer = RepositoryIndexer(self.repository)
        self.dependency_graph = DependencyGraph(self.indexer)
        self.architecture = ArchitectureMapper(self.indexer, self.dependency_graph)
        self.impact = ImpactAnalyzer(self.indexer, self.dependency_graph, self.architecture)
        self.planner = ChangePlanner(self.indexer, self.dependency_graph, self.architecture, self.impact)
        self.safety = RefactorSafetyEngine(self.indexer, self.dependency_graph, self.architecture, self.impact)
        self.simulator = ChangeSimulation(self.indexer, self.dependency_graph, self.architecture, self.impact)
        self.refactoring = RefactoringEngine(self.indexer, self.dependency_graph, self.architecture, self.impact)
        self.verifier = verifier or CodingVerifier(self.repository)
        self.tool_broker = CodingToolBroker(self)

    @property
    def name(self) -> str:
        return "Coding AI"

    @property
    def description(self) -> str:
        return (
            "Repository-focused coding specialist: source indexing, dependency analysis, "
            "architecture mapping, change simulation, refactoring, and deterministic test verification."
        )

    def health_check(self) -> dict[str, Any]:
        """Probe repository accessibility and indexer readiness."""
        exists = self.repository.exists()
        is_dir = self.repository.is_dir()
        file_count = 0
        if exists and is_dir:
            try:
                entries = self.indexer.all_entries()
                file_count = len(entries)
            except Exception:
                file_count = 0
        healthy = exists and is_dir
        return {
            "status": CapabilityHealth.HEALTHY.value if healthy else CapabilityHealth.UNHEALTHY.value,
            "details": {
                "repository": str(self.repository),
                "exists": exists,
                "is_dir": is_dir,
                "indexed_files": file_count,
            },
        }

    def get_capabilities(self) -> list[CapabilityDefinition]:
        """Return authoritative capability definitions exported by Coding AI."""
        return [
            CapabilityDefinition(
                name="coding.index_repository",
                type=CapabilityType.SPECIALIST_ACTION,
                owner_module=self.name,
                description="Scan and build AST/file intelligence of the active workspace",
                inputs={"force": {"type": "boolean", "default": False}},
                outputs={"repository": {"type": "object"}},
                requirements=["filesystem"],
                risk=RiskTier.LOW,
                verification=VerificationSpec(method="indexed_entries_present"),
                health=CapabilityHealth.HEALTHY,
                health_check=lambda: bool(self.health_check()["status"] == "healthy"),
                handler=lambda force=False: self.indexer.index(force=force).summary(),
            ),
            CapabilityDefinition(
                name="coding.map_architecture",
                type=CapabilityType.SPECIALIST_ACTION,
                owner_module=self.name,
                description="Analyze architectural layers, components, and module dependencies",
                inputs={},
                outputs={"architecture": {"type": "object"}, "dependencies": {"type": "object"}},
                requirements=["filesystem"],
                risk=RiskTier.LOW,
                verification=VerificationSpec(method="architecture_layers_mapped"),
                health=CapabilityHealth.HEALTHY,
                handler=lambda: {
                    "architecture": self.architecture.map_layers().to_dict(),
                    "dependencies": self.dependency_graph.summary(),
                },
            ),
            CapabilityDefinition(
                name="coding.plan_change",
                type=CapabilityType.SPECIALIST_ACTION,
                owner_module=self.name,
                description="Generate a dependency-aware, atomic change plan for a programming objective",
                inputs={
                    "objective": {"type": "string"},
                    "changes": {"type": "array", "description": "Optional explicit file changes"},
                },
                outputs={"plan": {"type": "object"}},
                requirements=["filesystem"],
                risk=RiskTier.LOW,
                verification=VerificationSpec(method="plan_non_empty"),
                health=CapabilityHealth.HEALTHY,
                handler=lambda objective, changes=None: self.plan(objective, changes).to_dict(),
            ),
            CapabilityDefinition(
                name="coding.simulate_change",
                type=CapabilityType.SPECIALIST_ACTION,
                owner_module=self.name,
                description="Predict affected files, merge conflicts, and architectural breakages before changing code",
                inputs={"objective": {"type": "string"}},
                outputs={"simulation": {"type": "object"}},
                requirements=["filesystem"],
                risk=RiskTier.LOW,
                verification=VerificationSpec(method="simulation_reported"),
                health=CapabilityHealth.HEALTHY,
                handler=lambda objective: self.simulator.simulate(self.plan(objective)).to_dict(),
            ),
            CapabilityDefinition(
                name="coding.execute_refactor",
                type=CapabilityType.SPECIALIST_ACTION,
                owner_module=self.name,
                description="Safely apply code modifications, run tests, and verify outcomes against regressions",
                inputs={
                    "objective": {"type": "string"},
                    "commands": {"type": "array", "description": "Test verification commands"},
                },
                outputs={"result": {"type": "object"}},
                requirements=["filesystem", "python"],
                risk=RiskTier.MEDIUM,
                risk_tags=["modify", "code", "refactor"],
                verification=VerificationSpec(method="tests_pass_cleanly"),
                health=CapabilityHealth.HEALTHY,
                handler=lambda objective, commands=None: self.execute(
                    objective,
                    constraints=CodingConstraints(commands=commands or []),
                ).to_dict(),
            ),
            CapabilityDefinition(
                name="coding.verify_code",
                type=CapabilityType.SPECIALIST_ACTION,
                owner_module=self.name,
                description="Run deterministic test commands and inspect git working tree status",
                inputs={"commands": {"type": "array", "description": "Test or build commands to execute"}},
                outputs={"verification": {"type": "object"}},
                requirements=["filesystem", "terminal"],
                risk=RiskTier.LOW,
                verification=VerificationSpec(method="exit_code_zero"),
                health=CapabilityHealth.HEALTHY,
                handler=lambda commands=None: self.verifier.verify(commands or []).to_dict(),
            ),
        ]

    def execute_capability(
        self,
        capability_name: str,
        params: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> SpecialistResult:
        caps = {cap.name: cap for cap in self.get_capabilities()}
        if capability_name not in caps:
            return SpecialistResult(
                success=False,
                error=f"Capability '{capability_name}' not owned by {self.name}. Available: {list(caps.keys())}",
            )
        cap = caps[capability_name]
        try:
            output = cap.handler(**params) if cap.handler else None
            res = SpecialistResult(
                success=True,
                output=output,
            )
            verified, reason = self.verify(capability_name, res)
            res.verified = verified
            res.verification_reason = reason
            return res
        except Exception as ex:
            return SpecialistResult(
                success=False,
                error=f"Execution of {capability_name} failed: {ex}",
                verified=False,
                verification_reason="Exception raised during execution",
            )

    def verify(self, capability_name: str, result: SpecialistResult) -> tuple[bool, str]:
        if not result.success:
            return False, f"Execution failed: {result.error}"
        if capability_name == "coding.index_repository":
            return True, "Repository indexed successfully"
        elif capability_name == "coding.map_architecture":
            return True, "Architecture layers and dependencies mapped"
        elif capability_name == "coding.plan_change":
            return True, "Change plan constructed"
        elif capability_name == "coding.simulate_change":
            return True, "Simulation completed without crashes"
        elif capability_name == "coding.verify_code":
            v = result.output or {}
            is_ok = v.get("status") == "success"
            return is_ok, f"Verification status: {v.get('status', 'unknown')}"
        elif capability_name == "coding.execute_refactor":
            res = result.output or {}
            status = res.get("status")
            return status == "success", f"Execution outcome: {status}"
        return True, "Verified by default rule"

    def capability_contract(self) -> dict[str, Any]:
        return self.contract.to_dict()

    def refresh_repository_intelligence(self) -> dict[str, Any]:
        self.indexer.index(force=True)
        self.dependency_graph.build()
        architecture = self.architecture.map_layers()
        return {
            "repository": self.indexer.summary(),
            "dependencies": self.dependency_graph.summary(),
            "architecture": architecture.to_dict(),
        }

    def classify_risk(self, objective: str, changes: list[FileChange]) -> str:
        text = " ".join([objective] + [change.file for change in changes]).lower()
        if any(token in text for token in ("auth", "authentication", "security", "database", "migration", "deploy", "production")):
            return "high"
        if len(changes) > 3 or any(change.change_type in {ChangeType.DELETE, ChangeType.RENAME} for change in changes):
            return "medium"
        return "low"

    def _infer_changes(self, objective: str) -> list[FileChange]:
        matches = self.indexer.search(objective)
        if not matches:
            tokens = [token.strip(".,:;!?()[]{}").lower() for token in objective.split()]
            scored = []
            for entry in self.indexer.all_entries():
                score = sum(1 for token in tokens if token and token in entry.path.lower())
                if score:
                    scored.append((score, entry))
            matches = [entry for _, entry in sorted(scored, key=lambda item: item[0], reverse=True)[:5]]
        return [FileChange(ChangeType.MODIFY, entry.path, f"Investigate for objective: {objective}") for entry in matches[:5]]

    def plan(self, objective: str, changes: list[FileChange] | None = None) -> ChangePlan:
        self.refresh_repository_intelligence()
        return self.planner.plan(objective, changes if changes is not None else self._infer_changes(objective))

    def execute(
        self,
        objective: str,
        repository: str | Path | None = None,
        constraints: CodingConstraints | dict[str, Any] | None = None,
        risk_policy: dict[str, Any] | None = None,
        changes: list[FileChange] | None = None,
        implementer: Implementer | None = None,
    ) -> CodingResult:
        if repository is not None and Path(repository).resolve() != self.repository:
            return CodingAI(repository, memory=self.memory, event_bus=self.event_bus, task_graph_factory=self.task_graph_factory, tool_registry=self.tool_registry).execute(
                objective, constraints=constraints, risk_policy=risk_policy, changes=changes, implementer=implementer
            )
        if isinstance(constraints, dict):
            constraints = CodingConstraints(**constraints)
        constraints = constraints or CodingConstraints()
        actions: list[CodingAction] = []
        failures: list[str] = []
        intelligence = self.refresh_repository_intelligence()
        actions.append(CodingAction("repository_intelligence", "Built repository, dependency, and architecture context", intelligence))

        plan = self.planner.plan(objective, changes if changes is not None else self._infer_changes(objective))
        actions.append(CodingAction("planning", "Created dependency-aware change plan", plan.to_dict()))
        risk = self.classify_risk(objective, plan.changes)
        if risk == "high" and not constraints.allow_high_risk and not (risk_policy or {}).get("allow_high_risk", False):
            failures.append("High-risk coding objective requires approval before implementation")
            verification = self.verifier.verify(constraints.commands).to_dict()
            return CodingResult(
                CodingStatus.PARTIAL,
                objective,
                plan.to_dict(),
                actions,
                verification=verification,
                failures=failures,
                evidence={"risk": risk, "contract": self.capability_contract()},
                remaining_risks=[risk],
            )

        simulation = self.simulator.simulate(plan)
        actions.append(CodingAction("simulation", "Predicted affected files, conflicts, and breakages", simulation.to_dict()))

        # When no implementer is injected, ask the tool broker to select a
        # capability for observability. Selection alone does not authorize
        # filesystem changes; execution remains explicit via an implementer.
        active_implementer = implementer
        broker_selection: dict | None = None
        broker_implementer = None
        if active_implementer is None:
            sel = self.tool_broker.select_capability(plan)
            broker_selection = sel.to_dict()
            actions.append(CodingAction(
                "tool_selection",
                f"Broker selected capability: {sel.capability.value}",
                broker_selection,
            ))
            # A broker-supplied implementer is only meaningful when a
            # verification signal exists; without commands every attempt would
            # fail identically, so execution stays off (honest UNKNOWN).
            if constraints.commands:
                broker_implementer = self.tool_broker.build_implementer(plan)

        implementation_records: list[dict[str, Any]] = []
        # A repair loop only makes sense when verification commands exist:
        # with no commands there is no failure signal to repair against, so
        # the implementer gets exactly one attempt (never blind retries).
        max_attempts = max(1, constraints.max_attempts) if constraints.commands else 1
        attempts_used = 0
        last_verification = None
        for attempt in range(1, max_attempts + 1):
            attempt_implementer = active_implementer or broker_implementer
            if attempt_implementer is None:
                break
            if attempt > 1:
                actions.append(CodingAction(
                    "repair",
                    f"Repair attempt {attempt} after failed verification",
                    {"attempt": attempt, "prior_failures": list(failures)},
                ))
            attempts_used = attempt
            records = attempt_implementer(plan)
            implementation_records.extend(records)
            actions.append(CodingAction("implementation", f"Implementation attempt {attempt}", {"records": records}))
            last_verification = self.verifier.verify(constraints.commands)
            actions.append(CodingAction("verification", f"Verification attempt {attempt}", last_verification.to_dict()))
            if last_verification.status == "success":
                return CodingResult(
                    CodingStatus.SUCCESS,
                    objective,
                    plan.to_dict(),
                    actions,
                    files_changed=last_verification.files_changed,
                    tests=[check.to_dict() for check in last_verification.checks],
                    verification=last_verification.to_dict(),
                    evidence={
                        "risk": risk,
                        "implementation": implementation_records,
                        "attempts": attempts_used,
                        "contract": self.capability_contract(),
                    },
                )
            failures.extend(
                f"{check.command} failed"
                for check in (last_verification.checks or [])
                if not check.success
            )

        # Honest outcome: if an implementer acted but verification never
        # confirmed success, the result is FAILED — never optimistic. When
        # nothing was implemented, the outcome cannot be established: UNKNOWN.
        implementer_ran = attempts_used > 0
        verification = last_verification if last_verification is not None else self.verifier.verify(constraints.commands)
        status = CodingStatus.FAILED if implementer_ran else CodingStatus.UNKNOWN
        return CodingResult(
            status,
            objective,
            plan.to_dict(),
            actions,
            files_changed=verification.files_changed,
            tests=[check.to_dict() for check in verification.checks],
            verification=verification.to_dict(),
            failures=failures,
            evidence={
                "risk": risk,
                "implementation": implementation_records,
                "attempts": attempts_used,
                "contract": self.capability_contract(),
            },
            remaining_risks=[item.message for item in simulation.breakages],
        )
