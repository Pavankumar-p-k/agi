# Plan: Replace in-house TUI with tuillem

## Phase 1: Fix server startup

### File: `cli_server.py`

**Problem**: Server starting in a new console window (`CREATE_NEW_CONSOLE`) hides crash errors. If uvicorn fails to import something, the console flashes and disappears, and `wait_for_server` times out.

**Changes to `ensure_server_running`**:

1. Replace `spawn_background("JARVIS-Server", ...)` with `subprocess.Popen` that captures stdout+stderr to `logs/server.log`
2. Call `stop_local_services(include_ollama=False)` before `free_port(port)` to kill any lingering `core.main:app` process
3. Add `PYTHONUNBUFFERED=1` to env
4. On failure, print the log path so user can see the actual error

**Code** (replace the function body starting at line 87):

```python
def ensure_server_running(base_url: str, host: str = "127.0.0.1", port: int = 8000):
    target_host, target_port = parse_server_location(base_url)
    if target_host not in {"127.0.0.1", "localhost"}:
        return
    stop_local_services(include_ollama=False)
    free_port(target_port)
    if is_server_reachable(base_url, timeout=0.5):
        return
    print("JARVIS backend is not running. Starting local server...")
    env = common_env()
    env["PYTHONUNBUFFERED"] = "1"
    log_dir = ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "server.log"
    cmd = backend_server_cmd(target_host or host, target_port or port, False)
    subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env=env,
        stdout=open(log_path, "w"),
        stderr=subprocess.STDOUT,
    )
    if wait_for_server(base_url):
        print(f"JARVIS backend ready at {base_url}")
        return
    print(f"JARVIS backend did not become ready at {base_url}")
    print(f"  Server log: {log_path}")
    sys.exit(1)
```

### File: `cli_server.py` — `stop_local_services`

Make it more robust: use `wmic` or `taskkill` on Windows as a fallback if the CIM query fails.

## Phase 2: Download and configure tuillem

### Step 2a: Download Windows binary

```powershell
# In the project root
mkdir -Force ~\.local\bin
curl.exe -sL "https://github.com/seesee/tuillem/releases/download/v0.1.4/tuillem-x86_64-pc-windows-msvc.zip" -o tuillem.zip
Expand-Archive -Path tuillem.zip -DestinationPath ~\.local\bin\ -Force
Remove-Item tuillem.zip
# Verify
~\.local\bin\tuillem.exe --help
```

### Step 2b: Create config file

Path: `%APPDATA%\com.tuillem.tuillem\config.yaml`

```yaml
providers:
  - name: jarvis
    provider_type: openai
    api_key: "not-needed"
    base_url: http://127.0.0.1:8000/v1
    default_model: jarvis-reasoning
    models:
      - jarvis-reasoning

defaults:
  provider: jarvis
  model: jarvis-reasoning

ui:
  sidebar_width: 35
  show_thinking: false
  show_token_usage: true
  mouse: true
```

## Phase 3: Rewrite `cmd_tui`

### File: `cli_commands.py`

Replace the current `cmd_tui` function (lines 218-239) with:

```python
def cmd_tui(args: argparse.Namespace) -> int:
    from core.session import ConversationManager, get_last_session_id
    env = common_env()
    base_url = env.get("JARVIS_SERVER", "http://127.0.0.1:8000")
    ensure_local_stack_running(env)
    tuillem = shutil.which("tuillem")
    if not tuillem:
        tuillem = str(Path.home() / ".local" / "bin" / "tuillem.exe")
        if not os.path.exists(tuillem):
            print("tuillem not found. Install from https://github.com/seesee/tuillem/releases")
            return 1
    print("Launching tuillem chat client...")
    os.execv(tuillem, [tuillem])
    return 0
```

Note: `os.execv` replaces the current process with tuillem, so the JARVIS server stays running in the background. On Windows, `os.execv` has limitations — may need `subprocess.run` instead.

Alternative (more portable):

```python
import subprocess
proc = subprocess.Popen([tuillem])
proc.wait()
return proc.returncode
```

### File: `cli_tui/` — leave in place (don't delete), just stop importing it

## Phase 4: Add OpenRouter provider (bonus)

tuillem supports multiple providers. We can add OpenRouter as a second provider for when the user wants cloud models:

```yaml
  - name: openrouter
    provider_type: openrouter
    api_key: "${OPENROUTER_API_KEY}"
    default_model: anthropic/claude-sonnet-4-20250514
    models:
      - anthropic/claude-sonnet-4-20250514
      - google/gemini-2.5-pro-exp-03-25
      - openai/gpt-4o
```

## Verification

1. Run `uv run jarvis tui`
2. Server should start and log to `logs/server.log`
3. tuillem should launch with 3-pane UI
4. Type a message — should hit JARVIS `POST /v1/chat/completions`
5. Response should render with markdown, syntax highlighting
6. `Ctrl+L` toggles sidebar with conversation history
7. `Ctrl+K` opens command palette
8. `Ctrl+S` opens settings panel
