# JARVIS Release Remediation Plan

**Goal:** Fix all 14 blocking items and achieve **ALPHA READY** status.
**Target:** 3-5 days of focused engineering work.

---

## Quick-Win Patches (Day 1)

Apply the 5 pre-generated patches. Each takes <5 minutes.

| # | Patch | File | Verification |
|---|-------|------|-------------|
| 1 | `fixes/patches/C01-shell-tools-auth-bypass.patch` | `core/tools/security.py` | `git apply --check` |
| 2 | `fixes/patches/C02-edit-file-path-confinement.patch` | `core/tools/execution.py` | `git apply --check` |
| 3 | `fixes/patches/C04-ssrf-dns-rebinding.patch` | `core/ssrf.py` | `git apply --check` |
| 4 | `fixes/patches/C09-rate-limiter-logic.patch` | `core/main.py` | `git apply --check` |
| 5 | `fixes/patches/C10-api-call-owner.patch` | `core/tools/execution.py` | `git apply --check` |

**Total time:** ~15 minutes

---

## Day 1 — Critical Security Fixes

### 1.1 Fix SSRF loopback hostname gaps (C-05)

**File:** `core/ssrf.py`

Add to `resolve_and_check()`:
```python
import ipaddress

# Before DNS resolution, check if host is an IP literal
try:
    addr = ipaddress.ip_address(host)
    if addr.is_private or addr.is_loopback or addr.is_link_local:
        logger.warning("[SSRF] Blocked private/loopback IP %s", host)
        return False
except ValueError:
    pass  # Not an IP literal, resolve DNS

# Additional hostname checks
LOCAL_HOSTNAMES = frozenset({
    "localhost", "localhost.localdomain", "localhost6",
    "127.0.0.1", "0.0.0.0", "0",
    "127.1", "127.0.1.1",
})
# Reject bare decimals pointing to 127.0.0.1 (e.g. 2130706433)
try:
    packed = socket.inet_aton(host)
    if ipaddress.ip_address(packed).is_loopback:
        return False
except (OSError, ValueError):
    pass

# DNS rebinding mitigation: resolve twice, compare
try:
    addrs_first = set(
        sockaddr[0] for _, _, _, _, sockaddr in socket.getaddrinfo(host, None)
    )
    import time
    time.sleep(0.1)  # Force re-resolution
    addrs_second = set(
        sockaddr[0] for _, _, _, _, sockaddr in socket.getaddrinfo(host, None)
    )
    if addrs_first != addrs_second:
        logger.warning("[SSRF] DNS rebinding detected for %s", host)
        return False
except socket.gaierror:
    pass
```

### 1.2 Replace compile() with ast.parse() (C-06)

**File:** `core/tools/execution.py` line 935

```python
# Replace:
compile(new_text, str(path), "exec")
# With:
import ast
try:
    ast.parse(new_text, filename=str(path))
except SyntaxError as e:
    raise ValueError(f"Syntax error in generated code: {e}")
```

### 1.3 Replace pickle with JSON in face_recognition (C-07)

**File:** `vision/face_recognition.py`

Replace `pickle.loads`/`pickle.dumps` with:
```python
import json
import numpy as np

# Serialize
def _serialize_embeddings(embeddings: dict) -> str:
    serializable = {
        k: v.tolist() if isinstance(v, np.ndarray) else v
        for k, v in embeddings.items()
    }
    return json.dumps(serializable)

# Deserialize
def _deserialize_embeddings(data: str) -> dict:
    raw = json.loads(data)
    return {
        k: np.array(v) if isinstance(v, list) else v
        for k, v in raw.items()
    }
```

Remove the HMAC integrity check (not needed with JSON — no deserialization RCE vector).

### 1.4 Implement or remove #!bg (C-08)

**Option A (Implement — 2 hours):** Create `core/tools/bg_jobs.py`:

