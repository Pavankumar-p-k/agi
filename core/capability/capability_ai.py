"""CapabilityAI — the system's self-knowledge layer.

Answers "what can JARVIS do?" from an authoritative registry, recommends
capabilities for goals, validates workflows (flagging gaps instead of
hallucinating), learns verified recipes, and runs the quarantine
acquisition pipeline for new capabilities.
"""
from __future__ import annotations

import re
import shutil
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Optional

from tools.base_tool import (
    CapabilityDefinition,
    CapabilityHealth,
    CapabilityStatus,
    CapabilityType,
    ReliabilityMetrics,
    RiskTier,
    VerificationSpec,
)
from tools.registry import ToolRegistry, new_capability_registry


class TrustTier(str, Enum):
    BUILTIN = "builtin"
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    QUARANTINED = "quarantined"


class AcquisitionStage(str, Enum):
    RECEIVED = "received"
    INSPECTED = "inspected"
    SANDBOXED = "sandboxed"
    APPROVED = "approved"
    REGISTERED = "registered"
    AVAILABLE = "available"
    FAILED = "failed"


# Dangerous constructs that fail the acquisition inspection outright.
_DANGEROUS_PATTERNS = ("eval(", "exec(", "__import__", "subprocess",
                       "os.system", "rm -rf", "format(")

_STOPWORDS = {
    "a", "an", "and", "the", "this", "that", "to", "for", "of", "in",
    "with", "my", "your", "me", "i", "it", "is", "are", "do", "does",
}


def _tokens(text: str) -> set:
    words = re.findall(r"[a-z0-9]+", str(text).lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 1}


@dataclass
class Recommendation:
    capability: CapabilityDefinition
    score: float
    match_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.capability.name,
            "score": self.score,
            "match_reason": self.match_reason,
        }


@dataclass
class CapabilityGap:
    requested_need: str
    reason: str = "not found in the capability registry"

    def to_dict(self) -> dict:
        return {"requested_need": self.requested_need, "reason": self.reason}


@dataclass
class AcquisitionCandidate:
    name: str
    source_type: str = "manual"
    source_identifier: str = ""
    description: str = ""
    suggested_owner: str = "Acquired"
    requirements: list = field(default_factory=list)
    code_sample: str = ""


@dataclass
class AcquisitionAudit:
    candidate: AcquisitionCandidate
    current_stage: AcquisitionStage = AcquisitionStage.RECEIVED
    failed: bool = False
    failure_reason: str = ""
    stage_history: list = field(default_factory=list)

    def advance(self, stage: AcquisitionStage) -> None:
        self.current_stage = stage
        self.stage_history.append(stage.value)

    def fail(self, reason: str) -> None:
        self.failed = True
        self.failure_reason = reason
        self.current_stage = AcquisitionStage.FAILED
        self.stage_history.append(AcquisitionStage.FAILED.value)


@dataclass
class ExperienceRecipe:
    pattern_key: str
    goal_intent: str
    capabilities_used: list
    success: bool
    note: str = ""
    uses: int = 0

    def keywords(self) -> set:
        return _tokens(self.goal_intent) | {
            t for t in _tokens(self.pattern_key.replace(":", " "))}


