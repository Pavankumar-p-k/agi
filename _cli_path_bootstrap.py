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

"""Root-level shims re-exporting the reference CLI implementation.

The canonical CLI modules live in ``jarvis-export/cli/``; tests and integrations
import them as top-level ``cli_*`` packages. These shims make that work without
duplicating the implementation.
"""
from __future__ import annotations

import sys

_CLI_DIR = __import__("pathlib").Path(__file__).resolve().parent / "jarvis-export" / "cli"

if str(_CLI_DIR) not in sys.path:
    sys.path.insert(0, str(_CLI_DIR))
