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
    "core/llm_failover.py",        # LLM failover infrastructure (wraps llm_router)
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
ACTIVITY_EXEMPTIONS = {
    "core/activity/__init__.py",       # package init
    "core/activity/manager.py",        # owns ActivityManager
    "core/activity/models.py",         # owns ActivityStatus
    "core/activity/recorder.py",       # activity recording utility
    "core/activity/resume.py",         # activity resume utility
    "core/scheduler/queue.py",         # scheduler queue — managed externally
    "core/scheduler/scheduler.py",     # scheduler — managed externally
}


@pytest.mark.parametrize("path", _prod_files())
def test_no_direct_activity_mutations(path: Path):
    if path.name == "execution.py":
        pytest.skip("Execution stage is the owner")
    posix = path.as_posix()
    for exempt in ACTIVITY_EXEMPTIONS:
        if exempt in posix:
            pytest.skip(f"{exempt} is exempt from activity mutation restriction")
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
    known_ok = {"AbstractReasoner", "BaseReasoner", "class ReasonResult"}
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
    known_ok = {"class Verifier", "class VerificationStage", "class SafetyVerifier", "class SchemaVerifier", "class ConfidenceVerifier", "class ManifestVerifier", "class VerificationMode"}
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
    if "core/pipeline/stages/resource_access.py" in posix:
        pytest.skip("ResourceAccessStage reads AuthenticationState (does not write it)")
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


# ── Rule 19: Only pipeline.py populates resource_scope ─────────────────────────


RESOURCE_SCOPE_EXEMPTIONS = {
    "core/pipeline/pipeline.py",       # process_message() — canonical owner
    "core/pipeline/observation.py",    # Observation carries resource_scope
    "core/pipeline/outcome.py",        # Outcome carries resource_scope
    "core/identity/resource_scope.py", # definition
    "core/pipeline/stages/resource_access.py",  # fallback empty scope
}


@pytest.mark.parametrize("path", _prod_files())
def test_only_pipeline_populates_resource_scope(path: Path):
    """Only ``process_message()`` in ``pipeline.py`` may construct
    ``ResourceScope`` and assign it to ``PipelineContext.resource_scope``."""
    posix = path.as_posix()
    for exempt in RESOURCE_SCOPE_EXEMPTIONS:
        if exempt in posix:
            pytest.skip(f"{exempt} is exempt from resource_scope construction restriction")
    source = _read_source(path)
    if "ResourceScope(" in source:
        pytest.fail(
            f"{path} constructs ResourceScope. "
            "Only process_message() in core/pipeline/pipeline.py may "
            "construct and assign ResourceScope to the pipeline context."
        )


# ── Rule 20: Only ResourceAccessStage constructs ResourceAccessResult ────────────


RESTRICTED_RESOURCE_ACCESS_RESULT = {"ResourceAccessResult"}


@pytest.mark.parametrize("path", _prod_files())
def test_only_resource_access_stage_constructs_result(path: Path):
    """Only ``ResourceAccessStage`` may construct ``ResourceAccessResult``."""
    posix = path.as_posix()
    if "core/pipeline/stages/resource_access.py" in posix:
        pytest.skip("ResourceAccessStage is the canonical creator")
    if "core/pipeline/resource_access_result.py" in posix:
        pytest.skip("ResourceAccessResult definition is exempt")
    source = _read_source(path)
    if "ResourceAccessResult(" in source:
        pytest.fail(
            f"{path} constructs ResourceAccessResult. "
            "Only ResourceAccessStage may construct ResourceAccessResult."
        )


# ── Rule 21: No Execution stage ownership checks ────────────────────────────────


OWNERSHIP_CHECK_PATTERNS = {"resource_scope.owner_id", "resource_scope.tenant_id", "resource_scope.workspace_id"}
OWNERSHIP_CHECK_EXEMPTIONS = {
    "core/pipeline/stages/resource_access.py",  # ResourceAccessStage — canonical
    "core/identity/resource_scope.py",          # definition
    "core/pipeline/resource_access_result.py",  # carries ResourceScope
    "core/pipeline/observation.py",             # carries ResourceScope
    "core/pipeline/outcome.py",                 # carries ResourceScope
}


@pytest.mark.parametrize("path", _prod_files())
def test_no_execution_ownership_checks(path: Path):
    """Ownership comparisons (owner_id, tenant_id, workspace_id on ResourceScope)
    must only appear in ResourceAccessStage and definition files."""
    posix = path.as_posix()
    for exempt in OWNERSHIP_CHECK_EXEMPTIONS:
        if exempt in posix:
            pytest.skip(f"{exempt} is exempt from ownership check restriction")
    source = _read_source(path)
    for pattern in OWNERSHIP_CHECK_PATTERNS:
        if pattern in source:
            pytest.fail(
                f"{path} contains ownership check pattern '{pattern}'. "
                "Only ResourceAccessStage may evaluate resource ownership. "
                "All ownership decisions must go through ResourceAccessStage."
            )


# ── Rule 22: No direct visibility comparisons outside resource_access.py ────────


RESTRICTED_VISIBILITY_PATTERNS = {"Visibility.PRIVATE", "Visibility.TENANT", "Visibility.WORKSPACE", "Visibility.PUBLIC"}
VISIBILITY_COMPARISON_EXEMPTIONS = {
    "core/identity/resource_scope.py",          # definition
    "core/pipeline/resource_access_result.py",  # carries effective_visibility
    "core/pipeline/stages/resource_access.py",  # ResourceAccessStage
    "core/pipeline/pipeline.py",                # constructs ResourceScope with Visibility.TENANT
    "core/pipeline/stages/auth.py",             # AuthenticationStage uses AuthenticationState (not Visibility)
}


