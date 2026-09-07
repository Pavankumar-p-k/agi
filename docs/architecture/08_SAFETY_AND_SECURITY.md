# Safety & Security Architecture Audit

**Generated:** 2026-07-28  
**Scope:** Full codebase audit — no fixes, reality score only

---

## Executive Summary

JARVIS implements a **layered defense-in-depth** model across 6 security domains:
1. **Tool Execution RBAC** (`core/tools/security.py`, `core/tools/execution/authorization.py`)
2. **Filesystem Guards** (`core/tools/execution/security.py`)
3. **Desktop Automation Safety** (`core/desktop/safety.py`, `core/desktop/controller.py`)
4. **Browser Automation Security** (`core/tools/browser_tools.py`, `core/ssrf.py`)
5. **API Key / Secrets Management** (`core/api_key_vault.py`, `core/prompt_security.py`)
6. **Runtime Governance** (`governance/MetaGovernor.py`, `governance/RuntimeGovernanceLayer.py`, `governance/GovernanceValidator.py`)

**Reality Score: 7.2/10** — Strong primitives, gaps in silent failure handling and dangerous path coverage.

---

## 1. Permissions & RBAC

### 1.1 Tool Authorization (`core/tools/security.py:39-62`)
```python
def is_authorized_to_execute(tool_name: str, ctx: AuthContext) -> bool:
    # 1. Admin bypass
    if ctx and Role.ADMIN in ctx.roles: return True
    # 2. Policy engine lookup
    policy = policy_engine.get_policy(tool_name)
    required_scope = policy.required_scope or Scope.TOOLS_EXECUTE_HIGH
    # 3. RBAC engine evaluation
    return authz_engine.evaluate(ctx, required_scope, resource=f"tool:{tool_name}")
```

**Findings:**
- ✅ RBAC with scopes: `TOOLS_EXECUTE_LOW` / `TOOLS_EXECUTE_HIGH`
- ✅ Admin escape hatch
- ✅ Legacy blocklist fallback (`NON_ADMIN_BLOCKED_TOOLS` — 36 tools)
- ⚠️ **Silent failure:** `is_public_blocked_tool()` returns `False` on any exception (line 86-87) — auth failures become "allowed"
- ⚠️ **No audit trail** on authorization decisions (only warning log on block)

### 1.2 Approval Flow (`core/tools/execution/authorization.py:27-47`)
```python
async def check_approval(tool: str, content: str) -> tuple[bool, str | None]:
    policy = policy_engine.get_policy(tool)
    if policy and policy.needs_confirmation:
        approval_id = uuid.uuid4().hex
        decision = await mcp_server.wait_for_approval(...)
        if decision == "deny": return False, result
```

**Findings:**
- ✅ MCP Bridge human-in-the-loop for high-risk tools
- ✅ UUID tracking per approval
- ⚠️ **No timeout** on `wait_for_approval()` — can block indefinitely
- ⚠️ **No fallback** if MCP server unavailable (tool silently fails/blocks)

### 1.3 Path Authorization (`core/tools/execution/security.py:76-99`)
```python
def _resolve_tool_path(raw_path: str) -> str:
    expanded = os.path.expanduser(str(raw_path).strip())
    resolved = os.path.realpath(expanded)
    if _is_sensitive_path(resolved): raise ValueError(...)
    for root in _tool_path_roots():
        if common == root: return resolved
    raise ValueError(f"path '{raw_path}' is outside the allowed roots")
```

**Allowed Roots:** `DATA_DIR`, `/tmp`, `$TMPDIR`, configured `tool_path_extra_roots`

**Findings:**
- ✅ Symlink resolution via `realpath()`
- ✅ Sensitive path blocklist: `.ssh`, `.gnupg`, `.env`, `authorized_keys`, `id_rsa*`
- ✅ Path traversal prevention via `commonpath` check
- ⚠️ **Windows gap:** No handling of UNC paths, junction points, or drive-letter case sensitivity
- ⚠️ **Race condition:** TOCTOU between check and actual file operation
- ⚠️ **Silent failure:** Exceptions in `_tool_path_roots()` caught and logged at DEBUG only (line 58-59)

---

## 2. Confirmation Gates

### 2.1 Routing Safety Classification (`core/routing/safety.py:55-95`)
```python
def classify_tool(tool: str, args: str) -> SafetyLevel:
    # DANGEROUS patterns (require explicit override)
    # CONFIRM patterns (require user approval)
    # SAFE patterns (auto-execute)
```

