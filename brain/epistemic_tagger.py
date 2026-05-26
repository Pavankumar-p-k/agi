import re

class EpistemicTagger:
    """Utility to strip epistemic tags from responses (tagging removed, only cleanup remains)."""
    def strip_tags(self, text: str) -> str:
        """Remove all epistemic tags from text."""
        return re.sub(r'\[(VERIFIED|RETRIEVED|DERIVED|ASSUMED|UNCERTAIN)\]\s*', '', text).strip()

epistemic_tagger = EpistemicTagger()