```python
"""Background job management for long-running bash commands."""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class BackgroundJob:
    id: str
    command: str
    start_time: float
    process: asyncio.subprocess.Process = None
    stdout: str = ""
    stderr: str = ""
    returncode: Optional[int] = None
    done: bool = False

_jobs: dict[str, BackgroundJob] = {}
_job_counter: int = 0

async def launch(command: str, cwd: str = None, env: dict = None) -> str:
    global _job_counter
    _job_counter += 1
    job_id = f"bg_{int(time.time())}_{_job_counter}"
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=env,
    )
    job = BackgroundJob(id=job_id, command=command, start_time=time.time(), process=proc)
    _jobs[job_id] = job
    asyncio.create_task(_watch_job(job_id))
    return job_id

async def _watch_job(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        return
    try:
        stdout, stderr = await job.process.communicate()
        job.stdout = stdout.decode() if stdout else ""
        job.stderr = stderr.decode() if stderr else ""
        job.returncode = job.process.returncode
    except Exception as e:
        logger.error(f"Background job {job_id} failed: {e}")
    finally:
        job.done = True

async def get_result(job_id: str) -> Optional[dict]:
    job = _jobs.get(job_id)
    if not job:
        return None
    if not job.done:
        return {"status": "running", "job_id": job_id}
    return {
        "status": "completed",
        "job_id": job_id,
        "stdout": job.stdout,
        "stderr": job.stderr,
        "returncode": job.returncode,
    }

def cleanup_old_jobs(max_age_seconds: int = 3600):
    now = time.time()
    stale = [jid for jid, j in _jobs.items() if now - j.start_time > max_age_seconds]
    for jid in stale:
        del _jobs[jid]
```

**Option B (Remove — 10 minutes):** Strip `#!bg` handling from `execution.py`.

---

## Day 2 — API Authentication & Security

### 2.1 Add auth to all unprotected routes

**Files:** All 38+ router modules in `core/routes/`, `api/`, `routers/`, `automation/`

**Strategy (lowest friction with minimal refactor):**

1. Create an `optional_auth` dependency:
```python
# core/auth.py
async def optional_auth(request: Request):
    """Authenticate if possible, but don't block. Sets request.state.user."""
    token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    if not token:
        request.state.user = None
        return
    user = verify_token_static(token)
    request.state.user = user

async def require_auth(request: Request):
    """Block unauthenticated requests."""
    await optional_auth(request)
    if request.state.user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
```

2. Add middleware instead of modifying every route:
```python
# core/middleware.py
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    PUBLIC_PATHS = {"/health", "/docs", "/openapi.json", "/redoc", "/static"}
    if request.url.path in PUBLIC_PATHS or request.url.path.startswith("/auth/"):
        return await call_next(request)
    token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    if not token:
        return JSONResponse(status_code=401, content={"error": "Authentication required"})
    user = verify_token_static(token)
    if user is None:
        return JSONResponse(status_code=401, content={"error": "Invalid token"})
    request.state.user = user
    return await call_next(request)
```

**Critical note:** This middleware approach is a "big hammer." Test that WebSocket routes (`/ws/*`) and SSE streams still work — they may need special handling.

### 2.2 Fix all 40+ silent except blocks

**Strategy (automated):**

Create and run a codemod script:

```python
"""fix_silent_excepts.py — Find and fix bare 'except: pass' blocks."""
import re
import os

SOURCE_DIRS = ["core", "memory", "ai_os", "api"]

def fix_file(filepath):
    with open(filepath) as f:
        content = f.read()
    
    # Pattern: except [ExceptionType]:\n        pass
    pattern = r'(except\s+(?:\w+(?:\s*,\s*\w+)*\s*)?:)\s*\n(\s+)pass\b'
    
    def replacement(m):
        header = m.group(1)
        indent = m.group(2)
        return f'{header}\n{indent}logger.warning("Unhandled exception in {os.path.basename(filepath)}", exc_info=True)'
    
    new_content = re.sub(pattern, replacement, content)
    if new_content != content:
        with open(filepath, 'w') as f:
            f.write(new_content)
        return True
    return False
```

**Manual triage required for ~10 blocks** where the fix needs specific context (e.g., `except:` that should catch specific exceptions, or where `logger` is not imported).

### 2.3 Fix CORS origin validation

**File:** `core/main.py` (or `core/config_schema.py`)

Add startup validation:
```python
@app.on_event("startup")
async def validate_cors():
    origins = jarvis_config.server.allowed_origins
    if "*" in origins:
        logger.warning("CORS allows all origins — insecure for production")
    if jarvis_config.server.allowed_origins and jarvis_config.server.allow_credentials:
        # When credentials are enabled, * is not valid
        if "*" in jarvis_config.server.allowed_origins:
            raise RuntimeError("CORS: Cannot use allow_origins=['*'] with allow_credentials=True")
```

