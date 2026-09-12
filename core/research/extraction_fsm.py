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

from enum import Enum

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from core.research.models import Fact, Claim, Evidence, Source, ResearchResult, Hypothesis

logger = logging.getLogger("jarvis.research.extraction_fsm")


class ExtractionState(Enum):
    """States in the extraction finite state machine."""
    INITIAL = "initial"
    SCANNING = "scanning"
    EXTRACTING = "extracting"
    VALIDATING = "validating"
    COMPLETE = "complete"
    ERROR = "error"


class ExtractionFSM:
    """Finite state machine controlling the extraction process."""
    
    def __init__(self, extractor):
        self.extractor = extractor
        self.state = ExtractionState.INITIAL
        self.current_text = ""
        self.current_source = ""
        self.facts_found: List[Fact] = []
        self.claims_found: List[Claim] = []
        self.evidence_found: List[Evidence] = []
        self.step_counter = 0
        self.max_steps = 10
    
    def transition(self, new_state: ExtractionState, **kwargs) -> None:
        """Transition to a new state."""
        old_state = self.state
        self.state = new_state
        logger.debug(f"Extraction FSM: {old_state.value} -> {new_state.value}")
        
        # State-specific handling
        if new_state == ExtractionState.EXTRACTING:
            self.step_counter = 0
        elif new_state == ExtractionState.COMPLETE:
            self._finalize()
        elif new_state == ExtractionState.ERROR:
            self._handle_error(kwargs.get("error", "unknown error"))
    
    def _finalize(self) -> None:
        """Finalize extraction and compile results."""
        logger.info(f"Extraction complete: {len(self.facts_found)} facts, "
                     f"{len(self.claims_found)} claims, {len(self.evidence_found)} evidence")
    
    def _handle_error(self, error: str) -> None:
        """Handle extraction error."""
        logger.error(f"Extraction FSM error: {error}")
        self.state = ExtractionState.ERROR
    
    async def process(self, text: str, source_url: str = "", 
                      source_title: str = "", query: str = "") -> Dict[str, Any]:
        """Process text through the extraction FSM."""
        
        self.current_text = text
        self.current_source = source_url
        self.facts_found = []
        self.claims_found = []
        self.evidence_found = []
        self.step_counter = 0
        
        # State machine loop
        while self.state != ExtractionState.COMPLETE and self.state != ExtractionState.ERROR:
            if self.step_counter >= self.max_steps:
                self.transition(ExtractionState.ERROR, 
                              error="Max extraction steps reached")
                break
            
            self.step_counter += 1
            
            # Transition through states
            if self.state == ExtractionState.INITIAL:
                self.transition(ExtractionState.SCANNING)
            
            elif self.state == ExtractionState.SCANNING:
                # Scan text for patterns
                facts = self.extractor.extract_from_text(
                    text, source_url, source_title, query)
                claims = self.extractor.extract_claims_from_text(
                    text, source_url, source_title, query)
                evidence = self.extractor.extract_evidence_from_text(
                    text, source_url, source_title)
                
                self.facts_found.extend(facts)
                self.claims_found.extend(claims)
                self.evidence_found.extend(evidence)
                
                if self.facts_found or self.claims_found or self.evidence_found:
                    self.transition(ExtractionState.VALIDATING)
                else:
                    # Continue scanning or move to complete
                    if self.step_counter >= self.max_steps:
                        self.transition(ExtractionState.COMPLETE)
                    else:
                        self.transition(ExtractionState.INITIAL)
            
            elif self.state == ExtractionState.VALIDATING:
                # Validate extracted items
                validated_facts = self._validate_facts(self.facts_found)
                validated_claims = self._validate_claims(self.claims_found)
                validated_evidence = self._validate_evidence(self.evidence_found)
                
                self.facts_found = validated_facts
                self.claims_found = validated_claims
                self.evidence_found = validated_evidence
                
                self.transition(ExtractionState.COMPLETE)
        
        return self._get_results()
    
    def _validate_facts(self, facts: List[Fact]) -> List[Fact]:
        """Validate and rank extracted facts."""
        # Remove facts with very low confidence or empty text
        valid = []
        for fact in facts:
            if fact.text and len(fact.text.strip()) > 10 and fact.confidence > 0.2:
                valid.append(fact)
        # Sort by confidence
        return sorted(valid, key=lambda f: f.confidence, reverse=True)
    
    def _validate_claims(self, claims: List[Claim]) -> List[Claim]:
        """Validate and rank extracted claims."""
        valid = []
        for claim in claims:
            if claim.text and len(claim.text.strip()) > 10:
                valid.append(claim)
        return sorted(valid, key=lambda c: c.confidence, reverse=True)
    
    def _validate_evidence(self, evidence: List[Evidence]) -> List[Evidence]:
        """Validate and rank extracted evidence."""
        valid = []
        for ev in evidence:
            if ev.content and len(ev.content.strip()) > 10:
                valid.append(ev)
        return sorted(valid, key=lambda e: e.relevance, reverse=True)
    
    def _get_results(self) -> Dict[str, Any]:
        """Get the final extraction results."""
        return {
            "state": self.state.value,
            "facts": [self._fact_to_dict(f) for f in self.facts_found],
            "claims": [self._claim_to_dict(c) for c in self.claims_found],
            "evidence": [self._evidence_to_dict(e) for e in self.evidence_found],
            "statistics": {
                "facts_count": len(self.facts_found),
                "claims_count": len(self.claims_found),
                "evidence_count": len(self.evidence_found),
            }
        }
    
    def _fact_to_dict(self, fact: Fact) -> Dict[str, Any]:
        """Convert Fact to dict."""
        return {
            "id": fact.id,
            "claim": fact.claim,
            "source_url": fact.source_url,
            "source_title": fact.source_title,
            "text": fact.text,
            "confidence": fact.confidence,
        }
    
    def _claim_to_dict(self, claim: Claim) -> Dict[str, Any]:
        """Convert Claim to dict."""
        return {
            "id": claim.id,
            "text": claim.text,
            "source_url": claim.source_url,
            "source_title": claim.source_title,
            "confidence": claim.confidence,
        }
    
    def _evidence_to_dict(self, evidence: Evidence) -> Dict[str, Any]:
        """Convert Evidence to dict."""
        return {
            "id": evidence.id,
            "content": evidence.content,
            "source_url": evidence.source_url,
            "source_title": evidence.source_title,
            "relevance": evidence.relevance,
            "confidence": evidence.confidence,
        }


# Export for use by other modules
extraction_fsm = ExtractionFSM(None)