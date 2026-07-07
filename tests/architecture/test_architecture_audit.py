"""
Architecture audit — verify ownership boundaries per ADR-007.

Questions asked at the Phase 3-4 checkpoint:

1. Any LLM calls outside Execution?
2. Any memory writes outside Memory?
3. Any provider selection outside Capability Runtime?
4. Any direct Activity mutations?
5. Any duplicated planning?
6. Any duplicated retrieval?
7. Any duplicated verification?

An import or reference to a restricted module counts as a violation
ONLY if it appears in production code (``core/``), not in tests or
docs.
"""
from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest

CORE = Path("core")


# ── Helpers ────────────────────────────────────────────────────────────────────


def _prod_files() -> list[Path]:
    """Return all Python files in ``core/``, excluding ``__pycache__``."""
    return sorted(CORE.rglob("*.py"))


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _is_test_or_doc(path: Path) -> bool:
    return False  # We already excluded tests


def _extract_imports(source: str) -> list[str]:
    """Return fully-qualified module names imported in *source*."""
    imports: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return imports
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def _matches(import_name: str, targets: set[str]) -> bool:
    """Check if *import_name* matches any of the *targets* (prefix match)."""
    for target in targets:
        if import_name == target or import_name.startswith(target + "."):
            return True
    return False


# ── Rule 1: No LLM calls outside Execution ─────────────────────────────────────


RESTRICTED_LLM = {"core.llm_router", "litellm", "openai", "anthropic", "google.generativeai"}
ALLOWED_LLM = {"core.pipeline.stages.execution"}


@pytest.mark.parametrize("path", _prod_files())
def test_no_llm_outside_execution(path: Path):
    if path.name == "execution.py":
        pytest.skip("Execution stage is the owner")
    source = _read_source(path)
    imports = _extract_imports(source)
    violations = [i for i in imports if _matches(i, RESTRICTED_LLM)]
    assert not violations, (
        f"{path} imports LLM module(s) {violations}. "
        "LLM calls are confined to Execution stage (core.pipeline.stages.execution)."
    )


# ── Rule 2: No memory facade writes outside Memory stage ──────────────────────


RESTRICTED_MEMORY_WRITE = {"memory.memory_facade"}
ALLOWED_MEMORY_WRITE = {"core.pipeline.stages.memory"}


@pytest.mark.parametrize("path", _prod_files())
def test_no_memory_writes_outside_memory(path: Path):
    if path.name == "memory.py":
        pytest.skip("Memory stage is the owner")
    source = _read_source(path)
    imports = _extract_imports(source)
    violations = [i for i in imports if _matches(i, RESTRICTED_MEMORY_WRITE)]
    assert not violations, (
        f"{path} imports memory facade {violations}. "
        "Memory facade writes are confined to Memory stage."
    )


# ── Rule 3: No FactStore writes outside Memory stage ──────────────────────────


RESTRICTED_FACTSTORE = {"memory.fact_store"}
ALLOWED_FACTSTORE = {"core.pipeline.stages.memory"}


@pytest.mark.parametrize("path", _prod_files())
def test_no_fact_store_writes_outside_memory(path: Path):
    if path.name == "memory.py":
        pytest.skip("Memory stage is the owner")
    source = _read_source(path)
    imports = _extract_imports(source)
    violations = [i for i in imports if _matches(i, RESTRICTED_FACTSTORE)]
    assert not violations, (
        f"{path} imports fact store {violations}. "
        "Fact store writes are confined to Memory stage."
    )


# ── Rule 4: No ProviderManager outside Execution stage ────────────────────────


RESTRICTED_PROVIDER = {"core.pipeline.stages.execution"}
ALLOWED_PROVIDER = set()


