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

import logging
from typing import Any, Optional, Dict
from importlib import import_module


def _optional_import(module_path: str, symbol: str):
    try:
        module = import_module(module_path, package=__name__)
        return getattr(module, symbol)
    except (ImportError, AttributeError):
        return None


from .execution_context import BrainExecutionContext
from .reasoning_engine import ReasoningEngine
from .cognitive_patterns import PATTERNS
from .UnifiedBrain import UnifiedBrain

logger = logging.getLogger(__name__)