**Dangerous Shell Patterns (18):**
```
rm -rf /, rm -rf ~, format, mkfs, dd if=, fork bomb,
chmod -R 000, > /dev/sda, shutdown, reboot, kill -9 1
```

**Confirm Shell Patterns (18):**
```
git reset --hard, git push --force, rm, kill, docker rm/rmi/prune,
pip uninstall, drop table, delete from
```

**Findings:**
- ✅ Three-tier classification: SAFE / CONFIRM / DANGEROUS
- ✅ Pattern matching on raw args string
- ⚠️ **Partial string match** — `"echo rm -rf /"` triggers DANGEROUS (false positive)
- ⚠️ **No context awareness** — `rm -rf /tmp/build` treated same as `rm -rf /`
- ⚠️ **Windows gaps:** No `del /s /f`, `rd /s`, `Remove-Item -Recurse -Force`
- ⚠️ **Missing patterns:** `chmod 777`, `chown root`, `mount`, `umount`, `systemctl`, `reg add/delete`, PowerShell execution bypass

### 2.2 Desktop Safety (`core/desktop/safety.py:121-179`)
```python
def check(self, action_type: DesktopActionType, details: dict) -> SafetyDecision:
    # Gate 1: Emergency stop
    if self._emergency_stop: return SafetyDecision(allowed=False, ...)
    # Gate 2: Cooldown (50ms min)
    # Gate 3: Forbidden screen regions
    # Gate 4: Mouse speed limit (2000 px/s)
    # Gate 5: Typing rate limit (30 char/s, 500 char max)
    # Gate 6: Screenshot rate (10/min)
    # Gate 7: Click rate (60/min)
```

**Findings:**
- ✅ Emergency stop killswitch
- ✅ Rate limits on all input actions
- ✅ Forbidden screen regions (configurable)
- ✅ Mouse velocity limiting
- ⚠️ **No confirmation prompt** — only programmatic allow/deny
- ⚠️ **No user-visible indication** when action blocked (silent drop)
- ⚠️ **Forbidden regions** not persisted across restarts

---

## 3. Desktop Safety

### 3.1 Controller (`core/desktop/controller.py:64-281`)
```python
def click(self, x: int, y: int, button: str = "left") -> DesktopAction:
    decision = self._safety.check(DesktopActionType.MOUSE_CLICK, {"x": x, "y": y})
    if not decision.allowed: return self._reject(...)
    self._get_pyautogui().click(x, y, button=button)
```

**Findings:**
- ✅ PyAutoGUI FAILSAFE enabled (line 40) — corner escape
- ✅ All actions routed through SafetyManager
- ✅ Replay logging for audit trail
- ✅ EventBus emission for observability
- ⚠️ **No sandbox/container isolation** — runs on host desktop
- ⚠️ **No application allowlist** — `launch_app()` uses `shutil.which()` + hardcoded map (line 248-256)
- ⚠️ **`subprocess.Popen([exe])` with `shell=False`** (good) but no path validation on `exe`
- ⚠️ **No screen capture permission check** — `screen_capture` action only rate-limited

### 3.2 Dangerous Desktop Paths

| Path | Risk | Mitigation |
|------|------|------------|
| `launch_app("cmd.exe")` → arbitrary command | HIGH | No validation on app_name |
| `hotkey("win", "r")` → Run dialog | HIGH | No forbidden hotkey list |
| `type_text("malicious_script")` | MEDIUM | Rate limit only |
| `screen_capture` on password field | MEDIUM | No content awareness |

---

## 4. Browser Safety

### 4.1 Navigation Guards (`core/tools/browser_tools.py:13-23`)
```python
DANGEROUS_SCHEMES = ("file://", "chrome://", "edge://", "about:", "javascript:", "data:")

def _validate_url(url: str, is_admin: bool = False) -> str:
    if not url.startswith(("http://", "https://")):
        if not is_admin and any(url.lower().startswith(s) for s in DANGEROUS_SCHEMES):
            raise PermissionError(...)
```

**Findings:**
- ✅ Scheme allowlist (http/https only for non-admin)
- ✅ Admin bypass for internal schemes
- ⚠️ **Auto-prepends `https://`** — `"localhost:8080"` → `"https://localhost:8080"` (breaks local dev)
- ⚠️ **No hostname validation** — can navigate to internal IPs if DNS resolves