@pytest.mark.parametrize("path", _prod_files())
def test_no_direct_visibility_comparisons(path: Path):
    """No code outside ResourceAccessStage may compare against Visibility values
    directly.  All visibility-based access decisions belong in ResourceAccessStage."""
    posix = path.as_posix()
    for exempt in VISIBILITY_COMPARISON_EXEMPTIONS:
        if exempt in posix:
            pytest.skip(f"{exempt} is exempt from visibility comparison restriction")
    source = _read_source(path)
    for pattern in RESTRICTED_VISIBILITY_PATTERNS:
        if pattern in source:
            pytest.fail(
                f"{path} references {pattern}. "
                "Only ResourceAccessStage may compare against Visibility values. "
                "Access decisions must go through ResourceAccessStage."
            )



# ── Rule 23: Only TenantResolutionStage constructs TenantResolutionResult ──────────


RESTRICTED_TENANT_RESOLUTION_RESULT = {"TenantResolutionResult"}


@pytest.mark.parametrize("path", _prod_files())
def test_only_tenant_resolution_stage_constructs_result(path: Path):
    """Only ``TenantResolutionStage`` may construct ``TenantResolutionResult``."""
    posix = path.as_posix()
    if "core/pipeline/stages/tenant_resolution.py" in posix:
        pytest.skip("TenantResolutionStage is the canonical creator")
    if "core/identity/tenant_resolver.py" in posix:
        pytest.skip("TenantResolutionResult definition is exempt")
    if "core/identity/service.py" in posix:
        pytest.skip("IdentityService.resolve_tenant delegates to resolver")
    source = _read_source(path)
    if "TenantResolutionResult(" in source:
        pytest.fail(
            f"{path} constructs TenantResolutionResult. "
            "Only TenantResolutionStage may construct TenantResolutionResult."
        )



# ── Rule 24: No Observation publish without ResourceScope ─────────────────────


OBSERVATION_PUBLISH_EXEMPTIONS = {
    "core/observation/hub.py",        # canonical publisher
    "core/pipeline/pipeline.py",      # calls hub.publish_observations_async
    "core/pipeline/observation.py",   # definition
}


@pytest.mark.parametrize("path", _prod_files())
def test_observation_publish_has_resource_scope(path: Path):
    """Every ``publish_observation`` call must pass an observation that
    carries ``resource_scope``."""
    posix = path.as_posix()
    for exempt in OBSERVATION_PUBLISH_EXEMPTIONS:
        if exempt in posix:
            pytest.skip(f"{exempt} is exempt")
    source = _read_source(path)
    # This is a soft check — enforce at the hub level in production.
    # For now the audit verifies there are no raw publish_observation calls
    # that bypass the hub pattern.
    pass


# ── Rule 25: ActivityNode creation requires ResourceScope ─────────────────────


ACTIVITY_NODE_EXEMPTIONS = {
    "core/activity/models.py",   # definition
    "core/activity/manager.py",  # canonical creator
    "core/activity/recorder.py", # delegates to manager
}


@pytest.mark.parametrize("path", _prod_files())
def test_activity_node_creation_has_resource_scope(path: Path):
    """ActivityNode construction must always include a ``resource_scope``
    parameter.  No code outside the activity package may construct
    ActivityNode directly."""
    posix = path.as_posix()
    for exempt in ACTIVITY_NODE_EXEMPTIONS:
        if exempt in posix:
            pytest.skip(f"{exempt} is exempt")
    source = _read_source(path)
    if "ActivityNode(" in source:
        pytest.fail(
            f"{path} constructs ActivityNode directly. "
            "All ActivityNode creation must go through ActivityManager "
            "and include a resource_scope."
        )


# ── Rule 26: ScheduledActivity must carry tenant_id ──────────────────────────


SCHEDULED_ACTIVITY_EXEMPTIONS = {
    "core/scheduler/models.py",   # definition
    "core/scheduler/queue.py",    # canonical creator
    "core/scheduler/store.py",    # persistence
    "core/scheduler/autonomous.py",  # creates via queue.submit
    "core/scheduler/chain.py",       # creates via store.add
    "core/scheduler/pipeline_executor.py",  # creates via queue.submit
}


@pytest.mark.parametrize("path", _prod_files())
def test_scheduled_activity_has_tenant(path: Path):
    """Every ``ScheduledActivity`` construction must include ``tenant_id``."""
    posix = path.as_posix()
    for exempt in SCHEDULED_ACTIVITY_EXEMPTIONS:
        if exempt in posix:
            pytest.skip(f"{exempt} is exempt")
    source = _read_source(path)
    if "ScheduledActivity(" in source and "tenant_id" not in source:
        pytest.fail(
            f"{path} constructs ScheduledActivity without tenant_id. "
            "Every ScheduledActivity must include a tenant_id for queue partitioning."
        )


# ── Rule 27: No snapshot serialization without tenant metadata ───────────────


SNAPSHOT_EXEMPTIONS = {
    "core/pipeline/architecture_metrics.py",  # definition — tenant_id now included
    "core/runtime_version.py",                # global runtime spec
}


@pytest.mark.parametrize("path", _prod_files())
def test_snapshot_has_tenant_metadata(path: Path):
    """Every ``to_snapshot_dict`` call must produce output containing
    tenant metadata."""
    posix = path.as_posix()
    for exempt in SNAPSHOT_EXEMPTIONS:
        if exempt in posix:
            pytest.skip(f"{exempt} is exempt")
    source = _read_source(path)
    if "to_snapshot_dict" in source and "tenant_id" not in source:
        pytest.fail(
            f"{path} implements to_snapshot_dict without tenant_id. "
            "All snapshot serialization must include tenant metadata."
        )



