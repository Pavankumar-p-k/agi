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
from __future__ import annotations

import uuid
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime


def uuid4_str():
    """Generate a UUID string for default field values."""
    return str(uuid.uuid4())


@dataclass
class ResearchTask:
    """A research task / goal to be accomplished."""
    id: str = field(default_factory=uuid4_str)
    query: str = ""
    description: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    status: str = "pending"  # pending, researching, completed, failed
    priority: float = 0.5


@dataclass
class ResearchPlan:
    """A structured research plan breaking a task into steps."""
    id: str = field(default_factory=uuid4_str)
    task_id: str = ""
    goal: str = ""
    steps: List[dict] = field(default_factory=list)
    status: str = "pending"  # pending, in_progress, completed, failed
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ResearchStep:
    """A single step in a research plan."""
    id: str = field(default_factory=uuid4_str)
    step_number: int = 0
    action: str = ""  # e.g., "search", "fetch", "extract", "synthesize"
    description: str = ""
    input: dict = field(default_factory=dict)
    output: Any = None
    status: str = "pending"  # pending, completed, failed
    error: str = ""


@dataclass
class Source:
    """A research source (web page, document, etc.)."""
    id: str = field(default_factory=uuid4_str)
    url: str = ""
    title: str = ""
    content: str = ""
    snippet: str = ""
    fetched_at: datetime = field(default_factory=datetime.now)
    credibility: float = 0.5  # 0.0-1.0
    relevance: float = 0.0  # 0.0-1.0 to query


@dataclass
class Evidence:
    """Evidence supporting a claim."""
    id: str = field(default_factory=uuid4_str)
    claim_id: str = ""
    source_id: str = ""
    content: str = ""
    relevance: float = 0.5  # 0.0-1.0
    confidence: float = 0.5  # 0.0-1.0 in claim
    extracted_at: datetime = field(default_factory=datetime.now)


@dataclass
class Claim:
    """A claim made during research."""
    id: str = field(default_factory=uuid4_str)
    text: str = ""
    research_task_id: str = ""
    status: str = "unverified"  # unverified, supported, contradicted, false
    evidence_ids: List[str] = field(default_factory=list)
    confidence: float = 0.5  # 0.0-1.0
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Fact:
    """A extracted fact from a source."""
    id: str = field(default_factory=uuid4_str)
    claim: str = ""
    source_url: str = ""
    source_title: str = ""
    text: str = ""
    confidence: float = 0.5  # 0.0-1.0
    extracted_at: datetime = field(default_factory=datetime.now)


@dataclass
class Hypothesis:
    """A hypothesis generated during research."""
    id: str = field(default_factory=uuid4_str)
    text: str = ""
    research_task_id: str = ""
    status: str = "unsubstantiated"  # unsubstantiated, supported, rejected
    supporting_evidence: List[str] = field(default_factory=list)
    contradicting_evidence: List[str] = field(default_factory=list)
    confidence: float = 0.5
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ResearchResult:
    """The final result of a research task."""
    id: str = field(default_factory=uuid4_str)
    task_id: str = ""
    summary: str = ""
    key_findings: List[str] = field(default_factory=list)
    sources: List[Source] = field(default_factory=list)
    claims: List[Claim] = field(default_factory=list)
    hypotheses: List[Hypothesis] = field(default_factory=list)
    conclusion: str = ""
    overall_confidence: float = 0.0  # 0.0-1.0
    status: str = "completed"  # completed, failed
    completed_at: datetime = field(default_factory=datetime.now)


@dataclass
class ResearchReport:
    """Structured research report output."""
    summary: str = ""
    key_findings: List[str] = field(default_factory=list)
    sources: List[Dict[str, Any]] = field(default_factory=list)
    claims: List[Dict[str, Any]] = field(default_factory=list)
    overall_confidence: float = 0.0
    status: str = "completed"
    generated_at: datetime = field(default_factory=datetime.now)


@dataclass
class ResearchConfidence:
    """Confidence assessment for research results."""
    overall: float = 0.5
    source_quality: float = 0.5
    evidence_coverage: float = 0.5
    contradiction_count: int = 0
    missing_info: List[str] = field(default_factory=list)


@dataclass
class Belief:
    """A belief state representing what the research AI 'believes' about a claim."""
    id: str = field(default_factory=uuid4_str)
    claim_id: str = ""
    state: str = "unverified"  # verified, unverified, contradicted
    confidence: float = 0.5
    evidence_ids: List[str] = field(default_factory=list)
    last_updated: datetime = field(default_factory=datetime.now)


@dataclass
class BeliefState:
    """Container for tracking multiple belief states."""
    beliefs: Dict[str, Belief] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=datetime.now)

    def update(self, belief: Belief) -> None:
        """Update or add a belief state."""
        self.beliefs[belief.id] = belief
        self.updated_at = datetime.now()

    def get(self, belief_id: str) -> Optional[Belief]:
        """Get a belief by ID."""
        return self.beliefs.get(belief_id)


@dataclass
class Conclusion:
    """A conclusion drawn from research evidence."""
    claim_id: str = ""
    claim_text: str = ""
    support_level: str = "unverified"  # verified, unverified, contradicted
    confidence: float = 0.5
    supporting_evidence_count: int = 0
    contradicting_evidence_count: int = 0
    evidence_summary: str = ""
    overall_confidence: float = 0.5


@dataclass
class CounterHypothesis:
    """An alternative hypothesis to explain the same evidence."""
    id: str = field(default_factory=uuid4_str)
    text: str = ""
    related_claim: str = ""
    evidence_required: List[str] = field(default_factory=list)
    status: str = "unsubstantiated"  # unsubstantiated, supported, rejected
    confidence: float = 0.3


@dataclass
class ResearchError:
    """Error information from research failure."""
    code: str = ""
    message: str = ""
    recoverable: bool = True
    suggested_action: str = ""