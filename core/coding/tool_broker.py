"""Coding AI tool broker — capability-selection layer.

The CodingToolBroker maps a ChangePlan to the best available coding tool or
agent.  It is a thin selector, not a new brain.  It does not own memory, a
task graph, or a tool registry.  Its only job is to answer the question:

    "Given this plan and the tools available in this environment,
     which capability should execute the implementation?"

Available capability types (in precedence order):
    patch_applicator  — RefactoringEngine (always available, pure Python)
    shell             — subprocess / terminal (available if Python is present)
    git               — Git CLI (available if `git` is on PATH)
    test_runner       — Python subprocess (always available)
    linter            — flake8 / ruff / pylint (available if on PATH)
    cli_agent         — External coding agent CLI (optional, checked via PATH)

The broker produces an ``Implementer`` callable that CodingAI.execute() can
use when no external implementer is injected.  The ``Implementer`` protocol is
unchanged: it receives a ``ChangePlan`` and returns a list of dicts recording
what was done.

Architectural invariant
-----------------------
CodingToolBroker MUST NOT:
  - instantiate a second CodingAI or CodingBrain
  - own its own memory system
  - own its own task graph
  - own its own tool registry beyond the local availability cache

It MAY:
  - hold a weak reference back to the owning CodingAI for filesystem access
  - call shutil.which() to probe tool availability
  - call subprocess.run() to invoke tools
  - use RefactoringEngine to apply patches
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from core.coding.coding_agent import CodingAI

from core.coding.change_planner import ChangePlan, ChangeType, FileChange


# ---------------------------------------------------------------------------
# Capability taxonomy
# ---------------------------------------------------------------------------

class CodingCapability(str, Enum):
    """Named capabilities the broker can select from."""
    PATCH_APPLICATOR = "patch_applicator"   # RefactoringEngine — always available
    SHELL             = "shell"             # Generic subprocess/terminal execution
    GIT               = "git"              # Git CLI for diffs, commits, branches
    TEST_RUNNER       = "test_runner"       # Python subprocess test execution
    LINTER            = "linter"            # flake8 / ruff / pylint
    CLI_AGENT         = "cli_agent"         # External coding agent (aider, cursor, etc.)
    NONE              = "none"              # No capability available / not applicable


@dataclass
class CapabilityInfo:
    """Metadata about a single discovered capability."""
    capability: CodingCapability
    available: bool
    binary: str | None = None           # Path to the binary if applicable
    version: str | None = None          # Version string if probed
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability.value,
            "available": self.available,
            "binary": self.binary,
            "version": self.version,
            "notes": self.notes,
        }


@dataclass
class ToolSelection:
    """Result of a capability selection for a given plan."""
    capability: CodingCapability
    rationale: str
    info: CapabilityInfo
    fallback: CodingCapability | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability.value,
            "rationale": self.rationale,
            "available": self.info.available,
            "binary": self.info.binary,
            "fallback": self.fallback.value if self.fallback else None,
        }


# ---------------------------------------------------------------------------
# Broker
# ---------------------------------------------------------------------------

class CodingToolBroker:
    """Capability-selection layer for Coding AI.

    Selects the best available tool for a given ``ChangePlan`` and produces an
    ``Implementer`` callable the CodingAI can use directly.

    Parameters
    ----------
    coding_ai:
        Weak back-reference to the owning CodingAI.  Used for filesystem
        access (indexer, refactoring engine) only.  Must not be used to
        re-enter CodingAI.execute().
    cli_agent_binaries:
        Optional ordered list of CLI coding-agent binary names to probe.
        Defaults to common agents: aider, cursor, continue, openhands.
    """

    # CLI coding agents to probe, in preference order
    _DEFAULT_CLI_AGENTS: list[str] = ["aider", "cursor", "continue", "openhands", "codeium"]
    # Linters to probe, in preference order
    _DEFAULT_LINTERS: list[str] = ["ruff", "flake8", "pylint"]

    def __init__(
        self,
        coding_ai: "CodingAI",
        *,
        cli_agent_binaries: list[str] | None = None,
    ) -> None:
        self._ai = coding_ai
        self._cli_agents = cli_agent_binaries or self._DEFAULT_CLI_AGENTS
        self._capability_cache: dict[CodingCapability, CapabilityInfo] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enumerate_available_tools(self, *, refresh: bool = False) -> dict[CodingCapability, CapabilityInfo]:
        """Probe and return all capabilities available in the current environment.

        Results are cached after the first call.  Pass ``refresh=True`` to
        re-probe (useful in tests or when the environment changes).
        """
        if self._capability_cache is not None and not refresh:
            return self._capability_cache

        caps: dict[CodingCapability, CapabilityInfo] = {}

        # patch_applicator: RefactoringEngine is pure Python — always available
        caps[CodingCapability.PATCH_APPLICATOR] = CapabilityInfo(
            capability=CodingCapability.PATCH_APPLICATOR,
            available=True,
            binary=sys.executable,
            notes="RefactoringEngine (pure Python, always available)",
        )

        # shell: Python subprocess is always available
        caps[CodingCapability.SHELL] = CapabilityInfo(
            capability=CodingCapability.SHELL,
            available=True,
            binary=sys.executable,
            notes="subprocess.run() — always available",
        )

        # git
        git_path = shutil.which("git")
        caps[CodingCapability.GIT] = CapabilityInfo(
            capability=CodingCapability.GIT,
            available=git_path is not None,
            binary=git_path,
            version=self._probe_version("git", ["git", "--version"]) if git_path else None,
            notes="Git CLI",
        )

        # test_runner: Python is always available for running tests
        caps[CodingCapability.TEST_RUNNER] = CapabilityInfo(
            capability=CodingCapability.TEST_RUNNER,
            available=True,
            binary=sys.executable,
            notes="Python subprocess test runner (always available)",
        )

        # linter: first available wins
        linter_path: str | None = None
        linter_name: str | None = None
        for name in self._DEFAULT_LINTERS:
            p = shutil.which(name)
            if p:
                linter_path = p
                linter_name = name
                break
        caps[CodingCapability.LINTER] = CapabilityInfo(
            capability=CodingCapability.LINTER,
            available=linter_path is not None,
            binary=linter_path,
            version=self._probe_version(linter_name or "", [linter_name or "", "--version"]) if linter_path else None,
            notes=f"{linter_name} linter" if linter_name else "No linter found on PATH",
        )

        # cli_agent: first available wins
        agent_path: str | None = None
        agent_name: str | None = None
        for name in self._cli_agents:
            p = shutil.which(name)
            if p:
                agent_path = p
                agent_name = name
                break
        caps[CodingCapability.CLI_AGENT] = CapabilityInfo(
            capability=CodingCapability.CLI_AGENT,
            available=agent_path is not None,
            binary=agent_path,
            notes=f"{agent_name} CLI agent" if agent_name else "No CLI coding agent found on PATH",
        )

        self._capability_cache = caps
        return caps

    def select_capability(self, plan: ChangePlan) -> ToolSelection:
        """Choose the best capability for the given plan.

        Selection logic (in order of precedence):
        1. If a CLI agent is available AND the plan has many changes (>= 3) or
           is a CREATE — prefer the CLI agent for large/greenfield tasks.
        2. If changes are MODIFY/DELETE/RENAME — prefer patch_applicator
           (deterministic, always available, no external dependencies).
        3. Shell is always a fallback for any implementation.

        Returns a ``ToolSelection`` with the chosen capability and rationale.
        """
        tools = self.enumerate_available_tools()
        changes = plan.changes

        # Classify the plan
        has_creates = any(c.change_type == ChangeType.CREATE for c in changes)
        n_changes = len(changes)
        has_deletes = any(c.change_type == ChangeType.DELETE for c in changes)
        has_renames = any(c.change_type == ChangeType.RENAME for c in changes)

        # --- Rule 1: CLI agent for large or greenfield tasks ---
        if tools[CodingCapability.CLI_AGENT].available and (n_changes >= 3 or (has_creates and n_changes >= 2)):
            return ToolSelection(
                capability=CodingCapability.CLI_AGENT,
                rationale=(
                    f"CLI agent selected: {n_changes} changes with "
                    f"{'CREATE ' if has_creates else ''}"
                    f"{'DELETE ' if has_deletes else ''}"
                    f"tasks suit an interactive coding agent"
                ),
                info=tools[CodingCapability.CLI_AGENT],
                fallback=CodingCapability.PATCH_APPLICATOR,
            )

        # --- Rule 2: patch_applicator for structural changes ---
        if has_deletes or has_renames:
            return ToolSelection(
                capability=CodingCapability.PATCH_APPLICATOR,
                rationale="patch_applicator selected: DELETE/RENAME operations need safe snapshot+rollback",
                info=tools[CodingCapability.PATCH_APPLICATOR],
                fallback=CodingCapability.SHELL,
            )

        # --- Rule 3: patch_applicator for all MODIFY changes (default) ---
        if changes and all(c.change_type == ChangeType.MODIFY for c in changes):
            return ToolSelection(
                capability=CodingCapability.PATCH_APPLICATOR,
                rationale="patch_applicator selected: all MODIFY changes — deterministic patch application",
                info=tools[CodingCapability.PATCH_APPLICATOR],
                fallback=CodingCapability.SHELL,
            )

        # --- Rule 4: shell for CREATE or mixed ---
        if changes:
            return ToolSelection(
                capability=CodingCapability.SHELL,
                rationale=f"shell selected: mixed change types ({set(c.change_type.value for c in changes)})",
                info=tools[CodingCapability.SHELL],
                fallback=CodingCapability.PATCH_APPLICATOR,
            )

        # --- Rule 5: empty plan — nothing to do ---
        return ToolSelection(
            capability=CodingCapability.NONE,
            rationale="No changes in plan — no capability needed",
            info=CapabilityInfo(CodingCapability.NONE, available=False, notes="Empty plan"),
            fallback=None,
        )

    def build_implementer(self, plan: ChangePlan) -> Callable[[ChangePlan], list[dict[str, Any]]] | None:
        """Produce an Implementer callable for the given plan.

        The returned callable matches the ``Implementer`` protocol:
            implementer(plan: ChangePlan) -> list[dict[str, Any]]

        Each dict records what the tool did (file, change, tool, status).

        Returns ``None`` when no suitable capability is available (e.g. empty plan).
        The CodingAI will treat None the same as no implementer provided, yielding
        CodingStatus.UNKNOWN — the honest outcome.
        """
        selection = self.select_capability(plan)

        if selection.capability == CodingCapability.NONE:
            return None

        if selection.capability == CodingCapability.PATCH_APPLICATOR:
            return self._patch_applicator_implementer(selection)

        if selection.capability == CodingCapability.CLI_AGENT:
            # CLI agent not yet wired for automated invocation — fall back
            fallback_cap = selection.fallback or CodingCapability.PATCH_APPLICATOR
            fallback_info = self.enumerate_available_tools().get(
                fallback_cap,
                CapabilityInfo(CodingCapability.PATCH_APPLICATOR, available=True),
            )
            fallback_selection = ToolSelection(
                capability=fallback_cap,
                rationale=f"CLI agent available but not auto-invocable; falling back to {fallback_cap.value}",
                info=fallback_info,
                fallback=None,
            )
            return self._patch_applicator_implementer(fallback_selection)

        if selection.capability == CodingCapability.SHELL:
            return self._shell_implementer(selection)

        # Default: patch_applicator
        return self._patch_applicator_implementer(selection)

    def capability_summary(self) -> dict[str, Any]:
        """Return a JSON-serialisable summary of all discovered capabilities."""
        tools = self.enumerate_available_tools()
        selection = self.select_capability(
            __import__("core.coding.change_planner", fromlist=["ChangePlan"]).ChangePlan(request="summary")
        )
        return {
            "tools": {cap.value: info.to_dict() for cap, info in tools.items()},
            "default_selection": selection.to_dict(),
            "environment": {
                "python": sys.executable,
                "platform": sys.platform,
            },
        }

    # ------------------------------------------------------------------
    # Private implementer factories
    # ------------------------------------------------------------------

    def _patch_applicator_implementer(
        self, selection: ToolSelection
    ) -> Callable[[ChangePlan], list[dict[str, Any]]]:
        """Return an Implementer that uses RefactoringEngine to apply patches.

        This is the safest default: it generates patches with TODO stubs for
        MODIFY/CREATE, captures snapshots, and records what was done.  The
        actual code content must be provided by a higher layer (Super-Brain or
        human operator) — the broker's role is to *structure* the application,
        not to generate the code content.
        """
        ai = self._ai

        def implementer(plan: ChangePlan) -> list[dict[str, Any]]:
            records: list[dict[str, Any]] = []
            try:
                patches = ai.refactoring.generate_patches(plan)
                snapshots = ai.refactoring.apply_patches(patches, dry_run=True)
                for patch in patches:
                    records.append({
                        "file": patch.file,
                        "change": patch.description,
                        "tool": CodingCapability.PATCH_APPLICATOR.value,
                        "patch_type": patch.patch_type,
                        "status": "dry_run_snapshot",
                        "rationale": selection.rationale,
                    })
            except Exception as exc:
                records.append({
                    "file": "unknown",
                    "change": "patch_applicator failed",
                    "tool": CodingCapability.PATCH_APPLICATOR.value,
                    "status": "error",
                    "error": str(exc),
                })
            return records

        return implementer

    def _shell_implementer(
        self, selection: ToolSelection
    ) -> Callable[[ChangePlan], list[dict[str, Any]]]:
        """Return an Implementer that uses shell commands for file operations.

        Currently generates shell command strings without executing them
        (dry-run); actual execution requires explicit approval from the
        Super-Brain or human operator (high-risk gate).
        """
        def implementer(plan: ChangePlan) -> list[dict[str, Any]]:
            records: list[dict[str, Any]] = []
            for change in plan.changes:
                cmd = _change_to_shell_cmd(change)
                records.append({
                    "file": change.file,
                    "change": change.description,
                    "tool": CodingCapability.SHELL.value,
                    "shell_command": cmd,
                    "status": "dry_run_command",
                    "rationale": selection.rationale,
                })
            return records

        return implementer

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _probe_version(name: str, cmd: list[str]) -> str | None:
        """Run ``cmd`` and return the first line of stdout, or None on failure."""
        if not name or not cmd or not cmd[0]:
            return None
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().splitlines()[0]
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _change_to_shell_cmd(change: FileChange) -> str:
    """Translate a FileChange into an approximate shell command string (informational)."""
    ct = change.change_type
    if ct == ChangeType.CREATE:
        return f"touch {change.file!r}  # then populate"
    if ct == ChangeType.DELETE:
        return f"rm {change.file!r}"
    if ct == ChangeType.RENAME and change.new_file:
        return f"mv {change.file!r} {change.new_file!r}"
    if ct == ChangeType.MOVE and change.new_file:
        return f"mv {change.file!r} {change.new_file!r}"
    return f"# modify {change.file!r}: {change.description}"
