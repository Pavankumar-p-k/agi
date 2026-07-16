# Phase 8: Safety & Security Architecture Audit

**Status**: READ ONLY — no code was modified.  
**Date**: 2026-07-15  
**Scope**: Permissions, Confirmation, Desktop/Browser/Filesystem Safety, API Keys & Secrets, Dangerous Commands, Shell Injection, Recovery, Logging, Rate Limits, Emergency Stop.

---

## 1. Executive Summary

### Overall Safety Posture by Domain

| Domain | Score | Key Strength | Key Gap |
|--------|-------|-------------|---------|
| **Permissions / Auth** | 8/10 | Multi-layer RBAC + policy engine + pipeline stages | Legacy `auth.py` deprecated but still imported |
| **Desktop Safety** | 7/10 | 7-gate SafetyManager, emergency stop, pyautogui failsafe | `launch_app()` uses `shell=True` on Windows |
| **Browser Safety** | 3/10 | Stealth/evasion protections | No URL blocklist, no navigation confirmation, permissions auto-granted |
| **Filesystem Safety** | 5/10 | Path traversal check in tool execution, atomic writes, backup guards | `file_agent.py` lacks path containment; `shutil.rmtree()` without validation |
| **API Key / Secrets** | 4/10 | bcrypt passwords, Fernet encryption available, API key rotation | Keys stored in plaintext JSON, encryption key on same filesystem, `.env` with live secrets |
| **Shell Injection** | 6/10 | Most code uses `shell=False` + `shlex.split()`, no `os.system()` | 3 HIGH-risk paths, sandbox `parse_command()` uses naive split |
| **Recovery** | 5/10 | Workflow + graph recovery exist | No circuit breaker pattern, no global kill switch |
| **Rate Limiting** | 8/10 | Sliding window, per-profile, loopback exempt, tested | None significant |
| **Emergency Stop** | 4/10 | Desktop-only emergency stop, pyautogui FAILSAFE | No global agent kill switch |
| **Logging of Secrets** | 5/10 | Most code avoids logging secrets | `cookbook_tools.py` leaks passwords/TOTP, `as_dict()` returns unmasked secrets |
| **Self-Modification** | 8/10 | Pre/post checks, rollback, thresholds | None significant |
| **Input Sanitization** | 7/10 | PII stripping, prompt injection guards, homoglyph normalization | None significant |

### Key Findings

- **S-1**: API keys stored in **plaintext JSON** at `~/.jarvis/api_keys.json` — Fernet encryption exists but is not used
- **S-2**: **Live secrets in `.env` file** (GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, EMAIL_PASS, TAVILY_API_KEY, SECRET_KEY)
- **S-3**: `DesktopController.launch_app()` uses `shell=True` on Windows — shell injection vector
- **S-4**: No global agent kill switch — only desktop emergency stop exists
- **S-5**: `cookbook_tools.py:1428/1431` leaks passwords and TOTP secrets to output/logs
- **S-6**: Configuration `as_dict()` returns secrets unmasked (unlike `as_api_dict()`)
- **S-7**: Browser has no URL blocklist, no navigation confirmation — clipboard permissions auto-granted
- **S-8**: WebSocket terminal (`routes/terminal.py`) and persistent shell (`persistent_shell.py`) accept raw commands with zero sanitization (HIGH risk)
- **S-9**: OAuth tokens stored in plaintext JSON at `~/.jarvis/oauth_tokens.json`
- **S-10**: No file permission hardening (`chmod 0o600`) on any secret files

---

## 2. Permissions & Authorization

### 2.1 Architecture (Multi-Layer)

