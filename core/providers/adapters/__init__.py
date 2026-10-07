"""
Module: core.providers.adapters.__init__
Provider adapters re-exports.

Every adapter present on disk is imported and re-exported; optional adapters
not yet rebuilt are reported as explicit import warnings instead of breaking
the whole package (loud, per-module, greppable — never silent).
"""
from __future__ import annotations

import importlib
import logging

logger = logging.getLogger(__name__)

# module name -> (class symbols the module must export,)
_REQUIRED: dict[str, tuple[str, ...]] = {
    "forge": ("ForgeProvider",),
    "claude_code": ("ClaudeCodeProvider",),
    "codex": ("CodexProvider",),
}

# Deleted in the de-poisoning pass; on the rebuild backlog. A missing one
# must not make the whole package un-importable — warn per module instead.
_OPTIONAL: dict[str, tuple[str, ...]] = {
    "browser_provider": ("BrowserProvider",),
    "research_provider": ("ResearchProvider",),
    "automation_provider": ("AutomationProvider",),
    "messaging_provider": ("MessagingProvider",),
    "deployment_provider": ("DeploymentProvider",),
}


def _bind(module_name: str, symbols: tuple[str, ...]) -> None:
    module = importlib.import_module(f"{__name__}.{module_name}")
    for symbol in symbols:
        globals()[symbol] = getattr(module, symbol)


for _mod, _syms in _REQUIRED.items():
    try:
        _bind(_mod, _syms)
    except Exception as exc:  # noqa: BLE001 — required: report precisely, then raise
        logger.error(
            "required adapter import failed: core.providers.adapters.%s: %s", _mod, exc
        )
        raise

for _mod, _syms in _OPTIONAL.items():
    try:
        _bind(_mod, _syms)
    except ModuleNotFoundError as exc:
        logger.warning(
            "adapter not rebuilt yet (backlog): core.providers.adapters.%s — %s", _mod, exc
        )
    except Exception as exc:  # noqa: BLE001 — present but broken: fail loudly
        logger.error(
            "optional adapter import failed: core.providers.adapters.%s: %s", _mod, exc
        )

__all__ = sorted(
    symbol
    for _map in (_REQUIRED, _OPTIONAL)
    for _syms in _map.values()
    for symbol in _syms
    if symbol in globals()
)
