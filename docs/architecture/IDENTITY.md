# Identity — Phase 6A Sprint 1

> Canonical identity models and propagation through the pipeline.
> Sprint 1 is purely structural — no authentication, authorization, or
> persistence behavior.

---

## 1. Identity Models

All identity types live in `core/identity/models.py` and are frozen
dataclasses.

```
UserIdentity
  id              str          — canonical user identifier
  email           str | None
  display_name    str | None
  roles           tuple[str]   — ["admin", "operator", "guest", …]
  metadata        dict

AgentIdentity
  id              str          — agent identifier (e.g. "cli", "web-1")
  type            str          — "cli", "web", "voice", "scheduler", "api"
  version         str | None
  origin          str | None   — "browser", "mobile", "autonomous", …
  metadata        dict

SessionIdentity
  id              str          — session token or conversation id
  user_id         str | None
  created_at      datetime | None
  expires_at      datetime | None
  metadata        dict

TenantIdentity
  id              str | None
  organization_id str | None
  workspace_id    str | None

IdentityContext
  user                UserIdentity | None
  session             SessionIdentity | None
  agent               AgentIdentity | None
  tenant              TenantIdentity
  authentication_state AuthenticationState  — ANONYMOUS / IDENTIFIED /
                                               AUTHENTICATED / SYSTEM
```

### AuthenticationState enum

| Value | Meaning |
|---|---|
| `ANONYMOUS` | No identity information available |
| `IDENTIFIED` | User identity claimed but not validated |
| `AUTHENTICATED` | Identity validated (Sprint 2+) |
| `SYSTEM` | Internal/system request (scheduler, admin) |

---

## 2. IdentityService

Location: `core/identity/service.py`

### IdentityResolver protocol

```python
class IdentityResolver(Protocol):
    def create_context(self, *, user_id, session_id,
                       agent_type, agent_version, agent_origin) -> IdentityContext
    def resolve_user(self, user_id) -> UserIdentity
    def resolve_session(self, session_id) -> SessionIdentity
```

### IdentityService implementation

Sprint 1 performs **structural mapping only**:

- `create_context()` wraps raw strings into identity objects
- `resolve_user()` creates `UserIdentity` from a string — no DB lookup
- `resolve_session()` creates `SessionIdentity` from a string — no token validation
- `authentication_state` is `IDENTIFIED` if `user_id` is provided, else `ANONYMOUS`

### Singleton access

```python
get_identity_service()  # lazy singleton, returns IdentityResolver
set_identity_service(svc)  # override for tests
```

---

## 3. Propagation through pipeline

```
Transport Adapter
       │
       ▼
   Request(user_id, session_id)
       │
       ▼
   process_message()
       │
       ├── create PipelineContext
       ├── ctx.identity = get_identity_service().create_context(...)
       │
       ▼
   Pipeline.execute(ctx)
       │
       ▼
   ctx.identity  ← accessible by any stage
```

### STAGE_OWNERSHIP

`identity` is owned by the `load_context` stage (alongside `user_id` and
`session_id`). This ensures a single canonical owner if future stages
need to write to it.

---

## 4. Architecture audit — Rule 12

Only `core/identity/service.py` may construct `IdentityContext` directly
in production code. All other code must call
`get_identity_service().create_context()`. Tests and identity model
definitions are exempt.

Enforced by AST scan in `test_architecture_audit.py`.

---

## 5. Sprint 1 constraints

| Allowed | Not allowed |
|---|---|
| Create identity models | Token validation |
| Propagate identity through pipeline | AuthManager integration |
| Singleton service with test override | Authorization/permission checks |
| STAGE_OWNERSHIP entry | AuthenticationStage changes |
| Architecture audit Rule 12 | LoadContextStage identity resolution |
| Identity documentation | `authentication_state = AUTHENTICATED` |
| | Removing `user_id` / `session_id` fields |
| | Tenant isolation |
| | Identity persistence |

---

## 6. Future sprints

- **Sprint 2** — Authenticate: token validation, `AuthManager` integration,
  `AuthenticationStage` resolves identity, `authentication_state = AUTHENTICATED`
- **Sprint 3** — Authorize: permission checks, `AuthorizationStage`,
  scope enforcement
- **Sprint 4** — Tenant isolation: lookup and propagate tenant identity
  from request context
