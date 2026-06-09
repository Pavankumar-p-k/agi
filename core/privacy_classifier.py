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

import logging
import re

logger = logging.getLogger(__name__)
from enum import Enum


class PrivacyTier(Enum):
    LOCAL = "LOCAL"
    HYBRID = "HYBRID"
    CLOUD = "CLOUD"

class PrivacyClassifier:
    """
    3-tier privacy classifier for JARVIS.
    """
    def __init__(self):
        self.nlp = None
        self._nlp_loaded = False

    def _ensure_nlp(self):
        if not self._nlp_loaded:
            self._nlp_loaded = True
            try:
                import spacy
                self.nlp = spacy.load("en_core_web_sm")
            except Exception as e:
                logger.exception("[PRIVACY] spacy model load failed: %s", e)
                self.nlp = None

        self.tier_1_patterns = [
            r'api[_-]?key', r'password', r'token', r'ssh[_-]?key',
            r'medical', r'diagnosis', r'prescription',
            r'account[_-]?number', r'routing[_-]?number',
            r'ssn', r'social[_-]?security',
            r'credit[_-]?card', r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',
            r'private[_-]?file', r'c:\\', r'/home/', r'secret'
        ]

        self.pii_entities = ["PERSON", "ORG", "GPE", "LOC", "FAC", "DATE", "TIME"]

    def classify(self, query: str, context: dict | None = None) -> PrivacyTier:
        """
        Classify query into LOCAL, HYBRID, or CLOUD.
        """
        query_lower = query.lower()

        # Tier 1: Local Only (Sensitive Info) â€” check BEFORE cloud keyword
        if any(re.search(p, query_lower) for p in self.tier_1_patterns):
            return PrivacyTier.LOCAL

        if any(kw in query_lower for kw in ["keep local", "private", "dont share"]):
            return PrivacyTier.LOCAL

        # Regex for email, phone
        if re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', query):
            return PrivacyTier.LOCAL
        if re.search(r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b', query):
            return PrivacyTier.LOCAL

        # Tier 3: Explicit Cloud Request (after PII checks â€” never leak sensitive data)
        if any(kw in query_lower for kw in ["ask claude", "use gpt", "use gemini", "ask openai"]):
            return PrivacyTier.CLOUD

        # Default: LOCAL â€” all normal chat stays local
        return PrivacyTier.LOCAL

    def sanitize(self, text: str, tier: PrivacyTier = PrivacyTier.HYBRID) -> str:
        """
        Strip PII using spacy NER.
        LOCAL: strip all PII entities (PERSON, ORG, GPE, etc.) + patterns.
        HYBRID: only strip email, phone, SSN, credit card patterns â€” NOT names.
        CLOUD: no sanitization (user explicitly opted in).
        """
        if tier == PrivacyTier.CLOUD:
            return text

        # Pattern-based sanitization (always for LOCAL and HYBRID)
        sanitized = text
        patterns = {
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b': '[EMAIL]',
            r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b': '[PHONE]',
            r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b': '[CC]',
        }
        for pattern, replacement in patterns.items():
            sanitized = re.sub(pattern, replacement, sanitized)

        if tier == PrivacyTier.LOCAL:
            self._ensure_nlp()
            if not self.nlp:
                return sanitized
            doc = self.nlp(sanitized)
            for ent in reversed(doc.ents):
                if ent.label_ in self.pii_entities:
                    sanitized = sanitized[:ent.start_char] + f"[{ent.label_}]" + sanitized[ent.end_char:]

        return sanitized

# Singleton
privacy_classifier = PrivacyClassifier()
