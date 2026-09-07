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
student_agi_main.py
═══════════════════════════════════════════════════════════════════════
JARVIS STUDENT AGI — Main Entry Point

Runs the complete autonomous learning system:

  1. StudentBrain     — knows, thinks, answers, learns from mistakes
  2. JarvisTeacher    — teaches, quizzes, grades, corrects, encourages
  3. WorldModel       — builds causal + conceptual understanding
  4. Daily Loop       — studies every day autonomously

This is completely separate from the JARVIS operational system.
JARVIS is the teacher. This brain is the student.

Run:
  python student_agi_main.py                  # start autonomous learner
  python student_agi_main.py --teach "python" # teach one topic now
  python student_agi_main.py --ask "question" # ask student a question
  python student_agi_main.py --status         # show learning progress
  python student_agi_main.py --daily          # run today's study session

API also available at port 11436:
  POST /student/teach    — teach the student a topic
  POST /student/ask      — ask student a question
  GET  /student/status   — student's knowledge state
  POST /student/daily    — run full daily lesson
  GET  /student/mistakes — recent mistakes with explanations
  GET  /student/progress — learning progress over time
═══════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations
import asyncio, json, logging, sys, time
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from brain.student_brain import StudentBrain
from teacher.jarvis_teacher import JarvisTeacher
from cognition.world_model import WorldModel, CausalEngine, AnalogyEngine, MetaCognition

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
)
logger = logging.getLogger("student_agi")


# ─────────────────────────────────────────────────────────────────────
#  GLOBAL INSTANCES
# ─────────────────────────────────────────────────────────────────────

student  = StudentBrain(student_id="jarvis_student")
teacher  = JarvisTeacher(student=student)
world    = WorldModel()
causal   = CausalEngine(world)
analogy  = AnalogyEngine()
meta     = MetaCognition()


# ─────────────────────────────────────────────────────────────────────
#  FASTAPI APP
# ─────────────────────────────────────────────────────────────────────

app = FastAPI(title="JARVIS Student AGI", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])


class TeachReq(BaseModel):
    topic:      str
    concept:    str = ""
    difficulty: int = None
    n_questions:int = 3

class AskReq(BaseModel):
    question: str
    context:  str = ""

class LearnReq(BaseModel):
    topic:    str
    fact:     str
    confidence: float = 0.7

class FeedbackReq(BaseModel):
    question:       str
    my_answer:      str
    correct_answer: str
    was_correct:    bool
    explanation:    str = ""
    session_id:     str = ""

class WorldReq(BaseModel):
    concept:    str
    category:   str = "concept"
    properties: dict = {}

class CausalReq(BaseModel):
    cause:    str
    effect:   str
    strength: float = 0.7


@app.get("/student/status")
async def status():
    """Full student knowledge state."""
    intro = student.introspect()
    thinking = meta.thinking_summary()
    return {
        **intro,
        "metacognition":   thinking,
        "world_concepts":  world.concept_count(),
        "analogies":       analogy.analogy_count(),
        "teacher_stats":   teacher.all_session_stats(),
    }


@app.post("/student/teach")
async def teach(req: TeachReq):
    """Run a full lesson cycle on a topic."""
    session = await teacher.run_lesson_cycle(
        topic       = req.topic,
        n_questions = req.n_questions,
        difficulty  = req.difficulty,
    )
    return {
        "session_id":  session.id,
        "topic":       session.topic,
        "accuracy":    round(session.accuracy, 3),
        "questions":   len(session.questions),
        "lessons":     len(session.lessons),
        "completed":   session.completed,
        "student_emotion": student.emotion.current.value,
        "grades": [
            {
                "question": g.question[:80],
                "answer":   g.student_answer[:80],
                "score":    g.score,
                "correct":  g.was_correct,
                "feedback": g.feedback[:150],
                "shout":    g.shout,
                "praise":   g.praise,
            }
            for g in session.grades
        ],
    }


@app.post("/student/ask")
async def ask_student(req: AskReq):
    """Ask student a question — returns their answer and reasoning."""
    response = await student.answer(req.question, req.context)

    # Log thinking in metacognition
    meta.log_thought(
        process    = "reason" if response["knowledge_used"] else "guess",
        question   = req.question,
        outcome    = response["answer"][:80],
        confidence = response["confidence"],
    )

    # Check if student should ask for help
    needs_help = meta.should_ask_for_help(
        response["confidence"],
        topic=req.question.split()[0]
    )

    return {
        **response,
        "needs_teacher_help": needs_help,
        "am_i_guessing":     meta.am_i_guessing(response["reasoning"]),
    }


