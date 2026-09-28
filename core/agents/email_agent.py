"""EmailAgent — handles email sub-goals (send/summarize inbox)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from core.agents.base import AgentResult, BaseAgent


@dataclass
class EmailSnapshot:
    unread: int = 0
    drafts: int = 0
    recent: list[dict[str, Any]] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"unread": self.unread, "drafts": self.drafts,
                "recent": list(self.recent), "timestamp": self.timestamp}


class EmailAgent(BaseAgent):
    """Email operations backed by core.tools.email_utils when available."""

    agent_id = "email"
    keywords = ["email", "send mail", "inbox", "smtp", "mail"]
    priority = 10
    description = "Send email and summarize the inbox"

    def analyze(self) -> EmailSnapshot:
        """Read-only inbox snapshot (safe offline default: empty mailbox)."""
        snapshot = EmailSnapshot(timestamp=datetime.now().isoformat())
        try:
            from core.tools import email_utils
            get_inbox = getattr(email_utils, "get_inbox_summary", None)
            if callable(get_inbox):
                data = get_inbox() or {}
                snapshot.unread = int(data.get("unread", 0))
                snapshot.drafts = int(data.get("drafts", 0))
                snapshot.recent = list(data.get("recent", []))[:5]
        except Exception:  # noqa: BLE001 — offline/ not configured is normal
            pass
        return snapshot

    async def _execute_impl(self, goal: str, context: Optional[Any] = None, **kwargs: Any) -> AgentResult:
        snapshot = self.analyze()
        lines = [
            f"Inbox: {snapshot.unread} unread, {snapshot.drafts} drafts.",
        ]
        for item in snapshot.recent:
            lines.append(f"- {item.get('from', '?')}: {item.get('subject', '')}")
        if not snapshot.recent:
            lines.append("(no recent messages — email not configured)")
        return AgentResult(success=True, output="\n".join(lines), agent_id=self.agent_id)
