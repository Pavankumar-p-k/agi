# Root shim — canonical implementation: jarvis-export/cli/cli_completer.py
# Loaded under a private module name to avoid the circular self-import that a
# plain `from cli_completer import ...` inside a same-named shim would cause.
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_CANONICAL = Path(__file__).resolve().parent / "jarvis-export" / "cli" / "cli_completer.py"
_SPEC = importlib.util.spec_from_file_location("_jarvis_cli_completer", _CANONICAL)
assert _SPEC is not None and _SPEC.loader is not None
_canonical = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _canonical  # required before exec (dataclasses introspection)
_SPEC.loader.exec_module(_canonical)

JarvisCompleter = _canonical.JarvisCompleter
Completion = getattr(_canonical, "Completion", None)
if Completion is None:  # fallback: prompt_toolkit's Completion
    try:
        from prompt_toolkit.completion import Completion as _PTCompletion
        Completion = _PTCompletion
    except ImportError:  # pragma: no cover
        class Completion:  # type: ignore[no-redef]
            def __init__(self, text: str = "", start_position: int = 0, **kwargs) -> None:
                self.text = text
                self.start_position = start_position

__all__ = ["JarvisCompleter", "Completion"]
