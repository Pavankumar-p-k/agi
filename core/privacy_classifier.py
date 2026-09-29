import re
import spacy
from enum import Enum
from typing import Optional, Dict, List

class PrivacyTier(Enum):
    LOCAL = "LOCAL"
    HYBRID = "HYBRID"
    CLOUD = "CLOUD"

class PrivacyClassifier:
    """
    3-tier privacy classifier for JARVIS.
    """
    def __init__(self):
        try:
            self.nlp = spacy.load("en_core_web_sm")
        except:
            self.nlp = None
            print("[Privacy] spacy model not found. NER disabled.")

        self.tier_1_patterns = [
            r'api[_-]?key', r'password', r'token', r'ssh[_-]?key',
            r'medical', r'diagnosis', r'prescription',
            r'account[_-]?number', r'routing[_-]?number',
            r'ssn', r'social[_-]?security',
            r'credit[_-]?card', r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',
            r'private[_-]?file', r'c:\\', r'/home/', r'secret'
        ]
        
        self.pii_entities = ["PERSON", "ORG", "GPE", "LOC", "FAC", "DATE", "TIME"]

    def classify(self, query: str, context: Optional[Dict] = None) -> PrivacyTier:
        """
        Classify query into LOCAL, HYBRID, or CLOUD.
        """
        query_lower = query.lower()

        # Tier 3: Explicit Cloud Request
        if any(kw in query_lower for kw in ["ask claude", "use gpt", "use gemini", "ask openai"]):
            return PrivacyTier.CLOUD

        # Tier 1: Local Only (Sensitive Info)
        if any(re.search(p, query_lower) for p in self.tier_1_patterns):
            return PrivacyTier.LOCAL
        
        if any(kw in query_lower for kw in ["keep local", "private", "dont share"]):
            return PrivacyTier.LOCAL

        # Regex for email, phone
        if re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', query):
            return PrivacyTier.LOCAL
        if re.search(r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b', query):
            return PrivacyTier.LOCAL

        # Tier 2: Hybrid (Sanitize then Cloud)
        # Default for general coding/reasoning if no sensitive info found
        return PrivacyTier.HYBRID

    def sanitize(self, text: str) -> str:
        """
        Strip PII using spacy NER.
        """
        if not self.nlp:
            return text

        doc = self.nlp(text)
        sanitized = text
        for ent in reversed(doc.ents):
            if ent.label_ in self.pii_entities:
                sanitized = sanitized[:ent.start_char] + f"[{ent.label_}]" + sanitized[ent.end_char:]
        
        return sanitized

# Singleton
privacy_classifier = PrivacyClassifier()