---

## Day 3 — Documentation & Open Source

### 3.1 Fix README license mismatch

**File:** `README.md` line 368
```diff
- [MIT](LICENSE) — Free for personal and commercial use.
+ [Apache 2.0](LICENSE) — Free for personal and commercial use.
```

### 3.2 Add Apache-2.0 headers to all source files

**Automated script:**

```python
"""add_license_headers.py"""
import os
from pathlib import Path

HEADER = """# Copyright 2026 Pavankumar-p-k
# SPDX-License-Identifier: Apache-2.0

"""

SOURCE_DIRS = ["core", "memory", "ai_os", "api", "tools", "jarvis_os"]

for directory in SOURCE_DIRS:
    for py_file in Path(directory).rglob("*.py"):
        content = py_file.read_text()
        if "SPDX-License-Identifier" in content[:500]:
            continue
        # Skip __init__.py files (optional)
        if py_file.name == "__init__.py" and len(content.strip()) < 50:
            continue
        py_file.write_text(HEADER + content)
        print(f"Added header: {py_file}")
```

### 3.3 Fix CHANGELOG

Reconstruct from `git log`:
```bash
git log --oneline --reverse --format="## %s%n%n- %b%n" v0.1.0..HEAD > /tmp/changelog_draft.md
```

Then manually curate into `CHANGELOG.md` following Keep a Changelog format:

```markdown
# Changelog

## [1.1.0] - 2026-06-09
### Added
- [list features from commits]

### Changed
- [list changes]

### Fixed
- [list fixes]

## [1.0.0] - 2026-05-01
...
```

### 3.4 Add PR template

**File:** `.github/pull_request_template.md`
```markdown
## Description
<!-- Brief description of the change -->

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Refactor
- [ ] Documentation
- [ ] Security fix

## Testing
- [ ] Unit tests pass
- [ ] Manual testing completed

## Checklist
- [ ] No new silent `except:` blocks
- [ ] No `shell=True` usage
- [ ] Environment variables documented in `.env.example`
- [ ] License header present
```

### 3.5 Remove wrong copilot-instructions.md

```bash
git rm .github/copilot-instructions.md
```

### 3.6 Add .gitignore entries

```diff
+ .python-version
+ .envrc
+ *.so
+ .mypy_cache/
+ .ruff_cache/
```

---

## Day 4 — Architecture & Code Quality

### 4.1 Remove or implement AGI stubs (M-11)

**File:** `core/agi_core.py`

**Option A (Recommended — Remove stubs):**
```python
# Remove: _StubAttr class
# Remove: self.memory = _StubAttr(), self.reflector = _StubAttr(), etc.
# Replace with: self.memory = None, self.reflector = None, etc.
# In callers, add None-checks or fall through gracefully.
```

**Option B (Implement — deferred to v1.2):**
Replace each stub with a TODO reference to the roadmap.

### 4.2 Fix orphan CLI handlers

**File:** `cli_commands.py`

```python
# Either register them in jarvis.py build_parser():
p = subparsers.add_parser("autonomy", ...)
p.set_defaults(func=cmd_autonomy_passthrough)

# Or remove the dead functions entirely.
```

### 4.3 Add WAL mode to legacy SQLite

**File:** `core/database_models.py` line 24

```python
engine = create_engine(
    f"sqlite:///{DB_PATH.as_posix()}",
    echo=False,
    connect_args={
        "check_same_thread": False,
        "timeout": 30,
    },
)

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()
```

### 4.4 Add missing database indexes

```python
# In database_models.py or a migration:
Index("idx_scheduled_active", "scheduled_tasks.is_active"),
Index("idx_api_tokens_active", "api_tokens.is_active"),
Index("idx_gallery_owner", "gallery_images.owner"),
Index("idx_notes_owner", "agent_notes.owner"),
```

### 4.5 Fix duplicate memory writes

**File:** `memory/memory_facade.py`

```python
def store(self, text, user_id="default", metadata=None):
    tiered = self._tiered_memory
    if tiered is not None:
        tiered.remember(content, metadata=metadata or {})
        # Don't also call mem0.add() here — tiered_memory.remember() handles it
```

