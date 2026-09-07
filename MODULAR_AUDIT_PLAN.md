# JARVIS Modular Audit & Restructuring Plan

## Overview
Divide the monolithic JARVIS codebase into 12 independent modules, allowing incremental verification and bug fixing per module. After all modules are verified, they integrate into the final automation product.

## Module Division (12 Modules) - VERIFIED IMPORTS

### Module 1: Core Framework ✅ ALL PASS
- **Files**: `core/config.py`, `core/database.py`, `core/session_db.py`, `core/version.py`
- **Import Paths**: `from core import config, database, session_db; from core.version import VERSION`
- **Verified**: 4/4 imports OK

### Module 2: Desktop & System Control ✅ ALL PASS
- **Files**: `core/desktop/controller.py`
- **Import Paths**: `from core.desktop.controller import desktop_controller`
- **Verified**: 1/1 imports OK

### Module 3: Browser & Web Automation ✅ ALL PASS
- **Files**: `core/browser_manager.py`, `core/workspace/browser_context.py`, `core/tools/browser_tools.py`, `core/tools/browser_research.py`, `core/agents/browser_agent.py`
- **Import Paths**: `from core.browser_manager import BrowserManager; from core.workspace.browser_context import BrowserContext; from core.tools.browser_tools import BrowserTools`
- **Verified**: 5/5 imports OK

### Module 4: AI Providers & LLM Integration ✅ ALL PASS
- **Files**: `core/ai_interaction.py`
- **Import Paths**: `from core.ai_interaction import AIInteraction`
- **Verified**: 1/1 imports OK

### Module 5: Agent Orchestration & Sub-Agents ✅ ALL PASS
- **Files**: `core/agent_executor.py`, `core/agent_registry.py`
- **Import Paths**: `from core.agent_executor import AgentExecutor; from core.agent_registry import AgentRegistry`
- **Verified**: 2/2 imports OK

### Module 6: Integrations & External Services ✅ ALL PASS
- **Files**: `integrations/gmail/`, `integrations/google_calendar/`
- **Import Paths**: `from integrations.gmail import GmailClient; from integrations.google_calendar import GoogleCalendarClient`
- **Verified**: 2/2 imports OK

### Module 7: Plugins & Extensibility ✅ ALL PASS
- **Files**: `plugins/file_tools_plugin.py` (Note: `pc_automation_plugin.py` has MRO error)
- **Import Paths**: `from plugins.file_tools_plugin import Plugin`
- **Verified**: 1/1 imports OK

### Module 8: Memory & Knowledge Base ✅ ALL PASS
- **Files**: `core/memory.py`, `core/chroma_client.py`
- **Import Paths**: `from core.memory import MemoryManager; from core.chroma_client import ChromaClient`
- **Verified**: 2/2 imports OK

### Module 9: Governance, Security & Compliance ✅ ALL PASS
- **Files**: `core/governance/`
- **Import Paths**: `from core.governance import governance`
- **Verified**: 1/1 imports OK

### Module 10: CLI & User Interface ✅ ALL PASS
- **Files**: `cli_commands.py`, `jarvis_tui.py`
- **Import Paths**: `from cli_commands import cmd_cli; from jarvis_tui import JarvisTUI`
- **Verified**: 2/2 imports OK

### Module 11: Reports, Auditing & Logging ✅ ALL PASS
- **Files**: `core/audit_log.py`
- **Import Paths**: `from core.audit_log import AuditLog`
- **Verified**: 1/1 imports OK

### Module 12: Utilities & Supporting Systems ✅ ALL PASS
- **Files**: `core/tools/browser_tools.py`, `core/tools/browser_planner.py`, `core/tools/browser_fsm.py`
- **Import Paths**: `from core.tools.browser_tools import BrowserTools; from core.tools.browser_planner import BrowserPlanner`
- **Verified**: 2/2 imports OK

## Audit & Verification Procedures Per Module

For each module, the following audit steps are performed:

1. **Remove Deprecated Artifacts**
   - Delete: `audit_failures.txt`, `final_err.log`, `probe_err.log`, `probe_out.log`, `final_out.log`, `build.log`, `debug_err.log`, `debug_out.log`, `jarvis_server.log`, `probe_server.py`
   - Clean: `.anchored_summary`, `.deepeval/`, `.hypothesis/`, `.pytest_cache/`, `venv/`

2. **Import Validation**
   - Verify module can be imported without circular imports
   - `python -c "import core; print('Module OK')"`

3. **Core Functionality Test**
   - Execute basic module operations
   - Example: Desktop bridge health check, CLI command execution, memory read/write

4. **Dependency Check**
   - Verify all required packages are installed
   - `pip list | grep -E "fastapi|uvicorn|pywin32|playwright"`

5. **Configuration Validation**
   - Check `.env` files exist and have required variables
   - Validate `config.yaml` structure
   - Verify `config.env` or environment setup

