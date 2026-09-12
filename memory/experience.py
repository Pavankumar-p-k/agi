"""Goal-level procedural experience for JARVIS.

This module answers one question for the future Super-Brain / planner:

    "Have I done something like this before, and what worked?"

It is NOT a new memory system.  It composes the existing memory stack:

    EpisodicStore (memory/episodic_store.py)  ← the only storage backend
    memory.memory_facade.MemoryFacade         ← the single public entry point

Flow (the plan's Experience diagram):

    verified specialist outcome (Browser AI, Coding AI, ...)
        ↓ record_outcome()
    ONE EPISODE in EpisodicStore (goal, actions, context, result)
        ↓ recall_outcomes() / best_procedure()
    similar past episodes → workflow, success_rate, last_verified

Expiry matters: websites and codebases change, so every recalled procedure
carries ``days_since_verified`` and ``fresh`` fields rather than being
treated as permanent truth.
"""
from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# A procedure older than this (days since last verified success) is reported
# as stale so consumers can re-verify instead of blindly replaying it.
DEFAULT_FRESH_DAYS = 14.0

# Similarity at or above this is considered "the same task" when aggregating.
DEFAULT_SIMILARITY_THRESHOLD = 0.35


class ExperienceRecorder:
    """Record verified outcomes and retrieve reusable procedures.

    Backed exclusively by :class:`memory.episodic_store.EpisodicStore` —
    no new database, no new tables, no parallel store.
    """

    def __init__(self, episodic_store: Any | None = None):
        if episodic_store is None:
            from memory.episodic_store import EpisodicStore
            episodic_store = EpisodicStore()
        self._episodic = episodic_store

    # ------------------------------------------------------------------ #
    # Recording                                                          #
    # ------------------------------------------------------------------ #

    def record_outcome(
        self,
        goal: str,
        actions: list[dict],
        *,
        verified: bool,
        context: dict | None = None,
        error: str | None = None,
        evidence: dict | None = None,
        specialist: str = "",
        episode_type: str = "task",
        tags: list[str] | None = None,
        user_id: str = "default",
    ) -> str:
        """Store one verified execution outcome as an episode.

        Parameters mirror ``EpisodicStore.store``; ``verified`` is the honest
        SUCCESS signal (from a verification engine, never a return value).
        """
        result: dict[str, Any] = {
            "success": bool(verified),
            "verified": bool(verified),
            "recorded_at": time.time(),
        }
        if error:
            result["error"] = error
        if evidence:
            result["evidence"] = evidence
        ctx = dict(context or {})
        if specialist:
            ctx["specialist"] = specialist
        episode_tags = list(tags or [])
        if specialist and specialist not in episode_tags:
            episode_tags.append(specialist)
        episode_tags.append("verified" if verified else "unverified")

        try:
            return self._episodic.store(
                goal=goal,
                actions=actions,
                context=ctx,
                result=result,
                episode_type=episode_type,
                tags=episode_tags,
                user_id=user_id,
            )
        except Exception as exc:
            logger.warning("[experience] record_outcome failed: %s", exc)
            return ""

    # ------------------------------------------------------------------ #
    # Retrieval                                                          #
    # ------------------------------------------------------------------ #

    def recall_outcomes(
        self,
        goal: str,
        top_k: int = 5,
        *,
        user_id: str = "default",
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    ) -> list[dict]:
        """Return past episodes similar to ``goal``, most similar first.

        Each item adds: ``success``, ``verified``, ``days_since_verified``,
        ``fresh`` — the verification/expiry semantics the plan requires.
        """
        try:
            episodes = self._episodic.retrieve(
                goal, top_k=top_k, user_id=user_id
            )
        except Exception as exc:
            logger.warning("[experience] recall failed: %s", exc)
            return []

        results = []
        for ep in episodes:
            similarity = float(ep.get("_similarity", 0.0))
            if similarity < similarity_threshold:
                continue
            item = self._with_expiry(ep)
            item["similarity"] = round(similarity, 3)
            results.append(item)
        return results

    def best_procedure(
        self,
        goal: str,
        *,
        user_id: str = "default",
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        max_episodes: int = 10,
    ) -> dict | None:
        """Aggregate similar episodes into one reusable procedure summary.

        Returns ``None`` when no sufficiently similar episode exists — callers
        should treat that as "no memory, plan from scratch" rather than
        inventing a procedure.
        """
        episodes = self.recall_outcomes(
            goal,
            top_k=max_episodes,
            user_id=user_id,
            similarity_threshold=similarity_threshold,
        )
        if not episodes:
            return None

        verified_hits = [ep for ep in episodes if ep.get("verified")]
        successes = [ep for ep in episodes if ep.get("success")]
        total = len(episodes)

        # Workflow: the action sequence of the most recent *verified success*,
        # which is the procedure that demonstrably worked last time.
        template = None
        for ep in sorted(verified_hits, key=lambda e: e.get("timestamp", 0), reverse=True):
            actions = ep.get("actions") or []
            if actions:
                template = [dict(a) for a in actions]
                break
        if template is None:
            for ep in sorted(successes, key=lambda e: e.get("timestamp", 0), reverse=True):
                actions = ep.get("actions") or []
                if actions:
                    template = [dict(a) for a in actions]
                    break

        last_verified = max(
            (ep.get("timestamp", 0.0) for ep in verified_hits), default=0.0
        )
        known_failures = [
            {"goal": ep.get("goal", ""), "error": (ep.get("result") or {}).get("error", "")}
            for ep in episodes
            if not ep.get("success")
        ]
        known_failures = [f for f in known_failures if f["error"]]

        return {
            "goal": goal,
            "matches": total,
            "verified_matches": len(verified_hits),
            "success_rate": round(len(successes) / total, 2) if total else 0.0,
            "workflow": template or [],
            "last_verified": last_verified,
            "days_since_verified": round((time.time() - last_verified) / 86400, 2) if last_verified else None,
            "fresh": bool(last_verified) and (time.time() - last_verified) / 86400 <= DEFAULT_FRESH_DAYS,
            "known_failures": known_failures,
            "episodes": episodes,
        }

    # ------------------------------------------------------------------ #
    # Helpers                                                            #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _with_expiry(episode: dict) -> dict:
        result = episode.get("result") or {}
        recorded_at = float(result.get("recorded_at") or episode.get("timestamp", 0.0) or 0.0)
        age_days = (time.time() - recorded_at) / 86400 if recorded_at else None
        return {
            "id": episode.get("id", ""),
            "goal": episode.get("goal", ""),
            "actions": episode.get("actions", []),
            "context": episode.get("context", {}),
            "result": result,
            "tags": episode.get("tags", []),
            "importance": episode.get("importance", 0.0),
            "success": bool(result.get("success", False)),
            "verified": bool(result.get("verified", False)),
            "error": result.get("error", ""),
            "timestamp": recorded_at,
            "days_since_verified": round(age_days, 2) if age_days is not None else None,
            "fresh": bool(recorded_at) and age_days <= DEFAULT_FRESH_DAYS,
        }