**File:** `memory/tiered_memory.py`

```python
def remember(self, content, importance=0.5, metadata=None):
    # Add to Hot tier only
    self.hot_tier.append({
        "content": content,
        "timestamp": time.time(),
        "metadata": metadata or {}
    })
    # Remove the mem0.add() call from here too
    # Memory consolidation to cold tier should be a separate async process
```

---

## Day 5 — Testing & Verification

### 5.1 Security verification

```bash
# 1. Apply all patches
git apply fixes/patches/*.patch

# 2. Run auth tests
pytest tests/ -k "auth or security or sso" -v

# 3. Verify unauthenticated routes return 401
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/settings
# Expected: 401

# 4. Verify public routes still work
curl -s http://localhost:8000/health
# Expected: 200

# 5. Verify rate limiter works
for i in $(seq 1 100); do curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/models; done
# Expected: 429 after limit reached
```

### 5.2 Functionality verification

```bash
# 1. CLI works
python jarvis.py doctor --json

# 2. Edit with path confinement
python jarvis.py agent run forge "edit ~/.ssh/authorized_keys to add a key"
# Expected: Rejected with "path is inside a sensitive directory"

# 3. Background jobs work (if implemented)
python jarvis.py cli
> #!bg echo hello

# 4. Memory deduplication
python jarvis.py agent run oraccle "remember that I like Python"
# Expected: Stored once, recalled once
```

### 5.3 Lint & type check

```bash
ruff check core/ memory/ ai_os/ --fix
mypy core/ memory/
```

### 5.4 Run test suite

```bash
pytest tests/ -x --timeout=60 -v 2>&1 | tail -50
```

---

## Rollback Plan

Each fix is independently revertible:

| Fix | Rollback |
|-----|----------|
| Security patches | `git checkout -- core/tools/security.py core/ssrf.py core/main.py core/tools/execution.py` |
| API auth | `git checkout -- core/middleware.py core/auth.py` |
| Documentation | `git checkout -- README.md CHANGELOG.md .github/` |
| SQLite WAL | `git checkout -- core/database_models.py` |
| Memory fix | `git checkout -- memory/memory_facade.py memory/tiered_memory.py` |

---

## Effort Summary

| Area | Estimated Effort | Dependencies |
|------|-----------------|--------------|
| 5 patch applications | 15 min | None |
| SSRF gaps | 30 min | None |
| compile() → ast.parse() | 10 min | None |
| pickle → JSON | 30 min | None |
| #!bg implement (A) | 2 hours | None |
| #!bg remove (B) | 10 min | None |
| API auth middleware | 3 hours | Requires testing all routes |
| Fix except blocks | 2 hours | Manual triage needed |
| CORS validation | 15 min | None |
| README fix | 5 min | None |
| License headers | 15 min | Git history |
| CHANGELOG | 1 hour | Git log |
| PR template | 15 min | None |
| Remove copilot-instructions | 1 min | None |
| AGI stubs | 30 min | None |
| Orphan CLI handlers | 15 min | None |
| SQLite WAL + indexes | 1 hour | Test migration |
| Memory dedup | 30 min | Test recall |
| Verification & testing | 3 hours | All fixes applied |

**Total: ~18-22 hours (3 days with focus, 5 days comfortable)**

---

## Alpha Ready Checklist

After completing all items above:

- [ ] All 10 critical security issues fixed
- [ ] Auth enforced on all API routes (except public endpoints)
- [ ] SSRF protection covers DNS rebinding + all loopback variants
- [ ] No `compile()` on model-controlled content
- [ ] No `pickle.loads()` on untrusted data
- [ ] `#!bg` either works or is removed
- [ ] Rate limiter works correctly
- [ ] Owner parameter passed to all handlers
- [ ] 0 silent `except: pass` blocks remaining
- [ ] README license matches LICENSE file
- [ ] All source files have Apache-2.0 headers
- [ ] CHANGELOG reflects v1.1.0
- [ ] No AGI stubs pretending to be features
- [ ] No orphan CLI handlers
- [ ] SQLite databases use WAL mode
- [ ] Memory storage is deduplicated
- [ ] All 5 patches applied and passing
