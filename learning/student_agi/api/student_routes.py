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
learning/student_agi/api/student_routes.py
Routes for Student AGI system integration with main JARVIS backend.
"""
import httpx
import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List

logger = logging.getLogger(__name__)

router = APIRouter(tags=["student-agi"])

# Student AGI service URL (defaults to localhost:11436)
STUDENT_AGI_BASE_URL = "http://localhost:11436"

# ─────────────────────────────────────────────────────────────
#  Request/Response Models
# ─────────────────────────────────────────────────────────────

class TeachRequest(BaseModel):
    topic: str
    difficulty: Optional[str] = "intermediate"
    context: Optional[str] = None

class AskRequest(BaseModel):
    question: str
    topic: Optional[str] = None

class FeedbackRequest(BaseModel):
    answer: str
    question: str
    grade: float  # 0.0-1.0
    explanation: Optional[str] = None

# ─────────────────────────────────────────────────────────────
#  Health Check
# ─────────────────────────────────────────────────────────────

@router.get("/health")
async def student_agi_health():
    """Check if Student AGI service is running"""
    async with httpx.AsyncClient(timeout=2.0) as client:
        try:
            resp = await client.get(f"{STUDENT_AGI_BASE_URL}/docs")
            return {"status": "online", "service": "Student AGI"}
        except Exception as e:
            return {
                "status": "offline",
                "service": "Student AGI",
                "error": str(e),
                "help": "Start with: python learning/student_agi/student_agi_main.py"
            }

# ─────────────────────────────────────────────────────────────
#  Teaching
# ─────────────────────────────────────────────────────────────

@router.post("/teach")
async def teach(req: TeachRequest):
    """Teach the Student AGI a topic"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                f"{STUDENT_AGI_BASE_URL}/student/teach",
                json={
                    "topic": req.topic,
                    "difficulty": req.difficulty,
                    "context": req.context
                }
            )
            if resp.status_code != 200:
                raise HTTPException(resp.status_code, resp.text)
            return resp.json()
        except httpx.ConnectError:
            raise HTTPException(
                503,
                "Student AGI service not running. "
                "Start with: python learning/student_agi/student_agi_main.py"
            )

# ─────────────────────────────────────────────────────────────
#  Questioning
# ─────────────────────────────────────────────────────────────

@router.post("/ask")
async def ask(req: AskRequest):
    """Ask the Student AGI a question"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                f"{STUDENT_AGI_BASE_URL}/student/ask",
                json={"question": req.question, "topic": req.topic}
            )
            if resp.status_code != 200:
                raise HTTPException(resp.status_code, resp.text)
            return resp.json()
        except httpx.ConnectError:
            raise HTTPException(
                503,
                "Student AGI service not running"
            )

# ─────────────────────────────────────────────────────────────
#  Feedback & Learning
# ─────────────────────────────────────────────────────────────

@router.post("/feedback")
async def give_feedback(req: FeedbackRequest):
    """Give feedback on student's answer to help it learn"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                f"{STUDENT_AGI_BASE_URL}/student/feedback",
                json={
                    "answer": req.answer,
                    "question": req.question,
                    "grade": req.grade,
                    "explanation": req.explanation
                }
            )
            if resp.status_code != 200:
                raise HTTPException(resp.status_code, resp.text)
            return resp.json()
        except httpx.ConnectError:
            raise HTTPException(503, "Student AGI service not running")

# ─────────────────────────────────────────────────────────────
#  Status & Progress
# ─────────────────────────────────────────────────────────────

@router.get("/status")
async def student_status():
    """Get student's knowledge status and learning progress"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{STUDENT_AGI_BASE_URL}/student/status")
            if resp.status_code != 200:
                raise HTTPException(resp.status_code, resp.text)
            return resp.json()
        except httpx.ConnectError:
            raise HTTPException(503, "Student AGI service not running")

@router.get("/progress")
async def learning_progress():
    """Get detailed learning progress and metrics"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{STUDENT_AGI_BASE_URL}/student/progress")
            if resp.status_code != 200:
                raise HTTPException(resp.status_code, resp.text)
            return resp.json()
        except httpx.ConnectError:
            raise HTTPException(503, "Student AGI service not running")

@router.get("/mistakes")
async def recent_mistakes(limit: int = 10):
    """Get recent mistakes the student made (why it was wrong, what it lacked)"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{STUDENT_AGI_BASE_URL}/student/mistakes",
                params={"limit": limit}
            )
            if resp.status_code != 200:
                raise HTTPException(resp.status_code, resp.text)
            return resp.json()
        except httpx.ConnectError:
            raise HTTPException(503, "Student AGI service not running")

# ─────────────────────────────────────────────────────────────
#  Daily Learning
# ─────────────────────────────────────────────────────────────

@router.post("/daily")
async def run_daily_lesson(background_tasks: BackgroundTasks):
    """Run today's autonomous learning session"""
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            resp = await client.post(f"{STUDENT_AGI_BASE_URL}/student/daily")
            if resp.status_code != 200:
                raise HTTPException(resp.status_code, resp.text)
            return resp.json()
        except httpx.ConnectError:
            raise HTTPException(503, "Student AGI service not running")

# ─────────────────────────────────────────────────────────────
#  Knowledge Management
# ─────────────────────────────────────────────────────────────

@router.get("/knowledge/{topic}")
async def get_topic_knowledge(topic: str):
    """Get student's knowledge about a specific topic"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{STUDENT_AGI_BASE_URL}/student/knowledge/{topic}"
            )
            if resp.status_code != 200:
                raise HTTPException(resp.status_code, resp.text)
            return resp.json()
        except httpx.ConnectError:
            raise HTTPException(503, "Student AGI service not running")

@router.get("/curiosity-queue")
async def get_curiosity_queue():
    """Get the list of topics the student is curious about"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{STUDENT_AGI_BASE_URL}/student/curiosity")
            if resp.status_code != 200:
                raise HTTPException(resp.status_code, resp.text)
            return resp.json()
        except httpx.ConnectError:
            raise HTTPException(503, "Student AGI service not running")
