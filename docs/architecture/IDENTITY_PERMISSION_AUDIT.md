# Identity & Permission Architecture Audit — Phase 2 (Document 7)

> **Purpose:** Trace every identity, authentication, authorization, tenant, and permission system — from request identity resolution through pipeline auth stages, RBAC, permission gating, and audit logging.
>
> **Scope:** `core/identity/`, `core/auth.py`, `core/authz/`, `core/permission/`, `core/oauth.py`, pipeline auth stages, HTTP middleware, tool-level RBAC, and provider SDK permissions.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Identity System (`core/identity/`)](#2-identity-system-coreidentity)
3. [Authentication System (`core/auth.py`)](#3-authentication-system-coreauthpy)
4. [OAuth System (`core/oauth.py`)](#4-oauth-system-coreoauthpy)
5. [Authorization / RBAC (`core/authz/`)](#5-authorization--rbac-coreauthz)
6. [Permission System (`core/permission/`)](#6-permission-system-corepermission)
7. [Pipeline Auth Stages](#7-pipeline-auth-stages)
8. [HTTP API Auth Layer](#8-http-api-auth-layer)
9. [Tool-Level RBAC](#9-tool-level-rbac)
10. [Provider SDK Permissions](#10-provider-sdk-permissions)
11. [Distributed Worker Auth](#11-distributed-worker-auth)
12. [Ownership Matrix](#12-ownership-matrix)
13. [Duplication Analysis](#13-duplication-analysis)
14. [Findings](#14-findings)
15. [Recommendations](#15-recommendations)

---

## 1. Architecture Overview

### Five Security Layers Executed in Order

```
Request Inbound
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│  HTTP Layer (FastAPI middleware + route-level Depends)        │
│  • session_auth_middleware → req.state.current_user          │
│  • SecurityHeadersMiddleware (CSP, XFO, XCTO)               │
│  • Route-level Depends(verify_token)                         │
│  • Rate limiting (AuthRateLimiter)                           │
│  • Admin-only require_admin()                                │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│  Pipeline Auth Stages (core/pipeline/stages/)                │
│  Stage 3: AuthenticationStage  (token → Authenticated)     │
│  Stage 4: TenantResolutionStage (identity → tenant)        │
│  Stage 5: AuthorizationStage   (scope → grant/deny)       │
│  Stage 6: ResourceAccessStage  (visibility → allow/block) │
│  Stage 7: RateLimitStage       (pass-through, unimplemented)│
└──────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│  Execution Layer (tool-level)                                │
│  • is_authorized_to_execute() → authz_engine.evaluate()     │
│  • NON_ADMIN_BLOCKED_TOOLS (36 tools)                        │
│  • PermissionManager.resolve() → PolicyEngine evaluation    │
│  • PermissionAudit.record()                                  │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│  Provider Layer (provider_sdk)                               │
│  • PermissionDeclarationStage (install-time validation)      │
│  • RuntimePermissionRegistrationStage (activate at runtime)  │
│  • RuntimeObserver (undeclared usage detection)              │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
  Response
```

### Component Inventory

| Layer | System | Location | Purpose |
|-------|--------|----------|---------|
| **Identity** | IdentityService | `core/identity/` | Resolve "who is this request?" via pipeline |
| **AuthN** | AuthManager | `core/auth.py` | Password + session + TOTP auth |
| **AuthN** | Firebase | `core/firebase.py` | Firebase Admin SDK integration |
| **AuthN** | OAuth | `core/oauth.py` | Google, GitHub, Discord OAuth |
| **AuthZ** | PolicyEngine | `core/authz/engine.py` | RBAC scope evaluation |
| **AuthZ** | PermissionManager | `core/permission/` | Fine-grained capability permission gating |
| **AuthZ** | Pipeline stages | `core/pipeline/stages/*.py` | Request-level auth N + Z + tenant + resource access |
| **AuthZ** | Tool-level RBAC | `core/tools/security.py` | Tool execution authorization |

---

## 2. Identity System (`core/identity/`)

### 2.1 Data Models (Frozen Dataclasses)

| Model | Fields | Purpose |
|-------|--------|---------|
| `AuthenticationState` (enum) | `ANONYMOUS`, `IDENTIFIED`, `AUTHENTICATED`, `SYSTEM` | Auth level |
| `UserIdentity` | `id`, `email`, `display_name`, `roles: tuple`, `metadata` | Who the user is |
| `AgentIdentity` | `id`, `type`, `version`, `origin`, `metadata` | Which agent |
| `SessionIdentity` | `id`, `user_id`, `created_at`, `expires_at`, `metadata` | Auth session |
| `TenantIdentity` | `id`, `organization_id`, `workspace_id` | Multi-tenant scope |
| `IdentityContext` | `user`, `session`, `agent`, `tenant`, `authentication_state` | **Aggregate root** |

### 2.2 IdentityService

| Method | Description |
|--------|-------------|
| `create_context(user_id, session_id, agent_type, agent_version, agent_origin)` | Build IdentityContext from raw fields |
| `resolve_user(user_id) → UserIdentity` | Lookup user |
| `resolve_session(session_id) → SessionIdentity` | Lookup session |
| `authenticate_session(token) → (UserIdentity, SessionIdentity)` | Validate token via AuthManager |
| `resolve_tenant(identity) → TenantResolutionResult` | Tenant resolution |
| `authorize(identity, scope) → AuthorizationResult` | Policy evaluation |

### 2.3 Architectural Rule

**Critical constraint** (enforced by architecture audit test): Only `core/identity/service.py` may instantiate `IdentityContext`. All production code must obtain IdentityContext through `IdentityService` or pipeline context.

### 2.4 Tenant System

| Component | Purpose |
|-----------|---------|
| `TenantResolver` (protocol) | resolve_tenant(identity) |
| `DefaultTenantResolver` | identity→default→DEFAULT_TENANT_ID="__default__" |
| `TenantResolutionResult` | tenant_id, organization_id, workspace_id, source, valid |
| `ResourceScope` | tenant_id, workspace_id, owner_id, visibility |
| `Visibility` enum | PRIVATE < TENANT < WORKSPACE < PUBLIC < SYSTEM |
| `CANONICAL_SCOPES` | 7 scopes: chat.execute, memory.read/write, scheduler.enqueue/execute, capability.use, provider.invoke, admin.runtime |

---

## 3. Authentication System (`core/auth.py`)

### 3.1 AuthManager

| Aspect | Detail |
|--------|--------|
| **Storage** | JSON files: `data/auth.json` (users), `data/sessions.json` (sessions) |
| **Password hashing** | bcrypt |
| **Session tokens** | `secrets.token_hex(32)`, 7-day TTL |
| **Rate limiting** | `AuthRateLimiter`: 10 req / 300s; `api_rate_limiter`: 120 req / 60s |
| **TOTP/2FA** | Full support with backup codes |
| **User model** | username, password_hash, is_admin, privileges dict, totp fields |

### 3.2 Key Methods

| Method | Purpose |
|--------|---------|
| `setup(username, password)` | First-run admin creation |
| `create_user(username, password, is_admin)` | User registration |
| `delete_user(username, requesting_user)` | Admin-only deletion |
| `verify_password(username, password)` | Authentication check |
| `create_session(username, password)` | Login → session token |
| `validate_token(token)` | Token validity check |
| `get_username_for_token(token)` | User lookup by token |
| `revoke_token(token)` | Logout |
| `resolve_context(username) → AuthContext` | Role resolution for RBAC |

### 3.3 Privileges Model

```python
DEFAULT_PRIVILEGES = {
    "can_use_agent": True, "can_use_browser": True, "can_use_bash": False,
    "can_use_documents": True, "can_use_research": True, "can_generate_images": True,
    "can_manage_memory": True, "max_messages_per_day": 0, "allowed_models": [],
}
```

### 3.4 Firebase Integration

| Aspect | Detail |
|--------|--------|
| **Initialization** | `init_firebase()` from `firebase-credentials.json` |
| **User sync** | `_get_or_create_user()` — auto-creates User in SQLAlchemy DB |

---

## 4. OAuth System (`core/oauth.py`)

| Aspect | Detail |
|--------|--------|
| **Supported providers** | Google, GitHub, Discord |
| **Library** | `authlib` with Starlette integration |
| **Token storage** | `~/.jarvis/oauth_tokens.json` |
| **Userinfo** | Google: ID token; GitHub/Discord: API call |
| **Routes** | `/auth/login/{provider}`, `/auth/callback`, `/auth/revoke` |
| **Gmail** | Separate `GmailAuth` in `integrations/gmail/auth.py` using `google_auth_oauthlib` |

---

## 5. Authorization / RBAC (`core/authz/`)

### 5.1 PolicyEngine

| Aspect | Detail |
|--------|--------|
| **File** | `core/authz/engine.py` |
| **Singleton** | `authz_engine` |
| **Core method** | `evaluate(ctx, required_scope, resource) → bool` |
| **Logic** | Deny by default → Admin escape → Role scopes → Direct scopes → Glob match |
| **Glob matching** | `fnmatch`-style (e.g., `tools:execute:*` matches `tools:execute:high`) |

### 5.2 Role Definitions (`config/roles.yaml`)

| Role | Scopes |
|------|--------|
| **operator** | `tools:execute:*`, `files:read`, `files:write`, `memory:read`, `memory:write`, `system:status`, `plugins:list` |
| **developer** | `tools:execute:medium`, `tools:execute:low`, `files:read`, `files:write`, `memory:read`, `memory:write`, `system:status`, `plugins:list`, `llm:complete` |
| **analyst** | `tools:execute:low`, `files:read`, `memory:read`, `system:status`, `llm:complete` |
| **guest** | `system:status`, `memory:read` |

### 5.3 Scope Enum (20+ scopes)

Categories: TOOLS (4 levels), FILES (4), MEMORY (3), SYSTEM (4), GOVERNANCE (2), PLUGINS (2), AUTH (2), LLM (2).

### 5.4 AuthContext

Mutable dataclass: `user_id`, `roles: set[Role]`, `scopes: set[Scope]`, `ip_address`, `session_id`, `metadata`, `is_admin` property.

---

## 6. Permission System (`core/permission/`)

### 6.1 Architecture

```
PermissionRegistry  ←──────────  Permissions declared by providers/capabilities
       │
       ▼
PermissionManager.resolve(capability_id)
       │
       ├── Looks up required permissions for capability
       ├── Evaluates each against PolicyProfile
       │
       ▼
PermissionResolution
  ├── results: dict[perm_id, Decision]
  ├── overall: ALLOW | DENY | NEED_CONFIRM
  └── reason: str
       │
       ▼
PermissionAudit.record() → ~/.jarvis/permission_audit.jsonl
```

### 6.2 Data Model

| Component | Values |
|-----------|--------|
| **Categories** | FILESYSTEM, NETWORK, DESKTOP, BROWSER, PROCESS, CLIPBOARD, SYSTEM, GIT |
| **Risk Levels** | LOW, MEDIUM, HIGH, CRITICAL |
| **Decisions** | ALLOW, DENY, NEED_CONFIRM |
| **Built-in permissions** | 20 total (4 LOW, 4 MEDIUM, 4 HIGH, 8 CRITICAL) |
| **Policy Profiles** | STRICT, DEVELOPER, AUTONOMOUS |

### 6.3 Policy Profiles

| Profile | Max Risk | Confirmation | Critical Allowed | Categories Blocked |
|---------|----------|-------------|-----------------|-------------------|
| **STRICT** | LOW | Required | No | desktop, browser, process, system (except env) |
| **DEVELOPER** | HIGH | Required for HIGH | Requires confirmation | desktop, system |
| **AUTONOMOUS** | CRITICAL | None | Yes | None |

### 6.4 RuntimeObserver

| Aspect | Detail |
|--------|--------|
| **Purpose** | Detect undeclared permission usage by providers |
| **Method** | `observe(provider_id, permission_id)` — compares against `declare()`d permissions |
| **Quarantine** | `should_quarantine(provider_id, threshold=3)` — auto-quarantine after 3 violations |

---

## 7. Pipeline Auth Stages

### 7.1 Stage Order

```
receive → load_context → authentication → tenant_resolution → authorization → resource_access → rate_limit → intent → ...
   1           2                3                   4                  5                6             7
```

### 7.2 AuthenticationStage

| Property | Value |
|----------|-------|
| **File** | `core/pipeline/stages/auth.py` |
| **Input** | `context.identity`, `context.metadata["auth_token"]` |
| **Logic** | SYSTEM → auto-authenticated. Token → `IdentityService.authenticate_session()` |
| **Output** | AuthenticationState: ANONYMOUS → IDENTIFIED → AUTHENTICATED |

### 7.3 TenantResolutionStage

| Property | Value |
|----------|-------|
| **File** | `core/pipeline/stages/tenant_resolution.py` |
| **Logic** | `IdentityService.resolve_tenant(identity)` → updates `context.resource_scope` |
| **Default** | `DEFAULT_TENANT_ID = "__default__"` |

### 7.4 AuthorizationStage

| Property | Value |
|----------|-------|
| **File** | `core/pipeline/stages/authorization.py` |
| **Input** | `context.identity`, `context.metadata["auth_scope"]` |
| **Logic** | SYSTEM → auto-authorized. Otherwise `IdentityService.authorize()` |
| **Output** | `ResourceGrant` on success, `AuthorizationResult` |

### 7.5 ResourceAccessStage

| Property | Value |
|----------|-------|
| **File** | `core/pipeline/stages/resource_access.py` |
| **Logic** | Visibility-based check against identity: PUBLIC → always; TENANT → same tenant; WORKSPACE → same workspace; PRIVATE → owner; SYSTEM → always |

### 7.6 RateLimitStage

| Property | Value |
|----------|-------|
| **File** | `core/pipeline/stages/rate_limit.py` |
| **Status** | **Pass-through / no-op**. HTTP-level rate limiting exists in middleware but pipeline stage is unimplemented. |

---

## 8. HTTP API Auth Layer

### 8.1 Middleware

| Middleware | Purpose | Exempt Paths |
|-----------|---------|-------------|
| `session_auth_middleware` | Sets `request.state.current_user` from session token | `/health`, `/docs`, `/auth/**`, `/ws`, `/`, static assets |
| `SecurityHeadersMiddleware` | CSP, X-Frame-Options, X-CTO, Referrer-Policy | None |

### 8.2 FastAPI Dependencies

| Dependency | Purpose |
|-----------|---------|
| `verify_token(authorization, request, db) → User` | Token validation with cookie fallback |
| `get_auth_context(user, request) → AuthContext` | Role resolution (ADMIN, DEVELOPER, GUEST, OPERATOR) |
| `require_scope(scope)` | Checks `authz_engine.evaluate()` |
| `require_role(role)` | Checks user has required role |
| `verify_token_from_request(request, db)` | Trusted-proxy forwarding via X-Forwarded-User |
| `require_admin()` | Admin check with internal-token escape hatch |

### 8.3 Exempt Routes Accessible Without Auth

`/health`, `/docs`, `/openapi.json`, `/redoc`, `/static`, `/assets`, `/manifest.json`, `/sw.js`, `/api/auth/**, `/auth/**`, `/api/setup`, `/api/whatsapp`, `/icons`, `/_next`, `/ws`, `/`.

---

## 9. Tool-Level RBAC

### 9.1 is_authorized_to_execute()

| Property | Value |
|----------|-------|
| **File** | `core/tools/security.py` |
| **Logic** | 1. Admin escape → allow. 2. Lookup tool policy scope. 3. `authz_engine.evaluate()`. 4. Legacy blocklist fallback. |
| **Blocked tools** | 36 tools that non-admins cannot use (bash, python, shell, file operations, email, etc.) |

### 9.2 NON_ADMIN_BLOCKED_TOOLS

Includes: `bash`, `python`, `shell`, `execute_command`, `read_file`, `write_file`, `edit_file`, `delete_file`, `execute_project_tool`, `run_script`, `send_email`, `take_screenshot`, `type_keyboard`, `click_mouse`, `navigate_url`, `install_package`, `modify_system`, `manage_services`, `execute_sql`, `manage_network`, `modify_registry`, `schedule_task`, `modify_firewall`, `manage_users`, `docker_exec`, `kubectl_exec`, `ssh_exec`, `ansible_exec`, `terraform_exec`, `sudo_exec`, `run_as`, `manage_secrets`, `decrypt_data`, `manage_certificates`, `modify_audit`, `wipe_logs`.

---

## 10. Provider SDK Permissions

### 10.1 PermissionDeclarationStage (Stage 4)

Validates provider-declared permissions against `ALL_PERMISSIONS` set during provider installation.

### 10.2 RuntimePermissionRegistrationStage (Stage 8)

Calls `permission_manager.grant(provider_id, permissions)` to activate permissions at runtime.

### 10.3 RuntimeObserver

Monitors actual permission usage and auto-quarantines providers that use undeclared permissions (threshold: 3 violations).

---

## 11. Distributed Worker Auth

| Aspect | Detail |
|--------|--------|
| **File** | `core/distribution/contracts.py` |
| **Mechanism** | `WorkerRequest` carries full `RuntimeContext` (identity, authN, authZ, tenant, resource_scope, resource_grant) |
| **Security** | Request `signature` + `nonce` for verification |
| **Purpose** | Secure worker distribution with identity propagation |

---

## 12. Ownership Matrix

| Component | Owner | Creator | Reader | Writer | Destroyer | Persistence | Lifetime |
|-----------|-------|---------|--------|--------|-----------|-------------|----------|
| **IdentityService** | `core/identity/service.py` | Module import (singleton) | Pipeline stages | Pipeline stages | Process death | In-memory | Process |
| **IdentityContext** | `core/identity/models.py` | IdentityService only | Pipeline, services | None (frozen) | Per-request | None | Per-request |
| **AuthManager** | `core/auth.py` | Module import | API routes, middleware | API routes | Process death | JSON files (auth.json, sessions.json) | Persistent |
| **PolicyEngine** | `core/authz/engine.py` | Module import (singleton) | is_authorized_to_execute(), pipeline | None (read-only) | Process death | config/roles.yaml | Persistent config |
| **PermissionManager** | `core/permission/manager.py` | Module import (singleton) | Provider SDK, execution | Provider SDK | Process death | In-memory | Process |
| **PermissionRegistry** | `core/permission/registry.py` | Module import (singleton) | PermissionManager | Provider install | Process death | In-memory | Process |
| **PermissionAudit** | `core/permission/audit.py` | Module import (singleton) | Audit queries | PermissionManager | clear() | JSONL file | Persistent |
| **RuntimeObserver** | `core/permission/observer.py` | Module import (singleton) | Quarantine check | Provider SDK | Process death | In-memory | Process |
| **OAuthManager** | `core/oauth.py` | Module import | API routes | API routes | Process death | JSON file | Persistent |
| **AuthRateLimiter** | `core/auth.py` | Module import | verify_token() | verify_token() | Process death | In-memory | Process |
| **SecurityHeadersMiddleware** | `core/middleware.py` | FastAPI startup | Every HTTP request | None (read-only) | Process death | None | Process |
| **Pipeline Auth Stages** | `core/pipeline/stages/` | Pipeline factory | Pipeline execute | Self | Per-request | None | Per-request |
| **Tool-level RBAC** | `core/tools/security.py` | Module import | execute_tool_block() | None (read-only) | Process death | None | Per-policy |

---

## 13. Duplication Analysis

### 13.1 Three AuthZ Systems

| System | Scope | Granularity | Config | Consumers |
|--------|-------|-------------|--------|-----------|
| **PolicyEngine (authz/)** | RBAC scopes | Coarse (role → scope set) | YAML config | Pipeline, tool RBAC |
| **PermissionManager (permission/)** | Capability permissions | Fine (per-category risk level) | Code-defined profiles | Provider SDK, execution |
| **AuthManager privileges** | User-level feature flags | Medium (boolean flags per user) | Embedded in auth.json | Legacy routes |

**Impact:** Three authorization systems with different granularity levels, addressing different concerns. PolicyEngine controls logical access; PermissionManager controls capability risk; AuthManager privileges control feature enablement. They are **complementary, not duplicative**, but a developer must understand all three to answer "can this user do this action?"

### 13.2 AuthManager vs Firebase Auth

| Aspect | AuthManager | Firebase |
|--------|-------------|----------|
| **Backend** | JSON files | Firebase Admin SDK |
| **Users** | Stored in auth.json | Stored in SQLAlchemy `User` table |
| **Sync** | None | `_get_or_create_user()` syncs Firebase→SQLAlchemy |
| **Usage** | Primary for session management | Supplementary for Firebase-based apps |

**Impact:** The same user can exist in both systems with different session tokens. There is no unified user repository.

### 13.3 Auth Rate Limiting (2x)

| Rate Limiter | Target | Limit | Scope |
|-------------|--------|-------|-------|
| `AuthRateLimiter` | Auth endpoints | 10 req / 300s | Per-IP |
| `api_rate_limiter` | General API | 120 req / 60s | Global |

The pipeline `RateLimitStage` is a no-op, meaning request-level rate limiting only happens at the HTTP middleware layer, not within the pipeline.

### 13.4 User Storage (3x)

| Store | Location | Schema | Purpose |
|-------|----------|--------|---------|
| `auth.json` | `data/auth.json` | Username, hash, admin flag, privileges | AuthManager sessions |
| SQLAlchemy `User` | Configurable DB | uid, email, display_name, preferences | Firebase users |
| `IdentityService` | In-memory protocol | UserIdentity (id, email, roles) | Pipeline identity resolution |

**Impact:** Three user representations with different schemas, no single source of truth.

---

## 14. Findings

### F-1: Well-Designed Layered Security
The five-layer architecture (HTTP → Pipeline → Execution → Provider → Audit) provides defense-in-depth. Each layer addresses a different security concern: transport auth, request identity, tool authorization, capability permissions, and audit logging.

### F-2: IdentityService Architectural Rule Is Enforced
The rule "only IdentityService may construct IdentityContext" is enforced by `test_architecture_audit.py`. This prevents identity spoofing and ensures consistent identity resolution.

### F-3: AuthManager Uses JSON Files Instead of SQLite
User credentials and session tokens are stored in flat JSON files (`auth.json`, `sessions.json`) with no write-ahead logging, no transactions, and no concurrency protection. Concurrent authentication requests risk session corruption.

### F-4: Pipeline RateLimitStage Is a No-Op
Rate limiting only exists at the HTTP middleware layer. The pipeline's RateLimitStage performs no actual rate limiting, meaning any execution path that bypasses the HTTP layer (internal calls, MCP, WebSocket) has no request-level rate limiting.

### F-5: Three AuthZ Systems Require Multi-System Understanding
While the three systems are not duplicative, determining whether an action is authorized requires evaluating PolicyEngine scopes, PermissionManager risk profiles, and AuthManager privileges — three separate evaluations with no unified query interface.

### F-6: OAuth Token Storage Is JSON-File-Based
OAuth tokens (containing refresh tokens) are stored in `~/.jarvis/oauth_tokens.json` with no encryption at rest. A compromise of the file system exposes long-lived provider tokens.

### F-7: AuthManager Has No User Registration API
Users can only be created via `AuthManager.create_user()`, which requires admin privileges. There is no self-registration flow, password reset, or email verification.

### F-8: Anonymous Identity Is the Default
The default `AuthenticationState` is `ANONYMOUS`. Many pipeline stages and API endpoints accept anonymous requests, with authentication only applied where explicitly required.

### F-9: RuntimeObserver Has No Persistence
Undeclared permission violations are tracked in memory only. A process restart resets violation counts, allowing providers with persistent undeclared usage patterns to escape quarantine detection.

### F-10: Tool Blocklist Is Legacy
The 36-tool `NON_ADMIN_BLOCKED_TOOLS` list in `core/tools/security.py` operates alongside the PolicyEngine-based scope evaluation. It's a legacy denylist that bypasses the scope system. Tools can be blocked in the list while also being denied by scope, creating confusion about which mechanism is authoritative.

---

## 15. Recommendations

### R-1: (Medium) Migrate AuthManager to SQLite
Replace `auth.json` and `sessions.json` with SQLite tables. This provides transaction safety, WAL mode for concurrent access, and consistency with the rest of the system.

### R-2: (Medium) Implement Pipeline RateLimitStage
Add actual rate limiting to the pipeline stage, using the same rate limiter as the HTTP layer but applied universally regardless of entry point.

### R-3: (Medium) Unify User Storage
Design a single user model used by AuthManager, Firebase, and IdentityService. The SQLAlchemy `User` table is the most natural candidate, with AuthManager migrating to use it instead of JSON files.

### R-4: (Low) Encrypt OAuth Token Storage
Add encryption-at-rest for `oauth_tokens.json` using a key derived from a configured secret.

### R-5: (Low) Replace Tool Blocklist with Scope-Based Equivalent
Remove the `NON_ADMIN_BLOCKED_TOOLS` list and express the same constraints through PolicyEngine role-scope mappings. This eliminates the dual-authority problem.

### R-6: (Low) Add RuntimeObserver Persistence
Persist violation counts to the permission audit log or a dedicated table so that quarantine state survives restarts.

### R-7: (Low) Create Unified Authorization Query
Add a single `Authorizer.authorize(action, context, resource)` method that evaluates PolicyEngine scopes, PermissionManager risk, and AuthManager privileges in a single call, returning a unified `(ALLOW/DENY, reason)` result.

### R-8: (Low) Add Self-Registration Flow
Implement password reset, email verification, and optional self-registration for multi-user deployments.
