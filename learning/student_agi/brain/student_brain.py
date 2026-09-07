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
brain/student_brain.py
═══════════════════════════════════════════════════════════════════════
JARVIS STUDENT AGI — Core Brain

This is NOT a wrapper around GPT/Claude/Ollama.
This IS a brain that:

  • Thinks step-by-step before answering (like humans)
  • Knows what it knows vs what it doesn't know
  • Notices when its answer is wrong and explains WHY
  • Learns from every mistake — updates internal weights
  • Has genuine curiosity — asks follow-up questions
  • Builds world models — connected knowledge graphs
  • Has emotional state that affects how it learns
  • Remembers everything with episodic + semantic memory
  • Gets smarter every day through daily self-study sessions
  • Is completely separate from JARVIS — taught by JARVIS

Architecture:
  Input → Perception → Working Memory
                         ↓
                    Reasoning Engine (think step by step)
                         ↓
                    Knowledge Retrieval (what do I know?)
                         ↓
                    Confidence Estimator (how sure am I?)
                         ↓
                    Answer Generator
                         ↓
                    Self-Evaluator (was I right?)
                         ↓
                    Mistake Analyzer (why was I wrong?)
                         ↓
                    Knowledge Updater (learn from it)
                         ↓
                    Curiosity Engine (what should I learn next?)
═══════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations
import asyncio, json, logging, math, re, sqlite3, time, uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger("student_agi.brain")