```
LAYER 1: API AUTH (FastAPI middleware)
  core/auth.py → verify_token() → IdentityService.authenticate_session()
  Pipeline: AuthenticationStage → AuthorizationStage → RateLimitStage

LAYER 2: RBAC (tool execution)
  core/authz/engine.py → PolicyEngine.evaluate(scope, resource)
  core/tools/security.py → is_authorized_to_execute(tool_name, ctx)
    → 37 tools blocked for non-admins (bash, shell, write_file, vault_*, etc.)
    → Admin escape hatch (Role.ADMIN bypasses ALL checks)

LAYER 3: CAPABILITY PERMISSIONS (agent actions)
  core/permission/manager.py → PermissionManager.resolve(capability_id)
    → Checks PolicyProfile (STRICT / DEVELOPER / AUTONOMOUS)
    → Returns ALLOW / DENY / NEED_CONFIRM
    → Records to JSONL audit trail
    → RuntimeObserver: 3 violations → quarantine

LAYER 4: PROVIDER SDK PERMISSIONS (plugin isolation)
  provider_sdk/permissions.py → PermissionManager.validate_permissions()
    → Rejects wildcards ("*", "all") and unknown permissions
    → 25 granular permissions + 6 HIGH_RISK
```

### 2.2 Reality Scores by Component

| Component | File | Score | Notes |
|-----------|------|-------|-------|
| `auth.py` (legacy) | `core/auth.py` | 5/10 | Deprecated shim, still functional, bcrypt + TOTP + sessions |
| `authz/engine.py` | `core/authz/engine.py` | 8/10 | Clean RBAC, glob scope matching, admin escape |
| `identity/auth_store.py` | `core/identity/auth_store.py` | 8/10 | bcrypt hashes, SQLite storage |
| `permission/manager.py` | `core/permission/manager.py` | 8/10 | Clean 3-profile policy engine, audit trail, runtime observer |
| `permission/registry.py` | `core/permission/registry.py` | 7/10 | Maps capabilities → permissions |
| `tools/security.py` | `core/tools/security.py` | 8/10 | RBAC + blocklist, admin escape, AuthContext-based |
| `pipeline/auth.py` | `core/pipeline/stages/auth.py` | 8/10 | Identity validation stage |
| `pipeline/authorization.py` | `core/pipeline/stages/authorization.py` | 8/10 | Scope-based ResourceGrant stage |

### 2.3 Dangerous Paths

| Path | File | Issue |
|------|------|-------|
| Admin escape hatch | `core/tools/security.py:48` | `Role.ADMIN` bypasses ALL tool authorization — necessary but dangerous if admin role is improperly granted |
| Legacy blocklist | `core/tools/security.py:27-36` | 37 tools blocked by name only — new tools not in blocklist are implicitly allowed |
| `NEED_CONFIRM` enforcement | `core/permission/manager.py` | DEPENDS on caller respecting the NEED_CONFIRM decision — there's no mechanism to force confirmation |

---

## 3. Confirmation Dialogs / Human-in-the-Loop

### 3.1 Inventory of Confirmation Points

| Location | File | What It Confirms | Bypass? |
|----------|------|------------------|---------|
| MCP Bridge approval | `core/tools/execution/authorization.py:27-48` | Tool execution (when `needs_confirmation=True`) | No bypass |
| Safety classify tool | `core/routing/safety.py:55-95` | Shell/file ops into SAFE/CONFIRM/DANGEROUS | Classification is advisory |
| FileAgent write | `core/file_agent.py:88-94` | Showing diff before file overwrite | `skip_confirm=True` parameter |
| FileAgent execute | `core/file_agent.py:279` | Execute shell command? | `skip_confirm=True` parameter |
| ComputerAgent | `pc_agent/computer_agent.py:161` | Execute natural language instruction | `confirm=True` (default) — but caller can set `False` |

### 3.2 Silent Failure Paths

| Path | File | Issue |
|------|------|-------|
| `SafetyManager.check()` returns `SafetyDecision(allowed=False)` | `core/desktop/safety.py` | Caller must check return value — no exception thrown on deny. DesktopController checks it, but other callers might not |
| `PermissionManager.resolve()` returns DENY | `core/permission/manager.py` | Returns `PermissionResolution` — caller must check `.allowed` or `.denied`. No exception thrown |
| `classify_tool()` returns DANGEROUS | `core/routing/safety.py` | Returns enum value — caller must act on it. No exception or block mechanism in the classifier itself |

