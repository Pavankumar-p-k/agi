"""
Module: core.providers.adapters.__init__
Provider adapters re-exports.
"""
from __future__ import annotations
from typing import Any
import logging

logger = logging.getLogger(__name__)

from core.providers.adapters.forge import ForgeProvider
from core.providers.adapters.claude_code import ClaudeCodeProvider
from core.providers.adapters.codex import CodexProvider
from core.providers.adapters.browser_provider import BrowserProvider
from core.providers.adapters.research_provider import ResearchProvider
from core.providers.adapters.automation_provider import AutomationProvider
from core.providers.adapters.messaging_provider import MessagingProvider
from core.providers.adapters.deployment_provider import DeploymentProvider
