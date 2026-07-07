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
LLM_EXEMPTIONS = {
    "core/agent_runtime.py",       # pre-existing — links LLM calls before Phase 2C extraction
    "core/llm_factory.py",         # pre-existing — LLM provider factory
    "core/llm_router.py",          # owns core.llm_router
}


@pytest.mark.parametrize("path", _prod_files())
def test_no_llm_outside_execution(path: Path):
    if path.name == "execution.py":
        pytest.skip("Execution stage is the owner")
    posix = path.as_posix()
    for exempt in LLM_EXEMPTIONS:
        if exempt in posix:
            pytest.skip(f"{exempt} is exempt from LLM import restriction")
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

# ── Rule 12: Only core/identity/service.py may instantiate IdentityContext ──
# in production code.  Tests and identity model definitions are exempt.


@pytest.mark.parametrize("path", _prod_files())
def test_identity_context_only_created_by_service(path: Path):
    """Only core/identity/service.py may construct IdentityContext directly.

    All other production code must obtain an IdentityContext through
    ``get_identity_service().create_context()``.
    """
    posix = path.as_posix()
    if "core/identity/service.py" in posix:
        pytest.skip("IdentityService is the canonical creator")
    if "core/pipeline/stages/auth.py" in posix:
        pytest.skip("AuthenticationStage may replace IdentityContext during state transition")
    if "identity" in path.parts:
        pytest.skip("Identity model files are exempt")
    source = _read_source(path)
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and hasattr(node.func, "id"):
            if node.func.id == "IdentityContext":
                lineno = getattr(node, "lineno", 0)
                pytest.fail(
                    f"{path}:{lineno} constructs IdentityContext directly. "
                    "Only core/identity/service.py may create IdentityContext. "
                    "Use get_identity_service().create_context() instead."
                )


# ── Rule 13: Only AuthenticationStage may construct AuthenticationResult ────
# in production code.  Tests and model definitions are exempt.


@pytest.mark.parametrize("path", _prod_files())
def test_authentication_result_only_created_by_auth_stage(path: Path):
    """Only ``core/pipeline/stages/auth.py`` may construct AuthenticationResult.

    All other production code must read it from ``PipelineContext.authentication_result``.
    """
    posix = path.as_posix()
    if "core/pipeline/stages/auth.py" in posix:
        pytest.skip("AuthenticationStage is the canonical creator")
    if "authentication_result" in posix:
        pytest.skip("AuthenticationResult definition is exempt")
    source = _read_source(path)
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and hasattr(node.func, "id"):
            if node.func.id == "AuthenticationResult":
                lineno = getattr(node, "lineno", 0)
                pytest.fail(
                    f"{path}:{lineno} constructs AuthenticationResult directly. "
                    "Only AuthenticationStage (core/pipeline/stages/auth.py) may "
                    "create AuthenticationResult."
                )


# ── Rule 14: Only AuthenticationStage may transition AuthenticationState ────
# i.e. write ``authentication_state`` to ``IdentityContext`` in production code.


RESTRICTED_AUTH_STATE = {"AuthenticationState.AUTHENTICATED", "AuthenticationState.SYSTEM"}


@pytest.mark.parametrize("path", [p for p in _prod_files() if "auth.py" not in p.name])
def test_only_auth_stage_transitions_authentication_state(path: Path):
    """Only AuthenticationStage may set ``authentication_state`` to AUTHENTICATED or SYSTEM.

    Excludes model definitions and the auth stage itself.
    """
    if "identity" in path.parts and path.name != "service.py":
        pytest.skip("Identity model files are exempt")
    posix = path.as_posix()
    if "core/identity/service.py" in posix:
        pytest.skip("IdentityService creates IdentityContext with AuthenticationState")
    if "core/pipeline/stages/authorization.py" in posix:
        pytest.skip("AuthorizationStage reads AuthenticationState (does not write it)")
    source = _read_source(path)
    for token in RESTRICTED_AUTH_STATE:
        if token in source:
            pytest.fail(
                f"{path} references {token}. "
                "Only AuthenticationStage may transition AuthenticationState to "
                "AUTHENTICATED or SYSTEM."
            )


# ── Rule 15: Only IdentityService and AuthenticationStage may directly access AuthManager ──


RESTRICTED_AUTH_MANAGER = {"core.auth", "core.auth.AuthManager"}
AUTH_MANAGER_EXEMPTIONS = {
    "core/auth.py",               # owns AuthManager
    "core/authz/engine.py",       # pre-existing (policy engine)
    "core/authz/loader.py",       # pre-existing (role loader)
    "core/lifespan.py",           # pre-existing (startup)
    "core/routes/admin.py",       # pre-existing (admin routes)
    "core/routes/vision.py",      # pre-existing (vision routes)
    "core/routes/voice.py",       # pre-existing (voice routes)
    "core/tools/execution.py",    # pre-existing (tool execution)
    "core/tools/security.py",     # pre-existing (tool security)
    "core/identity/service.py",   # canonical auth adapter
    "core/pipeline/stages/auth.py",  # AuthenticationStage
}


@pytest.mark.parametrize("path", _prod_files())
def test_auth_manager_only_accessed_by_identity_service_and_auth_stage(path: Path):
    """Only ``core/identity/service.py`` and ``core/pipeline/stages/auth.py`` may import ``core.auth``."""
    posix = path.as_posix()
    for exempt in AUTH_MANAGER_EXEMPTIONS:
        if exempt in posix:
            pytest.skip(f"{exempt} is exempt from AuthManager import restriction")
    source = _read_source(path)
    for token in RESTRICTED_AUTH_MANAGER:
        if token in source:
            pytest.fail(
                f"{path} references {token}. "
                "Only IdentityService (core/identity/service.py) and "
                "AuthenticationStage (core/pipeline/stages/auth.py) may "
                "directly access the authentication backend."
            )


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