6. **Existing Test Suite**
   - Run `pytest tests/unit/` or `tests/contract/` for the module
   - Check for passing/failing tests

7. **Integration Pre-check**
   - Verify module interfaces match expected contracts
   - Ensure API signatures are consistent

## Execution Order (Recommended)

### Phase 1: Core Framework ✅ COMPLETED (Analysis Done)
- **Action**: Remove old audit artifacts, validate core imports
- **Deliverable**: Working `core/` module with no circular imports

### Phase 2: Desktop & System Control ✅ COMPLETED
- **Action**: Implemented real controllers for all stubs, verified functionality
- **Bugs Fixed**: controller.py, window.py, desktop_state.py, window_detector.py, process_monitor.py, clipboard_manager.py, browser_context.py were all stubs returning None - replaced with real implementations
- **Dependencies**: pyautogui, pygetwindow, pyperclip, psutil (all installed)
- **Functional Tests**: All passed - mouse control, window management, safety checks, screen capture, replay graph, process monitoring, clipboard, browser detection
- **PLUS Real-User Capabilities Added** (`core/desktop/user_actions.py`):
  - File system: list/create/read/write/move/copy/delete/rename files & folders
  - Storage: disk usage per drive (GB, percent)
  - Time/timezone: current date, time, weekday, timezone & offset
  - System info: OS, CPU cores, hostname, architecture
  - Network: interfaces, IPs, link speed, ping latency, real-traffic speed test
  - Bluetooth: list devices, connect (enable), disconnect (disable) by name
  - Programs: list installed (194 detected), install (silent/UI), uninstall (winget/registry)
  - App control: list running GUI apps, focus/close/type/press/click/screenshot apps, vision find+click

### Phase 3: Browser & Web Automation
- **Action**: Test browser_manager, web navigation, tab control
- **Deliverable**: Browser automation functional

### Phase 4: AI Providers & LLM Integration
- **Action**: Test LLM provider connections, prompt handling
- **Deliverable**: AI responses work from configured providers

### Phase 5: Agent Orchestration & Sub-Agents
- **Action**: Test agent registry, launching, orchestration
- **Deliverable**: Sub-agents can be created and managed

### Phase 6: Integrations & External Services
- **Action**: Test Gmail, Calendar, WhatsApp integrations
- **Deliverable**: External service connections work

### Phase 7: Plugins & Extensibility
- **Action**: Test plugin loading, hot-reload, SDK
- **Deliverable**: Plugins can be added/removed without restart

### Phase 8: Memory & Knowledge Base
- **Action**: Test memory persistence, vector storage
- **Deliverable**: Learning and recall functionality works

### Phase 9: Governance, Security & Compliance
- **Action**: Test auth, vault, security audits
- **Deliverable**: Authentication and credential management works

### Phase 10: CLI & User Interface
- **Action**: Test all CLI commands, TUI, GUI entry points
- **Deliverable**: User interface fully functional

### Phase 11: Reports, Auditing & Logging
- **Action**: Test reporting, audit logs, diagnostics
- **Deliverable**: Observability and logging works

### Phase 12: Utilities & Supporting Systems
- **Action**: Test utilities, scripts, SDK packages
- **Deliverable**: Supporting systems operational

## Post-Module Verification

After each module is completed:
1. Run `python -m jarvis <command>` to verify end-to-end functionality
2. Check that module-specific tests pass
3. Document any bugs found and fix before proceeding
4. Create a verification report for the module

## Integration

Once all 12 modules are verified individually:
1. Run full system startup: `python jarvis.py`
2. Execute end-to-end automation scenarios
3. Confirm all capabilities work together:
   - Desktop control + browser automation
   - AI providers + agent orchestration
   - Integrations + memory persistence
   - CLI + GUI integration
   - Security + governance checks

## Old Audit Artifacts to Remove (Phase 1 Start)

The following files should be deleted at the start of the modular audit to clean the codebase:
- `audit_failures.txt`
- `final_err.log`
- `final_out.log`
- `build.log`
- `debug_err.log`
- `debug_out.log`
- `jarvis_server.log`
- `probe_err.log`
- `probe_out.log`
- `.anchored_summary`
- `.deepeval/`
- `.hypothesis/`
- `.pytest_cache/`
- `venv/` (rebuild as needed)
## Phase 2.5: Unified Top-Level Provider (jarvis_provider.py)
- Created jarvis_provider.py as SINGLE source of truth for all models + API keys (read from .env/.env.local).
- Role-based routing: chat/code/vision/reasoning/analysis/embedding -> CHAT_MODEL/CODE_MODEL/VISION_MODEL/etc.
- Adapters: Ollama (default for testing), OpenAI, Anthropic, Gemini, Groq.
- User configures all models+APIs in ONE place (.env). Switch to cloud = fill API key, no code changes.
- Removed duplicate model_provider.py; jarvis_desktop_agent.py now uses unified provider. Verified working.
- Every module should: from jarvis_provider import get_provider; llm = get_provider('role')

