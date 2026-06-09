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
backend/learning/__init__.py
Learning and development systems including Student AGI.

Student AGI runs as a separate service:
  python backend/learning/student_agi/student_agi_main.py

Routes available at /student-agi/* when service is online.
"""
from . import student_agi  # noqa: F401