---

## 4. Desktop Safety

### 4.1 SafetyManager Gates (`core/desktop/safety.py`)

7 enforcement gates in order:

| Gate | Lines | Limit | Enforcement |
|------|-------|-------|-------------|
| 1. Emergency stop | 92-103 | Blocks ALL actions when active | Hard block |
| 2. Cooldown | 136-146 | 50ms minimum between actions | 500ms default cooldown |
| 3. Mouse speed | 201-214 | 2000 px/sec max | Rejects exceeding |
| 4. Typing rate | 223-237 | 30 char/sec, max 500 chars | Rate-limited |
| 5. Screenshot rate | 242-253 | 10/min max | Rate-limited |
| 6. Click rate | 255-266 | 60/min max | Rate-limited |
| 7. Forbidden regions | 191-199 | Configurable blocked screen areas | Rejects clicks in region |

### 4.2 DesktopController (`core/desktop/controller.py`)

| Operation | Safety Gate | Status |
|-----------|-------------|--------|
| Mouse move/click/scroll/drag | SafetyManager.check() | Connected |
| Keyboard type/press/hotkey | SafetyManager.check() | Connected |
| Screenshot capture | SafetyManager.check() | Connected |
| Window focus/minimize/close | SafetyManager.check() | Connected |
| `launch_app()` | **No gate** — direct Popen | **shell=True** on Windows |

### 4.3 Reality Scores

| Component | Score | Notes |
|-----------|-------|-------|
| SafetyManager | 8/10 | Comprehensive gates, emergency stop, configurable |
| DesktopController | 6/10 | Wraps SafetyManager well, but `launch_app()` uses `shell=True` |
| PyAutoGUI failsafe | 10/10 | `FAILSAFE=True`, `PAUSE=0.35`, mouse to corner (0,0) stops everything |

---

## 5. Browser Safety

### 5.1 Browser Manager (`core/browser_manager.py`)

No safety mechanisms for:
- **URL blocklist** — no restrictions on what URLs can be visited
- **Navigation confirmation** — no human approval before navigation
- **Form submission** — no confirmation before filling/submitting forms
- **Download scanning** — no scanning of downloaded files
- **Clipboard permissions** — actively spoofed (navigator.permissions returns 'granted')

### 5.2 Reality Scores

| Component | Score | Notes |
|-----------|-------|-------|
| Browser stealth/evasion | 7/10 | Good bot-detection evasion |
| Browser safety | 2/10 | No restrictions on any browser operation |
| Overall | 3/10 | |

---

## 6. Filesystem Safety

### 6.1 Protection Layers

| Layer | File | Method | Status |
|-------|------|--------|--------|
| Path traversal protection | `core/tools/execution/security.py` | `_resolve_tool_path()` + `_is_sensitive_path()` | Connected for tool execution |
| Sensitive file blocklist | `core/tools/execution/security.py:6-12` | Blocks `.ssh/`, `.gnupg/`, `.env`, `authorized_keys`, `id_rsa`, etc. | Connected |
| Chroot containment | `core/tools/execution/security.py:85-97` | Path must be within DATA_DIR, /tmp, or configured roots | Connected |
| Backup path traversal | `core/backup.py:101-110` | `_is_within_directory()` check for tar files | Connected |
| Atomic writes | `core/atomic_io.py` | Temp file + os.replace() | Connected for config/auth files |

### 6.2 Dangerous Paths

| Path | File | Issue |
|------|------|-------|
| `file_agent.py:read_file/write_file` | `core/file_agent.py` | **No path containment** — only `os.path.expanduser()` called, no chroot check (unlike `_resolve_tool_path`) |
| `shutil.rmtree(path)` | `core/checkpoint_manager.py:174` | No path validation before recursive delete |
| `shutil.rmtree(path)` | `core/project_state.py:229` | No path validation before recursive delete |
| `shutil.rmtree(path, ignore_errors=True)` | `core/embeddings.py:161` | No path validation + errors ignored |

