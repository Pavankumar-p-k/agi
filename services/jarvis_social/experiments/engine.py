"""
experiments/engine.py — Experiment Engine + Intervention System
================================================================
Experiment engine:
  - Selects ONE trait, shifts ≤ 0.05, tests 20 messages
  - If engagement improves → keep, else → revert
  - Hard-locked traits never touched

Intervention system:
  - Detects engagement drop, conflict spike, cold responses
  - Auto micro-adjusts ≤ 0.05
  - Logs with severity LOW/MEDIUM/HIGH
  - HIGH → flags for manual takeover
"""
from __future__ import annotations
import logging, time, random, sqlite3
from dataclasses import dataclass
from typing import Optional
from db.schema import connect, clamp, DB_PATH
from friends.registry import FriendRegistry

logger = logging.getLogger(__name__)

EXPERIMENT_MESSAGES = 20
MAX_EXPERIMENT_SHIFT = 0.05
MAX_INTERVENTION_SHIFT = 0.05

# Traits allowed in experiments (locked traits excluded)
EXPERIMENTABLE_TRAITS = ["humor","caring","formality","emoji","energy","directness"]
LOCKED_TRAITS = {"aggression","manipulation","dependency","jealousy","conflict_escalation"}


# ══════════════════════════════════════════════════
#  EXPERIMENT ENGINE
# ══════════════════════════════════════════════════

@dataclass
class Experiment:
    id:               int
    friend_id:        str
    trait_name:       str
    original_value:   float
    test_value:       float
    messages_tested:  int
    target_messages:  int
    engagement_before: float
    engagement_after:  float
    result:           str   # pending|kept|reverted


class ExperimentEngine:

    def __init__(self, db_path: str = DB_PATH):
        self._db  = db_path
        self._reg = FriendRegistry(db_path)

    def start_experiment(self, friend_id: str,
                          trait: str = None) -> Optional[Experiment]:
        """
        Start a new experiment on a randomly selected (or specified) trait.
        Returns None if an experiment is already running for this friend.
        """
        if self._has_active_experiment(friend_id):
            logger.debug("[Experiment] Already running for %s", friend_id)
            return None

        traits = self._reg.get_traits(friend_id)
        if not traits:
            return None

        # Select trait
        if trait and trait in EXPERIMENTABLE_TRAITS and trait not in LOCKED_TRAITS:
            selected = trait
        else:
            selected = random.choice(EXPERIMENTABLE_TRAITS)

        original = float(traits.get(selected, 0.5))

        # Random shift direction, clamped
        shift = random.uniform(0.02, MAX_EXPERIMENT_SHIFT)
        direction = random.choice([-1, 1])
        test_val = clamp(original + direction * shift)

        # Get current engagement baseline
        eng_before = self._get_recent_engagement(friend_id)

        # Store experiment
        con = connect(self._db)
        cur = con.execute("""
            INSERT INTO experiment_history
            (friend_id, trait_name, original_value, test_value,
             target_messages, engagement_before, result, started_at)
            VALUES (?,?,?,?,?,?,'pending',?)
        """, (friend_id, selected, original, test_val,
              EXPERIMENT_MESSAGES, eng_before, time.time()))
        exp_id = cur.lastrowid
        con.commit()
        con.close()

        # Apply test value
        self._reg.update_trait(friend_id, selected, test_val)
        logger.info("[Experiment] Started: %s.%s %.3f→%.3f",
                     friend_id, selected, original, test_val)

        return Experiment(exp_id, friend_id, selected, original, test_val,
                           0, EXPERIMENT_MESSAGES, eng_before, 0.0, "pending")

    def tick(self, friend_id: str) -> Optional[str]:
        """
        Call after each message sent during an experiment.
        Returns 'kept' or 'reverted' when experiment ends, None if still running.
        """
        exp = self._get_active_experiment(friend_id)
        if not exp:
            return None

        # Increment counter
        new_count = exp["messages_tested"] + 1
        con = connect(self._db)
        con.execute("UPDATE experiment_history SET messages_tested=? WHERE id=?",
                    (new_count, exp["id"]))
        con.commit()
        con.close()

        if new_count >= exp["target_messages"]:
            return self._conclude(exp)
        return None

    def _conclude(self, exp: dict) -> str:
        eng_after = self._get_recent_engagement(exp["friend_id"])
        result = "kept" if eng_after >= exp["engagement_before"] else "reverted"

        if result == "reverted":
            # Restore original trait
            self._reg.update_trait(exp["friend_id"], exp["trait_name"],
                                    exp["original_value"])
            logger.info("[Experiment] Reverted %s.%s → %.3f",
                         exp["friend_id"], exp["trait_name"], exp["original_value"])
        else:
            logger.info("[Experiment] Kept %s.%s = %.3f (eng %.3f→%.3f)",
                         exp["friend_id"], exp["trait_name"],
                         exp["test_value"], exp["engagement_before"], eng_after)

        con = connect(self._db)
        con.execute("""
            UPDATE experiment_history
            SET result=?, engagement_after=?, ended_at=? WHERE id=?
        """, (result, eng_after, time.time(), exp["id"]))
        con.commit()
        con.close()
        return result

    def get_history(self, friend_id: str, limit: int = 20) -> list[dict]:
        con = connect(self._db)
        rows = con.execute(
            "SELECT * FROM experiment_history WHERE friend_id=? ORDER BY started_at DESC LIMIT ?",
            (friend_id, limit)
        ).fetchall()
        con.close()
        return [dict(r) for r in rows]

    def _has_active_experiment(self, friend_id: str) -> bool:
        return self._get_active_experiment(friend_id) is not None

    def _get_active_experiment(self, friend_id: str) -> Optional[dict]:
        con = connect(self._db)
        row = con.execute(
            "SELECT * FROM experiment_history WHERE friend_id=? AND result='pending' LIMIT 1",
            (friend_id,)
        ).fetchone()
        con.close()
        return dict(row) if row else None

    def _get_recent_engagement(self, friend_id: str) -> float:
        con = connect(self._db)
        row = con.execute(
            "SELECT AVG(engagement) as avg_e FROM metadata_logs "
            "WHERE friend_id=? AND timestamp > ?",
            (friend_id, time.time() - 7*86400)
        ).fetchone()
        con.close()
        return float(row["avg_e"]) if row and row["avg_e"] else 0.5