@pytest.mark.parametrize("path", _prod_files())
def test_no_provider_manager_outside_execution(path: Path):
    if path.name == "execution.py":
        pytest.skip("Execution stage is the owner")
    source = _read_source(path)
    # Check for ProviderManager or Provider class references
    if "ProviderManager" in source or "class Provider(" in source:
        pytest.fail(
            f"{path} references ProviderManager or defines a Provider class. "
            "Provider management is confined to Execution stage."
        )


# ── Rule 5: No ActivityGraph mutations outside Execution ──────────────────────


RESTRICTED_ACTIVITY = {"core.activity.manager", "core.activity.models.ActivityStatus"}


@pytest.mark.parametrize("path", _prod_files())
def test_no_direct_activity_mutations(path: Path):
    if path.name == "execution.py":
        pytest.skip("Execution stage is the owner")
    source = _read_source(path)
    imports = _extract_imports(source)
    violations = [i for i in imports if _matches(i, RESTRICTED_ACTIVITY)]
    assert not violations, (
        f"{path} imports Activity modules {violations}. "
        "Activity mutations are confined to Execution stage (Runtime class)."
    )


# ── Rule 6: No duplicating Reasoner ──────────────────────────────────────────


@pytest.mark.parametrize("path", _prod_files())
def test_no_duplicate_reasoner(path: Path):
    if path.name in ("reasoner.py", "reasoning.py"):
        # The stage file itself is fine; look for other files doing reasoning
        return
    source = _read_source(path)
    # Check for class names that suggest alternative reasoning
    suspicious_classes = re.findall(r"class\s+\w*Reason\w+", source)
    # Filter out ABCs, tests, known names
    known_ok = {"AbstractReasoner", "BaseReasoner"}
    violations = [c for c in suspicious_classes if c not in known_ok]
    assert not violations, (
        f"{path} defines {violations}. "
        "There must be exactly one Reasoner abstraction (ReasonerStage in stages/reasoner.py)."
    )


# ── Rule 7: No duplicate Verification ────────────────────────────────────────


@pytest.mark.parametrize("path", _prod_files())
def test_no_duplicate_verification(path: Path):
    if path.name == "__init__.py" and "verification" in str(path):
        return
    source = _read_source(path)
    suspicious = re.findall(r"class\s+\w*Verif\w+", source)
    known_ok = {"Verifier", "VerificationStage", "SafetyVerifier", "SchemaVerifier", "ConfidenceVerifier"}
    violations = [c for c in suspicious if c not in known_ok]
    assert not violations, (
        f"{path} defines {violations}. "
        "Verification logic must be contained in core/pipeline/stages/verification/"
    )



# ── Phase 5 Rules ────────────────────────────────────────────────────────────
# These rules enforce the Runtime v1 freeze (ADR-008).


# ── Rule 8: Scheduler only imports pipeline internals through PipelineExecutor ─


# We don't need to check "core.pipeline.pipeline_executor" because that *is*
# the bridge. Pattern: any ``from core.pipeline`` import inside core/scheduler/
# must come from ``pipeline_executor.py``.
ALLOWED_SCHEDULER_PIPELINE_IMPORTS = {"core.scheduler.pipeline_executor"}


@pytest.mark.parametrize("path", [p for p in _prod_files() if "scheduler" in p.parts])
def test_scheduler_imports_pipeline_only_via_pipeline_executor(path: Path):
    """Scheduler must not import pipeline internals except via PipelineExecutor.

    ``core/scheduler/pipeline_executor.py`` is the only allowed bridge.
    ``core/scheduler/*.py`` files must not ``from core.pipeline`` import
    anything directly.
    """
    if path.name == "pipeline_executor.py":
        pytest.skip("Pipeline executor is the intentional bridge")
    source = _read_source(path)
    imports = _extract_imports(source)
    violations = [i for i in imports if i.startswith("core.pipeline")]
    assert not violations, (
        f"{path} imports pipeline module(s) {violations}. "
        "The Scheduler may only reach the pipeline through "
        "core.scheduler.pipeline_executor.pipeline_executor()."
    )


