"""core/session.py
ConversationManager — persistent session state for CLI, API, Flutter, Web.
Each session = UUID + message list, saved as ~/.jarvis/sessions/<uuid>.json.
"""

import os
import json
import uuid
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

import tiktoken

logger = logging.getLogger("session")

SESSION_DIR = Path.home() / ".jarvis" / "sessions"
LAST_SESSION_FILE = Path.home() / ".jarvis" / "last_session"
DEFAULT_MAX_TOKENS = 8000
DEFAULT_MODEL = "gpt-4"  # tiktoken encoding name


def _ensure_dir():
    SESSION_DIR.mkdir(parents=True, exist_ok=True)


def _count_tokens(messages: List[Dict], model: str = DEFAULT_MODEL) -> int:
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    num_tokens = 0
    for msg in messages:
        num_tokens += 4  # per-message overhead
        for key, value in msg.items():
            if isinstance(value, str):
                num_tokens += len(encoding.encode(value))
            if key == "role":
                num_tokens += 1  # role enum
            elif key == "content":
                num_tokens += 1  # content marker
    num_tokens += 2  # priming
    return num_tokens


class ConversationManager:
    """Manages a single conversation session with token-aware trimming."""

    def __init__(self, session_id: Optional[str] = None, max_tokens: int = DEFAULT_MAX_TOKENS):
        _ensure_dir()
        self.session_id = session_id or str(uuid.uuid4())
        self.max_tokens = max_tokens
        self.name: Optional[str] = None
        self.messages: List[Dict] = []
        self.created_at: str = datetime.utcnow().isoformat()
        self.updated_at: str = self.created_at
        self._loaded = False

    @property
    def path(self) -> Path:
        return SESSION_DIR / f"{self.session_id}.json"

    def add_message(self, role: str, content: str, **extra) -> Dict:
        msg = {"role": role, "content": content, "timestamp": datetime.utcnow().isoformat()}
        msg.update(extra)
        self.messages.append(msg)
        self.updated_at = datetime.utcnow().isoformat()
        self.trim()
        return msg

    def get_context(self, last_n: int = 20) -> List[Dict]:
        """Return last N messages as {role, content} list for LLM context."""
        trimmed = self.messages[-last_n:] if last_n else self.messages
        return [{"role": m["role"], "content": m["content"]} for m in trimmed]

    def trim(self):
        """Trim oldest messages until under max_tokens."""
        while self.messages and _count_tokens(self.messages) > self.max_tokens:
            removed = self.messages.pop(0)
            logger.debug(f"Trimmed message: role={removed.get('role')}")

    def save(self):
        _ensure_dir()
        data = {
            "session_id": self.session_id,
            "name": self.name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "messages": self.messages,
        }
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        LAST_SESSION_FILE.write_text(self.session_id, encoding="utf-8")

    def load(self):
        if not self.path.exists():
            logger.warning(f"Session file not found: {self.path}")
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.session_id = data.get("session_id", self.session_id)
            self.name = data.get("name")
            self.created_at = data.get("created_at", self.created_at)
            self.updated_at = data.get("updated_at", self.updated_at)
            self.messages = data.get("messages", [])
            self._loaded = True
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Failed to load session {self.session_id}: {e}")

    def delete(self):
        if self.path.exists():
            self.path.unlink()
        if LAST_SESSION_FILE.exists() and LAST_SESSION_FILE.read_text(encoding="utf-8") == self.session_id:
            LAST_SESSION_FILE.unlink()

    def clear(self):
        self.messages.clear()
        self.updated_at = datetime.utcnow().isoformat()

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def token_count(self) -> int:
        return _count_tokens(self.messages)

    def __repr__(self) -> str:
        return f"ConversationManager(id={self.session_id[:8]}..., msgs={self.message_count}, tokens={self.token_count})"

    def rename(self, name: str):
        self.name = name
        self.save()

    def export_transcript(self, output_dir=None) -> str:
        output_dir = output_dir or (Path.home() / ".jarvis" / "exports")
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{self.session_id}.txt"
        lines = [
            f"Session: {self.session_id}",
            f"Created: {self.created_at}",
            f"Messages: {self.message_count}",
            "=" * 60,
        ]
        for msg in self.messages:
            ts = msg.get("timestamp", "")[:19]
            lines.append(f"[{ts}] {msg['role'].upper()}: {msg['content']}")
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
        return str(path)

    def fork(self) -> "ConversationManager":
        new_cm = ConversationManager()
        new_cm.messages = list(self.messages)
        new_cm.save()
        return new_cm

    def compact(self, keep_last=10):
        if len(self.messages) <= keep_last * 2:
            return
        old = self.messages[:-(keep_last * 2)]
        recent = self.messages[-(keep_last * 2):]
        summary = f"[Compacted {len(old)} messages: "
        summary += "; ".join(f"{m['role']}: {m['content'][:80]}" for m in old)
        summary += "]"
        self.messages = [{"role": "system", "content": summary}] + recent
        self.save()

    def stash_prompt(self, text: str, label: str = "") -> int:
        stash_dir = Path.home() / ".jarvis" / "stash"
        stash_dir.mkdir(parents=True, exist_ok=True)
        existing = sorted(stash_dir.glob("*.json"))
        idx = len(existing) + 1
        data = {"index": idx, "label": label, "text": text, "created": datetime.utcnow().isoformat()}
        (stash_dir / f"{idx:03d}.json").write_text(json.dumps(data), encoding="utf-8")
        return idx

    def list_stash(self) -> list:
        stash_dir = Path.home() / ".jarvis" / "stash"
        if not stash_dir.exists():
            return []
        result = []
        for f in sorted(stash_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                result.append(data)
            except Exception:
                pass
        return result

    def load_stash(self, idx: int) -> str:
        stash_dir = Path.home() / ".jarvis" / "stash"
        path = stash_dir / f"{idx:03d}.json"
        if not path.exists():
            return ""
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("text", "")


def get_last_session_id() -> Optional[str]:
    if LAST_SESSION_FILE.exists():
        return LAST_SESSION_FILE.read_text(encoding="utf-8").strip()
    return None


def list_sessions() -> List[Dict]:
    _ensure_dir()
    sessions = []
    for f in sorted(SESSION_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            sessions.append({
                "session_id": data.get("session_id", f.stem),
                "created_at": data.get("created_at", ""),
                "updated_at": data.get("updated_at", ""),
                "message_count": len(data.get("messages", [])),
            })
        except (json.JSONDecodeError, OSError):
            continue
    return sessions
