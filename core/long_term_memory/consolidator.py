"""Consolidator — periodic background task that extracts experiences and synthesizes knowledge.

Runs on a configurable interval (default 300s / 5min). Scans for new
completed activities, extracts experiences, runs cross-activity synthesis,
and prunes stale knowledge.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from core.activity.manager import ActivityManager
from core.activity.storage import ActivityStore
from core.long_term_memory.extractor import ExperienceExtractor
from core.long_term_memory.store import KnowledgeStore
from core.long_term_memory.synthesizer import KnowledgeSynthesizer

logger = logging.getLogger(__name__)

_DEFAULT_INTERVAL_SECONDS = 300  # 5 minutes
_STALE_KNOWLEDGE_DAYS = 90  # prune unvalidated knowledge after 90 days


class Consolidator:
    """Periodic knowledge consolidation background loop.

    Usage:
        consolidator = Consolidator(activity_manager)
        asyncio.create_task(consolidator.run())

    Or run a single cycle:
        await consolidator.consolidate_once()
    """

    def __init__(
        self,
        activity_manager: ActivityManager | None = None,
        store: KnowledgeStore | None = None,
        interval_seconds: int = _DEFAULT_INTERVAL_SECONDS,
        belief_integrator: Any | None = None,
    ):
        self._store = store or KnowledgeStore()
        self._am = activity_manager or ActivityManager(
            store=ActivityStore(self._store._db_path),
        )
        self._extractor = ExperienceExtractor(self._am, self._store)
        self._belief = belief_integrator or self._create_belief_integrator()
        self._synthesizer = KnowledgeSynthesizer(self._store, belief_integrator=self._belief)
        self._interval = interval_seconds
        self._running = False

    async def run(self) -> None:
        """Run the consolidation loop forever."""
        self._running = True
        logger.info("Consolidator: started (interval=%ds)", self._interval)
        while self._running:
            try:
                await self._consolidate_once_async()
            except Exception:
                logger.exception("Consolidator: error in cycle")
            await asyncio.sleep(self._interval)

    def stop(self) -> None:
        self._running = False

    async def consolidate_once_async(self) -> dict[str, Any]:
        """Run one consolidation cycle (async wrapper)."""
        return await asyncio.to_thread(self.consolidate_once)

    def consolidate_once(self) -> dict[str, Any]:
        """Run one consolidation cycle: extract → synthesize → improve → prune.

        Returns a summary dict.
        """
        result: dict[str, Any] = {
            "experiences_extracted": 0,
            "knowledge_created": 0,
            "improvement_proposals": 0,
            "knowledge_pruned": 0,
        }

        # 1. Extract new experiences from completed activities
        new_experiences = self._extractor.extract_all_completed()
        result["experiences_extracted"] = len(new_experiences)

        # 2. Synthesize new knowledge
        all_experiences = self._store.get_all_experiences()
        new_knowledge = self._synthesizer.synthesize_from_experiences(all_experiences)
        result["knowledge_created"] = len(new_knowledge)

        # 3. Detect improvement opportunities from accumulated knowledge
        proposals_detected = 0
        try:
            from core.improvement.detector import ImprovementDetector
            from core.improvement.proposals import ProposalEngine
            from core.improvement.experiment import ExperimentRunner
            detector = ImprovementDetector(store=self._store)
            proposals = detector.detect_all()
            proposals_detected = len(proposals)
            result["improvement_proposals"] = proposals_detected
            if proposals:
                logger.info("Consolidator: %d improvement proposal(s) detected", proposals_detected)
                for p in proposals:
                    logger.debug("  [proposal] %s (conf=%.2f, cat=%s)",
                                 p.reason, p.confidence, p.category.value)
                # Wire ProposalEngine + ExperimentRunner
                try:
                    prop_engine = ProposalEngine()
                    changes = prop_engine.evaluate_all(proposals)
                    if changes:
                        logger.info("Consolidator: %d knob change(s) proposed", len(changes))
                        for c in changes:
                            logger.debug("  [knob] %s = %s (%s)", c.knob_name, c.new_value, c.reason[:60])
                        exp_runner = ExperimentRunner()
                        for change in changes:
                            try:
                                exp = exp_runner.create_experiment(
                                    proposal_id=p.proposal_id if hasattr(p, 'proposal_id') else "auto",
                                    changes=[change],
                                )
                                logger.info("Consolidator: experiment %s created for %s",
                                            exp.experiment_id, change.knob_name)
                            except Exception as exp_err:
                                logger.debug("Consolidator: experiment creation skipped: %s", exp_err)
                except Exception as prop_err:
                    logger.debug("Consolidator: proposal evaluation skipped: %s", prop_err)
        except Exception as e:
            logger.debug("Consolidator: improvement detection skipped: %s", e)

        # 4. Prune stale, low-confidence knowledge
        pruned = self._prune_stale()
        result["knowledge_pruned"] = pruned

        total = result["experiences_extracted"] + result["knowledge_created"]
        if total > 0:
            logger.info("Consolidator: cycle complete — %s", result)

        return result

    def _prune_stale(self) -> int:
        """Remove knowledge items that haven't been validated in STALE_KNOWLEDGE_DAYS
        and have low confidence."""
        count = 0
        threshold = datetime.utcnow() - timedelta(days=_STALE_KNOWLEDGE_DAYS)
        all_items = self._store.get_all_knowledge(limit=500)
        for item in all_items:
            last_val = item.last_validated or item.created_at
            if last_val and last_val < threshold and item.confidence < 0.4:
                self._store.delete_knowledge(item.knowledge_id)
                count += 1
        if count > 0:
            logger.info("Consolidator: pruned %d stale knowledge items", count)
        return count

    @staticmethod
    def _create_belief_integrator():
        try:
            from core.belief.integration import BeliefIntegrator
            return BeliefIntegrator()
        except ImportError:
            return None
