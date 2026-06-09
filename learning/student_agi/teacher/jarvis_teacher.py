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
teacher/jarvis_teacher.py
═══════════════════════════════════════════════════════════════════════
JARVIS TEACHER ENGINE

JARVIS acts as the teacher. The StudentBrain is the student.
This is exactly like a human teacher-student relationship:

  1. LESSON        — teacher explains a concept clearly
  2. QUIZ          — teacher asks questions to test understanding
  3. GRADE         — teacher evaluates answers (right/wrong/partial)
  4. CORRECT       — teacher explains what was wrong and why
  5. SHOUT         — teacher gets firm when student repeats mistakes
  6. PRAISE        — teacher celebrates correct answers
  7. REVIEW        — teacher reviews previous lessons
  8. CHALLENGE     — teacher gives harder questions as student improves
  9. CURRICULUM    — teacher plans what to teach next
  10. PROGRESS     — teacher tracks improvement over time

Teaching styles:
  SOCRATIC  — asks questions to make student think, not just tell
  DIRECT    — explains directly, tests immediately
  CHALLENGE — gives hard problems, watches how student approaches
  REVIEW    — revisits weak areas until mastered

JARVIS uses its own LLM (qwen3:4b, mistral, etc.) to:
  - Generate lesson content for any topic
  - Create test questions of varying difficulty
  - Grade answers (not just right/wrong — partial credit)
  - Generate detailed corrections
  - Adapt to student's current level
═══════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations
import asyncio, json, logging, re, time, uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import httpx

from brain.student_brain import StudentBrain, Emotion

logger = logging.getLogger("student_agi.teacher")

OLLAMA = "http://localhost:11434"


# ─────────────────────────────────────────────────────────────────────
#  TEACHING STYLE
# ─────────────────────────────────────────────────────────────────────

class TeachingStyle(str, Enum):
    SOCRATIC   = "socratic"    # guide with questions
    DIRECT     = "direct"      # explain then test
    CHALLENGE  = "challenge"   # throw hard problems
    REVIEW     = "review"      # revisit weak areas
    ENCOURAGEMENT = "encouragement"  # after many mistakes


# ─────────────────────────────────────────────────────────────────────
#  LESSON — one unit of teaching
# ─────────────────────────────────────────────────────────────────────

@dataclass
class Lesson:
    id:           str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    topic:        str = ""
    concept:      str = ""
    explanation:  str = ""
    examples:     list[str] = field(default_factory=list)
    key_points:   list[str] = field(default_factory=list)
    difficulty:   int = 1     # 1=beginner, 5=expert
    style:        TeachingStyle = TeachingStyle.DIRECT


@dataclass
class Question:
    id:           str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    topic:        str = ""
    text:         str = ""
    correct_answer: str = ""
    hints:        list[str] = field(default_factory=list)
    difficulty:   int = 1
    q_type:       str = "open"  # open | mcq | true_false | fill_blank


@dataclass
class GradingResult:
    question:       str
    student_answer: str
    correct_answer: str
    score:          float     # 0.0 – 1.0
    was_correct:    bool
    partial_credit: bool
    feedback:       str       # what the teacher says
    correction:     str       # the right answer with explanation
    shout:          bool = False   # teacher got stern
    praise:         bool = False   # teacher praised


@dataclass
class TeachingSession:
    id:           str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    topic:        str = ""
    started_at:   float = field(default_factory=time.time)
    lessons:      list[Lesson]       = field(default_factory=list)
    questions:    list[Question]     = field(default_factory=list)
    grades:       list[GradingResult]= field(default_factory=list)
    score:        float = 0.0
    completed:    bool = False

    @property
    def accuracy(self) -> float:
        if not self.grades:
            return 0.0
        return sum(1 for g in self.grades if g.was_correct) / len(self.grades)


# ─────────────────────────────────────────────────────────────────────
#  JARVIS TEACHER
# ─────────────────────────────────────────────────────────────────────

