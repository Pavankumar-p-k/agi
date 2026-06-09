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
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("jarvis.session")

SESSION_DIR = Path.home() / ".jarvis" / "sessions"
LAST_SESSION_FILE = Path.home() / ".jarvis" / "last_session"
BASE_DIR = Path(__file__).resolve().parents[1]


def _ensure_dir():
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    LAST_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)


_ensure_dir()

# ── ConversationManager (original JARVIS session system) ──


class ConversationManager:
    """Persistent message-based session with token tracking, stash, and lifecycle."""

    def __init__(self, session_id: str | None = None, name: str = ""):
        self.session_id = session_id or datetime.now().strftime("sess_%Y%m%d_%H%M%S")
        self.created_at = datetime.now().isoformat()
        self.name = name
        self.messages: list[dict] = []
        self.stash: list[dict] = []
        self.token_count = 2  # base overhead
        self._dirty = False

    @property
    def path(self) -> Path:
        return SESSION_DIR / f"{self.session_id}.json"

    @property
    def message_count(self) -> int:
        return len(self.messages)

    # ── Message management ──

    def add_message(self, role: str, content: str, **kwargs) -> dict:
        msg = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            **kwargs,
        }
        self.messages.append(msg)
        self.token_count += len(content.split()) + 3
        self._dirty = True
        return msg

    def get_context(self, last_n: int | None = None) -> list[dict]:
        msgs = self.messages[-last_n:] if last_n else self.messages[:]
        return [{"role": m["role"], "content": m["content"]} for m in msgs]

    # ── Persistence ──

    def save(self):
        data = {
            "session_id": self.session_id,
            "name": self.name,
            "messages": self.messages,
            "stash": self.stash,
            "tasks": self.tasks,
            "token_count": self.token_count,
        }
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        LAST_SESSION_FILE.write_text(self.session_id, encoding="utf-8")
        self._dirty = False

    def load(self):
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.session_id = data.get("session_id", self.session_id)
        self.name = data.get("name", "")
        self.messages = data.get("messages", [])
        self.stash = data.get("stash", [])
        self.tasks = data.get("tasks", {})
        self.token_count = data.get("token_count", 2)
        self._dirty = False

    def update_task(self, task_id: str, status: str, result: Any = None):
        self.tasks[task_id] = {
            "status": status,
            "result": result,
            "updated_at": datetime.now().isoformat()
        }
        self._dirty = True

    def delete(self):
        if self.path.exists():
            self.path.unlink()

    def clear(self):
        self.messages.clear()
        self.token_count = 2
        self._dirty = True

    def to_descriptor(self) -> dict:
        return {
            "session_key": self.session_id,
            "type": "conversation",
            "label": self.name or self.session_id,
            "message_count": self.message_count,
            "updated_at": self.messages[-1]["timestamp"] if self.messages else "",
            "last_message": self.messages[-1]["content"][:200] if self.messages else "",
        }

    # ── Lifecycle ──

    def fork(self) -> ConversationManager:
        new = ConversationManager(session_id=f"fork_{uuid.uuid4().hex[:8]}")
        new.messages = [dict(m) for m in self.messages]
        new.token_count = self.token_count
        return new

    def compact(self, keep_last: int = 10):
        if len(self.messages) > keep_last:
            self.messages = self.messages[-keep_last:]
            self.token_count = sum(len(m["content"].split()) + 3 for m in self.messages) + 2
            self._dirty = True

    def rename(self, name: str):
        self.name = name
        self._dirty = True
        self.save()

    def export_transcript(self, output_dir: Path | None = None) -> str:
        out = output_dir or SESSION_DIR
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{self.session_id}_transcript.txt"
        lines = []
        for m in self.messages:
            lines.append(f"[{m['role']}] {m['content']}")
        path.write_text("\n\n".join(lines), encoding="utf-8")
        return str(path)

    # ── Stash ──

    def stash_prompt(self, text: str, label: str = "") -> int:
        idx = len(self.stash) + 1
        self.stash.append({"id": idx, "text": text, "label": label or f"stash_{idx}"})
        return idx

    def list_stash(self) -> list[dict]:
        return list(self.stash)

    def load_stash(self, idx: int) -> str:
        for item in self.stash:
            if item["id"] == idx:
                return item["text"]
        return ""

    def __repr__(self):
        return f"ConversationManager(session_id={self.session_id}, msgs={self.message_count})"


def get_last_session_id() -> str | None:
    if LAST_SESSION_FILE.exists():
        return LAST_SESSION_FILE.read_text(encoding="utf-8").strip()
    return None


