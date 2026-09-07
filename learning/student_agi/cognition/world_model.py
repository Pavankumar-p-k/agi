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

"""
cognition/world_model.py
═══════════════════════════════════════════════════════════════════════
STUDENT AGI — World Model & Cognitive Engines

This is what makes the Student AGI think differently from normal LLMs.

Normal LLM:  input → predict next token → output
Student AGI: input → understand → reason causally → analogize →
             check consistency → form model → answer → evaluate self

Engines:
  1. WorldModel      — mental model of how things work
  2. CausalEngine    — understands cause → effect chains
  3. AnalogyEngine   — learns new things by analogy to known things
  4. ConsistencyChecker — catches contradictions in own knowledge
  5. MetaCognition   — thinks about its own thinking
═══════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations
import json, logging, math, re, sqlite3, time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("student_agi.cognition")

DB_PATH = Path("data/student/world_model.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────
#  WORLD MODEL — how does the student understand the world?
# ─────────────────────────────────────────────────────────────────────

@dataclass
class WorldNode:
    """One concept/entity in the world model."""
    name:        str
    category:    str   # person | place | thing | concept | event | process
    properties:  dict  = field(default_factory=dict)
    confidence:  float = 0.5
    times_seen:  int   = 0


@dataclass
class WorldEdge:
    """Relationship between two concepts."""
    source:      str
    target:      str
    relation:    str   # causes | is_a | has | part_of | leads_to | opposite_of
    strength:    float = 0.5
    confidence:  float = 0.5


class WorldModel:
    """
    Mental model of the world.
    Built up incrementally as student learns.
    Nodes = concepts, Edges = relationships.
    """

    def __init__(self):
        self._init_db()
        self._node_cache: dict[str, WorldNode] = {}

    def _init_db(self):
        con = sqlite3.connect(DB_PATH)
        con.executescript("""
            CREATE TABLE IF NOT EXISTS nodes (
                name       TEXT PRIMARY KEY,
                category   TEXT DEFAULT 'concept',
                properties TEXT DEFAULT '{}',
                confidence REAL DEFAULT 0.5,
                times_seen INTEGER DEFAULT 0,
                created_at REAL DEFAULT (unixepoch())
            );
            CREATE TABLE IF NOT EXISTS edges (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                source     TEXT,
                target     TEXT,
                relation   TEXT,
                strength   REAL DEFAULT 0.5,
                confidence REAL DEFAULT 0.5,
                created_at REAL DEFAULT (unixepoch()),
                UNIQUE(source, target, relation)
            );
        """)
        con.commit()
        con.close()

    def add_concept(self, name: str, category: str = "concept",
                     properties: dict = None, confidence: float = 0.5):
        """Add or update a concept in the world model."""
        con = sqlite3.connect(DB_PATH)
        con.execute("""
            INSERT INTO nodes (name, category, properties, confidence)
            VALUES (?,?,?,?)
            ON CONFLICT(name) DO UPDATE SET
                times_seen=times_seen+1,
                confidence=MIN(0.99, (confidence*0.7 + excluded.confidence*0.3))
        """, (name, category,
              json.dumps(properties or {}), confidence))
        con.commit()
        con.close()

        self._node_cache[name] = WorldNode(
            name=name, category=category,
            properties=properties or {},
            confidence=confidence)

    def add_relationship(self, source: str, target: str,
                          relation: str, confidence: float = 0.6):
        """Add a relationship between concepts."""
        # Make sure both nodes exist
        self.add_concept(source)
        self.add_concept(target)

        con = sqlite3.connect(DB_PATH)
        con.execute("""
            INSERT INTO edges (source, target, relation, confidence)
            VALUES (?,?,?,?)
            ON CONFLICT(source,target,relation) DO UPDATE SET
                confidence=MIN(0.99, confidence+0.05),
                strength=MIN(1.0, strength+0.05)
        """, (source, target, relation, confidence))
        con.commit()
        con.close()

    def get_related(self, concept: str,
                     relation: str = None,
                     min_conf: float = 0.3) -> list[dict]:
        """Find concepts related to this one."""
        con = sqlite3.connect(DB_PATH)
        if relation:
            rows = con.execute(
                "SELECT target, relation, confidence FROM edges "
                "WHERE source=? AND relation=? AND confidence>=?",
                (concept, relation, min_conf)).fetchall()
        else:
            rows = con.execute(
                "SELECT target, relation, confidence FROM edges "
                "WHERE source=? AND confidence>=?",
                (concept, min_conf)).fetchall()
        con.close()
        return [{"target": r[0], "relation": r[1], "confidence": r[2]}
                for r in rows]

    def concept_count(self) -> int:
        con = sqlite3.connect(DB_PATH)
        n   = con.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        con.close()
        return n

    def strongest_concepts(self, n: int = 10) -> list[str]:
        con  = sqlite3.connect(DB_PATH)
        rows = con.execute(
            "SELECT name FROM nodes ORDER BY confidence*times_seen DESC LIMIT ?",
            (n,)).fetchall()
        con.close()
        return [r[0] for r in rows]


# ─────────────────────────────────────────────────────────────────────
#  CAUSAL ENGINE — understand cause-effect chains
# ─────────────────────────────────────────────────────────────────────

class CausalEngine:
    """
    Builds causal models: A causes B causes C.
    When student learns "X happens because Y", stores causal chain.
    Can answer: "why does X happen?" by tracing the chain.
    """

    def __init__(self, world_model: WorldModel):
        self._world = world_model
        self._chains: list[dict] = []  # [(cause, effect, strength)]

    def add_cause(self, cause: str, effect: str,
                   strength: float = 0.7, context: str = ""):
        """Record: cause → effect."""
        self._world.add_relationship(cause, effect, "causes", strength)
        self._chains.append({
            "cause":    cause,
            "effect":   effect,
            "strength": strength,
            "context":  context,
            "ts":       time.time(),
        })

    def why(self, effect: str, depth: int = 3) -> list[str]:
        """
        Answer 'why does X happen?' by tracing causal chain.
        Returns chain from root cause to effect.
        """
        chain   = []
        current = effect
        visited = set()

        for _ in range(depth):
            if current in visited:
                break
            visited.add(current)

            causes = self._world.get_related(current, relation=None)
            # Find nodes that CAUSE current
            direct_causes = []
            for c in self._chains:
                if c["effect"] == current:
                    direct_causes.append(c["cause"])

            if not direct_causes:
                break
            best_cause = direct_causes[0]
            chain.insert(0, f"{best_cause} → {current}")
            current = best_cause

        return chain if chain else [f"No known cause for {effect}"]

    def what_happens_if(self, cause: str, depth: int = 2) -> list[str]:
        """Answer 'what happens if X?' by tracing effects."""
        effects = []
        current = cause
        visited = set()

        for _ in range(depth):
            if current in visited:
                break
            visited.add(current)
            related = self._world.get_related(current, "causes")
            if not related:
                break
            for r in related[:2]:
                effects.append(f"{current} → {r['target']}")
                current = r["target"]

        return effects if effects else [f"No known effects of {cause}"]


# ─────────────────────────────────────────────────────────────────────
#  ANALOGY ENGINE — learn by analogy
# ─────────────────────────────────────────────────────────────────────

class AnalogyEngine:
    """
    The student learns new things by analogy to what it already knows.
    "A CPU is like the brain of a computer" — stores structural analogy.
    When asked about new concept, finds closest known analogy.
    """

    def __init__(self):
        self._analogies: list[dict] = []

    def add_analogy(self, source: str, target: str,
                     mapping: dict, explanation: str):
        """
        Store: source is like target, where:
          mapping = {source_property: target_property}
        """
        self._analogies.append({
            "source":      source,
            "target":      target,
            "mapping":     mapping,
            "explanation": explanation,
            "uses":        0,
            "ts":          time.time(),
        })

    def find_analogy(self, concept: str) -> Optional[dict]:
        """Find best analogy for an unknown concept."""
        concept_lower = concept.lower()
        best = None
        best_score = 0

        for a in self._analogies:
            # Check if this analogy helps explain the concept
            relevance = sum(1 for word in concept_lower.split()
                           if word in a["source"].lower()
                           or word in a["target"].lower()
                           or word in a["explanation"].lower())
            if relevance > best_score:
                best_score = relevance
                best = a

        if best:
            best["uses"] += 1
            return best
        return None

    def explain_by_analogy(self, concept: str) -> str:
        """Explain concept using best available analogy."""
        analogy = self.find_analogy(concept)
        if analogy:
            return (f"{concept} is similar to {analogy['target']}: "
                    f"{analogy['explanation']}")
        return f"I don't have a good analogy for {concept} yet."

    def analogy_count(self) -> int:
        return len(self._analogies)


# ─────────────────────────────────────────────────────────────────────
#  CONSISTENCY CHECKER — catch contradictions in own knowledge
# ─────────────────────────────────────────────────────────────────────

class ConsistencyChecker:
    """
    Checks for contradictions in the student's knowledge.
    E.g., if student knows "A is true" AND "A is false" → contradiction.
    Resolves by keeping higher-confidence fact and flagging conflict.
    """

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path

    def find_contradictions(self) -> list[dict]:
        """Scan knowledge base for potential contradictions."""
        con  = sqlite3.connect(DB_PATH)
        rows = con.execute(
            "SELECT topic, fact, confidence FROM knowledge "
            "ORDER BY topic, confidence DESC").fetchall()
        con.close()

        contradictions = []
        by_topic: dict[str, list] = {}
        for topic, fact, conf in rows:
            by_topic.setdefault(topic, []).append((fact, conf))

        for topic, facts in by_topic.items():
            if len(facts) < 2:
                continue
            # Simple heuristic: if two facts have opposing words
            negation_pairs = [
                ("is", "is not"), ("has", "has no"), ("can", "cannot"),
                ("always", "never"), ("true", "false"),
                ("increases", "decreases"),
            ]
            for i, (f1, c1) in enumerate(facts):
                for f2, c2 in facts[i+1:]:
                    for pos, neg in negation_pairs:
                        if (pos in f1.lower() and neg in f2.lower()) or \
                           (neg in f1.lower() and pos in f2.lower()):
                            contradictions.append({
                                "topic":  topic,
                                "fact_a": f1[:80],
                                "conf_a": c1,
                                "fact_b": f2[:80],
                                "conf_b": c2,
                                "resolution": f1 if c1 > c2 else f2,
                            })
                            break

        return contradictions[:10]

    def resolve_contradiction(self, topic: str,
                               fact_a: str, fact_b: str,
                               conf_a: float, conf_b: float) -> str:
        """Keep the fact with higher confidence."""
        return fact_a if conf_a >= conf_b else fact_b


# ─────────────────────────────────────────────────────────────────────
#  METACOGNITION — thinking about thinking
# ─────────────────────────────────────────────────────────────────────

class MetaCognition:
    """
    The student monitors its own cognitive processes.
    - Am I understanding this or just memorizing?
    - Am I reasoning correctly?
    - Which topics do I actually understand vs just recall?
    - When should I ask for help vs try myself?
    """

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._thinking_log: list[dict] = []

    def log_thought(self, process: str, question: str,
                     outcome: str, confidence: float):
        self._thinking_log.append({
            "process":    process,   # recall | reason | analogy | guess
            "question":   question[:80],
            "outcome":    outcome[:80],
            "confidence": confidence,
            "ts":         time.time(),
        })
        if len(self._thinking_log) > 100:
            self._thinking_log = self._thinking_log[-80:]

    def should_ask_for_help(self, confidence: float,
                             topic: str) -> bool:
        """Should the student ask the teacher for help?"""
        # Ask for help if very uncertain
        if confidence < 0.25:
            return True
        # Ask for help if topic has many past mistakes
        try:
            con = sqlite3.connect(self._db_path)
            mistake_count = con.execute(
                "SELECT COUNT(*) FROM mistakes WHERE topic=?",
                (topic,)).fetchone()[0]
            con.close()
            if mistake_count >= 3:
                return True
        except Exception as err:
            import logging
            logging.getLogger(__name__).error("Exception swallowed: %s", err)
            raise RuntimeError(f"Exception swallowed: {err}")
        return False

    def am_i_guessing(self, reasoning_trace: list[str]) -> bool:
        """Detect if reasoning is just guessing vs genuine knowledge."""
        guess_signals = [
            "i think", "maybe", "probably", "i'm not sure",
            "i don't know", "i believe", "could be",
        ]
        for thought in reasoning_trace:
            if any(sig in thought.lower() for sig in guess_signals):
                return True
        return False

    def knowledge_depth(self, topic: str) -> str:
        """Is knowledge surface-level or deep?"""
        try:
            con  = sqlite3.connect(self._db_path)
            rows = con.execute(
                "SELECT COUNT(*), AVG(confidence) FROM knowledge WHERE topic=?",
                (topic,)).fetchone()
            con.close()
            count, avg_conf = rows
            if count == 0:
                return "none"
            if count < 3 or avg_conf < 0.4:
                return "surface"
            if count < 8 or avg_conf < 0.7:
                return "intermediate"
            return "deep"
        except Exception:
            return "unknown"

    def thinking_summary(self) -> dict:
        recent = self._thinking_log[-20:]
        if not recent:
            return {"avg_confidence": 0.5, "processes": {}, "guessing_rate": 0}

        avg_conf     = sum(t["confidence"] for t in recent) / len(recent)
        processes    = {}
        guess_count  = 0
        for t in recent:
            p = t["process"]
            processes[p] = processes.get(p, 0) + 1
            if t["confidence"] < 0.3:
                guess_count += 1

        return {
            "avg_confidence": round(avg_conf, 3),
            "processes":      processes,
            "guessing_rate":  round(guess_count / len(recent), 3),
            "thought_count":  len(self._thinking_log),
        }
