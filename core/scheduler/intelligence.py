"""ActivityIntelligence — historical stats collection, prediction, and calibration.

Phases:
  8.3A — Historical Learning: record outcomes, compute per-type stats
  8.3B — Prediction: predict before execution, calibrate after measurement
  8.3C — Resource Estimation: predict token/api/memory/browser cost, calibrate

Stored in same SQLite database as scheduler state (data/workflow.db).
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from core.scheduler.models import ScheduledActivity
from core.scheduler.resources import (
    ResourceEstimate,
    ResourceUsage,
    ResourceCalibration,
    ResourcePredictor,
    compute_resource_cost,
    ALL_RESOURCE_COLS,
    RESOURCE_MIGRATIONS,
)

logger = logging.getLogger(__name__)

_DEFAULT_DB = str(Path("data") / "workflow.db")
MIN_SAMPLES_FOR_STATS = 3
INTELLIGENCE_MULTIPLIER = 40
DURATION_PENALTY_PER_10S = 2
MAX_DURATION_PENALTY = 30

# Prediction confidence ramp: 0 confidence at 0 samples → 1.0 at CONFIDENCE_SATURATION samples
CONFIDENCE_SATURATION = 20
DEFAULT_PRIOR_SUCCESS = 0.5
DEFAULT_PRIOR_DURATION_MS = 10000.0

# Resource cost weights for priority scoring
RESOURCE_PENALTY_MULTIPLIER = 3

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS activity_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id TEXT NOT NULL,
    node_type TEXT NOT NULL,
    goal TEXT NOT NULL,
    chain_id TEXT,
    success INTEGER NOT NULL,
    duration_ms INTEGER NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    predicted_success REAL,
    predicted_duration_ms INTEGER,
    prediction_source TEXT DEFAULT 'historical_stats',
    predicted_tokens INTEGER,
    predicted_api_cost REAL,
    predicted_memory_mb REAL,
    predicted_browser_steps INTEGER,
    actual_tokens INTEGER,
    actual_api_cost REAL,
    actual_memory_mb REAL,
    actual_browser_steps INTEGER,
    completed_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_stats_type ON activity_stats(node_type);
CREATE INDEX IF NOT EXISTS idx_stats_success ON activity_stats(success);
CREATE INDEX IF NOT EXISTS idx_stats_completed ON activity_stats(completed_at);
CREATE INDEX IF NOT EXISTS idx_stats_predicted ON activity_stats(predicted_success);
"""


@dataclass
class TypeStats:
    node_type: str
    count: int = 0
    success_count: int = 0
    failure_count: int = 0
    success_rate: float = 0.5
    avg_duration_ms: float = 0.0
    median_duration_ms: float = 0.0
    min_duration_ms: float = 0.0
    max_duration_ms: float = 0.0


@dataclass
class Prediction:
    """A single prediction for an activity before execution.

    Attributes:
        success_probability: Estimated probability of success (0.0-1.0)
        expected_duration_ms: Estimated duration in milliseconds
        confidence: How much weight to give this prediction (0.0-1.0).
                    0 = no confidence (use prior), 1.0 = full confidence
        sample_size: Number of historical observations behind this prediction
        node_type: The activity type this prediction is for
        prediction_source: Where the prediction came from
                           (historical_stats, chain_stats, domain_stats, manual)
    """
    success_probability: float = DEFAULT_PRIOR_SUCCESS
    expected_duration_ms: float = DEFAULT_PRIOR_DURATION_MS
    confidence: float = 0.0
    sample_size: int = 0
    node_type: str = ""
    prediction_source: str = "historical_stats"


