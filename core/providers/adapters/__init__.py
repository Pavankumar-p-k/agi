"""core.providers.adapters — capability providers as adapter classes.

Every adapter follows the ExecutionProvider contract (provider_id,
name, capabilities(), health(), execute()).

Note: the module-level singleton *instances* stay inside their own
submodules (e.g. ``core.providers.adapters.desktop_provider.desktop_provider``)
and are deliberately NOT re-exported here — a lowercase instance would
shadow the submodule of the same name and break source inspection.
"""
from core.providers.adapters.forge import ForgeProvider
from core.providers.adapters.claude_code import ClaudeCodeProvider
from core.providers.adapters.codex import CodexProvider
from core.providers.adapters.browser_provider import BrowserProvider
from core.providers.adapters.research_provider import ResearchProvider
from core.providers.adapters.automation_provider import AutomationProvider
from core.providers.adapters.messaging_provider import MessagingProvider
from core.providers.adapters.deployment_provider import DeploymentProvider
from core.providers.adapters.desktop_provider import DesktopProvider
from core.providers.adapters.workspace_provider import WorkspaceProvider

__all__ = [
    "ForgeProvider", "ClaudeCodeProvider", "CodexProvider",
    "BrowserProvider", "ResearchProvider", "AutomationProvider",
    "MessagingProvider", "DeploymentProvider",
    "DesktopProvider", "WorkspaceProvider",
]
