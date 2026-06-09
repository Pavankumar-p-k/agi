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
# core/cloud/supabase_client.py
# Supabase client singleton — graceful no-op if env vars are missing.
from __future__ import annotations

import logging
import os

logger = logging.getLogger("jarvis.cloud.supabase")

_client = None
_connected: bool | None = None   # None = not yet checked


def get_client():
    """
    Return the Supabase client singleton.
    Returns None (with a warning) if credentials are not configured.
    """
    global _client
    if _client is not None:
        return _client

    url = os.getenv("SUPABASE_URL") or os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY")

    if not url or not key:
        logger.warning(
            "Supabase credentials not set (SUPABASE_URL / SUPABASE_KEY). "
            "Running in offline/SQLite-only mode."
        )
        return None

    try:
        from supabase import Client, create_client  # type: ignore
        _client = create_client(url, key)
        logger.info("Supabase client initialised (%s)", url)
        return _client
    except ImportError:
        logger.warning("supabase-py not installed. Run: pip install supabase>=2.0.0")
        return None
    except Exception as exc:
        logger.error("Supabase init failed: %s", exc)
        return None


def is_connected() -> bool:
    """
    Returns True if the Supabase client exists AND can reach the service.
    Caches the result for the lifetime of the process.
    """
    global _connected
    if _connected is not None:
        return _connected

    client = get_client()
    if client is None:
        _connected = False
        return False

    try:
        # Lightweight ping — list 1 row from a system table
        client.table("jarvis_memories").select("id").limit(1).execute()
        _connected = True
    except Exception as _e:
        logger.debug("supabase_client is_connected failed: %s", _e)
        _connected = False

    return _connected


def reset_connection_cache() -> None:
    """Force re-check on next is_connected() call (useful after network changes)."""
    global _connected, _client
    _connected = None
    _client    = None