@dataclass
class CalibrationStats:
    """Calibration quality for a prediction source or node_type.

    Attributes:
        node_type: The activity type these stats apply to
        sample_count: Number of prediction→outcome pairs analyzed
        prediction_error: Mean absolute error in success prediction
                          (e.g. 0.10 means predictions are off by 10% on avg)
        duration_error: Mean relative error in duration prediction
                        (e.g. 0.25 means 25% average error)
        calibration_score: 0.0-1.0 where 1.0 = perfectly calibrated.
                           Computed from prediction_error.
    """
    node_type: str = ""
    sample_count: int = 0
    prediction_error: float = 0.0
    duration_error: float = 0.0
    calibration_score: float = 0.5


class PredictionEngine:
    """Stateless prediction logic built on ActivityIntelligence stats.

    Can be extended later with chain-level, domain-level, or LLM-based
    predictors — all return the same Prediction dataclass.
    """

    @staticmethod
    def predict(node_type: str, stats: TypeStats | None = None) -> Prediction:
        """Produce a Prediction from historical TypeStats.

        Confidence ramps linearly from 0 at 0 samples to 1.0 at
        CONFIDENCE_SATURATION samples. Below MIN_SAMPLES_FOR_STATS,
        the prediction blends toward neutral priors.
        """
        if stats is None or stats.count == 0:
            return Prediction(
                node_type=node_type,
                confidence=0.0,
                sample_size=0,
            )

        sample_size = stats.count
        confidence = min(sample_size / CONFIDENCE_SATURATION, 1.0)

        # Blend historical rate with prior, weighted by confidence
        if sample_size >= MIN_SAMPLES_FOR_STATS:
            success_prob = stats.success_rate
            expected_dur = stats.avg_duration_ms
        else:
            # Below threshold: blend toward prior
            prior_weight = 1.0 - (sample_size / MIN_SAMPLES_FOR_STATS)
            success_prob = (
                stats.success_rate * (1 - prior_weight)
                + DEFAULT_PRIOR_SUCCESS * prior_weight
            )
            expected_dur = (
                stats.avg_duration_ms * (1 - prior_weight)
                + DEFAULT_PRIOR_DURATION_MS * prior_weight
            )

        return Prediction(
            success_probability=success_prob,
            expected_duration_ms=expected_dur,
            confidence=confidence,
            sample_size=sample_size,
            node_type=node_type,
            prediction_source="historical_stats",
        )

    @staticmethod
    def calibrate(
        predictions: list[tuple[float, int, bool, int]],
    ) -> CalibrationStats:
        """Compute calibration from a list of (predicted_success, predicted_dur_ms, actual_success, actual_dur_ms) pairs.

        Args:
            predictions: List of (predicted_success_prob, predicted_duration_ms,
                                  actual_success_bool, actual_duration_ms) tuples

        Returns:
            CalibrationStats with computed error and score metrics
        """
        if not predictions:
            return CalibrationStats()

        err_sum = 0.0
        dur_err_sum = 0.0
        for pred_succ, pred_dur, actual_succ, actual_dur in predictions:
            err_sum += abs(pred_succ - (1.0 if actual_succ else 0.0))
            if actual_dur > 0:
                dur_err_sum += abs(pred_dur - actual_dur) / max(actual_dur, 1)

        n = len(predictions)
        prediction_error = err_sum / n
        duration_error = dur_err_sum / n

        # Calibration score: 1.0 = perfect, 0.0 = always wrong
        calibration_score = max(0.0, 1.0 - prediction_error * 2.0)

        return CalibrationStats(
            sample_count=n,
            prediction_error=round(prediction_error, 4),
            duration_error=round(duration_error, 4),
            calibration_score=round(calibration_score, 4),
        )