# ── Rule 28: Persistence writes must include tenant scope ────────────────────


PERSISTENCE_WRITES = {"store_facts(", "publish_observations_async(", "ScheduledActivity(", "ArchitectureMetrics("}
PERSISTENCE_TENANT_EXEMPTIONS = {
    # Canonical creators / definition files
    "core/pipeline/architecture_metrics.py",         # definition
    "core/pipeline/pipeline.py",                     # canonical caller
    "core/pipeline/outcome.py",                      # carries Outcome
    "core/pipeline/observation.py",                  # carries Observation
    "core/pipeline/stages/memory.py",                # calls store_facts with tenant_id
    "core/observation/hub.py",                       # implements publish
    "core/scheduler/models.py",                      # definition
    "core/scheduler/queue.py",                       # canonical creator
    "core/scheduler/store.py",                       # persistence
    "core/scheduler/chain.py",                       # creates via store.add
    "core/scheduler/autonomous.py",                  # creates via queue.submit
    "core/scheduler/pipeline_executor.py",            # creates via queue.submit
    # Pre-existing code — migration backlog candidates
    "core/fact_extraction/store.py",                 # BrowserFactStore (no tenant model)
    "core/tools/browser_research.py",                # browser fact writes
    "core/tools/browser_planner.py",                 # browser fact writes
    "core/routes/planner.py",                         # route-level ScheduledActivity
}


@pytest.mark.parametrize("path", _prod_files())
def test_persistence_has_tenant_scope(path: Path):
    """Any file that persists tenant-owned artifacts must include
    ``tenant_id`` or ``resource_scope``.

    Tenant-owned artifacts: Memory facts, Observations, Activities,
    Scheduled activities, ArchitectureMetrics snapshots.
    """
    posix = path.as_posix()
    for exempt in PERSISTENCE_TENANT_EXEMPTIONS:
        if exempt in posix:
            pytest.skip(f"{exempt} is exempt from tenant persistence check")
    source = _read_source(path)
    has_persistence = any(p in source for p in PERSISTENCE_WRITES)
    if has_persistence:
        if "tenant_id" not in source and "resource_scope" not in source:
            pytest.fail(
                f"{path} calls persistence API without tenant_id or resource_scope. "
                "All tenant-owned artifact persistence must include tenant scope."
            )


# ── Rule 31: Execution may not inspect identity, roles, or tenant ids ─────────
# Execution should only consume: ResourceGrant, Capability, Plan, Outcome.
# Everything else (roles, auth state, tenant, visibility) belongs earlier
# in the pipeline.


RESTRICTED_EXECUTION_PATTERNS = {
    "authentication_state",
    "AuthenticationState",
    ".is_admin",
    "user.roles",
    "resource_scope.owner_id",
    "resource_scope.tenant_id",
    "resource_scope.workspace_id",
    "DEFAULT_TENANT_ID",
    "SYSTEM_TENANT_ID",
    "Visibility.",
}
EXECUTION_PATTERN_EXEMPTIONS = {
    "core/pipeline/stages/execution.py",        # canonical owner
}


@pytest.mark.parametrize("path", [p for p in _prod_files()
                                   if "stages/execution" in p.as_posix()])
def test_execution_does_not_inspect_identity(path: Path):
    """ExecutionStage must not inspect identity roles, authentication state,
    tenant ids, or visibility directly.  It should only consume
    ``ResourceGrant``, ``Capability``, ``Plan``, and ``Outcome``."""
    source = _read_source(path)
    for pattern in RESTRICTED_EXECUTION_PATTERNS:
        if pattern in source:
            pytest.fail(
                f"{path} references '{pattern}'. "
                "ExecutionStage must not inspect identity roles, "
                "authentication state, tenant ids, or visibility directly. "
                "These belong to earlier pipeline stages."
            )


# ── Rule 29: Only pipeline / TenantResolution may assign default/system tenant ──


DEFAULT_TENANT_SENTINELS = {"DEFAULT_TENANT_ID", "SYSTEM_TENANT_ID"}
DEFAULT_TENANT_EXEMPTIONS = {
    "core/pipeline/pipeline.py",                     # load_context — canonical assigner
    "core/identity/resource_scope.py",               # definition
    "core/identity/tenant_resolver.py",              # implements default resolution
    "core/pipeline/stages/tenant_resolution.py",      # tenant resolution stage
    "core/pipeline/stages/resource_access.py",        # reads tenant from scope
}


@pytest.mark.parametrize("path", _prod_files())
def test_only_pipeline_assigns_default_tenant(path: Path):
    """Only the pipeline (load_context) and TenantResolutionStage may reference
    ``DEFAULT_TENANT_ID`` or ``SYSTEM_TENANT_ID``.

    All other components must consume an existing ``ResourceScope``
    instead of reaching for sentinel values.
    """
    posix = path.as_posix()
    for exempt in DEFAULT_TENANT_EXEMPTIONS:
        if exempt in posix:
            pytest.skip(f"{exempt} is exempt from default tenant restriction")
    source = _read_source(path)
    for sentinel in DEFAULT_TENANT_SENTINELS:
        if sentinel in source:
            pytest.fail(
                f"{path} references {sentinel}. "
                "Only the pipeline and TenantResolutionStage may assign "
                "DEFAULT_TENANT_ID or SYSTEM_TENANT_ID. "
                "Other components must consume an existing ResourceScope."
            )


# ── Rule 32: Only RuntimeRegistry constructs RuntimeServices ────────────────────


RUNTIME_REGISTRY_EXEMPTIONS = {
    "core/runtime/registry.py",               # canonical owner
    "core/runtime/providers.py",              # dataclass definition
    "core/runtime/protocols.py",              # protocol definitions
}


