"""ExperienceExtractor — converts activity graph nodes into experience summaries.

Walks completed activities and produces condensed views suitable for
cross-activity pattern detection and knowledge synthesis.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from core.activity.manager import ActivityManager
from core.activity.models import ActivityStatus
from core.long_term_memory.models import ExperienceSummary
from core.long_term_memory.store import KnowledgeStore

logger = logging.getLogger(__name__)

_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "android": ["android", "apk", "gradle", "kotlin", "java", "app"],
    "web": ["web", "html", "css", "javascript", "react", "vue", "api"],
    "research": ["research", "search", "find", "lookup", "investigate"],
    "build": ["build", "compile", "deploy", "package"],
    "test": ["test", "pytest", "unittest", "integration"],
    "coding": ["refactor", "implement", "feature", "add", "change", "fix"],
    "email": ["email", "send", "mail"],
    "browser": ["browser", "navigate", "click", "fill", "snapshot"],
}


class ExperienceExtractor:
    """Extracts condensed experience summaries from the activity graph.

    Usage:
        extractor = ExperienceExtractor(activity_manager)
        summary = extractor.extract(activity_id)
        store.insert_experience(summary)
    """

    def __init__(self, activity_manager: ActivityManager,
                 store: KnowledgeStore | None = None):
        self._am = activity_manager
        self._store = store or KnowledgeStore()

    def extract(self, activity_id: str) -> ExperienceSummary | None:
        """Build an ExperienceSummary from a completed activity.

        Returns None if the activity doesn't exist or has no nodes.
        """
        tree = self._am.get_tree(activity_id)
        if not tree:
            return None

        root = tree[0]
        nodes = tree[1:] if len(tree) > 1 else []

        agents: set[str] = set()
        tools: set[str] = set()
        artifacts: list[str] = []
        tool_call_count = 0
        failed_count = 0
        error_msgs: list[str] = []

        for node in nodes:
            if node.agent_id:
                agents.add(node.agent_id)
            if node.node_type == "tool_call":
                tool_call_count += 1
                tools.add(node.label)
            if node.node_type == "artifact":
                artifacts.extend(node.artifacts.keys())
            if node.status == ActivityStatus.FAILED:
                failed_count += 1
                err = node.output.get("error", "")
                if err:
                    error_msgs.append(err)

        domain = self._infer_domain(root.label, tools)
        duration = self._compute_duration(root)
        success = root.status == ActivityStatus.COMPLETED
        quality = self._compute_quality(root, failed_count, tool_call_count)

        return ExperienceSummary(
            activity_id=activity_id,
            goal=root.label,
            domain=domain,
            status=root.status.value,
            node_count=len(tree),
            agent_ids=sorted(agents),
            tools_used=sorted(tools),
            artifacts_produced=artifacts,
            success=success,
            error_summary="; ".join(error_msgs[:3]) if error_msgs else None,
            duration_seconds=duration,
            outcome_quality=quality,
            created_at=root.completed_at or datetime.utcnow(),
        )

    def extract_and_store(self, activity_id: str) -> ExperienceSummary | None:
        """Extract and persist a single experience summary."""
        summary = self.extract(activity_id)
        if summary:
            self._store.insert_experience(summary)
        return summary

    def extract_all_completed(self, limit: int = 100) -> list[ExperienceSummary]:
        """Find completed activities from the store and extract all that are missing."""
        stored = self._store.get_all_experiences(limit)
        stored_ids = {e.activity_id for e in stored}

        # Query recent completed root nodes via ActivityStore
        from core.activity.storage import ActivityStore
        act_store = ActivityStore(self._store._db_path)
        with act_store._lock, __import__("sqlite3").connect(act_store._db_path) as conn:
            conn.row_factory = __import__("sqlite3").Row
            rows = conn.execute(
                """SELECT DISTINCT activity_id FROM activity_nodes
                   WHERE depth=0 AND status IN ('COMPLETED', 'FAILED')
                   ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()

        results: list[ExperienceSummary] = []
        for row in rows:
            aid = row["activity_id"]
            if aid in stored_ids:
                continue
            summary = self.extract(aid)
            if summary:
                self._store.insert_experience(summary)
                results.append(summary)
        return results

    def _infer_domain(self, goal: str, tools: set[str]) -> str:
        text = goal.lower()
        tool_text = " ".join(t.lower() for t in tools)
        combined = f"{text} {tool_text}"

        scores: list[tuple[str, int]] = []
        for domain, keywords in _DOMAIN_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in combined)
            if score > 0:
                scores.append((domain, score))

        if not scores:
            return "general"
        return max(scores, key=lambda x: x[1])[0]

    def _compute_duration(self, root) -> float | None:
        if root.started_at and root.completed_at:
            return (root.completed_at - root.started_at).total_seconds()
        return None

    def _compute_quality(self, root, failed_count: int, total_calls: int) -> float | None:
        if root.status == ActivityStatus.FAILED:
            return 0.0
        if total_calls == 0:
            return 1.0 if root.status == ActivityStatus.COMPLETED else None
        return max(0.0, 1.0 - (failed_count / total_calls))