### 4.2 SSRF Protection (`core/ssrf.py:106-163`)
```python
def resolve_and_check(url: str) -> bool:
    # 1. Scheme check
    # 2. Known localhost hostnames
    # 3. IP literal check (private/loopback/link-local)
    # 4. Decimal IP check (2130706433 = 127.0.0.1)
    # 5. DNS resolution x2 with rebinding detection
    # 6. All resolved IPs checked against private ranges
    # 7. Optional redirect chain validation
```

**Findings:**
- ✅ Multi-layer IP blocking (literal, resolved, decimal)
- ✅ DNS rebinding detection (double resolution + comparison)
- ✅ IPv4/IPv6 private range coverage
- ✅ Redirect chain following with re-validation
- ⚠️ **TOCTOU:** DNS checked at validation time, not at fetch time
- ⚠️ **No IPv6 zone ID handling** (e.g., `fe80::1%eth0`)
- ⚠️ **`_check_redirect_chain()` uses `httpx.Client` synchronously** in async context (blocks event loop)
- ⚠️ **No protection** against `http://169.254.169.254` (AWS metadata) if DNS resolves to public IP first

### 4.3 Browser Evaluate (`core/tools/browser_tools.py:525-534`)
```python
async def do_browser_evaluate(js: str, session_id: str = None) -> dict:
    result = await page.evaluate(js)  # ARBITRARY JS EXECUTION
```

**Findings:**
- ⚠️ **CRITICAL:** `browser_evaluate` allows arbitrary JavaScript in browser context
- ⚠️ Only gated by RBAC (`_ADMIN_TOOLS` includes `browser_evaluate` at line 66)
- ⚠️ No sandbox, no CSP, no script allowlist
- ⚠️ Can access `localStorage`, `cookies`, `fetch()`, `WebSocket`, `localStorage`

---

## 5. Filesystem Safety

### 5.1 Path Resolution (Recap)
- Allowed roots: `~/.jarvis/data`, `/tmp`, `$TMPDIR`, config extras
- Blocked: `.ssh`, `.gnupg`, `.env`, `authorized_keys`, `id_rsa*`, `id_ed25519`, `known_hosts`

### 5.2 Tool Coverage
| Tool | Path Validation |
|------|-----------------|
| `read_file` | ✅ via `_resolve_tool_path` |
| `write_file` | ✅ via `_resolve_tool_path` |
| `edit_file` | ✅ via `_resolve_tool_path` |
| `list_folder` | ✅ via `_resolve_tool_path` |
| `watch_file` | ✅ via `_resolve_tool_path` |
| `bash`/`shell` | ❌ **NO PATH VALIDATION** — raw command execution |

**Findings:**
- ⚠️ **Shell tools bypass filesystem guards entirely**
- ⚠️ `bash "cat /etc/passwd"` — no interception
- ⚠️ `shell "rm -rf ~"` — only caught by routing safety pattern match (string-based)
- ⚠️ Persistent shell (`core/tools/persistent_shell.py`) preserves cwd — `cd /etc && cat passwd` works

---

## 6. API Keys & Secrets

### 6.1 Vault (`core/api_key_vault.py:28-143`)
```python
class APIKeyVault:
    VAULT_PATH = Path.home() / ".jarvis" / "api_keys.json"
    USAGE_PATH = Path.home() / ".jarvis" / "key_usage.json"
    
    def get(self, service: str) -> str | None:
        keys = self._keys.get(service, [])
        if not keys:
            return os.getenv(f"{service.upper()}_API_KEY") or os.getenv(service.upper())
        # rotation logic...
```

**Findings:**
- ✅ Encrypted-at-rest: **NO** — plaintext JSON
- ✅ File permissions: **NO** — default umask
- ✅ Rotation on 429: **YES** (line 90-93)
- ✅ Usage tracking: **YES** (persisted)
- ⚠️ **Plaintext storage** — no encryption at rest
- ⚠️ **No key derivation** — keys stored raw
- ⚠️ **Env var fallback** reads all `*_API_KEY` — leaks in process list
- ⚠️ **No HSM/KMS integration**

### 6.2 Prompt Security (`core/prompt_security.py:19-62`)
```python
FORBIDDEN_TOKENS = ["<|endoftext|>", "<|endofprompt|>", "