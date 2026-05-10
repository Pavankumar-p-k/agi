"""
Privacy Classifier for JARVIS — Routes requests based on privacy tier
"""
import re
import os
from typing import Literal

class PrivacyClassifier:
    """Classifies user requests by privacy tier and routes accordingly."""
    
    # Detection patterns for sensitive data
    SENSITIVE_PATTERNS = [
        # API keys and secrets
        (r'api[_-]?key["\s:=]+["\s]?([a-zA-Z0-9_-]{20,})', 'API Key'),
        (r'secret["\s:=]+["\s]?([a-zA-Z0-9_-]{16,})', 'Secret'),
        (r'password["\s:=]+["\s]?([^\s]{8,})', 'Password'),
        (r'token["\s:=]+["\s]?([a-zA-Z0-9_-]{20,})', 'Token'),
        
        # Personal identifiable information
        (r'\b\d{3}-\d{2}-\d{4}\b', 'SSN'),
        (r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b', 'Credit Card'),
        (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', 'Email'),
        
        # Financial data
        (r'\$[\d,]+(\.\d{2})?', 'Money/Financial'),
        (r'(bank|account|routing)[-_\s]?(number|#)?', 'Bank Account'),
        
        # Medical data
        (r'(diagnosis|prescription|medication|condition)[-:\s]', 'Medical'),
        (r'\b(doctor|hospital|patient)[-:\s]', 'Medical'),
    ]
    
    # High-privacy keywords
    HIGH_PRIVACY_KEYWORDS = {
        'password', 'secret', 'api_key', 'apikey', 'token', 'credential',
        'ssn', 'social security', 'credit card', 'bank account', 'routing number',
        'medical', 'diagnosis', 'prescription', 'health', 'private', 'confidential',
    }
    
    # Medium-privacy keywords  
    MEDIUM_PRIVACY_KEYWORDS = {
        'email', 'phone', 'address', 'name', 'birthday', 'dob', 'age',
        'location', 'gps', 'coordinates', 'ip address', 'device',
    }
    
    def __init__(self):
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Pre-compile regex patterns."""
        self.compiled_patterns = [
            (re.compile(p, re.IGNORECASE), label) 
            for p, label in self.SENSITIVE_PATTERNS
        ]
    
    def classify(self, text: str) -> Literal['tier_1', 'tier_2', 'tier_3']:
        """
        Classify a request into privacy tier:
        - Tier 1: Local only (Ollama) - for sensitive data
        - Tier 2: Hybrid (PII stripped) - for general queries
        - Tier 3: Cloud (explicit user override) - for non-sensitive
        """
        text_lower = text.lower()
        
        # Check for explicit cloud override
        if any(kw in text_lower for kw in ['use cloud', 'use api', 'explicit', 'allow cloud']):
            return 'tier_3'
        
        # Check for sensitive patterns (Tier 1 - local only)
        for pattern, label in self.compiled_patterns:
            if pattern.search(text):
                return 'tier_1'
        
        # Check high-privacy keywords
        if any(kw in text_lower for kw in self.HIGH_PRIVACY_KEYWORDS):
            return 'tier_1'
        
        # Check medium-privacy keywords (Tier 2 - strip PII)
        if any(kw in text_lower for kw in self.MEDIUM_PRIVACY_KEYWORDS):
            return 'tier_2'
        
        # Default to local (Tier 1) for safety
        return 'tier_1'
    
    def strip_pii(self, text: str) -> str:
        """Strip PII from text for Tier 2 processing."""
        result = text
        
        # Mask email addresses
        result = re.sub(
            r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
            '[EMAIL]',
            result
        )
        
        # Mask phone numbers
        result = re.sub(
            r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b',
            '[PHONE]',
            result
        )
        
        # Mask SSN
        result = re.sub(
            r'\b\d{3}-\d{2}-\d{4}\b',
            '[SSN]',
            result
        )
        
        # Mask credit cards
        result = re.sub(
            r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',
            '[CARD]',
            result
        )
        
        return result
    
    def get_tier_description(self, tier: str) -> str:
        """Get description for tier."""
        descriptions = {
            'tier_1': 'Local (Ollama only) - Maximum privacy',
            'tier_2': 'Hybrid (PII stripped) - Balanced privacy',
            'tier_3': 'Cloud (full API) - Requires explicit permission',
        }
        return descriptions.get(tier, 'Unknown tier')


# Global instance
privacy_classifier = PrivacyClassifier()