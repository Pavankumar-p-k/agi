"""Browser AI specialist package.

Re-exports for the Browser AI specialist boundary.  This package reuses the
existing browser foundation (core/browser_manager.py, core/tools/browser_tools.py)
rather than creating a parallel architecture.
"""
from __future__ import annotations

from core.browser.browser_ai import BrowserAI, execute_workflow, get_browser_ai
from core.browser.page_security import (
    ApprovalDecision,
    ApprovalGate,
    classify_action,
    scan_page_text,
    wrap_page_payload,
)
from core.browser.procedural_memory import BrowserProceduralMemory, browser_procedural_memory
from core.browser.recovery import RecoveryContext, RecoveryEngine, RecoveryOutcome
from core.browser.verification import Check, VerificationOutcome, verify_outcome

__all__ = [
    "BrowserAI",
    "execute_workflow",
    "get_browser_ai",
    "ApprovalDecision",
    "ApprovalGate",
    "classify_action",
    "scan_page_text",
    "wrap_page_payload",
    "BrowserProceduralMemory",
    "browser_procedural_memory",
    "RecoveryContext",
    "RecoveryEngine",
    "RecoveryOutcome",
    "Check",
    "VerificationOutcome",
    "verify_outcome",
]
