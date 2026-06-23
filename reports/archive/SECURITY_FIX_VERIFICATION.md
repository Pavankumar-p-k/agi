# Security Fix Verification

## Fix 1 — Remove `shell=True`

| Before | After | File | Line |
|--------|-------|------|------|
| `subprocess.Popen(["start", "chrome"], shell=True)` | `subprocess.Popen(["cmd", "/c", "start", "chrome"])` | `core/routes/websocket.py` | 692 |

**Verification:** `python -c "import py_compile; py_compile.compile('core/routes/websocket.py', doraise=True)"` — OK

## Fix 2 — Path confinement for `do_refactor`

**File:** `core/tools/execution.py` — line 1130

Added `_resolve_tool_path(str(fp))` after path resolution. If path is outside allowed roots, returns `{"error": "path blocked: ..."}` instead of proceeding.

## Fix 3 — Path confinement for `do_undo_edit_file`

**File:** `core/tools/execution.py` — line 1190

Added `_resolve_tool_path(str(path))` after `path.resolve()`. Returns `{"error": "path blocked: ..."}` on confinement failure.

## Fix 4 — Path confinement for `do_batch_edit_file`

**File:** `core/tools/execution.py` — line 1240

Added `_resolve_tool_path(str(fp))` for each glob match. Rejected paths are recorded with `"path blocked: ..."` error and `total_failed` incremented.

## Aggregate Verification

```
$ python -c "import py_compile; py_compile.compile('core/tools/execution.py', doraise=True); print('OK')"
OK
```

## Remaining surface

| Location | shell=True? | Path confined? | Notes |
|----------|-------------|----------------|-------|
| `core/tools/execution.py` — `do_edit_file` | N/A | ✅ existing | Uses `_resolve_tool_path` since prior implementation |
| `core/tools/execution.py` — `do_refactor` | N/A | ✅ now | Fixed above |
| `core/tools/execution.py` — `do_undo_edit_file` | N/A | ✅ now | Fixed above |
| `core/tools/execution.py` — `do_batch_edit_file` | N/A | ✅ now | Fixed above |
| `core/routes/websocket.py` — chrome launch | ❌ → ✅ | N/A | Fixed above |
| `run_production_audit.py` | ❌ | N/A | Audit script, not shipped |
