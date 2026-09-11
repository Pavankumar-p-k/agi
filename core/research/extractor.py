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

import logging
import re
from typing import List, Dict, Any, Optional
from datetime import datetime

from core.research.models import Fact, Claim, Evidence, Source, ResearchResult

logger = logging.getLogger("jarvis.research.extractor")


class Extractor:
    """Extracts structured facts and claims from raw text sources."""
    
    def __init__(self):
        self.extraction_patterns = self._init_patterns()
    
    def _init_patterns(self) -> Dict[str, re.Pattern]:
        """Initialize regex patterns for fact extraction."""
        return {
            "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
            "url": re.compile(r"https?://[^\s<>\"'\)\]\},]+"),
            "phone": re.compile(r"(?:\+?1\s?)?\(?[0-9]{3}\)?[\s.-]?[0-9]{3}[\s.-]?[0-9]{4}"),
            "date": re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"),
            "money": re.compile(r"[\$£¥]?\s?\d[\d,.]*"),
        }
    
    def extract_from_text(self, text: str, source_url: str = "", 
                          source_title: str = "", query: str = "") -> List[Fact]:
        """Extract factual statements from raw text."""
        if not text or len(text.strip()) < 20:
            return []
        
        facts = []
        text_lower = text.lower()
        
        # Extract emails
        for match in self.extraction_patterns["email"].finditer(text):
            facts.append(Fact(
                claim=f"Contact: {match.group(0)}",
                source_url=source_url,
                source_title=source_title,
                text=match.group(0),
                confidence=0.8,
            ))
        
        # Extract URLs
        for match in self.extraction_patterns["url"].finditer(text):
            facts.append(Fact(
                claim=f"Resource URL: {match.group(0)}",
                source_url=source_url,
                source_title=source_title,
                text=match.group(0),
                confidence=0.7,
            ))
        
        # Extract phone numbers
        for match in self.extraction_patterns["phone"].finditer(text):
            facts.append(Fact(
                claim=f"Phone number: {match.group(0)}",
                source_url=source_url,
                source_title=source_title,
                text=match.group(0),
                confidence=0.7,
            ))
        
        # Extract dates
        for match in self.extraction_patterns["date"].finditer(text):
            facts.append(Fact(
                claim=f"Date: {match.group(0)}",
                source_url=source_url,
                source_title=source_title,
                text=match.group(0),
                confidence=0.6,
            ))
        
        # Extract money amounts
        for match in self.extraction_patterns["money"].finditer(text):
            facts.append(Fact(
                claim=f"Amount: {match.group(0)}",
                source_url=source_url,
                source_title=source_title,
                text=match.group(0),
                confidence=0.6,
            ))
        
        # Semantic fact extraction: sentences that look like factual claims
        sentences = re.split(r'(?<=[.!?])\s+', text)
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 20 or len(sentence) > 500:
                continue
            
            # Heuristic: sentences with "is", "are", "was", "were" often contain claims
            if any(kw in sentence_lower for kw in [" is ", " are ", " was ", " were ", " supports ", " requires ", " uses "]):
                # Skip if it looks like a question or command
                if sentence.startswith(("How ", "Why ", "What ", "Please ")):
                    continue
                
                # Extract as fact with moderate confidence
                facts.append(Fact(
                    claim=sentence[:200],  # Truncate if too long
                    source_url=source_url,
                    source_title=source_title,
                    text=sentence,
                    confidence=0.5,
                ))
        
        # Deduplicate facts by text similarity
        unique_facts = self._deduplicate_facts(facts)
        
        return unique_facts
    
    def _deduplicate_facts(self, facts: List[Fact]) -> List[Fact]:
        """Remove duplicate/very similar facts."""
        unique = []
        for fact in facts:
            is_duplicate = False
            for existing in unique:
                # Simple similarity: check if key terms overlap
                fact_words = set(fact.text.lower().split())
                existing_words = set(existing.text.lower().split())
                if fact_words and existing_words:
                    overlap = len(fact_words & existing_words) / max(len(fact_words), len(existing_words))
                    if overlap > 0.7:  # 70% overlap = duplicate
                        is_duplicate = True
                        break
            if not is_duplicate:
                unique.append(fact)
        return unique
    
    def extract_claims_from_text(self, text: str, source_url: str = "",
                                  source_title: str = "", query: str = "") -> List[Claim]:
        """Extract claims (propositions that can be true/false) from text."""
        if not text or len(text.strip()) < 20:
            return []
        
        claims = []
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        claim_keywords = [" supports ", " requires ", " uses ", " achieves ", " enables ",
                          " improves ", " reduces ", " increases ", " decreases "]
        
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 30 or len(sentence) > 400:
                continue
            
            sentence_lower = sentence.lower()
            
            # Check if sentence contains claim-like structure
            is_claim = any(kw in sentence_lower for kw in claim_keywords)
            
            # Also check for declarative sentences with subject + verb + predicate
            if not is_claim:
                # Simple heuristic: sentence has a verb and makes a positive assertion
                if len(sentence.split()) >= 5 and not sentence.startswith(("How ", "Why ", "?")):
                    is_claim = True
            
            if is_claim:
                # Truncate claim text
                claim_text = sentence[:250]
                claims.append(Claim(
                    text=claim_text,
                    source_url=source_url,
                    source_title=source_title,
                    confidence=0.5,
                ))
        
        return claims
    
    def extract_evidence_from_text(self, text: str, source_url: str = "",
                                    source_title: str = "") -> List[Evidence]:
        """Extract evidence items supporting claims from text."""
        if not text or len(text.strip()) < 20:
            return []
        
        evidence = []
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        # Evidence sentences typically contain data, references, or specific details
        evidence_keywords = ["data shows", "according to", "studies indicate", "research found",
                            "the study", "the report", "experiments revealed", "we found",
                            "the results", "analysis showed", "measured", "percent", "%"]
        
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 20 or len(sentence) > 300:
                continue
            
            sentence_lower = sentence.lower()
            
            # Check if sentence is evidence-like
            is_evidence = any(kw in sentence_lower for kw in evidence_keywords)
            
            # Also: sentences with citations, numbers, or specific references
            has_citation = bool(re.search(r'\([^)]+\d{4}\)|\[[^\]]+\]|et al\.?', sentence))
            has_numbers = bool(re.search(r'\d+%|\d+\.\d+|\d+,|\d+\.\d+%'))
            
            if is_evidence or (has_citation or has_numbers) and len(sentence) > 30:
                evidence.append(Evidence(
                    claim="",  # Will be linked later
                    source_url=source_url,
                    source_title=source_title,
                    content=sentence,
                    relevance=0.6,
                    confidence=0.5,
                ))
        
        return evidence
    
    def create_fact_from_extraction(self, claim_text: str, source: Source,
                                     confidence: float = 0.5) -> Fact:
        """Create a Fact from an extraction result."""
        return Fact(
            claim=claim_text,
            source_url=source.url,
            source_title=source.title,
            text=claim_text,
            confidence=confidence,
        )