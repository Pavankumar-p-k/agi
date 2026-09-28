"""MemoryAgent — handles memory recall/store sub-goals."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from core.agents.base import AgentResult, BaseAgent


@dataclass
class MemorySnapshot:
    total_memories: int = 0
    recent: list[str] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"total_memories": self.total_memories,
                "recent": list(self.recent), "timestamp": self.timestamp}


class MemoryAgent(BaseAgent):
    """Memory operations backed by memory.mem0_adapter (graceful offline)."""

    agent_id = "memory"
    keywords = ["remember", "recall", "memorize", "memory", "forget"]
    priority = 10
    description = "Store and recall user memories"

    def analyze(self) -> MemorySnapshot:
        """Read-only memory snapshot."""
        snapshot = MemorySnapshot(timestamp=datetime.now().isoformat())
        try:
            from memory import mem0_adapter
            all_mems = mem0_adapter.mem0_memory.get_all("default") or []
            snapshot.total_memories = len(all_mems)
            snapshot.recent = [
                str(m.get("memory", m.get("text", "")))
                for m in all_mems[:5]
                if isinstance(m, dict)
            ]
        except Exception:  # noqa: BLE001 — mem0 not installed is normal
            pass
        return snapshot

    async def _execute_impl(self, goal: str, context: Optional[Any] = None, **kwargs: Any) -> AgentResult:
        text = (goal or "").lower()
        snapshot = self.analyze()

        if any(kw in text for kw in ("remember", "memorize", "store")):
            content = goal
            try:
                from memory import mem0_adapter
                mem0_adapter.mem0_memory.add([{"role": "user", "content": content}],
                                            user_id="default")
                return AgentResult(success=True, output=f"Stored memory: {content}",
                                   agent_id=self.agent_id)
            except Exception as exc:  # noqa: BLE001
                return AgentResult(success=False, output="", agent_id=self.agent_id,
                                   error=f"memory store failed: {exc}")

        lines = [f"Memory bank: {snapshot.total_memories} entries."]
        lines += [f"- {m}" for m in snapshot.recent]
        if not snapshot.recent:
            lines.append("(no memories stored yet)")
        return AgentResult(success=True, output="\n".join(lines), agent_id=self.agent_id)
