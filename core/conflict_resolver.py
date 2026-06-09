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
"""core/conflict_resolver.py
File-locking manager for parallel agent execution.
Prevents concurrent writes and detects conflicts between agents.
"""
import logging
import time
from threading import Lock

logger = logging.getLogger(__name__)

_DEFAULT_LOCK_TIMEOUT = 120


class LockTimeoutError(Exception):
    pass


class FileLockManager:
    def __init__(self, lock_timeout: int = _DEFAULT_LOCK_TIMEOUT):
        self._timeout = lock_timeout
        self._locks: dict[str, dict] = {}
        self._lock = Lock()

    def _normalize(self, file_path: str) -> str:
        import os
        return os.path.abspath(os.path.normpath(file_path))

    def acquire(self, agent_name: str, file_path: str) -> bool:
        normalized = self._normalize(file_path)
        now = time.time()
        with self._lock:
            existing = self._locks.get(normalized)
            if existing:
                if existing["agent"] == agent_name:
                    existing["acquired_at"] = now
                    return True
                if now - existing["acquired_at"] >= self._timeout:
                    logger.warning(f"[LOCKS] Auto-releasing lock on {normalized} from {existing['agent']} (timeout)")
                    del self._locks[normalized]
                else:
                    logger.info(f"[LOCKS] {agent_name} cannot acquire {normalized} — held by {existing['agent']}")
                    return False
            self._locks[normalized] = {"agent": agent_name, "acquired_at": now}
            logger.info(f"[LOCKS] {agent_name} acquired lock on {normalized}")
            return True

    def release(self, agent_name: str, file_path: str):
        normalized = self._normalize(file_path)
        with self._lock:
            existing = self._locks.get(normalized)
            if existing and existing["agent"] == agent_name:
                del self._locks[normalized]
                logger.info(f"[LOCKS] {agent_name} released lock on {normalized}")
            elif existing:
                logger.warning(f"[LOCKS] {agent_name} tried to release lock held by {existing['agent']} on {normalized}")

    def is_locked(self, file_path: str) -> str | None:
        normalized = self._normalize(file_path)
        now = time.time()
        with self._lock:
            existing = self._locks.get(normalized)
            if not existing:
                return None
            if now - existing["acquired_at"] >= self._timeout:
                logger.warning(f"[LOCKS] Auto-releasing stale lock on {normalized} from {existing['agent']}")
                del self._locks[normalized]
                return None
            return existing["agent"]

    def get_owner(self, file_path: str) -> str | None:
        return self.is_locked(file_path)

    def detect_conflicts(self, agent_name: str, file_path: str) -> str | None:
        owner = self.is_locked(file_path)
        if owner and owner != agent_name:
            logger.warning(f"[LOCKS] CONFLICT: {agent_name} wants {file_path} held by {owner}")
            return owner
        return None

    def release_all(self, agent_name: str = None):
        with self._lock:
            if agent_name:
                to_release = [fp for fp, info in self._locks.items() if info["agent"] == agent_name]
                for fp in to_release:
                    del self._locks[fp]
                if to_release:
                    logger.info(f"[LOCKS] Released all {len(to_release)} locks for {agent_name}")
            else:
                count = len(self._locks)
                self._locks.clear()
                logger.info(f"[LOCKS] Released all {count} locks")

    @property
    def active_locks(self) -> dict[str, dict]:
        now = time.time()
        with self._lock:
            stale = [fp for fp, info in self._locks.items() if now - info["acquired_at"] >= self._timeout]
            for fp in stale:
                logger.warning(f"[LOCKS] Cleaning stale lock on {fp} from {self._locks[fp]['agent']}")
                del self._locks[fp]
            return dict(self._locks)


lock_manager = FileLockManager()
