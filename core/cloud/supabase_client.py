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

"""core.cloud.supabase_client — optional Supabase connection holder."""
from __future__ import annotations

import os
from typing import Any

# Module-level connection state (can be overridden/set directly in tests).
_connected: bool = False
_client: Any = None


def connect() -> Any:
    """Connect to Supabase if credentials exist; sets _connected/_client."""
    global _connected, _client
    if _client is not None:
        return _client
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        _connected = False
        return None
    try:
        from supabase import create_client

        _client = create_client(url, key)
        _connected = True
    except Exception:
        _connected = False
        _client = None
    return _client


def is_connected() -> bool:
    return _connected


def get_client() -> Any:
    return _client


def disconnect() -> None:
    global _connected, _client
    _connected = False
    _client = None


__all__ = ["connect", "is_connected", "get_client", "disconnect", "_connected", "_client"]
