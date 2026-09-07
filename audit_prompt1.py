#!/usr/bin/env python3
"""
PROMPT 1 - Copy this into any CLI tab to audit ONE module.
All import paths are verified and working.
"""
import sys
from pathlib import Path

ROOT = Path("C:/Users/peter/Desktop/jarvis")
sys.path.insert(0, str(ROOT))

MODULES = {
    1: {
        "name": "Core Framework",
        "imports": [
            "from core import config",
            "from core import database",
            "from core import session_db",
            "from core.version import VERSION",
        ],
    },
    2: {
        "name": "Desktop & System Control",
        "imports": [
            "from core.desktop.controller import desktop_controller",
        ],
    },
    3: {
        "name": "Browser & Web Automation",
        "imports": [
            "from core.browser_manager import BrowserManager",
            "from core.workspace.browser_context import BrowserContext",
            "from core.tools.browser_tools import BrowserTools",
            "from core.tools.browser_research import BrowserResearch",
            "from core.agents.browser_agent import BrowserAgent",
        ],
    },
    4: {
        "name": "AI Providers & LLM Integration",
        "imports": [
            "from core.ai_interaction import AIInteraction",
        ],
    },
    5: {
        "name": "Agent Orchestration & Sub-Agents",
        "imports": [
            "from core.agent_executor import AgentExecutor",
            "from core.agent_registry import AgentRegistry",
        ],
    },
    6: {
        "name": "Integrations (Gmail, Calendar)",
        "imports": [
            "from integrations.gmail import GmailClient",
            "from integrations.google_calendar import GoogleCalendarClient",
        ],
    },
    7: {
        "name": "Plugins & Extensibility",
        "imports": [
            "from plugins.file_tools_plugin import Plugin",
        ],
    },
    8: {
        "name": "Memory & Knowledge Base",
        "imports": [
            "from core.memory import MemoryManager",
            "from core.chroma_client import ChromaClient",
        ],
    },
    9: {
        "name": "Governance, Security & Compliance",
        "imports": [
            "from core.governance import governance",
        ],
    },
    10: {
        "name": "CLI & User Interface",
        "imports": [
            "from cli_commands import cmd_cli",
            "from jarvis_tui import JarvisTUI",
        ],
    },
    11: {
        "name": "Reports, Auditing & Logging",
        "imports": [
            "from core.audit_log import AuditLog",
        ],
    },
    12: {
        "name": "Utilities & Supporting Systems",
        "imports": [
            "from core.tools.browser_tools import BrowserTools",
            "from core.tools.browser_planner import BrowserPlanner",
            "from core.tools.browser_fsm import BrowserFSM",
        ],
    },
}

print("=" * 60)
print("  JARVIS Modular Audit - SINGLE MODULE Mode")
print("=" * 60)
for k, v in MODULES.items():
    print(f"  {k:2d}. {v['name']}")

print()
choice = input("Enter module number (1-12): ").strip()

if not choice.isdigit() or int(choice) not in MODULES:
    print("Invalid module number")
    sys.exit(1)

mod_num = int(choice)
mod = MODULES[mod_num]

print(f"\n{'='*60}")
print(f"  AUDITING: Module {mod_num} - {mod['name']}")
print(f"{'='*60}\n")

passed = 0
failed = 0
for imp in mod["imports"]:
    try:
        exec(imp)
        print(f"  OK   {imp}")
        passed += 1
    except Exception as e:
        print(f"  FAIL {imp}")
        print(f"       -> {e}")
        failed += 1

print(f"\n{'='*60}")
print(f"  RESULT: {passed} passed, {failed} failed")
if failed == 0:
    print(f"  Module {mod_num} ({mod['name']}) PASSED audit")
else:
    print(f"  Module {mod_num} ({mod['name']}) FAILED audit - fix imports above")
print(f"{'='*60}")