@app.post("/student/feedback")
async def give_feedback(req: FeedbackReq):
    """Give the student feedback on their answer."""
    mistake = await student.receive_feedback(
        question       = req.question,
        my_answer      = req.my_answer,
        correct_answer = req.correct_answer,
        was_correct    = req.was_correct,
        explanation    = req.explanation,
        session_id     = req.session_id,
    )
    if mistake:
        return {
            "learned":        True,
            "error_type":     mistake.error_type,
            "why_wrong":      mistake.why_wrong,
            "what_i_lacked":  mistake.what_i_lacked,
            "correction":     mistake.correction,
            "never_again":    mistake.never_again,
            "severity":       mistake.severity,
            "new_emotion":    student.emotion.current.value,
            "new_confidence": round(student.emotion.confidence, 3),
        }
    return {
        "learned":     True,
        "reinforced":  True,
        "new_emotion": student.emotion.current.value,
    }


@app.post("/student/learn")
async def learn_fact(req: LearnReq):
    """Directly teach the student a fact."""
    student.learn(req.topic, req.fact, req.confidence, source="api")
    world.add_concept(req.topic, confidence=req.confidence)
    return {
        "learned":   True,
        "topic":     req.topic,
        "fact":      req.fact[:80],
        "emotion":   student.emotion.current.value,
    }


@app.post("/student/daily")
async def daily_lesson():
    """Run today's full autonomous learning session."""
    results = await teacher.run_daily_teaching()
    return results


@app.get("/student/mistakes")
async def get_mistakes(n: int = 10):
    """Recent mistakes with full analysis."""
    import sqlite3
    con  = sqlite3.connect("data/student/student_brain.db")
    rows = con.execute(
        "SELECT topic, error_type, why_wrong, correction, "
        "never_again, severity, ts "
        "FROM mistakes ORDER BY ts DESC LIMIT ?",
        (n,)).fetchall()
    con.close()
    return {
        "mistakes": [
            {
                "topic":      r[0], "error_type": r[1],
                "why_wrong":  r[2][:200], "correction": r[3][:200],
                "never_again":r[4][:150], "severity":   r[5],
                "when":       time.strftime("%Y-%m-%d %H:%M",
                                           time.localtime(r[6])),
            }
            for r in rows
        ]
    }


@app.get("/student/progress")
async def get_progress(days: int = 7):
    """Learning progress over the last N days."""
    import sqlite3
    con  = sqlite3.connect("data/student/student_brain.db")
    rows = con.execute(
        "SELECT date, lessons, questions, correct, new_facts, "
        "mistakes_made, avg_confidence, peak_emotion "
        "FROM daily_progress ORDER BY date DESC LIMIT ?",
        (days,)).fetchall()
    con.close()
    return {
        "days": [
            {
                "date":            r[0],
                "lessons":         r[1],
                "questions":       r[2],
                "correct":         r[3],
                "accuracy":        round(r[3]/r[2], 3) if r[2] > 0 else 0,
                "new_facts":       r[4],
                "mistakes":        r[5],
                "avg_confidence":  round(r[6], 3),
                "peak_emotion":    r[7],
            }
            for r in rows
        ]
    }


@app.get("/student/curriculum")
async def get_curriculum():
    """Today's planned learning curriculum."""
    plan = await teacher.plan_daily_curriculum()
    return {"curriculum": plan}


@app.get("/student/curiosity")
async def get_curiosity():
    """Topics the student is curious about."""
    questions = student.get_curiosity_questions(10)
    return {"curiosity_questions": questions}


@app.post("/student/world/concept")
async def add_world_concept(req: WorldReq):
    """Add a concept to the world model."""
    world.add_concept(req.concept, req.category, req.properties)
    return {"added": req.concept, "total": world.concept_count()}


@app.post("/student/world/causal")
async def add_causal(req: CausalReq):
    """Add a causal relationship: cause → effect."""
    causal.add_cause(req.cause, req.effect, req.strength)
    return {"cause": req.cause, "effect": req.effect}


@app.get("/student/world/why/{concept}")
async def why(concept: str):
    """Why does something happen? (causal chain)"""
    chain = causal.why(concept)
    return {"concept": concept, "causal_chain": chain}


@app.get("/student/world/analogy/{concept}")
async def explain_analogy(concept: str):
    """Explain concept by analogy."""
    explanation = analogy.explain_by_analogy(concept)
    return {"concept": concept, "analogy": explanation}


@app.get("/student/consistency")
async def check_consistency():
    """Find contradictions in student's knowledge."""
    from cognition.world_model import ConsistencyChecker
    checker = ConsistencyChecker()
    contradictions = checker.find_contradictions()
    return {
        "contradictions": contradictions,
        "count":          len(contradictions),
    }