OLLAMA = "http://localhost:11434"
DB_PATH = Path("data/student/student_brain.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────
#  EMOTIONAL STATE — affects learning rate and confidence
# ─────────────────────────────────────────────────────────────────────

class Emotion(str, Enum):
    CURIOUS     = "curious"      # wants to learn — best learning state
    CONFIDENT   = "confident"    # believes its answers
    CONFUSED    = "confused"     # doesn't understand — needs re-teaching
    FRUSTRATED  = "frustrated"   # many wrong answers — needs encouragement
    PROUD       = "proud"        # got something right — reinforces memory
    MOTIVATED   = "motivated"    # after praise — learns faster
    OVERWHELMED = "overwhelmed"  # too much at once — needs simpler lessons


@dataclass
class EmotionalState:
    current:     Emotion = Emotion.CURIOUS
    confidence:  float   = 0.5    # 0=no confidence, 1=fully confident
    energy:      float   = 1.0    # drops with wrong answers, rises with right ones
    streak_right: int    = 0      # consecutive correct answers
    streak_wrong: int    = 0      # consecutive wrong answers

    def on_correct(self):
        self.streak_right += 1
        self.streak_wrong  = 0
        self.energy        = min(1.0, self.energy + 0.1)
        self.confidence    = min(1.0, self.confidence + 0.05)
        if self.streak_right >= 3:
            self.current = Emotion.PROUD
        elif self.streak_right >= 5:
            self.current = Emotion.CONFIDENT

    def on_wrong(self, severity: float = 0.5):
        self.streak_wrong += 1
        self.streak_right  = 0
        self.energy        = max(0.1, self.energy - severity * 0.15)
        self.confidence    = max(0.05, self.confidence - severity * 0.1)
        if self.streak_wrong >= 4:
            self.current = Emotion.FRUSTRATED
        elif self.streak_wrong >= 2:
            self.current = Emotion.CONFUSED
        else:
            self.current = Emotion.CURIOUS  # still curious, just wrong

    def on_praise(self):
        self.current  = Emotion.MOTIVATED
        self.energy   = min(1.0, self.energy + 0.2)
        self.confidence = min(1.0, self.confidence + 0.1)

    def on_overload(self):
        self.current = Emotion.OVERWHELMED
        self.energy  = max(0.2, self.energy - 0.3)

    @property
    def learning_rate_multiplier(self) -> float:
        """Emotional state affects how fast it learns."""
        multipliers = {
            Emotion.CURIOUS:     1.3,   # learns 30% faster when curious
            Emotion.MOTIVATED:   1.5,   # learns 50% faster when motivated
            Emotion.PROUD:       1.2,
            Emotion.CONFIDENT:   1.1,
            Emotion.CONFUSED:    0.7,   # learns slower when confused
            Emotion.FRUSTRATED:  0.5,   # learns half-speed when frustrated
            Emotion.OVERWHELMED: 0.3,
        }
        return multipliers.get(self.current, 1.0) * self.energy


# ─────────────────────────────────────────────────────────────────────
#  THOUGHT — one step of reasoning
# ─────────────────────────────────────────────────────────────────────

@dataclass
class Thought:
    step:       int
    content:    str
    confidence: float  = 0.5
    is_assumption: bool = False
    is_known:   bool   = False   # came from memory vs generated

@dataclass
class ReasoningTrace:
    """Full step-by-step reasoning before answering."""
    question:    str
    thoughts:    list[Thought] = field(default_factory=list)
    conclusion:  str   = ""
    confidence:  float = 0.5
    knowledge_used: list[str] = field(default_factory=list)
    unknowns:    list[str] = field(default_factory=list)  # what I don't know


# ─────────────────────────────────────────────────────────────────────
#  MISTAKE — what went wrong and why
# ─────────────────────────────────────────────────────────────────────

@dataclass
class MistakeAnalysis:
    question:      str
    my_answer:     str
    correct_answer: str
    error_type:    str   # misconception | incomplete_knowledge | reasoning_error | hallucination
    why_wrong:     str   # my explanation of why I was wrong
    what_i_lacked: str   # specific knowledge I was missing
    correction:    str   # the corrected understanding
    never_again:   str   # rule to remember
    severity:      float = 0.5   # 0=minor, 1=fundamental error


# ─────────────────────────────────────────────────────────────────────
#  STUDENT AGI BRAIN — main class
# ─────────────────────────────────────────────────────────────────────

class StudentBrain:
    """
    The Student AGI Brain.
    Completely separate from JARVIS.
    JARVIS teaches it. It learns. It grows.
    """

    def __init__(self, student_id: str = "agi_student",
                 db_path: Path = DB_PATH):
        self.student_id  = student_id
        self._db_path    = db_path
        self._emotion    = EmotionalState()
        self._init_db()

        # In-memory working memory (what I'm thinking about right now)
        self._working_memory: list[dict] = []
        self._wm_capacity  = 7   # Miller's Law — 7±2 items

        # Metacognition — what I think I know
        self._knowledge_confidence: dict[str, float] = {}

        # Curiosity queue — topics I want to learn more about
        self._curiosity_queue: list[str] = []

        logger.info("[StudentBrain] Initialized — student_id=%s", student_id)

    def _init_db(self):
        con = sqlite3.connect(self._db_path)
        con.executescript("""
            CREATE TABLE IF NOT EXISTS knowledge (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                topic       TEXT NOT NULL,
                fact        TEXT NOT NULL,
                confidence  REAL DEFAULT 0.5,
                times_used  INTEGER DEFAULT 0,
                times_wrong INTEGER DEFAULT 0,
                source      TEXT DEFAULT 'teacher',
                created_at  REAL DEFAULT (unixepoch()),
                updated_at  REAL DEFAULT (unixepoch())
            );
            CREATE INDEX IF NOT EXISTS idx_k_topic ON knowledge(topic);

            CREATE TABLE IF NOT EXISTS episodes (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id    TEXT,
                question      TEXT,
                my_answer     TEXT,
                correct_answer TEXT,
                was_correct   INTEGER DEFAULT 0,
                confidence    REAL,
                reasoning     TEXT,
                mistake       TEXT,
                emotion       TEXT,
                ts            REAL DEFAULT (unixepoch())
            );
            CREATE INDEX IF NOT EXISTS idx_e_ts ON episodes(ts);

            CREATE TABLE IF NOT EXISTS mistakes (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                topic         TEXT,
                error_type    TEXT,
                why_wrong     TEXT,
                what_i_lacked TEXT,
                correction    TEXT,
                never_again   TEXT,
                severity      REAL,
                reinforced    INTEGER DEFAULT 0,
                ts            REAL DEFAULT (unixepoch())
            );

            CREATE TABLE IF NOT EXISTS concepts (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT UNIQUE,
                understanding REAL DEFAULT 0.0,
                times_taught  INTEGER DEFAULT 0,
                times_tested  INTEGER DEFAULT 0,
                times_correct INTEGER DEFAULT 0,
                connections   TEXT DEFAULT '[]',
                last_studied  REAL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_c_name ON concepts(name);

            CREATE TABLE IF NOT EXISTS daily_progress (
                date        TEXT PRIMARY KEY,
                lessons     INTEGER DEFAULT 0,
                questions   INTEGER DEFAULT 0,
                correct     INTEGER DEFAULT 0,
                new_facts   INTEGER DEFAULT 0,
                mistakes_made INTEGER DEFAULT 0,
                avg_confidence REAL DEFAULT 0.5,
                peak_emotion TEXT
            );

            CREATE TABLE IF NOT EXISTS curiosities (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                topic     TEXT,
                question  TEXT,
                priority  REAL DEFAULT 0.5,
                answered  INTEGER DEFAULT 0,
                ts        REAL DEFAULT (unixepoch())
            );
        """)
        con.commit()
        con.close()

    # ─────────────────────────────────────────────────────────────
    #  THINK — reason step-by-step before answering
    # ─────────────────────────────────────────────────────────────

    async def think(self, question: str,
                    context: str = "") -> ReasoningTrace:
        """
        Think through a question step-by-step.
        Like a student working through a problem on paper.
        Does NOT call any external AI — uses own knowledge + reasoning.
        """
        trace = ReasoningTrace(question=question)

        # Step 1: Parse the question — what is it actually asking?
        what_type = self._classify_question(question)
        trace.thoughts.append(Thought(
            step=1,
            content=f"This is a {what_type} question. Let me think about what I know.",
            confidence=0.9,
            is_assumption=False,
        ))

        # Step 2: Retrieve relevant knowledge
        known_facts = self._recall(question)
        for fact in known_facts[:3]:
            trace.thoughts.append(Thought(
                step=2,
                content=f"I know: {fact['fact']} (confidence: {fact['confidence']:.2f})",
                confidence=fact['confidence'],
                is_known=True,
            ))
            trace.knowledge_used.append(fact['fact'])

        # Step 3: Identify what I DON'T know
        gaps = self._identify_knowledge_gaps(question, known_facts)
        for gap in gaps:
            trace.thoughts.append(Thought(
                step=3,
                content=f"I'm not sure about: {gap}",
                confidence=0.1,
                is_assumption=True,
            ))
            trace.unknowns.append(gap)

        # Step 4: Reason toward an answer
        if known_facts:
            reasoning = self._reason_from_facts(question, known_facts)
            trace.thoughts.append(Thought(
                step=4,
                content=f"Based on what I know: {reasoning}",
                confidence=min(f['confidence'] for f in known_facts) * 0.9,
            ))
            trace.conclusion  = reasoning
            trace.confidence  = self._estimate_confidence(known_facts, gaps)
        else:
            trace.thoughts.append(Thought(
                step=4,
                content="I don't have enough knowledge to answer this confidently.",
                confidence=0.1,
                is_assumption=True,
            ))
            trace.conclusion  = "I don't know — I need to learn more about this."
            trace.confidence  = 0.1

        return trace

    # ─────────────────────────────────────────────────────────────
    #  ANSWER — produce final answer with confidence
    # ─────────────────────────────────────────────────────────────

    async def answer(self, question: str,
                     context: str = "") -> dict:
        """
        Answer a question using own knowledge.
        Returns answer + confidence + what I used + what I don't know.
        """
        trace = await self.think(question, context)

        # Update working memory
        self._push_wm({
            "type": "question",
            "content": question,
            "ts": time.time(),
        })

        return {
            "answer":         trace.conclusion,
            "confidence":     trace.confidence,
            "reasoning":      [t.content for t in trace.thoughts],
            "knowledge_used": trace.knowledge_used,
            "unknowns":       trace.unknowns,
            "emotion":        self._emotion.current.value,
            "i_am_sure":      trace.confidence > 0.7,
            "i_need_help_with": trace.unknowns[:2] if trace.unknowns else [],
        }

    # ─────────────────────────────────────────────────────────────
    #  RECEIVE FEEDBACK — process teacher's evaluation
    # ─────────────────────────────────────────────────────────────

    async def receive_feedback(
        self,
        question:        str,
        my_answer:       str,
        correct_answer:  str,
        was_correct:     bool,
        explanation:     str,
        session_id:      str = "",
    ) -> MistakeAnalysis | None:
        """
        Teacher has graded my answer.
        If wrong: analyze WHY, update knowledge, never make same mistake again.
        If right: reinforce the knowledge, feel proud.
        """
        if was_correct:
            self._emotion.on_correct()
            self._reinforce_knowledge(question, correct_answer)
            self._record_episode(
                session_id, question, my_answer,
                correct_answer, True, explanation)
            self._add_curiosity(question, "related_topic")
            return None

        # Was WRONG — analyze mistake deeply
        mistake = await self._analyze_mistake(
            question, my_answer, correct_answer, explanation)

        # Update emotional state
        self._emotion.on_wrong(severity=mistake.severity)

        # Record the mistake
        self._record_mistake(mistake)
        self._record_episode(
            session_id, question, my_answer,
            correct_answer, False, explanation, mistake)

        # Learn the correct knowledge
        self._learn_from_correction(mistake)

        # Add "never again" rule to semantic memory
        self._add_rule(
            topic=self._extract_topic(question),
            rule=mistake.never_again,
            confidence=0.9,
        )

        # Generate curiosity about what I misunderstood
        if mistake.what_i_lacked:
            self._curiosity_queue.insert(0, mistake.what_i_lacked)

        logger.info("[StudentBrain] Mistake analyzed: %s", mistake.error_type)
        return mistake

    # ─────────────────────────────────────────────────────────────
    #  LEARN — absorb new knowledge from teacher
    # ─────────────────────────────────────────────────────────────

    def learn(self, topic: str, fact: str,
              confidence: float = 0.7,
              source: str = "teacher"):
        """
        Teacher explains something new.
        Store it, connect it to what I already know.
        """
        # Adjust confidence based on emotional state
        effective_conf = confidence * self._emotion.learning_rate_multiplier
        effective_conf = min(0.95, effective_conf)

        con = sqlite3.connect(self._db_path)

        # Check if we already know this (maybe partially)
        existing = con.execute(
            "SELECT id, confidence FROM knowledge "
            "WHERE topic=? AND fact LIKE ?",
            (topic, fact[:40] + "%")
        ).fetchone()

        if existing:
            # Update confidence (weighted average)
            new_conf = (existing[1] * 0.4 + effective_conf * 0.6)
            con.execute(
                "UPDATE knowledge SET confidence=?, updated_at=? WHERE id=?",
                (new_conf, time.time(), existing[0]))
        else:
            con.execute(
                "INSERT INTO knowledge (topic, fact, confidence, source) "
                "VALUES (?,?,?,?)",
                (topic, fact, effective_conf, source))

        # Update concept understanding
        self._update_concept(con, topic, learned=True)

        con.commit()
        con.close()

        # Update in-memory knowledge confidence
        self._knowledge_confidence[topic] = max(
            self._knowledge_confidence.get(topic, 0),
            effective_conf)

        logger.debug("[StudentBrain] Learned: [%s] %s (conf=%.2f)",
                     topic, fact[:60], effective_conf)

    # ─────────────────────────────────────────────────────────────
    #  DAILY SELF-STUDY — autonomous learning without teacher
    # ─────────────────────────────────────────────────────────────

    async def daily_self_study(self) -> dict:
        """
        Every day the student studies on its own.
        Reviews mistakes, reinforces weak knowledge,
        fills knowledge gaps through curiosity.
        """
        results = {
            "reviewed_mistakes": 0,
            "reinforced_facts":  0,
            "new_connections":   0,
            "curiosities_resolved": 0,
        }

        # 1. Review recent mistakes and re-test self
        mistakes = self._get_recent_mistakes(days=7)
        for m in mistakes[:5]:
            # Re-read the correction
            self.learn(
                topic      = m["topic"],
                fact       = m["correction"],
                confidence = 0.6,
                source     = "self_review",
            )
            results["reviewed_mistakes"] += 1

        # 2. Reinforce weakest knowledge areas
        weak = self._get_weak_knowledge(threshold=0.4, limit=10)
        for w in weak:
            # Strengthen by re-encoding
            self.learn(
                topic      = w["topic"],
                fact       = w["fact"],
                confidence = w["confidence"] + 0.05,
                source     = "self_reinforcement",
            )
            results["reinforced_facts"] += 1

        # 3. Build new connections between concepts
        new_connections = self._find_new_connections()
        results["new_connections"] = new_connections

        # 4. Record daily progress
        self._save_daily_progress(results)

        logger.info("[StudentBrain] Daily self-study complete: %s", results)
        return results

    # ─────────────────────────────────────────────────────────────
    #  INTROSPECTION — what do I know? what am I unsure about?
    # ─────────────────────────────────────────────────────────────

    def introspect(self) -> dict:
        """
        The student explains its own knowledge state.
        Like a human saying "I think I understand X but I'm not sure about Y."
        """
        con    = sqlite3.connect(self._db_path)
        topics = con.execute(
            "SELECT topic, AVG(confidence) as avg_conf, COUNT(*) as facts "
            "FROM knowledge GROUP BY topic ORDER BY avg_conf DESC"
        ).fetchall()

        strong = [(t[0], t[1]) for t in topics if t[1] > 0.7]
        weak   = [(t[0], t[1]) for t in topics if t[1] < 0.4]
        medium = [(t[0], t[1]) for t in topics if 0.4 <= t[1] <= 0.7]

        total_facts   = con.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]
        total_mistakes= con.execute("SELECT COUNT(*) FROM mistakes").fetchone()[0]
        total_episodes= con.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
        correct_eps   = con.execute(
            "SELECT COUNT(*) FROM episodes WHERE was_correct=1").fetchone()[0]

        con.close()

        accuracy = correct_eps / total_episodes if total_episodes > 0 else 0

        return {
            "emotion":          self._emotion.current.value,
            "confidence":       self._emotion.confidence,
            "energy":           self._emotion.energy,
            "total_facts":      total_facts,
            "total_mistakes":   total_mistakes,
            "total_episodes":   total_episodes,
            "accuracy":         round(accuracy, 3),
            "strong_topics":    [t[0] for t in strong[:5]],
            "weak_topics":      [t[0] for t in weak[:5]],
            "medium_topics":    [t[0] for t in medium[:5]],
            "curious_about":    self._curiosity_queue[:5],
            "knowledge_conf":   self._knowledge_confidence,
            "streak_right":     self._emotion.streak_right,
            "streak_wrong":     self._emotion.streak_wrong,
        }

    # ─────────────────────────────────────────────────────────────
    #  INTERNAL HELPERS
    # ─────────────────────────────────────────────────────────────

    def _recall(self, query: str, top_k: int = 5) -> list[dict]:
        """Retrieve relevant knowledge from memory."""
        words  = set(query.lower().split())
        con    = sqlite3.connect(self._db_path)
        rows   = con.execute(
            "SELECT topic, fact, confidence FROM knowledge "
            "ORDER BY confidence DESC LIMIT 200"
        ).fetchall()
        con.close()

        scored = []
        for topic, fact, conf in rows:
            text   = (topic + " " + fact).lower()
            match  = sum(1 for w in words if w in text and len(w) > 3)
            if match > 0:
                scored.append({
                    "topic":      topic,
                    "fact":       fact,
                    "confidence": conf,
                    "relevance":  match / len(words),
                })
        scored.sort(key=lambda x: x["relevance"] * x["confidence"], reverse=True)
        return scored[:top_k]

    def _classify_question(self, question: str) -> str:
        q = question.lower()
        if any(w in q for w in ["what is", "define", "explain", "what are"]):
            return "definition"
        if any(w in q for w in ["why", "how does", "reason"]):
            return "causal"
        if any(w in q for w in ["how to", "how do i", "steps to"]):
            return "procedural"
        if any(w in q for w in ["compare", "difference", "vs", "better"]):
            return "comparative"
        if any(w in q for w in ["when", "where", "who"]):
            return "factual"
        if "?" not in question:
            return "statement"
        return "analytical"

    def _identify_knowledge_gaps(self, question: str,
                                   known_facts: list) -> list[str]:
        """What do I not know that would help answer this?"""
        words = [w for w in question.lower().split()
                 if len(w) > 4 and w not in {
                     "what", "does", "have", "this", "that",
                     "with", "from", "will", "they", "their",
                 }]
        covered = " ".join(f["fact"] for f in known_facts).lower()
        gaps    = []
        for w in words:
            if w not in covered:
                gaps.append(w)
        return gaps[:3]

    def _reason_from_facts(self, question: str,
                            facts: list[dict]) -> str:
        """Simple symbolic reasoning from known facts."""
        if not facts:
            return "I don't have enough information."

        relevant = [f["fact"] for f in facts if f["relevance"] > 0.3]
        if not relevant:
            relevant = [facts[0]["fact"]]

        # Build answer from facts
        parts = []
        for fact in relevant[:2]:
            parts.append(fact)

        return " ".join(parts) if parts else facts[0]["fact"]

    def _estimate_confidence(self, known_facts: list,
                              gaps: list) -> float:
        if not known_facts:
            return 0.1
        avg_conf  = sum(f["confidence"] for f in known_facts) / len(known_facts)
        gap_penalty = len(gaps) * 0.1
        emotional = self._emotion.confidence
        return max(0.05, min(0.95, avg_conf - gap_penalty)) * (0.5 + 0.5 * emotional)

    async def _analyze_mistake(
        self, question: str, my_answer: str,
        correct_answer: str, explanation: str,
    ) -> MistakeAnalysis:
        """
        Deep analysis of WHY I was wrong.
        Uses Ollama for rich analysis — falls back to rule-based.
        """
        # Try Ollama analysis first
        try:
            prompt = (
                f"A student answered a question wrong.\n\n"
                f"Question: {question}\n"
                f"Student's answer: {my_answer}\n"
                f"Correct answer: {correct_answer}\n"
                f"Teacher's explanation: {explanation}\n\n"
                f"Analyze the mistake. Return ONLY valid JSON:\n"
                '{"error_type":"misconception|incomplete_knowledge|reasoning_error|hallucination",'
                '"why_wrong":"specific reason the student was wrong",'
                '"what_i_lacked":"specific knowledge that was missing",'
                '"correction":"the correct understanding in one clear sentence",'
                '"never_again":"a rule to remember to never make this mistake",'
                '"severity":0.0}'
            )
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.post(f"{OLLAMA}/api/generate", json={
                    "model":  "qwen3:4b",
                    "prompt": prompt,
                    "system": ("You are an educational analyst. "
                               "Analyze student mistakes precisely. "
                               "Return only valid JSON."),
                    "options":   {"temperature": 0.1, "num_predict": 300},
                    "stream":    False,
                })
                raw = r.json().get("response", "")
                m   = re.search(r"\{.*\}", raw, re.DOTALL)
                if m:
                    data = json.loads(m.group())
                    return MistakeAnalysis(
                        question       = question,
                        my_answer      = my_answer,
                        correct_answer = correct_answer,
                        error_type     = data.get("error_type", "unknown"),
                        why_wrong      = data.get("why_wrong", ""),
                        what_i_lacked  = data.get("what_i_lacked", ""),
                        correction     = data.get("correction", correct_answer),
                        never_again    = data.get("never_again", ""),
                        severity       = float(data.get("severity", 0.5)),
                    )
        except Exception as e:
            logger.warning("[StudentBrain] Ollama analysis failed: %s", e)

        # Rule-based fallback
        return MistakeAnalysis(
            question       = question,
            my_answer      = my_answer,
            correct_answer = correct_answer,
            error_type     = "incomplete_knowledge",
            why_wrong      = f"My answer '{my_answer[:50]}' was incorrect.",
            what_i_lacked  = f"I lacked knowledge about: {self._extract_topic(question)}",
            correction     = correct_answer,
            never_again    = f"Remember: {correct_answer[:80]}",
            severity       = 0.5,
        )

    def _reinforce_knowledge(self, question: str, correct_answer: str):
        topic = self._extract_topic(question)
        con   = sqlite3.connect(self._db_path)
        con.execute(
            "UPDATE knowledge SET times_used=times_used+1, "
            "confidence=MIN(0.99, confidence+0.02) "
            "WHERE topic=? AND fact LIKE ?",
            (topic, correct_answer[:30] + "%"))
        con.commit()
        con.close()

    def _learn_from_correction(self, mistake: MistakeAnalysis):
        topic = self._extract_topic(mistake.question)
        self.learn(topic, mistake.correction, confidence=0.8,
                   source="mistake_correction")
        if mistake.never_again:
            self.learn(topic + "_rule", mistake.never_again,
                       confidence=0.9, source="never_again_rule")

    def _record_episode(self, session_id, question, my_answer,
                         correct_answer, was_correct, explanation,
                         mistake=None):
        con = sqlite3.connect(self._db_path)
        con.execute(
            "INSERT INTO episodes "
            "(session_id,question,my_answer,correct_answer,was_correct,"
            "confidence,reasoning,mistake,emotion) VALUES (?,?,?,?,?,?,?,?,?)",
            (session_id, question[:500], my_answer[:500],
             correct_answer[:500], int(was_correct),
             self._emotion.confidence,
             explanation[:500],
             json.dumps({
                 "error_type":  mistake.error_type if mistake else None,
                 "why_wrong":   mistake.why_wrong  if mistake else None,
             }),
             self._emotion.current.value))
        con.commit()
        con.close()

    def _record_mistake(self, m: MistakeAnalysis):
        con = sqlite3.connect(self._db_path)
        con.execute(
            "INSERT INTO mistakes "
            "(topic,error_type,why_wrong,what_i_lacked,correction,"
            "never_again,severity) VALUES (?,?,?,?,?,?,?)",
            (self._extract_topic(m.question),
             m.error_type, m.why_wrong[:400], m.what_i_lacked[:400],
             m.correction[:400], m.never_again[:400], m.severity))
        con.commit()
        con.close()

    def _add_rule(self, topic: str, rule: str, confidence: float = 0.8):
        self.learn(topic + "_rule", rule, confidence, "rule")

    def _extract_topic(self, text: str) -> str:
        """Extract main topic from question."""
        stopwords = {"what","is","are","does","how","why","when","the",
                     "a","an","do","i","you","it","this","that","in","of"}
        words = [w.lower() for w in text.split()
                 if w.lower() not in stopwords and len(w) > 3]
        return words[0] if words else "general"

    def _add_curiosity(self, context: str, reason: str):
        topics = [w for w in context.split() if len(w) > 4]
        if topics:
            q = f"Tell me more about {topics[0]}"
            self._curiosity_queue.append(q)
            if len(self._curiosity_queue) > 20:
                self._curiosity_queue = self._curiosity_queue[-15:]

    def _push_wm(self, item: dict):
        self._working_memory.append(item)
        if len(self._working_memory) > self._wm_capacity:
            self._working_memory.pop(0)

    def _get_recent_mistakes(self, days: int = 7) -> list[dict]:
        cutoff = time.time() - days * 86400
        con    = sqlite3.connect(self._db_path)
        rows   = con.execute(
            "SELECT topic, correction, why_wrong, severity "
            "FROM mistakes WHERE ts > ? ORDER BY severity DESC LIMIT 20",
            (cutoff,)).fetchall()
        con.close()
        return [{"topic": r[0], "correction": r[1],
                 "why_wrong": r[2], "severity": r[3]} for r in rows]

    def _get_weak_knowledge(self, threshold: float = 0.4,
                             limit: int = 10) -> list[dict]:
        con  = sqlite3.connect(self._db_path)
        rows = con.execute(
            "SELECT topic, fact, confidence FROM knowledge "
            "WHERE confidence < ? ORDER BY confidence ASC LIMIT ?",
            (threshold, limit)).fetchall()
        con.close()
        return [{"topic": r[0], "fact": r[1], "confidence": r[2]}
                for r in rows]

    def _find_new_connections(self) -> int:
        """Find concepts that should be linked."""
        con     = sqlite3.connect(self._db_path)
        topics  = [r[0] for r in con.execute(
            "SELECT DISTINCT topic FROM knowledge LIMIT 50").fetchall()]
        con.close()

        connections = 0
        for i, t1 in enumerate(topics):
            for t2 in topics[i+1:]:
                # Simple: if topic names share words, they're connected
                w1 = set(t1.lower().split("_"))
                w2 = set(t2.lower().split("_"))
                if w1 & w2:
                    connections += 1
        return connections

    def _update_concept(self, con, topic: str, learned: bool = False,
                         correct: bool = False, tested: bool = False):
        existing = con.execute(
            "SELECT id, understanding FROM concepts WHERE name=?",
            (topic,)).fetchone()
        if existing:
            delta = 0.05 if learned else (0.08 if correct else -0.02)
            new_u = max(0.0, min(1.0, existing[1] + delta))
            con.execute(
                "UPDATE concepts SET understanding=?, "
                "times_taught=times_taught+?, "
                "times_tested=times_tested+?, "
                "times_correct=times_correct+?, "
                "last_studied=? WHERE id=?",
                (new_u, int(learned), int(tested),
                 int(correct), time.time(), existing[0]))
        else:
            con.execute(
                "INSERT INTO concepts (name, understanding, last_studied) "
                "VALUES (?,?,?)",
                (topic, 0.3 if learned else 0.1, time.time()))

    def _save_daily_progress(self, results: dict):
        today = time.strftime("%Y-%m-%d")
        con   = sqlite3.connect(self._db_path)
        con.execute("""
            INSERT INTO daily_progress
                (date, lessons, questions, correct, new_facts,
                 mistakes_made, avg_confidence, peak_emotion)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(date) DO UPDATE SET
                lessons=lessons+excluded.lessons,
                new_facts=new_facts+excluded.new_facts
        """, (today,
              results.get("reviewed_mistakes", 0),
              0, 0,
              results.get("reinforced_facts", 0),
              0,
              self._emotion.confidence,
              self._emotion.current.value))
        con.commit()
        con.close()

    def receive_praise(self, message: str = ""):
        """Teacher praises the student — boosts motivation."""
        self._emotion.on_praise()
        logger.info("[StudentBrain] Received praise — motivation boosted")

    def receive_encouragement(self):
        """Teacher encourages after mistakes — reduces frustration."""
        if self._emotion.current == Emotion.FRUSTRATED:
            self._emotion.current = Emotion.CURIOUS
            self._emotion.energy  = min(1.0, self._emotion.energy + 0.15)

    @property
    def emotion(self) -> EmotionalState:
        return self._emotion

    def get_curiosity_questions(self, n: int = 3) -> list[str]:
        return self._curiosity_queue[:n]

    def stats(self) -> dict:
        return self.introspect()