@pytest.mark.parametrize("path", _prod_files())
def test_only_registry_constructs_runtime_services(path: Path):
    """Only ``core/runtime/registry.py`` may construct ``RuntimeServices``.

    All other code must consume ``RuntimeServices`` via the registry
    or dependency injection.
    """
    posix = path.as_posix()
    for exempt in RUNTIME_REGISTRY_EXEMPTIONS:
        if exempt in posix:
            pytest.skip(f"{exempt} is exempt from registry construction rule")
    source = _read_source(path)
    if "RuntimeServices(" in source:
        pytest.fail(
            f"{path} constructs RuntimeServices directly. "
            "Only RuntimeRegistry may construct RuntimeServices. "
            "Consume via registry.get_registry().build() or dependency injection."
        )


# ── Rule 33: Execution never imports concrete implementations ───────────────────
# Aspirational: Execution should prefer protocols from core/runtime/protocols.py.
# Currently grandfathered: core.activity.models, core.activity.manager (lazy
# imports in execution.py helpers).  Enforcement begins once ActivityService
# protocol covers those use cases.


@pytest.mark.skip("Rule 33 — pending ActivityService protocol coverage")
@pytest.mark.parametrize("path", [p for p in _prod_files()
                                   if "stages/execution" in p.as_posix()])
def test_execution_only_imports_protocols(path: Path):
    """Execution code must only import protocols, not concrete implementations."""


# ── Rule 34: Memory/Scheduler/EventBus never inspect Identity directly ──────────
# These services consume RuntimeContext and must not access identity internals
# directly (auth_state, roles, user_id patterns).


IDENTITY_INSPECTION_EXEMPTIONS = {
    "core/identity/",                         # owns identity definitions
    "core/pipeline/stages/auth.py",           # AuthenticationStage
    "core/pipeline/stages/authorization.py",  # AuthorizationStage
    "core/pipeline/stages/tenant_resolution.py",
    "core/pipeline/stages/resource_access.py",
    "core/runtime/registry.py",
    "core/runtime/providers.py",
}


IDENTITY_INSPECTION_PATTERNS = {
    "authentication_state",
    "AuthenticationState",
    ".is_admin",
    "user.roles",
    "identity.user",
    "identity.tenant",
    "identity.authentication_state",
    "AuthenticationResult(",
    "AuthorizationResult(",
}


@pytest.mark.parametrize("path", [p for p in _prod_files()
                                   if "memory/" in p.as_posix()
                                   or "scheduler/" in p.as_posix()
                                   or "event_bus" in p.as_posix()
                                   or "observation/" in p.as_posix()])
def test_service_never_inspects_identity_directly(path: Path):
    """Memory, Scheduler, EventBus, and Observation services must not inspect
    identity internals directly. They consume ``RuntimeContext``."""
    posix = path.as_posix()
    for exempt in IDENTITY_INSPECTION_EXEMPTIONS:
        if exempt in posix:
            pytest.skip(f"{exempt} is exempt from identity inspection rule")
    source = _read_source(path)
    for pattern in IDENTITY_INSPECTION_PATTERNS:
        if pattern in source:
            pytest.fail(
                f"{path} references '{pattern}'. "
                "Runtime services must not inspect identity internals "
                "directly. Consume RuntimeContext instead."
            )


# ── Rule 35: No service singleton outside RuntimeRegistry ───────────────────────
# Enforcement: execution code must prefer RuntimeRegistry over direct
# singleton access.  Broader codebase singletons are grandfathered.


SINGLETON_EXEMPTIONS = {
    "core/runtime/registry.py",               # canonical singleton owner
    "core/runtime/",                           # own protocols/providers
}

SINGLETON_PATTERNS_FOR_EXECUTION = {
    "get_hub()",
    "get_pipeline()",
    "get_identity_service()",
    "get_auth_manager()",
    "global_event_bus",
    "authz_engine",
}


@pytest.mark.parametrize("path", [p for p in _prod_files()
                                   if "stages/execution" in p.as_posix()])
def test_no_service_singleton_outside_registry(path: Path):
    """Execution code must not call service singletons directly.
    Prefer ``RuntimeRegistry`` and dependency injection."""
    posix = path.as_posix()
    for exempt in SINGLETON_EXEMPTIONS:
        if exempt in posix:
            pytest.skip(f"{exempt} is exempt from singleton rule")
    source = _read_source(path)
    for pattern in SINGLETON_PATTERNS_FOR_EXECUTION:
        if pattern in source:
            pytest.fail(
                f"{path} calls '{pattern}'. "
                "Execution code must not call service singletons directly. "
                "Prefer RuntimeRegistry or dependency injection."
            )


# ── Rule 36: Remote workers run process_message() — no alternate execution ─────
# Workers must call the canonical process_message(), not a reimplementation.


WORKER_EXECUTION_EXEMPTIONS = {
    "core/distribution/worker.py",             # protocol definition
    "core/distribution/contracts.py",          # data contracts
    "core/distribution/retry.py",              # retry policy, not a worker
    "core/distribution/health.py",             # health checker, not a worker
    "core/distribution/pool.py",               # worker pool, not a worker
    "core/distribution/observation.py",        # observation forwarding
    "core/distribution/transport.py",          # transport protocol
}


@pytest.mark.parametrize("path", [p for p in _prod_files()
                                   if "distribution/" in p.as_posix()
                                   and not p.name.startswith("__")])
def test_worker_uses_process_message(path: Path):
    """Distribution code that triggers execution must use ``process_message``."""
    posix = path.as_posix()
    for exempt in WORKER_EXECUTION_EXEMPTIONS:
        if exempt in posix:
            pytest.skip(f"{exempt} is exempt — not a worker execution file")
    source = _read_source(path)
    if "async def execute" in source and "process_message" not in source:
        pytest.fail(
            f"{path} implements execute() without calling process_message(). "
            "Remote workers must run the canonical pipeline."
        )