### 6.3 Reality Scores

| Component | Score | Notes |
|-----------|-------|-------|
| Tool execution path safety | 7/10 | Good containment + sensitive path blocklist |
| FileAgent | 4/10 | No path containment, skip_confirm bypass |
| Backup | 7/10 | Path traversal check |
| Rmtree safety | 2/10 | No validation before recursive delete |

---

## 7. API Keys & Secrets

### 7.1 Secret Storage Map

| Storage | Format | Encrypted? | File | Risk |
|---------|--------|------------|------|------|
| API keys | Plaintext JSON | **No** | `~/.jarvis/api_keys.json` | HIGH |
| OAuth tokens | Plaintext JSON | **No** | `~/.jarvis/oauth_tokens.json` | HIGH |
| .env file | Plaintext | **No** | `jarvis/.env` (gitignored) | CRITICAL |
| Integration configs | Plaintext JSON | **No** | `~/.jarvis/integrations/*` | HIGH |
| Fernet key | Plaintext file | N/A (key itself) | `~/.jarvis/data/.app_key` | MEDIUM |
| Firebase creds | Plaintext JSON | **No** | `jarvis/firebase-credentials.json` | **In repo root** |
| Password hashes | bcrypt hash | Yes (one-way) | SQLite DB | SAFE |
| Session tokens | `secrets.token_hex(32)` | N/A (in-memory + SQLite) | SQLite DB | SAFE |

### 7.2 The Encryption Paradox

Fernet encryption exists (`core/secret_storage.py`) but:
- `APIKeyVault` stores keys in **plaintext** — never calls `encrypt()`
- `OAuthStore` stores tokens in **plaintext** — never calls `encrypt()`
- `IntegrationManager` stores credentials in **plaintext** — never calls `encrypt()`
- The Fernet key itself is stored on the **same filesystem** at `DATA_DIR/.app_key`
- If `secret_storage` import fails (e.g., `mcp/email_server.py:201`), decrypt silently becomes identity function

### 7.3 API Key Loading Chain

```
APIKeyVault.get(service)
  ├── ~/.jarvis/api_keys.json (plaintext array of keys)
  └── os.getenv("{SERVICE}_API_KEY") or os.getenv("{SERVICE}")  (fallback)

AuthProfile auto-discovery (llm_failover.py)
  └── Iterates ALL os.environ items ending in _API_KEY
      └── Stores raw key in AuthProfile.api_key dataclass field

LiteLLM Router auto-injection (llm_router.py)
  └── os.getenv(f"{provider.upper()}_API_KEY") for each model prefix
```

### 7.4 Key Rotation

`APIKeyVault.rotate(service)` — simple round-robin through a list of keys:
```
{"openai": ["sk-...key1", "sk-...key2", "sk-...key3"]}
rotate("openai") → index advances to next key
on_rate_limited("openai") → auto-rotate on 429
```

No automatic key revocation, no OAuth refresh, no key expiry detection.

### 7.5 Reality Scores

| Component | Score | Notes |
|-----------|-------|-------|
| APIKeyVault | 4/10 | Plaintext storage, rotation but no revocation |
| SecretStorage (Fernet) | 5/10 | Exists but unused by consumers; key on same filesystem |
| OAuth store | 3/10 | Plaintext, no encryption |
| Integration storage | 4/10 | Plaintext |
| Password hashing | 9/10 | bcrypt with salt everywhere |
| Key auto-discovery | 5/10 | `llm_failover.py` enumerates all env vars — risk of capturing non-API-key secrets |

---

## 8. Dangerous Commands & Shell Injection

### 8.1 Risk Inventory

**CRITICAL / HIGH RISK (3 paths):**