class JarvisTeacher:
    """
    JARVIS teaches the StudentBrain.
    Uses its own LLM to generate lessons, questions, and feedback.
    Adapts teaching style based on student's performance.
    """

    # How many wrong answers before JARVIS gets stern
    SHOUT_THRESHOLD  = 3
    # How many right to get praise
    PRAISE_THRESHOLD = 3

    def __init__(self, student: StudentBrain,
                 ollama_url: str = OLLAMA,
                 model:      str = "qwen3:4b"):
        self._student  = student
        self._ollama   = ollama_url
        self._model    = model
        self._sessions: list[TeachingSession] = []
        self._current: Optional[TeachingSession] = None
        logger.info("[Teacher] JarvisTeacher initialized")

    # ─────────────────────────────────────────────────────────────
    #  START SESSION
    # ─────────────────────────────────────────────────────────────

    async def start_session(self, topic: str) -> TeachingSession:
        style = self._choose_style()
        session = TeachingSession(topic=topic)
        self._current = session
        self._sessions.append(session)
        logger.info("[Teacher] Session started: %s (style=%s)", topic, style.value)
        return session

    # ─────────────────────────────────────────────────────────────
    #  TEACH — explain a concept
    # ─────────────────────────────────────────────────────────────

    async def teach(self, topic: str,
                    concept: str = "",
                    difficulty: int = None) -> Lesson:
        """
        Explain a concept to the student.
        Adapts difficulty to student's current level.
        """
        if difficulty is None:
            difficulty = self._calc_difficulty(topic)

        style     = self._choose_style()
        content   = await self._generate_lesson(topic, concept, difficulty, style)
        lesson    = Lesson(
            topic      = topic,
            concept    = concept or topic,
            explanation= content["explanation"],
            examples   = content.get("examples", []),
            key_points = content.get("key_points", []),
            difficulty = difficulty,
            style      = style,
        )

        # Student absorbs the lesson
        self._student.learn(
            topic      = topic,
            fact       = lesson.explanation[:400],
            confidence = 0.5 + (difficulty * 0.05),
            source     = "teacher_lesson",
        )
        for kp in lesson.key_points:
            self._student.learn(
                topic      = topic,
                fact       = kp,
                confidence = 0.6,
                source     = "key_point",
            )

        if self._current:
            self._current.lessons.append(lesson)

        logger.info("[Teacher] Lesson delivered: [%s] difficulty=%d",
                    topic, difficulty)
        return lesson

    # ─────────────────────────────────────────────────────────────
    #  ASK — generate a test question
    # ─────────────────────────────────────────────────────────────

    async def ask(self, topic: str,
                  difficulty: int = None,
                  q_type: str = "open") -> Question:
        """
        Generate a test question for the student.
        Difficulty adapts to performance.
        """
        if difficulty is None:
            difficulty = self._calc_difficulty(topic)

        # If student is frustrated, give easier question
        if self._student.emotion.current == Emotion.FRUSTRATED:
            difficulty = max(1, difficulty - 1)

        # If student is confident+correct, escalate
        if self._student.emotion.current == Emotion.PROUD:
            difficulty = min(5, difficulty + 1)

        q_data = await self._generate_question(topic, difficulty, q_type)
        question = Question(
            topic          = topic,
            text           = q_data["question"],
            correct_answer = q_data["answer"],
            hints          = q_data.get("hints", []),
            difficulty     = difficulty,
            q_type         = q_type,
        )

        if self._current:
            self._current.questions.append(question)

        return question

    # ─────────────────────────────────────────────────────────────
    #  GRADE — evaluate student's answer
    # ─────────────────────────────────────────────────────────────

    async def grade(self, question: Question,
                    student_answer: str) -> GradingResult:
        """
        Grade student's answer.
        Not just right/wrong — partial credit, nuanced feedback.
        Teacher may praise, correct, or get stern.
        """
        grading = await self._evaluate_answer(
            question.text,
            student_answer,
            question.correct_answer,
        )

        score    = grading["score"]
        correct  = score >= 0.8
        partial  = 0.3 <= score < 0.8

        # Decide teacher's tone
        shout  = False
        praise = False

        if correct:
            praise = self._student.emotion.streak_right >= self.PRAISE_THRESHOLD - 1
            feedback = await self._generate_praise(
                question.text, student_answer, praise)
        elif self._student.emotion.streak_wrong >= self.SHOUT_THRESHOLD:
            shout    = True
            feedback = await self._generate_stern_correction(
                question.text, student_answer, question.correct_answer)
        else:
            feedback = await self._generate_correction(
                question.text, student_answer,
                question.correct_answer, partial)

        result = GradingResult(
            question       = question.text,
            student_answer = student_answer,
            correct_answer = question.correct_answer,
            score          = score,
            was_correct    = correct,
            partial_credit = partial,
            feedback       = feedback,
            correction     = grading.get("correction", question.correct_answer),
            shout          = shout,
            praise         = praise,
        )

        # Feed result back to student brain
        mistake = await self._student.receive_feedback(
            question       = question.text,
            my_answer      = student_answer,
            correct_answer = question.correct_answer,
            was_correct    = correct,
            explanation    = feedback,
            session_id     = self._current.id if self._current else "",
        )

        if praise:
            self._student.receive_praise(feedback)

        if self._current:
            self._current.grades.append(result)

        if shout:
            logger.info("[Teacher] STERN correction issued to student")
        elif praise:
            logger.info("[Teacher] Praise given: streak=%d",
                        self._student.emotion.streak_right)

        return result

    # ─────────────────────────────────────────────────────────────
    #  FULL LESSON CYCLE — teach → ask → grade → correct
    # ─────────────────────────────────────────────────────────────

    async def run_lesson_cycle(
        self, topic: str,
        n_questions: int = 3,
        difficulty: int = None,
    ) -> TeachingSession:
        """
        Run a complete lesson:
          1. Teach the concept
          2. Ask N questions
          3. Grade each answer (student answers using own brain)
          4. Correct mistakes immediately
          5. If student fails 2+, re-teach before moving on

        Returns full session with scores.
        """
        session = await self.start_session(topic)

        # Step 1: Teach
        lesson = await self.teach(topic, difficulty=difficulty)
        logger.info("[Teacher] Lesson: %s", lesson.explanation[:80])

        # Step 2–4: Ask, get answer, grade, correct
        fail_count = 0
        for i in range(n_questions):
            # Escalate difficulty if doing well
            eff_diff = (difficulty or 1) + (i if session.accuracy > 0.8 else 0)

            question = await self.ask(topic, difficulty=eff_diff)
            logger.info("[Teacher] Q%d: %s", i+1, question.text[:60])

            # Student answers using own brain
            student_response = await self._student.answer(question.text)
            student_answer   = student_response["answer"]
            logger.info("[Teacher] Student: %s (conf=%.2f)",
                        student_answer[:60],
                        student_response["confidence"])

            grade = await self.grade(question, student_answer)
            logger.info("[Teacher] Grade: %.2f — %s",
                        grade.score,
                        "✓" if grade.was_correct else "✗")

            if not grade.was_correct:
                fail_count += 1

            # If 2+ failures, re-teach before continuing
            if fail_count >= 2 and i < n_questions - 1:
                logger.info("[Teacher] Re-teaching due to failures...")
                await self.teach(topic, concept="review",
                                 difficulty=max(1, eff_diff - 1))
                fail_count = 0

        session.completed = True
        session.score     = session.accuracy
        logger.info("[Teacher] Session done: %.1f%% accuracy",
                    session.accuracy * 100)
        return session

    # ─────────────────────────────────────────────────────────────
    #  DAILY CURRICULUM — plan what to teach today
    # ─────────────────────────────────────────────────────────────

    async def plan_daily_curriculum(self) -> list[dict]:
        """
        Each day, plan what to teach based on:
          - Student's weak topics
          - Unreviewed mistakes
          - Curiosity questions
          - World knowledge gaps
        """
        intro    = self._student.introspect()
        weak     = intro.get("weak_topics",    [])[:3]
        curious  = intro.get("curious_about",  [])[:2]
        accuracy = intro.get("accuracy", 0)

        plan = []

        # 1. Review mistakes from last 3 days
        plan.append({
            "type":  "review",
            "topic": "mistake_review",
            "desc":  "Review recent mistakes",
            "priority": 1,
        })

        # 2. Reinforce weak topics
        for topic in weak:
            plan.append({
                "type":  "lesson",
                "topic": topic,
                "desc":  f"Strengthen understanding of {topic}",
                "priority": 2,
            })

        # 3. Answer curiosity questions
        for q in curious:
            plan.append({
                "type":  "curiosity",
                "topic": q,
                "desc":  f"Explore curiosity: {q}",
                "priority": 3,
            })

        # 4. New topic if doing well
        if accuracy > 0.75:
            new_topic = await self._suggest_new_topic(intro)
            if new_topic:
                plan.append({
                    "type":   "new_topic",
                    "topic":  new_topic,
                    "desc":   f"New topic: {new_topic}",
                    "priority": 4,
                })

        return sorted(plan, key=lambda x: x["priority"])

    async def run_daily_teaching(self) -> dict:
        """
        Full daily teaching session.
        Runs automatically every day.
        """
        curriculum = await self.plan_daily_curriculum()
        results    = {
            "sessions":       [],
            "total_questions": 0,
            "total_correct":   0,
            "new_topics":      [],
        }

        for item in curriculum[:4]:   # max 4 items per day
            topic = item["topic"]
            if item["type"] in ("lesson", "new_topic", "curiosity"):
                session = await self.run_lesson_cycle(
                    topic, n_questions=3)
                results["sessions"].append({
                    "topic":    topic,
                    "accuracy": session.accuracy,
                    "lessons":  len(session.lessons),
                })
                results["total_questions"] += len(session.questions)
                results["total_correct"]   += sum(
                    1 for g in session.grades if g.was_correct)
                if item["type"] == "new_topic":
                    results["new_topics"].append(topic)

        # Student does self-study after teacher session
        self_study = await self._student.daily_self_study()
        results["self_study"] = self_study

        logger.info("[Teacher] Daily teaching done: %s", results)
        return results

    # ─────────────────────────────────────────────────────────────
    #  LLM HELPERS — generate content via Ollama
    # ─────────────────────────────────────────────────────────────

    async def _llm(self, prompt: str, system: str = "",
                   max_tokens: int = 400) -> str:
        try:
            async with httpx.AsyncClient(timeout=60) as c:
                r = await c.post(f"{self._ollama}/api/generate", json={
                    "model":   self._model,
                    "prompt":  prompt,
                    "system":  system,
                    "options": {"temperature": 0.2,
                                "num_predict": max_tokens},
                    "stream":  False,
                })
                return r.json().get("response", "").strip()
        except Exception as e:
            logger.warning("[Teacher] LLM error: %s", e)
            logger.warning("[Teacher] _llm returning empty string after exception")
            return ""

    async def _generate_lesson(self, topic: str, concept: str,
                                 difficulty: int,
                                 style: TeachingStyle) -> dict:
        style_instructions = {
            TeachingStyle.SOCRATIC:   "Guide with questions, don't give answers directly.",
            TeachingStyle.DIRECT:     "Explain clearly and directly.",
            TeachingStyle.CHALLENGE:  "Present the challenging aspects first.",
            TeachingStyle.REVIEW:     "Summarize and reinforce key points.",
            TeachingStyle.ENCOURAGEMENT: "Be warm, positive, and clear.",
        }

        prompt = (
            f"Teach the concept: {topic} - {concept}\n"
            f"Difficulty: {difficulty}/5\n"
            f"Style: {style_instructions[style]}\n\n"
            f"Return ONLY valid JSON:\n"
            '{"explanation":"clear 2-3 sentence explanation",'
            '"examples":["example 1","example 2"],'
            '"key_points":["point 1","point 2","point 3"]}'
        )
        raw = await self._llm(prompt, "You are a precise, clear teacher. Return only JSON.")
        try:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                return json.loads(m.group())
        except Exception as err:
            import logging
            logging.getLogger(__name__).error("Exception swallowed: %s", err)
            raise RuntimeError(f"Exception swallowed: {err}")
        return {
            "explanation": f"{topic}: {concept or 'An important concept in this domain.'}",
            "examples":    [f"Example of {topic}"],
            "key_points":  [f"Remember: {topic} is important"],
        }

    async def _generate_question(self, topic: str,
                                   difficulty: int,
                                   q_type: str) -> dict:
        prompt = (
            f"Create a test question about: {topic}\n"
            f"Difficulty: {difficulty}/5\n"
            f"Type: {q_type}\n\n"
            f"Return ONLY valid JSON:\n"
            '{"question":"clear specific question",'
            '"answer":"complete correct answer",'
            '"hints":["hint 1 if needed"]}'
        )
        raw = await self._llm(prompt, "You are a precise examiner. Return only JSON.")
        try:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                return json.loads(m.group())
        except Exception as err:
            import logging
            logging.getLogger(__name__).error("Exception swallowed: %s", err)
            raise RuntimeError(f"Exception swallowed: {err}")
        return {
            "question": f"Explain what you know about {topic}.",
            "answer":   f"{topic} is a concept that...",
            "hints":    [],
        }

    async def _evaluate_answer(self, question: str,
                                 student_answer: str,
                                 correct_answer: str) -> dict:
        prompt = (
            f"Evaluate this student answer:\n"
            f"Question: {question}\n"
            f"Student answer: {student_answer}\n"
            f"Correct answer: {correct_answer}\n\n"
            f"Return ONLY valid JSON:\n"
            '{"score":0.0,"correct":false,'
            '"correction":"what was wrong and right answer",'
            '"partial":false}'
        )
        raw = await self._llm(
            prompt,
            "You are a strict but fair examiner. Return only JSON. "
            "Score 1.0=perfect, 0.8=mostly right, 0.5=partial, 0.0=wrong.",
            200)
        try:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                data = json.loads(m.group())
                return {
                    "score":      float(data.get("score", 0.0)),
                    "correction": data.get("correction", correct_answer),
                }
        except Exception as err:
            import logging
            logging.getLogger(__name__).error("Exception swallowed: %s", err)
            raise RuntimeError(f"Exception swallowed: {err}")
        # Fallback: simple string match
        score = 0.8 if student_answer.lower()[:30] in correct_answer.lower() else 0.0
        return {"score": score, "correction": correct_answer}

    async def _generate_praise(self, question: str,
                                  answer: str,
                                  enthusiastic: bool) -> str:
        if enthusiastic:
            templates = [
                "Excellent! That's exactly right. You're really getting this!",
                "Perfect answer! Your understanding is strong.",
                "Outstanding! You've mastered this concept.",
                "Yes! Correct! Keep this up — you're doing brilliantly.",
            ]
        else:
            templates = [
                "Correct! Well done.",
                "Right answer! Good work.",
                "That's correct. Good.",
                "Yes, that's right.",
            ]
        import random
        return random.choice(templates)

    async def _generate_correction(self, question: str,
                                     student_answer: str,
                                     correct_answer: str,
                                     partial: bool) -> str:
        prefix = "Close! " if partial else "That's not quite right. "
        prompt = (
            f"Student answered: '{student_answer[:100]}'\n"
            f"Correct answer: '{correct_answer[:100]}'\n"
            f"Give a clear, helpful 1-2 sentence correction."
        )
        raw = await self._llm(prompt,
                               "You are a patient teacher giving feedback.")
        return prefix + (raw[:200] if raw else f"The correct answer is: {correct_answer[:100]}")

    async def _generate_stern_correction(self, question: str,
                                           student_answer: str,
                                           correct_answer: str) -> str:
        prompts = [
            f"We've covered this before! The answer is: {correct_answer[:100]}. "
            f"Please pay attention and remember this.",
            f"This is wrong again. Let me be very clear: {correct_answer[:100]}. "
            f"You must remember this.",
            f"No, that's incorrect — and this is the third time. "
            f"The correct answer is: {correct_answer[:100]}. Focus!",
        ]
        import random
        return random.choice(prompts)

    async def _suggest_new_topic(self, intro: dict) -> Optional[str]:
        strong  = intro.get("strong_topics", [])
        all_topics_prompt = (
            "Given that a student understands these topics well: "
            f"{', '.join(strong[:3])}, "
            "suggest ONE related topic they should learn next. "
            "Return only the topic name, nothing else."
        )
        raw = await self._llm(all_topics_prompt)
        return raw.strip().split("\n")[0][:50] if raw else None

    def _choose_style(self) -> TeachingStyle:
        em = self._student.emotion
        if em.current == Emotion.FRUSTRATED:
            return TeachingStyle.ENCOURAGEMENT
        if em.current == Emotion.CONFUSED:
            return TeachingStyle.DIRECT
        if em.current in (Emotion.CONFIDENT, Emotion.PROUD):
            return TeachingStyle.CHALLENGE
        if em.current == Emotion.CURIOUS:
            return TeachingStyle.SOCRATIC
        return TeachingStyle.DIRECT

    def _calc_difficulty(self, topic: str) -> int:
        conf = self._student.introspect().get(
            "knowledge_conf", {}).get(topic, 0.2)
        # Map confidence → difficulty
        if conf < 0.2:  return 1
        if conf < 0.4:  return 2
        if conf < 0.6:  return 3
        if conf < 0.8:  return 4
        return 5

    def session_summary(self) -> Optional[dict]:
        if not self._current:
            return None
        return {
            "id":       self._current.id,
            "topic":    self._current.topic,
            "accuracy": self._current.accuracy,
            "questions": len(self._current.questions),
            "lessons":   len(self._current.lessons),
            "completed": self._current.completed,
        }

    def all_session_stats(self) -> dict:
        total_q = sum(len(s.questions) for s in self._sessions)
        total_c = sum(sum(1 for g in s.grades if g.was_correct)
                      for s in self._sessions)
        return {
            "total_sessions":  len(self._sessions),
            "total_questions": total_q,
            "total_correct":   total_c,
            "overall_accuracy": total_c / total_q if total_q > 0 else 0,
        }