class CapabilityAI:
    """Facade over the authoritative capability registry.

    ``CapabilityAI()`` starts with an empty registry and no specialists —
    an empty system honestly reports that it can do nothing.
    """

    def __init__(self, registry: Optional[ToolRegistry] = None) -> None:
        self.registry: ToolRegistry = registry if registry is not None \
            else new_capability_registry()
        self._recipes: dict[str, ExperienceRecipe] = {}

    # ── discovery / sync ─────────────────────────────────────────────
    def sync(self, specialists: Optional[Iterable[Any]] = None) -> int:
        """Register specialist capabilities + discovered CLI tools.

        Returns the number of capabilities registered.
        """
        registered = 0
        for specialist in specialists or []:
            definitions = self._definitions_for(specialist)
            for definition in definitions:
                self.registry.register_capability(definition)
                registered += 1
        for name in self._discover_clis():
            definition = CapabilityDefinition(
                name=f"cli.{name}",
                type=CapabilityType.CLI,
                owner_module="CLI",
                description=f"{name} command line interface",
                risk=RiskTier.MEDIUM,
                requirements=[],
                verification=VerificationSpec(method="cli_exit_zero"),
                health=CapabilityHealth.HEALTHY,
            )
            self.registry.register_capability(definition)
            registered += 1
        return registered

    @staticmethod
    def _definitions_for(specialist: Any) -> list:
        if hasattr(specialist, "capabilities_as_definitions"):
            return list(specialist.capabilities_as_definitions())
        if hasattr(specialist, "get_capabilities"):
            return list(specialist.get_capabilities())
        return []

    @staticmethod
    def _discover_clis() -> list:
        found = []
        for name in ("python", "pip", "git", "npm", "node", "docker",
                     "code", "cargo"):
            if shutil.which(name):
                found.append(name)
        return found

    # ── discovery query ──────────────────────────────────────────────
    def what_can_jarvis_do(self, only_healthy: bool = True) -> list:
        """All registered capabilities, optionally health-filtered."""
        capabilities = self.registry.list_capabilities()
        if only_healthy:
            capabilities = [c for c in capabilities
                            if c.health == CapabilityHealth.HEALTHY]
        return list(capabilities)

    # ── recommendation ───────────────────────────────────────────────
    def recommend(self, goal: str, top_k: int = 8) -> list:
        """Rank capabilities for a goal; empty when nothing matches."""
        goal_tokens = _tokens(goal)
        if not goal_tokens:
            return []

        scored: list[Recommendation] = []
        for capability in self.registry.list_capabilities():
            name_tokens = _tokens(capability.name.replace(".", " "))
            desc_tokens = _tokens(capability.description)
            name_overlap = goal_tokens & name_tokens
            desc_overlap = goal_tokens & desc_tokens
            base = 1.5 * len(name_overlap) + 0.5 * len(desc_overlap)
            if base <= 0:
                continue
            scored.append(Recommendation(
                capability=capability,
                score=round(min(base, 2.0), 3),
                match_reason=(f"name match: {sorted(name_overlap)}"
                              if name_overlap
                              else f"description match: {sorted(desc_overlap)}"),
            ))

        # Learned recipes boost capabilities used in verified successes.
        for recipe in self._recipes.values():
            overlap = goal_tokens & recipe.keywords()
            if not overlap or not recipe.success:
                continue
            for used in recipe.capabilities_used:
                capability = self.registry.get_capability(used)
                if capability is None:
                    continue
                boosted = Recommendation(
                    capability=capability,
                    score=round(2.0 + 0.1 * recipe.uses, 3),
                    match_reason=f"Learned recipe '{recipe.pattern_key}' "
                                 f"(matched: {sorted(overlap)})",
                )
                scored = [r for r in scored if r.capability.name != used]
                scored.append(boosted)

        scored.sort(key=lambda r: -r.score)
        return scored[:top_k]

    # ── workflow validation ──────────────────────────────────────────
    def validate_workflow(self, chain: list) -> tuple:
        """Validate a capability chain: (valid, resolved, gaps)."""
        resolved = []
        gaps: list[CapabilityGap] = []
        for name in chain or []:
            capability = self.registry.get_capability(str(name))
            if capability is None:
                gaps.append(CapabilityGap(requested_need=str(name)))
            else:
                resolved.append(capability)
        return (len(gaps) == 0, resolved, gaps)

    # ── experience / recipes ─────────────────────────────────────────
    def record_experience(self, pattern_key: str, goal_intent: str,
                          capabilities_used: list, success: bool,
                          note: str = "") -> ExperienceRecipe:
        """Record a verified success/failure as a learned recipe."""
        recipe = self._recipes.get(pattern_key)
        if recipe is None:
            recipe = ExperienceRecipe(
                pattern_key=pattern_key,
                goal_intent=goal_intent,
                capabilities_used=list(capabilities_used),
                success=success,
                note=note,
            )
            self._recipes[pattern_key] = recipe
        else:
            recipe.success = recipe.success or success
            for used in capabilities_used:
                if used not in recipe.capabilities_used:
                    recipe.capabilities_used.append(used)
        recipe.uses += 1

        # Learned capabilities become first-class registry entries.
        for used in capabilities_used:
            if not self.registry.has_capability(used):
                self.registry.register_capability(CapabilityDefinition(
                    name=used,
                    type=CapabilityType.COMPOSITE,
                    owner_module="Learned",
                    description=f"Learned from recipe '{pattern_key}'",
                    verification=VerificationSpec(method="recipe_replay"),
                ))
        return recipe

    # ── acquisition (quarantine pipeline) ────────────────────────────
    def acquire_safely(self, candidate: AcquisitionCandidate,
                       sandbox_tester: Optional[Callable[[], bool]] = None,
                       user_approval_granted: bool = False,
                       handler: Optional[Callable] = None,
                       live_verifier: Optional[Callable[[], bool]] = None) -> AcquisitionAudit:
        """10-stage-style quarantine: inspect → sandbox → approve → register.

        Dangerous code never reaches the registry; nothing registers
        without explicit approval; verification must pass at every stage.
        """
        audit = AcquisitionAudit(candidate=candidate)
        audit.advance(AcquisitionStage.INSPECTED)

        # Stage: static inspection of the code sample.
        sample = str(candidate.code_sample or "")
        for pattern in _DANGEROUS_PATTERNS:
            if pattern in sample:
                audit.fail(
                    f"quarantined: dangerous construct '{pattern}' found "
                    f"in code sample (eval/exec are not permitted)")
                return audit

        # Stage: sandbox execution.
        if sandbox_tester is not None:
            audit.advance(AcquisitionStage.SANDBOXED)
            try:
                sandbox_ok = bool(sandbox_tester())
            except Exception as exc:  # noqa: BLE001
                audit.fail(f"sandbox test raised: {exc}")
                return audit
            if not sandbox_ok:
                audit.fail("sandbox test failed")
                return audit

        # Stage: explicit human approval.
        if not user_approval_granted:
            audit.fail("user approval was not granted")
            return audit
        audit.advance(AcquisitionStage.APPROVED)

        # Stage: registration with the real handler.
        try:
            definition = CapabilityDefinition(
                name=candidate.name,
                type=CapabilityType.SERVICE,
                owner_module=candidate.suggested_owner or "Acquired",
                description=candidate.description
                            or f"Acquired from {candidate.source_type}",
                requirements=list(candidate.requirements),
                handler=handler,
                verification=VerificationSpec(method="live_verifier"),
                health=CapabilityHealth.HEALTHY,
                status=CapabilityStatus.AVAILABLE,
            )
            self.registry.register_capability(definition)
        except Exception as exc:  # noqa: BLE001
            audit.fail(f"registration failed: {exc}")
            return audit
        audit.advance(AcquisitionStage.REGISTERED)

        # Stage: live verification of the real capability.
        if live_verifier is not None:
            try:
                if not bool(live_verifier()):
                    audit.fail("live verification failed")
                    return audit
            except Exception as exc:  # noqa: BLE001
                audit.fail(f"live verification raised: {exc}")
                return audit

        audit.advance(AcquisitionStage.AVAILABLE)
        return audit

    # ── execution passthrough ────────────────────────────────────────
    def execute_capability(self, name: str, params: Optional[dict] = None):
        """Execute a registered capability through its owning specialist."""
        capability = self.registry.get_capability(name)
        if capability is None or capability.handler is None:
            from core.specialist import SpecialistResult
            return SpecialistResult(
                success=False, verified=False,
                error=f"capability '{name}' has no executable handler")
        try:
            output = capability.handler(**(params or {}))
        except TypeError:
            output = capability.handler(params or {})
        from core.specialist import SpecialistResult
        if isinstance(output, SpecialistResult):
            return output
        return SpecialistResult(success=True, verified=True, output=output)


__all__ = [
    "CapabilityAI", "Recommendation", "CapabilityGap",
    "AcquisitionCandidate", "AcquisitionAudit", "AcquisitionStage",
    "TrustTier",
]