| # | File:Line | Pattern | Risk | Why |
|---|-----------|---------|------|-----|
| 1 | `core/desktop/controller.py:214` | `subprocess.Popen(exe, shell=True)` (Win32) | HIGH | **shell=True** + user-derived `app_name` |
| 2 | `core/routes/terminal.py:23-54` | `create_subprocess_exec(shell)` + raw stdin write | HIGH | **No auth, no validation, no rate limit** on WebSocket commands |
| 3 | `core/tools/persistent_shell.py:43-114` | `create_subprocess_exec(shell)` + raw stdin write | HIGH | **No sanitization** of LLM-provided commands |

**MEDIUM RISK (14 paths):**

| # | File:Line | Pattern | Risk | Protection |
|---|-----------|---------|------|------------|
| 4 | `core/tools/execution/direct_tools.py:70-82` | `cmd /c {content}` | MEDIUM | Shell interprets pipes/redirects |
| 5 | `core/tools/execution/handlers.py:342-361` | `shell.exec(content)` | MEDIUM | Docker sandbox path exists |
| 6 | `core/file_agent.py:290-318` | `subprocess.run(cmd)` + `cmd /c {cmd}` | MEDIUM | Has confirmation prompt |
| 7 | `core/providers/adapters/deployment_provider.py:108-275` | f-string commands → `shlex.split()` | MEDIUM | Argument injection risk |
| 8 | `core/agent_launcher.py:237-246` | f-string → manual quoting | MEDIUM | Inconsistent quoting |
| 9 | `core/legacy/control_loop.py:864` | f-string with unquoted JSON | MEDIUM | No `shlex.quote()` |
| 10 | `api/plugin_routes.py:58` | `pip install {package_name}` | MEDIUM | Supply chain risk |
| 11 | `provider_sdk/adapters/cli_adapter.py:34-35` | `subprocess.run(cmd.split())` | MEDIUM | Unvalidated manifest field |

### 8.2 Shell=True Occurrences

Exactly **one** production code path uses `shell=True`:
- `core/desktop/controller.py:214` — Windows-only fallback for `launch_app()`

No `os.system()`, no `eval()`, no `exec()` found in business logic.

### 8.3 Subprocess Patterns by Safety

| Pattern | Safety | Count |
|---------|--------|-------|
| `shlex.split()` + `create_subprocess_exec()` | SAFE | ~10 files |
| `subprocess.run(list_args, shell=False)` | SAFE | ~40 files |
| `create_subprocess_exec(shell, stdin=PIPE)` + raw stdin | **MEDIUM** | 2 files (terminal, persistent_shell) |
| `["cmd", "/c"]` + string | MEDIUM | ~5 files |
| `Popen(string, shell=True)` | **HIGH** | 1 file |

### 8.4 Sandbox Command Parsing Weakness

`core/sandbox/sandbox.py:68` — `parse_command()` uses naive `cmd.split()`:
```python
def parse_command(cmd: str) -> list[str]:
    return cmd.split()
```
Does not handle quoting, so `echo "hello world"` splits into `["echo", "\"hello", "world\""]`.

### 8.5 Existing Protections

| Protection | Coverage |
|-----------|----------|
| `shell=False` enforcement | ~95% of subprocess calls |
| `shlex.quote()` | `cookbook_tools.py`, `legacy/control_loop.py`, `vision_agent.py` |
| `shlex.split()` | ~10 files |
| Confirmation prompt | `file_agent.py:279` |
| Timeouts | Almost all subprocess calls |
| Output limits | `file_agent.py`, `sandbox.py`, `direct_tools.py` |
| Executable blocklist | `sandbox.py:35-43` — blocks format, registry, shutdown, etc. |
| Write path restriction | `sandbox.py:46-51` — only home, cwd, temp, appdata |
| Docker sandbox | `sandbox/docker_sandbox.py` |
| Plugin sandbox (AST scan) | `plugins/sandbox.py` |
| Kill on timeout | `subprocess.py:62-69`, `direct_tools.py` |
| Idle GC for shells | `persistent_shell.py:161-169` — 5 minute idle close |

---

## 9. Recovery Mechanisms

### 9.1 Inventory