def list_sessions() -> list[str]:
    if not SESSION_DIR.exists():
        return []
    files = sorted(SESSION_DIR.glob("*.json"), key=os.path.getmtime, reverse=True)
    return [f.stem for f in files]


# ── Hierarchical Session System (for sub-agent / plugin scoping) ──


class SessionKey:
    """Hierarchical session key: type:id[:suffix]
    e.g. user:pavan, agent:nexus:research_123, thread:main:456
    """

    def __init__(self, key: str):
        self.raw = key
        parts = key.split(":")
        self.type = parts[0]
        self.id = parts[1] if len(parts) > 1 else "default"
        self.suffix = parts[2] if len(parts) > 2 else None

    def __str__(self) -> str:
        return self.raw

    @property
    def parent(self) -> str | None:
        if ":" not in self.raw:
            return None
        return self.raw.rsplit(":", 1)[0]

    @property
    def spawn_depth(self) -> int:
        """Parse depth from key: agent:nexus:subagent:{uuid} → count colons - 1"""
        return max(0, self.raw.count(":") - 1)


class HierarchicalSession:
    """Scoped session with parent inheritance for data lookups."""

    def __init__(self, key: str, parent_id: str | None = None):
        self.key = SessionKey(key)
        self.parent_id = parent_id
        self.data: dict[str, Any] = {}
        self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at

    @property
    def spawned_by(self) -> str | None:
        return self.data.get("spawned_by")

    @spawned_by.setter
    def spawned_by(self, value: str):
        self.data["spawned_by"] = value

    def get(self, name: str, default: Any = None) -> Any:
        if name in self.data:
            return self.data[name]
        if self.parent_id:
            parent = session_manager.get_session(self.parent_id)
            if parent:
                return parent.get(name, default)
        return default

    def set(self, name: str, value: Any):
        self.data[name] = value
        self.updated_at = datetime.now().isoformat()


class SessionManager:
    """Global registry for hierarchical sessions."""

    def __init__(self):
        self._active: dict[str, HierarchicalSession] = {}

    def create_session(self, key: str, parent_id: str | None = None) -> HierarchicalSession:
        session = HierarchicalSession(key, parent_id)
        self._active[str(session.key)] = session
        return session

    def get_session(self, key: str) -> HierarchicalSession | None:
        return self._active.get(key)

    def list_conversations(self, limit: int = 50, search: str = "") -> list[dict]:
        """Return all sessions as conversation descriptors."""
        results = []
        for key, session in self._active.items():
            if search and search.lower() not in key.lower():
                continue

            results.append({
                "session_key": key,
                "type": session.key.type,
                "label": session.data.get("name", key),
                "message_count": len(getattr(session, 'messages', [])),
                "updated_at": session.updated_at,
            })
            if len(results) >= limit:
                break
        return results

    def fork_session(self, key: str, parent_key: str) -> HierarchicalSession:
        """Fork a child session with parent linkage."""
        parent = self.get_session(parent_key)
        child = self.create_session(key, parent_id=parent_key)
        if parent:
            child.data["spawned_by"] = parent_key
            child.data["spawn_depth"] = parent.data.get("spawn_depth", 0) + 1
        return child

    def save_session(self, key: str):
        session = self.get_session(key)
        if not session:
            return
        path = SESSION_DIR / f"hier_{key.replace(':', '_')}.json"
        data = {
            "key": str(session.key),
            "parent_id": session.parent_id,
            "data": session.data,
            "created_at": session.created_at,
            "updated_at": datetime.now().isoformat(),
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def delete_session(self, key: str, delete_file: bool = True):
        """Remove a session from memory and optionally delete its persisted file."""
        if key in self._active:
            del self._active[key]

        if delete_file:
            path = SESSION_DIR / f"hier_{key.replace(':', '_')}.json"
            if path.exists():
                try:
                    path.unlink()
                except Exception as e:
                    logger.error(f"Failed to delete session file {path}: {e}")

            # Also cleanup conversation history if it exists
            conv_path = SESSION_DIR / f"{key.replace(':', '_')}.json"
            if conv_path.exists():
                try:
                    conv_path.unlink()
                except Exception as e:
                    logger.error(f"Failed to delete conversation file {conv_path}: {e}")


session_manager = SessionManager()

__all__ = [
    "ConversationManager",
    "get_last_session_id",
    "list_sessions",
    "SESSION_DIR",
    "LAST_SESSION_FILE",
    "session_manager",
    "HierarchicalSession",
    "SessionKey",
]
