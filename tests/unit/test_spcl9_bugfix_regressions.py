"""SPCL-9 Step 1: regression coverage for two inline bug fixes.

Both bugs were found while smoke-testing each sub-AI with one task and
fixed inline (genuine off-by-order / wrong-call bugs in real, non-stub code).
These tests pin the fixed behavior so the bugs cannot silently regress.

Fix 1: core/research/extractor.py — the semantic-fact branch referenced
    ``sentence_lower`` before it was defined (NameError). Now uses
    ``sentence.lower()``.
Fix 2: core/coding/coding_agent.py — the ``coding.index_repository``
    capability handler called ``.summary()`` on the dict returned by
    ``RepositoryIndexer.index()``. ``summary()`` is a separate method on
    the indexer, so the handler now indexes first, then summarizes.
"""
import os
import shutil
import tempfile

from core.research.extractor import Extractor
from core.coding import CodingAI


class TestExtractorSemanticBranch:
    def test_semantic_sentence_extracts_without_name_error(self):
        """The sentence branch (the one that held the NameError) runs cleanly."""
        extractor = Extractor()
        sentence = "Python is a widely used programming language for automation."
        facts = extractor.extract_from_text(
            sentence,
            source_url="http://example.com",
            source_title="Example",
            query="What is Python?",
        )
        assert len(facts) == 1
        assert facts[0].text == sentence

    def test_short_text_still_returns_empty(self):
        """Guard clause behavior is unchanged by the fix."""
        assert Extractor().extract_from_text("too short") == []


class TestCodingIndexRepositoryCapability:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp()
        path = os.path.join(self._tmp, "mod.py")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("def hello():\n    return True\n")

    def teardown_method(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_index_repository_capability_succeeds(self):
        """Exercises the fixed handler lambda end-to-end via execute_capability."""
        ai = CodingAI(self._tmp)
        result = ai.execute_capability("coding.index_repository", {"force": True})
        assert result.success, f"capability failed: {result.error}"
        assert isinstance(result.output, dict)
        assert len(result.output) >= 1