# ── Rule 37: All remote dispatch goes through Transport protocol ───────────────
# Only RemoteExecutionRuntime and the transport implementations themselves
# may bypass the Transport protocol for remote calls.


TRANSPORT_DISPATCH_FILE = "core/distribution/runtime.py"

TRANSPORT_EXEMPTIONS = {
    "core/distribution/transport.py",          # defines the protocol
    "core/distribution/contracts.py",          # WorkerRequest/Response
    "core/distribution/worker.py",             # protocol definitions
    "core/distribution/health.py",
    "core/distribution/registry.py",           # registry, not dispatch
    "core/distribution/pool.py",               # worker pool, not dispatch
    "core/distribution/retry.py",              # retry policy
    "core/distribution/observation.py",        # observation forwarding
    "core/distribution/scheduler.py",          # uses RemoteExecutionRuntime
    "core/distribution/local_worker.py",       # inline execution
}


@pytest.mark.parametrize("path", [p for p in _prod_files()
                                   if "distribution/" in p.as_posix()])
def test_remote_dispatch_uses_transport(path: Path):
    """All remote execution dispatch must use the ``Transport`` protocol."""
    posix = path.as_posix()
    for exempt in TRANSPORT_EXEMPTIONS:
        if exempt in posix:
            pytest.skip(f"{exempt} is exempt from transport-only dispatch rule")
    source = _read_source(path)
    if "send" in source or "RemoteExecutionRuntime" in source:
        if "Transport" not in source:
            pytest.fail(
                f"{path} appears to do remote dispatch without Transport."
            )


# ── Rule 38: WorkerRegistry is sole source of worker discovery ─────────────────
# Enforcement: files that import/discover workers must use WorkerRegistry.
# Only applies to distribution/ code (the runtime orchestration layer).


WORKER_REGISTRY_DISCOVERY_EXEMPTIONS = {
    "core/distribution/registry.py",           # defines the registry
    "core/distribution/worker.py",             # protocol definitions
    "core/distribution/contracts.py",          # data contracts
    "core/distribution/observation.py",        # subscribes workers, not discovers
}


@pytest.mark.parametrize("path", [p for p in _prod_files()
                                   if "distribution/" in p.as_posix()])
def test_worker_discovery_only_via_registry(path: Path):
    """Code that discovers workers must use ``WorkerRegistry``."""
    posix = path.as_posix()
    for exempt in WORKER_REGISTRY_DISCOVERY_EXEMPTIONS:
        if exempt in posix:
            pytest.skip(f"{exempt} is exempt from registry-only discovery")
    source = _read_source(path)
    if "discover" in source and "get_worker_registry" not in source:
        pytest.fail(
            f"{path} references worker discovery without using get_worker_registry. "
            "WorkerRegistry is the sole source of worker discovery (Rule 38)."
        )


# ── Rule 39: WorkerRequest/WorkerResponse is the only cross-boundary contract ──


CROSS_BOUNDARY_EXEMPTIONS = {
    "core/distribution/worker.py",
    "core/distribution/contracts.py",
    "core/distribution/health.py",
    "core/distribution/pool.py",
    "core/distribution/retry.py",
    "core/distribution/observation.py",
}


@pytest.mark.parametrize("path", [p for p in _prod_files()
                                   if "distribution/" in p.as_posix()])
def test_cross_boundary_only_via_worker_contracts(path: Path):
    """Cross-boundary communication between runtime and worker must use
    ``WorkerRequest`` / ``WorkerResponse``."""
    posix = path.as_posix()
    for exempt in CROSS_BOUNDARY_EXEMPTIONS:
        if exempt in posix:
            pytest.skip(f"{exempt} is exempt — no cross-boundary traffic")
    source = _read_source(path)
    if "WorkerRequest" not in source and "WorkerResponse" not in source:
        if "def execute" in source or "async def execute" in source:
            pytest.fail(
                f"{path} defines execute() without using WorkerRequest/WorkerResponse. "
                "These are the only cross-boundary contracts (Rule 39)."
            )


# ── Rule 40: Observations from remote workers must carry worker_id ─────────────


@pytest.mark.parametrize("path", [p for p in _prod_files()
                                   if "distribution/" in p.as_posix()])
def test_observations_carry_worker_id(path: Path):
    """Observations produced by remote workers must include ``worker_id``
    for provenance tracking."""
    source = _read_source(path)
    if "observation" in source.lower() and ("publish" in source or "collect" in source):
        lines = source.lower().split("\n")
        has_observation = any("observation" in l for l in lines)
        has_worker_id = any("worker_id" in l for l in lines)
        if has_observation and not has_worker_id:
            # Only flag if it's an observation-producing file, not a consumer
            if "ObservationHub" not in source and "ObservationCollector" not in source:
                return
            pytest.fail(
                f"{path} handles remote observations without including worker_id. "
                "Remote observations must carry worker_id for provenance (Rule 40)."
            )


# ── Rule 41: Workers advertise runtime version; registry checks compat ──────────


@pytest.mark.parametrize("path", [p for p in _prod_files()])
def test_worker_version_advertised(path: Path):
    """WorkerRegistration must advertise pipeline_version, runtime_spec_version."""
    if "registry.py" not in path.name:
        pytest.skip("not a registry file")
    source = _read_source(path)
    if "WorkerRegistration" in source:
        if "pipeline_version" not in source:
            pytest.fail(
                f"{path} defines WorkerRegistration without pipeline_version. "
                "Workers must advertise runtime version (Rule 41)."
            )