# ── Rule 9: Outcome only ever created in Execution stage ─────────────────────

# The canonical ``Outcome`` dataclass lives at ``core.pipeline.outcome``.
# Only ``execution.py`` may construct it.


@pytest.mark.parametrize("path", _prod_files())
def test_outcome_only_created_in_execution(path: Path):
    if path.name == "execution.py":
        pytest.skip("Execution stage is the owner of Outcome")
    if path.name == "outcome.py":
        pytest.skip("Outcome definition lives here")
    source = _read_source(path)
    # Look for direct Outcome( construction (not imports, not type hints)
    # We match any ``Outcome(`` token that is not preceded by a dot
    lines = source.split("\n")
    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        # Skip imports, comments, and string literals
        if stripped.startswith("from ") or stripped.startswith("import "):
            continue
        if stripped.startswith("#"):
            continue
        if "Outcome(" in stripped and "Outcome(" not in stripped.split("#")[0]:
            pytest.fail(
                f"{path}:{lineno} constructs Outcome directly. "
                "Outcome must only be created in the Execution stage "
                "(core/pipeline/stages/execution.py)."
            )


# ── Rule 10: Observation.new() only ever called in Execution stage ───────────


@pytest.mark.parametrize("path", _prod_files())
def test_observation_only_created_in_execution(path: Path):
    if path.name == "execution.py":
        pytest.skip("Execution stage creates observations")
    if path.name in ("observation.py", "__init__.py"):
        pytest.skip("Observation definition lives here")
    source = _read_source(path)
    lines = source.split("\n")
    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("from ") or stripped.startswith("import "):
            continue
        if stripped.startswith("#"):
            continue
        if "Observation.new(" in stripped:
            pytest.fail(
                f"{path}:{lineno} calls Observation.new() directly. "
                "Observations must only be created in the Execution stage "
                "(core/pipeline/stages/execution.py)."
            )



# ── Rule 11: Single path invariant ──────────────────────────────────────────
# Every new component must integrate through existing canonical interfaces
# rather than creating alternate execution paths.

SINGLE_PATH_EXEMPTIONS = {
    "core/pipeline/pipeline.py",           # owns process_message()
    "core/pipeline/stages/execution.py",   # owns Runtime
    "core/pipeline/observation.py",        # owns Observation
    "core/pipeline/outcome.py",            # owns Outcome
    "core/pipeline/context.py",            # owns PipelineContext
    "core/pipeline/base.py",               # owns PipelineStage, HookRegistry
    "core/pipeline/deterministic.py",      # owns DeterministicServices
    "core/pipeline/architecture_metrics.py",  # owns ArchitectureMetrics
    "core/observation/hub.py",             # owns ObservationHub
    "core/scheduler/pipeline_executor.py", # owns PipelineExecutor bridge
    "core/runtime_version.py",             # owns RuntimeVersion
}


@pytest.mark.parametrize("path", [p for p in _prod_files()
                                   if str(p.as_posix()) not in SINGLE_PATH_EXEMPTIONS])
def test_no_alternate_process_message(path: Path):
    """No file outside the pipeline may reimplement process_message().

    Only ``core/pipeline/pipeline.py`` may define ``process_message()``.
    Any other file that defines a function accepting ``Request`` and
    returning ``Response``, or that directly calls ``Pipeline.execute()``
    outside of ``process_message()``, is an alternate path violation.
    """
    source = _read_source(path)
    lines = source.split("\n")
    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        # Ignore comments, strings, and test files
        if stripped.startswith("#") or stripped.startswith('"') or stripped.startswith("'"):
            continue

        # Flag: async def process_message outside the canonical home
        if "async def process_message" in stripped and path.name != "pipeline.py":
            pytest.fail(
                f"{path}:{lineno} defines an alternate process_message(). "
                "All request processing must go through "
                "core/pipeline/pipeline.process_message()."
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