class ActivityIntelligence:
    """Collects and serves predictive stats from completed activities.

    Thread-safe. Creates its own activity_stats table alongside
    the existing scheduled_activities table in workflow.db.

    Usage:
        ai = ActivityIntelligence()

        # Phase 8.3A: record outcomes
        ai.record("act_1", "build", 5000, True, "Build APK")

        # Phase 8.3B: predict + calibrate
        pred = ai.predict("build")
        ai.record("act_2", "build", 6000, True, "Build v2",
                   predicted_success=pred.success_probability,
                   predicted_duration_ms=pred.expected_duration_ms)
        cal = ai.get_calibration("build")
    """

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or _DEFAULT_DB
        self._lock = threading.Lock()
        self._cache: dict[str, TypeStats] = {}
        self._cache_valid = False
        self._init_db()

    def _init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.executescript(_TABLE_SQL)
            self._migrate(conn)

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """Add prediction + resource columns if they don't exist (safe for existing DBs)."""
        cursor = conn.execute("PRAGMA table_info(activity_stats)")
        existing = {row[1] for row in cursor.fetchall()}
        migrations = [
            ("predicted_success", "REAL"),
            ("predicted_duration_ms", "INTEGER"),
            ("prediction_source", "TEXT DEFAULT 'historical_stats'"),
        ] + RESOURCE_MIGRATIONS
        for col_name, col_type in migrations:
            if col_name not in existing:
                logger.info("ActivityIntelligence: adding column %s", col_name)
                conn.execute(
                    f"ALTER TABLE activity_stats ADD COLUMN {col_name} {col_type}"
                )

    # ── Recording ────────────────────────────────────────────────────────────

    def record(
        self,
        activity_id: str,
        node_type: str,
        duration_ms: int,
        success: bool,
        goal: str = "",
        metadata: dict[str, Any] | None = None,
        predicted_success: float | None = None,
        predicted_duration_ms: int | None = None,
        prediction_source: str | None = None,
        predicted_resources: ResourceEstimate | None = None,
        actual_resources: ResourceUsage | None = None,
    ) -> None:
        """Record a completed activity execution outcome.

        Args:
            activity_id: Unique activity identifier
            node_type: Activity type (build, research, email, etc.)
            duration_ms: Wall-clock execution time in milliseconds
            success: True if completed successfully, False if failed
            goal: Human-readable goal string
            metadata: Optional metadata dict (chain_id extracted if present)
            predicted_success: Prior prediction of success probability (0.0-1.0)
            predicted_duration_ms: Prior prediction of duration in ms
            prediction_source: Source of the prediction
            predicted_resources: Prior resource usage estimate
            actual_resources: Actual resource usage after execution
        """
        now = datetime.utcnow().isoformat()
        chain_id = (metadata or {}).get("chain_id", "")
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT INTO activity_stats
                   (activity_id, node_type, goal, chain_id, success,
                    duration_ms, retry_count,
                    predicted_success, predicted_duration_ms, prediction_source,
                    predicted_tokens, predicted_api_cost, predicted_memory_mb, predicted_browser_steps,
                    actual_tokens, actual_api_cost, actual_memory_mb, actual_browser_steps,
                    completed_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    activity_id,
                    node_type,
                    goal[:200],
                    chain_id or "",
                    1 if success else 0,
                    int(duration_ms),
                    (metadata or {}).get("retry_count", 0),
                    predicted_success,
                    predicted_duration_ms,
                    prediction_source or "historical_stats",
                    int(predicted_resources.token_cost) if predicted_resources else None,
                    predicted_resources.api_cost if predicted_resources else None,
                    predicted_resources.memory_mb if predicted_resources else None,
                    int(predicted_resources.browser_steps) if predicted_resources else None,
                    int(actual_resources.token_cost) if actual_resources else None,
                    actual_resources.api_cost if actual_resources else None,
                    actual_resources.memory_mb if actual_resources else None,
                    int(actual_resources.browser_steps) if actual_resources else None,
                    now,
                    now,
                ),
            )
        self._cache_valid = False
        logger.debug(
            "ActivityIntelligence: recorded %s type=%s success=%s duration=%dms%s",
            activity_id, node_type, success, duration_ms,
            f" (pred={predicted_success:.2f})" if predicted_success is not None else "",
        )

    def record_batch(
        self, records: list[dict[str, Any]]
    ) -> None:
        """Bulk-record multiple outcomes (for backfill or migration)."""
        now = datetime.utcnow().isoformat()
        with self._lock, sqlite3.connect(self._db_path) as conn:
            for r in records:
                meta = r.get("metadata", {})
                pred_res = r.get("predicted_resources")
                act_res = r.get("actual_resources")
                conn.execute(
                    """INSERT INTO activity_stats
                       (activity_id, node_type, goal, chain_id, success,
                        duration_ms, retry_count,
                        predicted_success, predicted_duration_ms, prediction_source,
                        predicted_tokens, predicted_api_cost, predicted_memory_mb, predicted_browser_steps,
                        actual_tokens, actual_api_cost, actual_memory_mb, actual_browser_steps,
                        completed_at, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        r["activity_id"],
                        r["node_type"],
                        r.get("goal", "")[:200],
                        meta.get("chain_id", ""),
                        1 if r.get("success", True) else 0,
                        int(r.get("duration_ms", 0)),
                        meta.get("retry_count", 0),
                        r.get("predicted_success"),
                        r.get("predicted_duration_ms"),
                        r.get("prediction_source", "historical_stats"),
                        int(pred_res.token_cost) if pred_res else None,
                        pred_res.api_cost if pred_res else None,
                        pred_res.memory_mb if pred_res else None,
                        int(pred_res.browser_steps) if pred_res else None,
                        int(act_res.token_cost) if act_res else None,
                        act_res.api_cost if act_res else None,
                        act_res.memory_mb if act_res else None,
                        int(act_res.browser_steps) if act_res else None,
                        r.get("completed_at", now),
                        now,
                    ),
                )
        self._cache_valid = False

    # ── Query ────────────────────────────────────────────────────────────────

    def get_stats(self, node_type: str) -> TypeStats:
        """Get predictive statistics for a given activity type.

        Returns TypeStats with learned success_rate, avg_duration, etc.
        If insufficient data, returns defaults (success_rate=0.5).
        """
        self._ensure_cache()
        return self._cache.get(node_type, TypeStats(node_type=node_type))

    def get_stats_summary(self) -> dict[str, TypeStats]:
        """Get all known type statistics."""
        self._ensure_cache()
        return dict(self._cache)

    # ── Phase 8.3C: Resource Prediction ──────────────────────────────────────

    def predict_resources(self, node_type: str) -> ResourceEstimate:
        """Predict resource usage for an activity of the given type.

        Returns a ResourceEstimate with historical averages and confidence.
        """
        with self._lock, sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                """SELECT AVG(actual_tokens), AVG(actual_api_cost),
                          AVG(actual_memory_mb), AVG(actual_browser_steps)
                   FROM activity_stats
                   WHERE node_type = ?
                     AND actual_tokens IS NOT NULL""",
                (node_type,),
            ).fetchone()
            count_row = conn.execute(
                "SELECT COUNT(*) FROM activity_stats WHERE node_type = ? AND actual_tokens IS NOT NULL",
                (node_type,),
            ).fetchone()
        sample_count = count_row[0] if count_row else 0
        has_data = row is not None and row[0] is not None and sample_count > 0

        estimate = ResourcePredictor.predict_from_stats(
            node_type, row if has_data else None, sample_count,
        )

        # Apply calibration
        cal = self.get_resource_calibration(node_type)
        if cal.sample_count >= 3:
            estimate = ResourcePredictor.apply_calibration(estimate, cal)

        return estimate

    def get_resource_calibration(self, node_type: str) -> ResourceCalibration:
        """Get calibration multipliers for resource predictions."""
        with self._lock, sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                """SELECT predicted_tokens, actual_tokens,
                          predicted_api_cost, actual_api_cost,
                          predicted_memory_mb, actual_memory_mb,
                          predicted_browser_steps, actual_browser_steps
                   FROM activity_stats
                   WHERE node_type = ?
                     AND predicted_tokens IS NOT NULL
                     AND actual_tokens IS NOT NULL
                   ORDER BY completed_at DESC
                   LIMIT 500""",
                (node_type,),
            ).fetchall()
        pairs = [
            (float(r[0] or 0), float(r[1] or 0),
             float(r[2] or 0), float(r[3] or 0),
             float(r[4] or 0), float(r[5] or 0),
             float(r[6] or 0), float(r[7] or 0))
            for r in rows
        ]
        result = ResourcePredictor.calibrate(pairs)
        result.node_type = node_type
        return result

    def resource_cost_score(self, node_type: str) -> int:
        """Compute a resource cost penalty for priority scoring.

        Returns an integer 0-30 representing relative resource cost.
        Higher = more expensive = lower priority.
        """
        stats = self.get_stats(node_type)
        if stats.count < MIN_SAMPLES_FOR_STATS:
            return 0

        estimate = self.predict_resources(node_type)
        if estimate.confidence == 0:
            return 0

        cost = compute_resource_cost(estimate)
        penalty = min(int(cost * RESOURCE_PENALTY_MULTIPLIER), MAX_DURATION_PENALTY)
        return penalty

    # ── Phase 8.3B: Prediction ───────────────────────────────────────────────

    def predict(self, node_type: str) -> Prediction:
        """Predict outcome for an activity of the given type.

        Uses PredictionEngine with historical TypeStats. Returns a
        Prediction with confidence weighted by sample count.
        """
        stats = self.get_stats(node_type)
        return PredictionEngine.predict(node_type, stats)

    def get_calibration(self, node_type: str) -> CalibrationStats:
        """Get calibration quality for a node_type.

        Compares all stored predictions against actual outcomes
        for the given type. Returns CalibrationStats with error metrics.
        """
        with self._lock, sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                """SELECT predicted_success, predicted_duration_ms,
                          success, duration_ms
                   FROM activity_stats
                   WHERE node_type = ?
                     AND predicted_success IS NOT NULL
                   ORDER BY completed_at DESC
                   LIMIT 500""",
                (node_type,),
            ).fetchall()

        pairs = [
            (row[0], row[1] or 0, bool(row[2]), row[3])
            for row in rows
        ]
        result = PredictionEngine.calibrate(pairs)
        result.node_type = node_type
        return result

    def get_calibration_summary(self) -> dict[str, CalibrationStats]:
        """Get calibration for all node_types that have prediction data."""
        with self._lock, sqlite3.connect(self._db_path) as conn:
            types = conn.execute(
                """SELECT DISTINCT node_type FROM activity_stats
                   WHERE predicted_success IS NOT NULL"""
            ).fetchall()
        return {
            row[0]: self.get_calibration(row[0])
            for row in types
        }

    def learned_priority(
        self, node_type: str, user_priority: int = 0,
    ) -> int:
        """Compute intelligence-adjusted priority contribution.

        Phase 8.3B formula:
            success = pred.success_probability * pred.confidence
                      + DEFAULT_PRIOR_SUCCESS * (1 - pred.confidence)
            adjusted_success = success * calibration_adjustment
            duration = pred.expected_duration_ms * pred.confidence
                       + DEFAULT_PRIOR_DURATION_MS * (1 - pred.confidence)
            boost = adjusted_success * INTELLIGENCE_MULTIPLIER
            penalty = min(duration / 10s * DURATION_PENALTY_PER_10S, MAX)
            result = boost - penalty

        Returns an integer in roughly [-30, +50] range that can be
        added to the scheduler score.
        """
        stats = self.get_stats(node_type)
        if stats.count < MIN_SAMPLES_FOR_STATS:
            return 0

        pred = self.predict(node_type)

        # Blend prediction with prior based on confidence
        c = pred.confidence
        blended_success = (
            pred.success_probability * c
            + DEFAULT_PRIOR_SUCCESS * (1 - c)
        )
        blended_duration = (
            pred.expected_duration_ms * c
            + DEFAULT_PRIOR_DURATION_MS * (1 - c)
        )

        # Apply calibration adjustment if available
        cal = self.get_calibration(node_type)
        if cal.sample_count >= 3 and cal.calibration_score < 0.8:
            # Dampen predictions from poorly calibrated types
            dampening = cal.calibration_score / 0.8  # 0.0 → 0.0, 0.4 → 0.5, 0.79 → 0.99
            blended_success = (
                blended_success * dampening
                + DEFAULT_PRIOR_SUCCESS * (1 - dampening)
            )

        success_boost = int(blended_success * INTELLIGENCE_MULTIPLIER)
        duration_penalty = min(
            int(blended_duration / 10000) * DURATION_PENALTY_PER_10S,
            MAX_DURATION_PENALTY,
        )

        # Phase 8.3C: resource cost penalty
        resource_penalty = self.resource_cost_score(node_type)

        return success_boost - duration_penalty - resource_penalty

    def expected_duration_ms(self, node_type: str) -> float:
        """Predicted duration in ms for a given activity type."""
        stats = self.get_stats(node_type)
        if stats.count >= MIN_SAMPLES_FOR_STATS:
            return stats.avg_duration_ms
        return 0.0

    def success_probability(self, node_type: str) -> float:
        """Predicted success probability for a given activity type."""
        stats = self.get_stats(node_type)
        if stats.count >= MIN_SAMPLES_FOR_STATS:
            return stats.success_rate
        return DEFAULT_PRIOR_SUCCESS

    def get_prediction_data(
        self, node_type: str, limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get raw prediction→outcome pairs for analysis."""
        with self._lock, sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                """SELECT id, activity_id, predicted_success, predicted_duration_ms,
                          prediction_source, success, duration_ms, completed_at
                   FROM activity_stats
                   WHERE node_type = ? AND predicted_success IS NOT NULL
                   ORDER BY completed_at DESC
                   LIMIT ?""",
                (node_type, limit),
            ).fetchall()
        return [
            {
                "id": r[0],
                "activity_id": r[1],
                "predicted_success": r[2],
                "predicted_duration_ms": r[3],
                "prediction_source": r[4],
                "actual_success": bool(r[5]),
                "actual_duration_ms": r[6],
                "completed_at": r[7],
            }
            for r in rows
        ]

    # ── Maintenance ──────────────────────────────────────────────────────────

    def clear(self) -> None:
        """Clear all recorded stats (testing)."""
        with self._lock, sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM activity_stats")
        self._cache.clear()
        self._cache_valid = False

    def count(self) -> int:
        """Total number of recorded activity outcomes."""
        with self._lock, sqlite3.connect(self._db_path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM activity_stats").fetchone()
        return row[0] if row else 0

    # ── Internal ─────────────────────────────────────────────────────────────

    def _ensure_cache(self) -> None:
        if self._cache_valid:
            return
        with self._lock, sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                """SELECT node_type,
                          COUNT(*) as cnt,
                          SUM(success) as successes,
                          AVG(CASE WHEN success=1 THEN duration_ms END) as avg_success_dur,
                          AVG(duration_ms) as avg_dur,
                          MIN(duration_ms) as min_dur,
                          MAX(duration_ms) as max_dur
                   FROM activity_stats
                   GROUP BY node_type
                   ORDER BY cnt DESC"""
            ).fetchall()

        self._cache.clear()
        for row in rows:
            node_type = row[0]
            count = row[1] or 0
            successes = row[2] or 0
            failures = count - successes
            avg_dur = float(row[4] or 0.0)
            min_dur = float(row[5] or 0.0)
            max_dur = float(row[6] or 0.0)

            self._cache[node_type] = TypeStats(
                node_type=node_type,
                count=count,
                success_count=successes,
                failure_count=failures,
                success_rate=successes / count if count > 0 else DEFAULT_PRIOR_SUCCESS,
                avg_duration_ms=avg_dur,
                median_duration_ms=avg_dur,
                min_duration_ms=min_dur,
                max_duration_ms=max_dur,
            )
        self._cache_valid = True
