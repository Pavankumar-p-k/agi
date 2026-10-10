# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Root shim for cli_config — loads the canonical implementation from
``jarvis-export/cli/cli_config.py`` under a private module name to avoid
the circular self-import a plain ``from cli_config import ...`` would cause.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_CANONICAL = Path(__file__).resolve().parent / "jarvis-export" / "cli" / "cli_config.py"
_SPEC = importlib.util.spec_from_file_location("_jarvis_cli_config", _CANONICAL)
assert _SPEC is not None and _SPEC.loader is not None
_canonical = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _canonical  # required before exec (dataclasses introspection)
_SPEC.loader.exec_module(_canonical)

JarvisConfig = _canonical.JarvisConfig
JARVIS_DIR = _canonical.JARVIS_DIR
CONFIG_PATH = _canonical.CONFIG_PATH

__all__ = ["JarvisConfig", "JARVIS_DIR", "CONFIG_PATH"]