@app.get("/health")
async def health():
    return {
        "status":   "ok",
        "student":  student.student_id,
        "emotion":  student.emotion.current.value,
        "accuracy": round(student.introspect().get("accuracy", 0), 3),
    }


# ─────────────────────────────────────────────────────────────────────
#  AUTONOMOUS DAILY LOOP
# ─────────────────────────────────────────────────────────────────────

async def autonomous_daily_loop():
    """
    Runs forever.
    Every day at 03:00 (when human is sleeping):
      1. Student does self-study
      2. Reviews mistakes
      3. Teacher runs curriculum if needed
    Every hour:
      - Check for new curiosity questions to explore
    """
    logger.info("[AutoLoop] Starting autonomous daily study loop")
    last_daily_ts = 0.0
    last_hourly_ts = 0.0

    while True:
        now = time.time()
        hour = time.localtime().tm_hour

        # Daily study at 3am
        if hour == 3 and now - last_daily_ts > 82800:  # 23h cooldown
            logger.info("[AutoLoop] Running daily study session...")
            try:
                results = await teacher.run_daily_teaching()
                logger.info("[AutoLoop] Daily study done: %s", results)
                last_daily_ts = now
            except Exception as e:
                logger.error("[AutoLoop] Daily study error: %s", e)

        # Hourly: process top curiosity question
        if now - last_hourly_ts > 3600:
            curious = student.get_curiosity_questions(1)
            if curious:
                logger.info("[AutoLoop] Exploring curiosity: %s", curious[0])
                try:
                    await teacher.teach(
                        topic      = curious[0][:50],
                        difficulty = 2,
                    )
                except Exception as e:
                    logger.warning("[AutoLoop] Curiosity exploration failed: %s", e)
            last_hourly_ts = now

        await asyncio.sleep(300)   # check every 5 minutes


# ─────────────────────────────────────────────────────────────────────
#  COMMAND LINE
# ─────────────────────────────────────────────────────────────────────

async def cli_main():
    args = sys.argv[1:]

    if not args or "--status" in args:
        state = student.introspect()
        print(f"\n{'='*50}")
        print("JARVIS STUDENT AGI — Knowledge State")
        print(f"{'='*50}")
        print(f"Emotion:     {state['emotion']}")
        print(f"Confidence:  {state['confidence']:.2f}")
        print(f"Accuracy:    {state['accuracy']*100:.1f}%")
        print(f"Total facts: {state['total_facts']}")
        print(f"Mistakes:    {state['total_mistakes']}")
        print(f"Strong:      {', '.join(state['strong_topics'][:3])}")
        print(f"Weak:        {', '.join(state['weak_topics'][:3])}")
        print(f"Curious:     {', '.join(state['curious_about'][:3])}")
        return

    if "--teach" in args:
        idx   = args.index("--teach")
        topic = args[idx+1] if idx+1 < len(args) else "python"
        print(f"\nTeaching: {topic}")
        session = await teacher.run_lesson_cycle(topic, n_questions=3)
        print(f"Accuracy: {session.accuracy*100:.1f}%")
        for g in session.grades:
            icon = "✓" if g.was_correct else "✗"
            print(f"  {icon} Q: {g.question[:50]}")
            print(f"    A: {g.student_answer[:50]}")
            if not g.was_correct:
                print(f"    → {g.feedback[:80]}")
        return

    if "--ask" in args:
        idx = args.index("--ask")
        q   = " ".join(args[idx+1:]) if idx+1 < len(args) else "What is Python?"
        print(f"\nQuestion: {q}")
        resp = await student.answer(q)
        print(f"Answer:     {resp['answer']}")
        print(f"Confidence: {resp['confidence']:.2f}")
        print(f"Reasoning:")
        for r in resp["reasoning"]:
            print(f"  • {r}")
        if resp["unknowns"]:
            print(f"I don't know: {resp['unknowns']}")
        return

    if "--daily" in args:
        print("\nRunning daily study session...")
        results = await teacher.run_daily_teaching()
        print(json.dumps(results, indent=2))
        return

    # Default: start API server + autonomous loop
    config = uvicorn.Config(
        app, host="0.0.0.0", port=11436,
        log_level="warning", loop="asyncio")
    server = uvicorn.Server(config)

    async def run_all():
        server_task = asyncio.create_task(server.serve())
        loop_task   = asyncio.create_task(autonomous_daily_loop())
        logger.info("JARVIS Student AGI started — API at http://localhost:11436")
        logger.info("Docs: http://localhost:11436/docs")
        await asyncio.gather(server_task, loop_task, return_exceptions=True)

    await run_all()


if __name__ == "__main__":
    asyncio.run(cli_main())
