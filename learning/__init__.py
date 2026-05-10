"""
backend/learning/__init__.py
Learning and development systems including Student AGI.

Student AGI runs as a separate service:
  python backend/learning/student_agi/student_agi_main.py

Routes available at /student-agi/* when service is online.
"""
__all__ = [
    "student_agi",
]
