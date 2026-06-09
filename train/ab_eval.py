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

"""A/B evaluation before deploying fine-tuned models."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from statistics import mean

import core.llm_router
from core.quality_grader import QualityGrader

BENCHMARK_QUERIES = [
    "Write a Python function to reverse a linked list",
    "Explain what a restaurant website should contain",
    "Summarize the key benefits of local AI models",
    "Write a bash script to find large files",
    "Create a responsive navbar in HTML/CSS",
    "Explain the difference between SQL and NoSQL",
    "Write a Python decorator for timing functions",
    "What is the best way to structure a Flask app?",
    "Create a simple REST API endpoint in Python",
    "How do I optimize a PostgreSQL query?",
]


@dataclass
class ABResult:
    deploy: bool
    base_mean: float
    ft_mean: float
    improvement: float
    details: list[dict] = field(default_factory=list)


async def run_ab_eval(base_model: str,
                       finetuned_model: str,
                       n_queries: int = 50) -> ABResult:
    grader = QualityGrader("config/quality_constitution.json", core.llm_router)
    base_scores: list[float] = []
    ft_scores: list[float] = []
    details: list[dict] = []

    for query in BENCHMARK_QUERIES[:n_queries]:
        messages = [{"role": "user", "content": query}]
        base_out = (await core.llm_router.complete(base_model, messages)).unwrap_or("")
        ft_out = (await core.llm_router.complete(finetuned_model, messages)).unwrap_or("")
        bs = (await grader.grade("response", base_out)).aggregate_score
        fs = (await grader.grade("response", ft_out)).aggregate_score
        base_scores.append(bs)
        ft_scores.append(fs)
        details.append({"query": query[:50], "base": round(bs, 1), "ft": round(fs, 1)})

    bm = mean(base_scores) if base_scores else 0.0
    fm = mean(ft_scores) if ft_scores else 0.0
    deploy = fm >= bm and (not ft_scores or min(ft_scores) >= min(base_scores) * 0.9)

    return ABResult(
        deploy=deploy, base_mean=round(bm, 1), ft_mean=round(fm, 1),
        improvement=round(fm - bm, 1), details=details,
    )
