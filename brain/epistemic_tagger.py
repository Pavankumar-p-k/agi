import re
from typing import List, Dict, Optional

class EpistemicTagger:
    """
    Epistemological tagging for JARVIS responses.
    Tags: [VERIFIED], [RETRIEVED], [DERIVED], [ASSUMED], [UNCERTAIN]
    """
    def __init__(self):
        self.tags = {
            "VERIFIED": "Claim cross-checked against multiple sources or high-confidence RAG",
            "RETRIEVED": "Claim retrieved from memory or external search",
            "DERIVED": "Claim is a logical deduction from verified premises",
            "ASSUMED": "Claim is plausible but unverified",
            "UNCERTAIN": "Jarvis is unsure or guessing (confidence < 0.6)"
        }

    def tag_response(self, response: str, sources: List[str] = None, confidence: float = 1.0) -> str:
        """
        Add epistemological tags to a response.
        """
        tagged_response = response
        
        # 1. Check for retrieval
        if sources:
            tagged_response = "[RETRIEVED] " + tagged_response
            
        # 2. Check for uncertainty
        if confidence < 0.6:
            tagged_response = tagged_response.replace("[RETRIEVED] ", "")
            tagged_response = "[UNCERTAIN] " + tagged_response
        elif confidence > 0.9 and sources:
            tagged_response = tagged_response.replace("[RETRIEVED] ", "")
            tagged_response = "[VERIFIED] " + tagged_response

        # Heuristics for internal sentences
        sentences = re.split(r'(?<=[.!?]) +', tagged_response)
        processed_sentences = []
        for sent in sentences:
            if any(kw in sent.lower() for kw in ["probably", "maybe", "might", "i think", "possibly"]):
                processed_sentences.append(f"[ASSUMED] {sent}")
            elif any(kw in sent.lower() for kw in ["therefore", "thus", "consequently", "so", "leads to"]):
                processed_sentences.append(f"[DERIVED] {sent}")
            else:
                processed_sentences.append(sent)
        
        return " ".join(processed_sentences)

    def explain_tags(self) -> str:
        explanation = "### Epistemological Tags Explanation\n"
        for tag, desc in self.tags.items():
            explanation += f"- **[{tag}]**: {desc}\n"
        return explanation

# Instance
epistemic_tagger = EpistemicTagger()