| Mechanism | File | What It Recovers | Status |
|-----------|------|------------------|--------|
| Workflow recovery | `core/workflow/recovery.py` | Stale RUNNING/RECOVERING/COMPENSATING workflows | Connected |
| Graph recovery | `core/distribution/graph/recovery.py` | Failed/paused distributed graph nodes | Connected |
| API key rotation | `core/api_key_vault.py:78-93` | Auto-rotate on 429 rate limit | Connected |
| Config fallback | `core/configuration/service.py:172-219` | 6-tier fallback chain | Connected |
| Auth fallback | `core/auth.py` | SQLite → JSON → first-run setup | Connected |

### 9.2 Missing Mechanisms

| Mechanism | Why Needed |
|-----------|-----------|
| **Circuit breaker** | No provider-level circuit breaker — if a provider fails, every subsequent request also fails |
| **Global kill switch** | No way to stop ALL agent activity (LLM calls + tools + desktop) |
| **Rate limit recovery** | After rate limit is hit, no backoff/retry strategy |
| **Self-healing** | `self_healing.py` exists but is file-system focused; no restart of failed subprocesses |

---

## 10. Logging of Sensitive Data

### 10.1 Confirmed Leaks

| # | File:Line | What Leaks | Severity |
|---|-----------|------------|----------|
| 1 | `core/tools/cookbook_tools.py:1428` | `f"Password: {login.get('password', '(none)')}"` | HIGH |
| 2 | `core/tools/cookbook_tools.py:1431` | `f"TOTP secret: {login['totp']}"` | HIGH |
| 3 | `core/configuration/service.py:287-295` | `as_dict()` returns ALL secrets unmasked | HIGH |
| 4 | `core/tools/schemas.py:55` | Tool arguments (may contain secrets) logged on parse failure | MEDIUM |
| 5 | `core/tools/schemas.py:59` | `repr()` of tool args (may contain secrets) | MEDIUM |
| 6 | `mcp/server.py:162` | Raw bridge client payload logged on JSON error | MEDIUM |
| 7 | `core/secret_storage.py:36` | `f"Encryption failed: {e}"` — e may contain data | LOW |
| 8 | `benchmarks/*.py` | `traceback.print_exc()` in 8 benchmark files | LOW |

### 10.2 Good Patterns (No Leak)

| File | Pattern |
|------|---------|
| `core/agent_launcher.py:129-130` | Keys masked before logging: `key[:8] + "..."` |
| `core/context_hub.py:117-119` | Env var snapshot filters out `key/token/secret/password/auth` |
| `core/configuration/service.py:299-302` | `_mask_secret()` correctly applied in `as_api_dict()` |

### 10.3 Configuration API Leak

`ConfigurationService` has two methods:
- `as_api_dict()` — calls `_mask_secret()` for entries tagged `secret=True` — **GOOD**
- `as_dict()` — returns raw values with NO masking — **LEAK**

Consumer: `core/tools/settings_tools.py:133` — calls `configuration.as_dict()` and applies its own `_is_secret()` heuristic which may miss secrets.

---

## 11. Rate Limits

### 11.1 Rate Limiters

| Limiter | File | Scope | Limit | Notes |
|---------|------|-------|-------|-------|
| `api_rate_limiter` | `core/rate_limiter.py` | Per {scope, client_ip} | 120 req / 60s | Sliding window |
| `auth_rate_limiter` | `core/rate_limiter.py` | Auth attempts | 10 req / 300s | Brute force protection |
| Pipeline RateLimitStage | `core/pipeline/stages/rate_limit.py` | Per profile | 30-120 req / min | Per transport |
| Desktop typing rate | `core/desktop/safety.py` | Keyboard | 30 char/sec | Hard limit |
| Desktop click rate | `core/desktop/safety.py` | Mouse click | 60 / min | Hard limit |
| Desktop screenshot rate | `core/desktop/safety.py` | Screenshot | 10 / min | Hard limit |

### 11.2 Reality Score