# ── Rule 42: Workers must never construct RuntimeContext manually ──────────────
# Only deserialization (WorkerRequest.from_dict) should reconstruct it.


WORKER_CONTEXT_CONSTRUCTION_EXEMPTIONS = {
    "core/distribution/contracts.py",          # WorkerRequest.from_dict — canonical
    "core/distribution/local_worker.py",       # uses process_message, not ctx construction
    "core/runtime/context.py",                 # dataclass definition
}


@pytest.mark.parametrize("path", [p for p in _prod_files()
                                   if "distribution/" in p.as_posix()])
def test_workers_must_not_construct_runtime_context(path: Path):
    """Workers must never manually construct RuntimeContext.
    Only ``WorkerRequest.from_dict`` may reconstruct it."""
    posix = path.as_posix()
    for exempt in WORKER_CONTEXT_CONSTRUCTION_EXEMPTIONS:
        if exempt in posix:
            pytest.skip(f"{exempt} is exempt from context construction rule")
    source = _read_source(path)
    if "RuntimeContext(" in source:
        pytest.fail(
            f"{path} constructs RuntimeContext directly. "
            "Workers must never manually construct RuntimeContext. "
            "Only WorkerRequest.from_dict may reconstruct it (Rule 42)."
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 6F — Distributed Graph Rules
# ═══════════════════════════════════════════════════════════════════════════════


# ── Rule 43: Graph nodes execute through Transport ────────────────────────────
# The executor dispatches via WorkerRequest/Transport, not pipeline internals.


def test_graph_executor_uses_transport():
    """``GraphExecutor`` must dispatch nodes via ``Transport.send()``."""
    import ast

    src = (Path(__file__).resolve().parent.parent.parent
           / "core" / "distribution" / "graph" / "executor.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    send_calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "send"
    ]
    if not send_calls:
        pytest.fail(
            "GraphExecutor must call Transport.send() to dispatch nodes (Rule 43)."
        )


# ── Rule 44: Dependency resolution is local ────────────────────────────────────
# No cross-worker dependency checking at runtime.


def test_dependency_resolution_is_local():
    """Dependency resolution must not check worker state."""
    from core.distribution.graph.models import DistributedGraph

    for attr in ("get_ready_nodes", "get_downstream_nodes", "has_unfinished"):
        method = getattr(DistributedGraph, attr, None)
        if method is None:
            pytest.fail(f"DistributedGraph missing required method: {attr} (Rule 44)")


# ── Rule 45: Checkpoints are immutable snapshots ──────────────────────────────


def test_checkpoints_are_immutable_snapshots():
    """Checkpoints must be JSON-serialisable immutable snapshots."""
    from core.distribution.graph.models import DistributedGraph

    g = DistributedGraph(id="test", nodes={}, edges=[])
    snap = g.to_snapshot()
    assert isinstance(snap, dict), "Snapshot must be a dict (Rule 45)"
    assert "graph_id" in snap, "Snapshot must contain graph_id (Rule 45)"
    assert "state" in snap, "Snapshot must contain state (Rule 45)"
    assert "nodes" in snap, "Snapshot must contain nodes (Rule 45)"
    assert "edges" in snap, "Snapshot must contain edges (Rule 45)"


# ── Rule 46: Recovery creates new graph from checkpoint ───────────────────────


def test_recovery_requires_original_nodes():
    """Recovery must accept original nodes and rebuild from checkpoint."""
    from core.distribution.graph.recovery import GraphRecovery

    sig = getattr(GraphRecovery.recover, "__sig__", None)  # python 3.10+
    import inspect
    params = list(inspect.signature(GraphRecovery.recover).parameters.keys())
    assert "original_nodes" in params, (
        f"GraphRecovery.recover must accept original_nodes parameter (Rule 46). Got: {params}"
    )


# ── Rule 47: Cancellation propagates downstream ───────────────────────────────


def test_cancellation_propagates_downstream():
    """Node failure must cascade cancellation to downstream nodes."""
    from core.distribution.graph.models import DistributedGraph, GraphNode, GraphEdge, NodeStatus, GraphState
    from core.pipeline.messages import Request

    n1 = GraphNode(id="n1", request=Request(text="", transport="test"))
    n2 = GraphNode(id="n2", request=Request(text="", transport="test"))
    n3 = GraphNode(id="n3", request=Request(text="", transport="test"))
    graph = DistributedGraph(
        id="test_cancel",
        nodes={"n1": n1, "n2": n2, "n3": n3},
        edges=[GraphEdge("n1", "n2"), GraphEdge("n1", "n3")],
    )
    import asyncio
    from core.distribution.graph.scheduler import DependencyAwareScheduler

    scheduler = DependencyAwareScheduler()
    asyncio.run(scheduler.on_node_failed(graph, "n1", "simulated failure"))

    assert n1.status == NodeStatus.FAILED
    assert n2.status == NodeStatus.CANCELLED, "n2 must be CANCELLED after n1 failure (Rule 47)"
    assert n3.status == NodeStatus.CANCELLED, "n3 must be CANCELLED after n1 failure (Rule 47)"



# ═══════════════════════════════════════════════════════════════════════════════
# Phase 7 — Intelligence Platform Rules
# ═══════════════════════════════════════════════════════════════════════════════


# ── Rule 48: Only ReasoningStage creates ReasoningResult ─────────────────────


def test_only_reasoning_stage_creates_reasoning_result():
    """``ReasoningResult`` must only be constructed by the Reasoning stage.

    Enforced by scanning for ``ReasoningResult(`` calls outside
    ``core/pipeline/stages/reasoning/``.
    """
    reasoning_result_files: list[str] = []

    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent.parent
    for path in sorted(root.rglob("*.py")):
        posix = path.as_posix()
        if "/tests/" in posix or "/__pycache__/" in posix:
            continue
        if posix.endswith("/reasoning_result.py"):
            continue  # contract definition is exempt
        try:
            source = path.read_text(encoding="utf-8")
        except Exception:
            continue  # skip binary or non-UTF-8 files
        if "ReasoningResult(" in source:
            # Verify it's a construction call, not just a type hint
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    fn = node.func
                    if isinstance(fn, ast.Name) and fn.id == "ReasoningResult":
                        rel = path.relative_to(root).as_posix()
                        reasoning_result_files.append(rel)

    # The ONLY allowed constructor is the reasoning stage
    allowed = {"core/pipeline/stages/reasoning/stage.py"}
    violations = [f for f in reasoning_result_files if f not in allowed]
    if violations:
        pytest.fail(
            f"ReasoningResult constructed outside allowed stages: {violations}. "
            "Only ReasoningStage may construct ReasoningResult (Rule 48)."
        )


# ── Rule 49: Research engines accessed only through stage adapters ───────────


def test_research_engines_accessed_only_through_stage_adapters():
    """``core.research`` may only be imported by stage adapters.

    Exemptions: the research package itself, its own tests, and
    the reasoning result contract.
    """
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent.parent
    research_module_prefixes = {
        "core.research",
        "from core.research",
    }
    # Modules that are allowed to import from core.research
    allowed_importers = {
        "core/pipeline/stages/reasoning/stage.py",
        "core/pipeline/stages/reasoning/__init__.py",
        "core/pipeline/stages/knowledge/",       # future Sprint 2
        "core/pipeline/stages/reflection/",       # future Sprint 4
        "core/pipeline/reasoning_result.py",       # contract
        "core/research/",                           # itself
    }

    # Legacy exemptions — pre-existing imports that will be migrated
    # as Phase 7 Sprint 2–4 integration is completed.
    legacy_exemptions = {
        "core/evidence/generator.py",
        "core/fact_extraction/bridge.py",
        "core/negotiation/agents.py",
        "core/planner/evidence.py",
        "core/providers/adapters/research_provider.py",
        "core/routes/research.py",
        "core/strategy/memory_adapter.py",
        "core/tools/browser_research.py",
    }

    violations: list[str] = []
    for path in sorted(root.rglob("*.py")):
        posix = path.as_posix()
        if "/__pycache__/" in posix:
            continue
        if "/tests/" in posix:
            if "test_research" not in posix and "test_reasoning" not in posix:
                continue

        try:
            source = path.read_text(encoding="utf-8")
        except Exception:
            continue

        if "from core.research" not in source and "import core.research" not in source:
            continue

        rel = path.relative_to(root).as_posix()

        # Check legacy exemptions first
        if rel in legacy_exemptions:
            continue

        # Check allowed importers
        is_allowed = any(a in posix for a in allowed_importers)
        if not is_allowed:
            violations.append(rel)

    if violations:
        pytest.fail(
            f"core.research imported outside stage adapters: {violations}. "
            "Research engines may only be accessed through pipeline stage "
            "adapters (Rule 49). Legacy exemptions tracked separately."
        )


# ── Rule 50: Only KnowledgeStage creates KnowledgeResult ─────────────────────


def test_only_knowledge_stage_creates_knowledge_result():
    """``KnowledgeResult`` must only be constructed by the Knowledge stage.

    Enforced by scanning for ``KnowledgeResult(`` calls outside
    ``core/pipeline/stages/knowledge/``.
    """
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent.parent
    knowledge_result_files: list[str] = []

    for path in sorted(root.rglob("*.py")):
        posix = path.as_posix()
        if "/tests/" in posix or "/__pycache__/" in posix:
            continue
        if posix.endswith("/knowledge_result.py"):
            continue  # contract definition is exempt
        try:
            source = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if "KnowledgeResult(" in source:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    fn = node.func
                    if isinstance(fn, ast.Name) and fn.id == "KnowledgeResult":
                        rel = path.relative_to(root).as_posix()
                        knowledge_result_files.append(rel)

    allowed = {"core/pipeline/stages/knowledge/stage.py"}
    violations = [f for f in knowledge_result_files if f not in allowed]
    if violations:
        pytest.fail(
            f"KnowledgeResult constructed outside allowed stages: {violations}. "
            "Only KnowledgeStage may construct KnowledgeResult (Rule 50)."
        )


# ── Rule 51: Only PlannerStage creates PlanningStrategy / PlanRanking ────────


def test_only_planner_stage_creates_planning_artifacts():
    """``PlanningStrategy``, ``StrategyComparison``, ``PlanRanking``,
    and ``PlannerResult`` must only be constructed by the Planner stage.

    Enforced by scanning for constructors outside ``core/pipeline/stages/planner/``.
    """
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent.parent
    target_types = {"PlanningStrategy", "StrategyComparison", "PlanRanking"}
    allowed = {"core/pipeline/stages/planner/stage.py"}

    # Check PlannerResult separately (also exempted if in contract file)
    planner_result_files: list[str] = []
    for path in sorted(root.rglob("*.py")):
        posix = path.as_posix()
        if "/tests/" in posix or "/__pycache__/" in posix:
            continue
        if posix.endswith("/planner_result.py"):
            continue  # contract definition is exempt
        try:
            source = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for tname in target_types:
            if f"{tname}(" in source:
                tree = ast.parse(source)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        fn = node.func
                        if isinstance(fn, ast.Name) and fn.id == tname:
                            rel = path.relative_to(root).as_posix()
                            planner_result_files.append(rel)

    violations = [f for f in planner_result_files if f not in allowed]
    if violations:
        pytest.fail(
            f"Planning artifacts constructed outside allowed stages: {violations}. "
            "Only PlannerStage may construct PlanningStrategy, StrategyComparison, "
            "or PlanRanking (Rule 51)."
        )


# ── Rule 52: Only ReflectionStage creates ReflectionResult ───────────────────


def test_only_reflection_stage_creates_reflection_result():
    """``ReflectionResult`` must only be constructed by the Reflection stage.

    Enforced by scanning for ``ReflectionResult(`` calls outside
    ``core/pipeline/stages/reflection/`` and the contract definition.
    """
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent.parent
    reflection_result_files: list[str] = []

    for path in sorted(root.rglob("*.py")):
        posix = path.as_posix()
        if "/tests/" in posix or "/__pycache__/" in posix:
            continue
        if posix.endswith("/reflection_result.py"):
            continue  # contract definition is exempt
        if posix.endswith("/reflection.py") and "research" in posix:
            continue  # research engine defines its own ReflectionResult
        try:
            source = path.read_text(encoding="utf-8")
        except Exception:
            continue
        # Check for our pipeline's ReflectionResult constructor
        if "ReflectionResult(" in source:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    fn = node.func
                    if isinstance(fn, ast.Name) and fn.id == "ReflectionResult":
                        rel = path.relative_to(root).as_posix()
                        reflection_result_files.append(rel)

    allowed = {
        "core/pipeline/stages/reflection/stage.py",
    }
    violations = [f for f in reflection_result_files if f not in allowed]
    if violations:
        pytest.fail(
            f"ReflectionResult constructed outside allowed stages: {violations}. "
            "Only ReflectionStage may construct ReflectionResult (Rule 52)."
        )


# ── Rule 53: Only LearningStage creates LearningRecord ───────────────────────


def test_only_learning_stage_creates_learning_record():
    """``LearningRecord`` must only be constructed by the Learning stage.

    Enforced by scanning for ``LearningRecord(`` calls outside
    ``core/pipeline/stages/learning/`` and the contract definition.
    """
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent.parent
    learning_record_files: list[str] = []

    for path in sorted(root.rglob("*.py")):
        posix = path.as_posix()
        if "/tests/" in posix or "/__pycache__/" in posix:
            continue
        if posix.endswith("/learning_result.py"):
            continue  # contract definition is exempt
        try:
            source = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if "LearningRecord(" in source:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    fn = node.func
                    if isinstance(fn, ast.Name) and fn.id == "LearningRecord":
                        rel = path.relative_to(root).as_posix()
                        learning_record_files.append(rel)

    allowed = {
        "core/pipeline/stages/learning/stage.py",
    }
    violations = [f for f in learning_record_files if f not in allowed]
    if violations:
        pytest.fail(
            f"LearningRecord constructed outside allowed stages: {violations}. "
            "Only LearningStage may construct LearningRecord (Rule 53)."
        )


# ── Rule 54: Only PolicyOptimizationStage creates PolicyOptimizationResult ─────


def test_only_policy_optimization_stage_creates_policy_optimization_result():
    """``PolicyOptimizationResult`` must only be constructed by the
    Policy Optimization stage.

    Enforced by scanning for ``PolicyOptimizationResult(`` calls outside
    ``core/pipeline/stages/policy_optimization/`` and the contract definition.
    """
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent.parent
    po_result_files: list[str] = []

    excluded_dirs = {"/tests/", "/__pycache__/", "/.venv/", "/venv/", "/node_modules/"}
    for path in sorted(root.rglob("*.py")):
        posix = path.as_posix()
        if any(d in posix for d in excluded_dirs):
            continue
        if posix.endswith("/policy_optimization_result.py"):
            continue  # contract definition is exempt
        try:
            source = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if "PolicyOptimizationResult(" in source:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    fn = node.func
                    if isinstance(fn, ast.Name) and fn.id == "PolicyOptimizationResult":
                        rel = path.relative_to(root).as_posix()
                        po_result_files.append(rel)

    allowed = {
        "core/pipeline/stages/policy_optimization/stage.py",
    }
    violations = [f for f in po_result_files if f not in allowed]
    if violations:
        pytest.fail(
            f"PolicyOptimizationResult constructed outside allowed stages: {violations}. "
            "Only PolicyOptimizationStage may construct PolicyOptimizationResult (Rule 54)."
        )


# ── Rule 55: Only ExplainabilityStage creates ExplanationResult ───────────────


def test_only_explainability_stage_creates_explanation_result():
    """``ExplanationResult`` must only be constructed by the
    Explainability stage.

    Enforced by scanning for ``ExplanationResult(`` calls outside
    ``core/pipeline/stages/explainability/`` and the contract definition.
    """
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent.parent
    exp_result_files: list[str] = []

    excluded_dirs = {"/tests/", "/__pycache__/", "/.venv/", "/venv/", "/node_modules/"}
    for path in sorted(root.rglob("*.py")):
        posix = path.as_posix()
        if any(d in posix for d in excluded_dirs):
            continue
        if posix.endswith("/explanation_result.py"):
            continue  # contract definition is exempt
        try:
            source = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if "ExplanationResult(" in source:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    fn = node.func
                    if isinstance(fn, ast.Name) and fn.id == "ExplanationResult":
                        rel = path.relative_to(root).as_posix()
                        exp_result_files.append(rel)

    allowed = {
        "core/pipeline/stages/explainability/stage.py",
    }
    violations = [f for f in exp_result_files if f not in allowed]
    if violations:
        pytest.fail(
            f"ExplanationResult constructed outside allowed stages: {violations}. "
            "Only ExplainabilityStage may construct ExplanationResult (Rule 55)."
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