# ══════════════════════════════════════════════════
#  INTERVENTION ENGINE
# ══════════════════════════════════════════════════

@dataclass
class Intervention:
    friend_id:      str
    trigger_reason: str
    severity:       str   # LOW|MEDIUM|HIGH
    trait_adjusted: str = ""
    old_value:      float = 0.0
    new_value:      float = 0.0
    manual_suggested: bool = False


class InterventionEngine:

    THRESHOLDS = {
        "engagement_drop":  {"LOW": 0.35, "MEDIUM": 0.25, "HIGH": 0.15},
        "conflict_spike":   {"LOW": 0.3,  "MEDIUM": 0.5,  "HIGH": 0.7},
        "cold_response":    {"LOW": 0.2,  "MEDIUM": 0.15, "HIGH": 0.10},
    }

    def __init__(self, db_path: str = DB_PATH,
                 notify_fn=None):
        self._db  = db_path
        self._reg = FriendRegistry(db_path)
        self._notify = notify_fn   # callback for admin notifications

    def check(self, friend_id: str) -> Optional[Intervention]:
        """
        Run all detectors for a friend. Returns Intervention if triggered.
        """
        metrics = self._get_metrics(friend_id)
        if not metrics:
            return None

        trigger, severity = self._detect(metrics)
        if not trigger:
            return None

        intervention = self._respond(friend_id, trigger, severity, metrics)
        self._log(intervention)

        if intervention.severity == "HIGH":
            msg = f"[JARVIS] HIGH severity intervention for {friend_id}: {trigger}"
            logger.warning(msg)
            if self._notify:
                self._notify(intervention)

        return intervention

    def _detect(self, metrics: dict) -> tuple[str, str]:
        """Returns (trigger_reason, severity) or ('', '')."""
        eng = metrics.get("avg_engagement", 0.5)
        conflict = metrics.get("avg_conflict", 0.0)
        sentiment = metrics.get("avg_sentiment", 0.5)

        # Engagement drop
        t = self.THRESHOLDS["engagement_drop"]
        if eng < t["HIGH"]:   return "engagement_drop", "HIGH"
        if eng < t["MEDIUM"]: return "engagement_drop", "MEDIUM"
        if eng < t["LOW"]:    return "engagement_drop", "LOW"

        # Conflict spike
        t = self.THRESHOLDS["conflict_spike"]
        if conflict > t["HIGH"]:   return "conflict_spike", "HIGH"
        if conflict > t["MEDIUM"]: return "conflict_spike", "MEDIUM"
        if conflict > t["LOW"]:    return "conflict_spike", "LOW"

        # Cold response (low sentiment)
        t = self.THRESHOLDS["cold_response"]
        if sentiment < t["HIGH"]:   return "cold_response", "HIGH"
        if sentiment < t["MEDIUM"]: return "cold_response", "MEDIUM"
        if sentiment < t["LOW"]:    return "cold_response", "LOW"

        return "", ""

    def _respond(self, friend_id: str, trigger: str,
                  severity: str, metrics: dict) -> Intervention:
        traits = self._reg.get_traits(friend_id)
        trait_to_adjust = self._pick_trait(trigger)
        old_val = float(traits.get(trait_to_adjust, 0.5))

        # Adjustment direction
        if trigger == "engagement_drop":
            direction = 1   # increase energy/humor
        elif trigger == "conflict_spike":
            direction = -1  # decrease energy/directness
        else:  # cold_response
            direction = 1   # increase caring/warmth

        # Scale shift by severity
        shift_map = {"LOW": 0.02, "MEDIUM": 0.04, "HIGH": 0.05}
        shift = shift_map.get(severity, 0.02) * direction
        new_val = clamp(old_val + shift)

        # Only adjust for LOW/MEDIUM automatically; HIGH = suggest manual
        if severity != "HIGH":
            try:
                self._reg.update_trait(friend_id, trait_to_adjust, new_val)
            except ValueError:
                raise RuntimeError("Placeholder/swallowed exception removed")

        return Intervention(
            friend_id=friend_id,
            trigger_reason=trigger,
            severity=severity,
            trait_adjusted=trait_to_adjust,
            old_value=old_val,
            new_value=new_val if severity != "HIGH" else old_val,
            manual_suggested=(severity == "HIGH"),
        )

    def _pick_trait(self, trigger: str) -> str:
        trait_map = {
            "engagement_drop":  "energy",
            "conflict_spike":   "directness",
            "cold_response":    "caring",
        }
        return trait_map.get(trigger, "energy")

    def _get_metrics(self, friend_id: str) -> dict:
        try:
            con = connect(self._db)
            row = con.execute("""
                SELECT AVG(sentiment) as avg_sentiment,
                       AVG(conflict_flag) as avg_conflict,
                       AVG(engagement) as avg_engagement,
                       COUNT(*) as count
                FROM metadata_logs
                WHERE friend_id=? AND timestamp > ?
            """, (friend_id, time.time() - 3*86400)).fetchone()
            con.close()
            if not row or not row["count"]:
                return {}
            return dict(row)
        except Exception:
            return {}

    def _log(self, iv: Intervention) -> None:
        try:
            con = connect(self._db)
            con.execute("""
                INSERT INTO intervention_logs
                (friend_id, trigger_reason, severity, trait_adjusted,
                 old_value, new_value, manual_suggested, timestamp)
                VALUES (?,?,?,?,?,?,?,?)
            """, (iv.friend_id, iv.trigger_reason, iv.severity,
                   iv.trait_adjusted, iv.old_value, iv.new_value,
                   int(iv.manual_suggested), time.time()))
            con.commit()
            con.close()
        except Exception as e:
            logger.warning("[Intervention] Log error: %s", e)

    def get_logs(self, friend_id: str = None, limit: int = 50) -> list[dict]:
        con = connect(self._db)
        if friend_id:
            rows = con.execute(
                "SELECT * FROM intervention_logs WHERE friend_id=? ORDER BY timestamp DESC LIMIT ?",
                (friend_id, limit)
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM intervention_logs ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
        con.close()
        return [dict(r) for r in rows]

    def get_unresolved_high(self) -> list[dict]:
        con = connect(self._db)
        rows = con.execute(
            "SELECT * FROM intervention_logs WHERE severity='HIGH' AND resolved=0 ORDER BY timestamp DESC"
        ).fetchall()
        con.close()
        return [dict(r) for r in rows]