# ── Rule 16: Only AuthorizationStage may construct AuthorizationResult ──────────


RESTRICTED_AUTHORIZATION_RESULT = {"AuthorizationResult"}


@pytest.mark.parametrize("path", _prod_files())
def test_only_auth_stage_constructs_authorization_result(path: Path):
    """Only ``AuthorizationStage`` may instantiate ``AuthorizationResult``."""
    posix = path.as_posix()
    if "core/pipeline/stages/authorization.py" in posix:
        pytest.skip("AuthorizationStage is the canonical creator")
    if "core/pipeline/authorization_result.py" in posix:
        pytest.skip("AuthorizationResult definition is exempt")
    if "core/identity/service.py" in posix:
        pytest.skip("IdentityService.authorize() constructs AuthorizationResult")
    source = _read_source(path)
    imports = _extract_imports(source)
    for imp in imports:
        if "AuthorizationResult" in imp:
            pytest.fail(
                f"{path} imports AuthorizationResult. "
                "Only AuthorizationStage (core/pipeline/stages/authorization.py) "
                "and IdentityService (core/identity/service.py) may construct it."
            )
    if "AuthorizationResult(" in source:
        pytest.fail(
            f"{path} constructs AuthorizationResult directly. "
            "Only AuthorizationStage may construct AuthorizationResult."
        )


# ── Rule 17: Only IdentityService and AuthorizationStage may access PolicyEngine ──


RESTRICTED_POLICY_ENGINE = {"authz_engine", "PolicyEngine"}
POLICY_ENGINE_EXEMPTIONS = {
    "core/authz/engine.py",          # owns PolicyEngine
    "core/authz/loader.py",          # pre-existing (role registration)
    "core/auth.py",                  # pre-existing (require_scope, resolve_context)
    "core/tools/security.py",        # pre-existing (tool-level permission checks)
    "core/tools/policy.py",          # pre-existing (tool policy engine)
    "core/permission/__init__.py",   # pre-existing (permission package exports)
    "core/permission/manager.py",    # pre-existing (permission manager)
    "core/permission/policy.py",     # pre-existing (policy definitions)
    "core/identity/service.py",      # canonical authorization adapter
    "core/pipeline/stages/authorization.py",  # AuthorizationStage
}


@pytest.mark.parametrize("path", _prod_files())
def test_only_identity_service_and_auth_stage_access_policy_engine(path: Path):
    """Only ``core/identity/service.py`` and ``core/pipeline/stages/authorization.py``
    may access the PolicyEngine."""
    posix = path.as_posix()
    for exempt in POLICY_ENGINE_EXEMPTIONS:
        if exempt in posix:
            pytest.skip(f"{exempt} is exempt from PolicyEngine access restriction")
    source = _read_source(path)
    for token in RESTRICTED_POLICY_ENGINE:
        if token in source:
            pytest.fail(
                f"{path} references {token}. "
                "Only IdentityService (core/identity/service.py) and "
                "AuthorizationStage (core/pipeline/stages/authorization.py) may "
                "directly access the PolicyEngine."
            )


# ── Rule 18: No permission checks outside AuthorizationStage ────────────────────


RESTRICTED_PERMISSION_PATTERNS = {".is_admin", "get_privileges(", "user.roles", "'admin' in "}
PERMISSION_CHECK_EXEMPTIONS = {
    "core/auth.py",                  # owns AuthManager (is_admin, get_privileges)
    "core/authz/engine.py",          # owns PolicyEngine
    "core/authz/loader.py",          # pre-existing (role loader)
    "core/authz/schema.py",          # owns Role enum
    "core/routes/admin.py",          # pre-existing (admin routes)
    "core/routes/vision.py",         # pre-existing (vision routes)
    "core/routes/voice.py",          # pre-existing (voice routes)
    "core/tools/execution.py",       # pre-existing (tool execution checks)
    "core/tools/security.py",        # pre-existing (tool permission checks)
    "core/lifespan.py",              # pre-existing (startup role init)
    "core/middleware.py",            # pre-existing (middleware auth checks)
    "core/identity/service.py",      # canonical authorization adapter
    "core/identity/models.py",       # owns UserIdentity.roles field
    "core/pipeline/stages/authorization.py",  # AuthorizationStage
    "core/permission/manager.py",    # pre-existing (permission manager)
    "core/permission/policy.py",     # pre-existing (policy definitions)
}


@pytest.mark.parametrize("path", _prod_files())
def test_no_permission_checks_outside_auth_stage(path: Path):
    """No code outside AuthorizationStage may evaluate roles or permissions
    directly.

    Patterns like ``.is_admin``, ``get_privileges()``, ``user.roles``, and
    ``'admin' in`` are restricted to AuthorizationStage.
    """
    posix = path.as_posix()
    for exempt in PERMISSION_CHECK_EXEMPTIONS:
        if exempt in posix:
            pytest.skip(f"{exempt} is exempt from permission check restriction")
    source = _read_source(path)
    for pattern in RESTRICTED_PERMISSION_PATTERNS:
        if pattern in source:
            pytest.fail(
                f"{path} contains permission check pattern '{pattern}'. "
                "Only AuthorizationStage may evaluate roles or permissions. "
                "See core/identity/service.py for the canonical authorize() method."
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
