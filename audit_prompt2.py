#!/usr/bin/env python3
"""
PROMPT 2 - Copy this into any CLI tab to VERIFY a module after audit.
Runs full import test + basic instantiation check.
"""
import sys
from pathlib import Path

ROOT = Path("C:/Users/peter/Desktop/jarvis")
sys.path.insert(0, str(ROOT))

VERIFICATIONS = {
    1: [
        ("from core import config", "config.create_settings"),
        ("from core import database", "database.get_database"),
        ("from core.version import VERSION", "VERSION"),
    ],
    2: [
        ("from core.desktop.controller import desktop_controller", "desktop_controller"),
    ],
    3: [
        ("from core.browser_manager import BrowserManager", "BrowserManager"),
        ("from core.workspace.browser_context import BrowserContext", "BrowserContext"),
        ("from core.tools.browser_tools import BrowserTools", "BrowserTools"),
    ],
    4: [
        ("from core.ai_interaction import AIInteraction", "AIInteraction"),
    ],
    5: [
        ("from core.agent_executor import AgentExecutor", "AgentExecutor"),
        ("from core.agent_registry import AgentRegistry", "AgentRegistry"),
    ],
    6: [
        ("from integrations.gmail import GmailClient", "GmailClient"),
        ("from integrations.google_calendar import GoogleCalendarClient", "GoogleCalendarClient"),
    ],
    7: [
        ("from plugins.file_tools_plugin import Plugin", "Plugin"),
    ],
    8: [
        ("from core.memory import MemoryManager", "MemoryManager"),
        ("from core.chroma_client import ChromaClient", "ChromaClient"),
    ],
    9: [
        ("from core.governance import governance", "governance"),
    ],
    10: [
        ("from cli_commands import cmd_cli", "cmd_cli"),
        ("from jarvis_tui import JarvisTUI", "JarvisTUI"),
    ],
    11: [
        ("from core.audit_log import AuditLog", "AuditLog"),
    ],
    12: [
        ("from core.tools.browser_tools import BrowserTools", "BrowserTools"),
        ("from core.tools.browser_planner import BrowserPlanner", "BrowserPlanner"),
    ],
}

NAMES = {
    1: "Core Framework",
    2: "Desktop & System Control",
    3: "Browser & Web Automation",
    4: "AI Providers & LLM Integration",
    5: "Agent Orchestration & Sub-Agents",
    6: "Integrations (Gmail, Calendar)",
    7: "Plugins & Extensibility",
    8: "Memory & Knowledge Base",
    9: "Governance, Security & Compliance",
    10: "CLI & User Interface",
    11: "Reports, Auditing & Logging",
    12: "Utilities & Supporting Systems",
}

module = input("Enter module number to verify (1-12): ").strip()

if not module.isdigit() or int(module) not in VERIFICATIONS:
    print("Invalid module number")
    sys.exit(1)

mod_num = int(module)
mod_name = NAMES[mod_num]
checks = VERIFICATIONS[mod_num]

print(f"\n{'='*60}")
print(f"  VERIFYING: Module {mod_num} - {mod_name}")
print(f"{'='*60}\n")

passed = 0
failed = 0
for imp, attr in checks:
    try:
        ns = {}
        exec(imp, ns)
        print(f"  OK   {imp}")
        passed += 1
    except Exception as e:
        print(f"  FAIL {imp}")
        print(f"       -> {e}")
        failed += 1

print(f"\n{'='*60}")
print(f"  RESULT: {passed}/{len(checks)} checks passed")
if failed == 0:
    print(f"  Module {mod_num} ({mod_name}) VERIFIED OK")
else:
    print(f"  Module {mod_num} ({mod_name}) FAILED - {failed} import(s) broken")
print(f"{'='*60}")
