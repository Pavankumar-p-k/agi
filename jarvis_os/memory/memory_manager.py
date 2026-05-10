from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .context_manager import ContextManager
from .vector_store import VectorStore


class MemoryManager:
    def __init__(self, config: Any) -> None:
        self.config = config
        self.context = ContextManager(limit=config.short_term_limit)
        self.vector_store = VectorStore()
        self.data_dir = Path(config.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.legacy_memory_file = self.data_dir / "long_term_memory.jsonl"
        self.files = {
            "conversation": self.data_dir / "conversation_memory.jsonl",
            "knowledge": self.data_dir / "knowledge_memory.jsonl",
            "event": self.data_dir / "event_memory.jsonl",
        }
        self._load_all()

    def _load_all(self) -> None:
        seen: set[str] = set()
        for path in [self.legacy_memory_file, *self.files.values()]:
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                item = json.loads(line)
                item_id = self._ensure_item_id(item)
                if item_id in seen:
                    continue
                seen.add(item_id)
                self.context.remember(item)
                self.vector_store.add(item)

    def remember(self, kind: str, text: str, metadata: dict[str, Any] | None = None) -> None:
        item = {
            "kind": kind,
            "text": text,
            "metadata": metadata or {},
            "timestamp": time.time(),
        }
        self._ensure_item_id(item)
        self.context.remember(item)
        self.vector_store.add(item)
        self._append(self._path_for_kind(kind), item)
        self._append(self.legacy_memory_file, item)

    def remember_conversation(self, speaker: str, text: str, metadata: dict[str, Any] | None = None) -> None:
        payload = dict(metadata or {})
        payload["speaker"] = speaker
        self.remember("conversation", text, payload)

    def remember_knowledge(self, text: str, metadata: dict[str, Any] | None = None) -> None:
        self.remember("knowledge", text, metadata or {})

    def record_episode(self, task_id: str, raw_input: str, status: str, elapsed_s: float, tool_used: str = "", result_summary: str = "") -> None:
        self.remember("episodic", f"EPISODE | {status} | {raw_input[:80]} | tool={tool_used} | elapsed={elapsed_s:.1f}s | {result_summary[:80]}", {
            "task_id": task_id, "input": raw_input[:200], "status": status, "elapsed_s": elapsed_s, "tool": tool_used, "summary": result_summary[:200]
        })

    def learn_fact(self, fact: str, source_task_id: str = "", importance: float = 0.6, tags: set | list | None = None) -> None:
        self.remember("semantic", fact, {"source_task": source_task_id, "importance": importance, "tags": list(tags or [])})

    def record_failure(self, raw_input: str, error: str, tool: str = "", intent_type: str = "") -> None:
        self.remember("failure", f"FAILURE | intent={intent_type} | tool={tool} | input={raw_input[:60]} | error={error[:80]}", {
            "input": raw_input[:200], "error": error[:200], "tool": tool, "intent_type": intent_type
        })

    def store_trace(self, task: str, task_type: str, strategy: str, steps: list, final_answer: str, verified: bool, confidence: float, debate_verdict: str, models_used: list, elapsed_ms: float) -> None:
        if not verified: return
        self.remember("reasoning_trace", f"TRACE | type={task_type} | strategy={strategy} | task={task[:100]}", {
            "task": task[:500], "task_type": task_type, "strategy": strategy, "steps": steps, "final_answer": final_answer[:2000], "verified": verified, "confidence": confidence, "debate_verdict": debate_verdict, "models_used": models_used, "elapsed_ms": elapsed_ms
        })

    def recall(
        self,
        query: str,
        top_k: int = 5,
        *,
        kinds: list[str] | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return self.vector_store.search(query, top_k=top_k, kinds=kinds, metadata_filter=metadata_filter)

    def search(
        self,
        query: str,
        top_k: int = 5,
        *,
        kinds: list[str] | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return self.vector_store.search(query, top_k=top_k, kinds=kinds, metadata_filter=metadata_filter)

    def build_context(
        self,
        query: str,
        *,
        conversation_limit: int = 4,
        knowledge_top_k: int = 3,
        metadata_filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        expected = metadata_filter or {}
        recent_conversation = self._recent_filtered("conversation", conversation_limit, expected)
        knowledge_hits = self.search(query, top_k=knowledge_top_k, kinds=["knowledge"], metadata_filter=expected or None)
        if expected:
            recent_knowledge = self._recent_filtered("knowledge", knowledge_top_k, expected)
            seen = {item.get("memory_id") for item in knowledge_hits}
            for item in recent_knowledge:
                item_id = item.get("memory_id")
                if item_id in seen:
                    continue
                knowledge_hits.append(item)
                seen.add(item_id)
                if len(knowledge_hits) >= knowledge_top_k:
                    break
        event_hits = self.search(
            query,
            top_k=2,
            kinds=["execution_step", "reflection", "self_improve", "event"],
            metadata_filter=expected or None,
        )
        return {
            "recent_conversation": recent_conversation,
            "knowledge_hits": knowledge_hits,
            "event_hits": event_hits,
        }

    def recent(self, *, kinds: list[str] | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        return self.context.recent(kinds=kinds, limit=limit)

    def conversation_recent(self, limit: int = 10) -> list[dict[str, Any]]:
        return self.context.recent(kinds=["conversation"], limit=limit)

    def knowledge_recent(self, limit: int = 10) -> list[dict[str, Any]]:
        return self.context.recent(kinds=["knowledge"], limit=limit)

    def _recent_filtered(self, kind: str, limit: int, metadata_filter: dict[str, Any]) -> list[dict[str, Any]]:
        items = self.context.recent(kinds=[kind])
        if metadata_filter:
            items = [item for item in items if self._metadata_matches(item.get("metadata", {}), metadata_filter)]
        return items[-limit:]

    def _path_for_kind(self, kind: str) -> Path:
        if kind == "conversation":
            return self.files["conversation"]
        if kind == "knowledge":
            return self.files["knowledge"]
        return self.files["event"]

    def _append(self, path: Path, item: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(item, ensure_ascii=True) + "\n")

    def _ensure_item_id(self, item: dict[str, Any]) -> str:
        item_id = str(item.get("memory_id", ""))
        if not item_id:
            item_id = f"mem_{int(float(item.get('timestamp', time.time())) * 1000)}_{abs(hash((item.get('kind', ''), item.get('text', '')))) % 1000000}"
            item["memory_id"] = item_id
        return item_id

    def _metadata_matches(self, metadata: dict[str, Any], expected: dict[str, Any]) -> bool:
        for key, value in expected.items():
            actual = metadata.get(key)
            if key == "agent_scope":
                if actual not in {None, "", value}:
                    return False
                continue
            if actual != value:
                return False
        return True