| Component | Score | Notes |
|-----------|-------|-------|
| API rate limiters | 8/10 | Sliding window, thread-safe, loopback exempt, tested |
| Pipeline rate limit stage | 8/10 | Per-profile, per-transport |
| Desktop rate limits | 8/10 | Hard limits on all input/output operations |

---

## 12. Emergency Stop

### 12.1 Existing Mechanisms

| Mechanism | Scope | How It Works | Status |
|-----------|-------|-------------|--------|
| `SafetyManager.emergency_stop()` | Desktop only | Sets `_emergency_stop=True` — blocks all desktop actions | Connected |
| PyAutoGUI FAILSAFE | Desktop only | Mouse to (0,0) → `FailSafeException` | Connected |
| Distribution worker shutdown | Workers only | Graceful `shutdown()` method | Connected |

### 12.2 Missing: Global Agent Kill Switch

There is **no mechanism** to stop ALL active agent activity:
- No global kill switch that halts LLM calls
- No watchdog process
- No SIGKILL/SIGTERM handler that gracefully shuts down tools
- No emergency button in the UI

If an agent enters a runaway loop (e.g., infinite tool calls), the only recourse is to kill the process.

---

## 13. Input Sanitization

### 13.1 Sanitization Layers

| Layer | File | What It Sanitizes | Status |
|-------|------|-------------------|--------|
| Privacy classifier | `core/privacy_classifier.py` | PII (emails, phones, credit cards, NER entities) | Connected — used before cloud LLM routing |
| LLM message sanitization | `core/llm_messages.py` | Unknown keys, orphan tool messages, unanswered calls | Connected — all messages |
| Prompt security | `core/prompt_security.py` | Untrusted content wrapper, special token stripping, homoglyph normalization | Connected — external content |
| Shell command parsing | `core/sandbox/sandbox.py:68` | Naive `cmd.split()` | **Weak** — no quote handling |

---

## 14. Self-Modification Safety

| File | What It Protects | Score |
|------|-----------------|-------|
| `core/self_modification/safety.py` | Pre/post checks, rollback, thresholds | 8/10 |
| `core/coding/refactor_safety.py` | Dependency graph, architecture validation, risk scoring | 8/10 |

These are well-designed safety layers for code self-modification. Not audited in depth as they are not directly in scope, but noted as strong.

---

## 15. Action Summary

### Priority 1: Critical (immediate)

| ID | Finding | File |
|----|---------|------|
| S-2 | Remove live secrets from `.env` or move to env vars only | `.env` |
| S-1 | Encrypt `~/.jarvis/api_keys.json` using Fernet from `secret_storage.py` | `core/api_key_vault.py` |
| S-3 | Remove `shell=True` from `DesktopController.launch_app()` | `core/desktop/controller.py:214` |
| S-5 | Remove password/TOTP leak from cookbook_tools output | `core/tools/cookbook_tools.py:1428/1431` |

### Priority 2: High

| ID | Finding | File |
|----|---------|------|
| S-6 | Fix `as_dict()` to mask secrets (like `as_api_dict()` does) | `core/configuration/service.py:287-295` |
| S-8 | Add sanitization + rate limiting to WebSocket terminal | `core/routes/terminal.py` |
| S-8 | Add command sanitization to persistent shell | `core/tools/persistent_shell.py` |
| S-9 | Encrypt `~/.jarvis/oauth_tokens.json` | `core/oauth.py` |
| S-10 | Add `chmod 0o600` to all secret file writes | Multiple files |

### Priority 3: Medium

| ID | Finding |
|----|---------|
|  | Add path containment to `file_agent.py` read/write operations |
|  | Add global kill switch (watchdog + SIGTERM handler) |
|  | Add circuit breaker pattern to provider execution |
|  | Add URL blocklist + navigation confirmation to browser manager |
|  | Fix sandbox `parse_command()` to handle quoted arguments |
|  | Add `*.pem`, `*.key`, `.app_key` to `.gitignore` |
|  | Remove `firebase-credentials.json` from repo root |

---

*End of Phase 8 — READ ONLY audit. No code was modified.*
