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

"""tests/test_memory_privacy.py — Tests for memory/embedding_memory.py, core/privacy_classifier.py, brain/epistemic_tagger.py."""
import pytest
from unittest.mock import patch, MagicMock
import numpy as np
from core.result import Ok, Err


class TestEmbeddingMemory:
    @pytest.fixture
    def memory(self):
        with patch("memory.embedding_memory.os.makedirs"):
            with patch("memory.embedding_memory.sqlite3.connect") as mock_conn:
                from memory.embedding_memory import EmbeddingMemory
                yield EmbeddingMemory(db_path="/tmp/test_mem.db")

    def test_init(self, memory):
        assert memory.db_path == "/tmp/test_mem.db"

    def test_embed_success(self, memory):
        with patch("memory.embedding_memory.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"embedding": [0.1, 0.2, 0.3]}
            mock_resp.raise_for_status.return_value = None
            mock_post.return_value = mock_resp
            result = memory.embed("test text")
            assert result.is_ok()
            emb = result.unwrap()
            assert isinstance(emb, np.ndarray)
            assert emb.shape == (3,)

    def test_embed_failure(self, memory):
        with patch("memory.embedding_memory.requests.post", side_effect=Exception("Ollama down")):
            result = memory.embed("test")
            assert result.is_err()

    def test_store_embedding_fails(self, memory):
        with patch.object(memory, "embed", side_effect=Exception("fail")):
            memory.store("some text")
            assert True

    def test_semantic_search_embedding_fails(self, memory):
        with patch.object(memory, "embed", return_value=Err(Exception("fail"))):
            result = memory.semantic_search("query")
            assert result.is_err()

    def test_semantic_search(self, memory):
        fake_emb = np.array([0.1, 0.2, 0.3], dtype=np.float32)
        with patch.object(memory, "embed", return_value=Ok(fake_emb)):
            mock_cursor = MagicMock()
            mock_cursor.__iter__.return_value = [
                ("text1", '{"key": "val"}', fake_emb.tobytes()),
            ]
            with patch("memory.embedding_memory.sqlite3.connect") as mock_conn:
                mock_conn.return_value.execute.return_value = mock_cursor
                result = memory.semantic_search("query")
                assert result.is_ok()
                items = result.unwrap()
                assert len(items) == 1
                assert items[0]["text"] == "text1"


class TestPrivacyClassifier:
    @pytest.fixture
    def classifier(self):
        with patch("core.privacy_classifier.spacy.load", side_effect=Exception("no model")):
            from core.privacy_classifier import PrivacyClassifier
            c = PrivacyClassifier()
            c.nlp = None
            return c

    def test_classify_api_key(self, classifier):
        from core.privacy_classifier import PrivacyTier
        assert classifier.classify("my api_key is secret") == PrivacyTier.LOCAL

    def test_classify_credit_card(self, classifier):
        from core.privacy_classifier import PrivacyTier
        assert classifier.classify("card 4111-1111-1111-1111") == PrivacyTier.LOCAL

    def test_classify_email(self, classifier):
        from core.privacy_classifier import PrivacyTier
        assert classifier.classify("email me@test.com") == PrivacyTier.LOCAL

    def test_classify_phone(self, classifier):
        from core.privacy_classifier import PrivacyTier
        assert classifier.classify("call 555-123-4567") == PrivacyTier.LOCAL

    def test_classify_keep_local_keyword(self, classifier):
        from core.privacy_classifier import PrivacyTier
        assert classifier.classify("keep this private") == PrivacyTier.LOCAL

    def test_classify_cloud_request(self, classifier):
        from core.privacy_classifier import PrivacyTier
        result = classifier.classify("ask claude about AI")
        assert result == PrivacyTier.CLOUD

    def test_classify_default_local(self, classifier):
        from core.privacy_classifier import PrivacyTier
        assert classifier.classify("hello how are you") == PrivacyTier.LOCAL

    def test_classify_medical(self, classifier):
        from core.privacy_classifier import PrivacyTier
        assert classifier.classify("my medical diagnosis") == PrivacyTier.LOCAL

    def test_sanitize_cloud_no_change(self, classifier):
        from core.privacy_classifier import PrivacyTier
        result = classifier.sanitize("my email is me@test.com", tier=PrivacyTier.CLOUD)
        assert result == "my email is me@test.com"

    def test_sanitize_hybrid_strips_email(self, classifier):
        from core.privacy_classifier import PrivacyTier
        result = classifier.sanitize("email me@test.com", tier=PrivacyTier.HYBRID)
        assert "[EMAIL]" in result
        assert "me@test.com" not in result

    def test_sanitize_hybrid_strips_phone(self, classifier):
        from core.privacy_classifier import PrivacyTier
        result = classifier.sanitize("call 555-123-4567", tier=PrivacyTier.HYBRID)
        assert "[PHONE]" in result

    def test_sanitize_hybrid_strips_cc(self, classifier):
        from core.privacy_classifier import PrivacyTier
        result = classifier.sanitize("card 4111111111111111", tier=PrivacyTier.HYBRID)
        assert "[CC]" in result

    def test_sanitize_local_no_nlp(self, classifier):
        from core.privacy_classifier import PrivacyTier
        result = classifier.sanitize("John Smith lives in New York", tier=PrivacyTier.LOCAL)
        assert "John" in result


class TestEpistemicTagger:
    @pytest.fixture
    def tagger(self):
        from brain.epistemic_tagger import EpistemicTagger
        return EpistemicTagger()

    def test_strip_tags_empty(self, tagger):
        assert tagger.strip_tags("") == ""

    def test_strip_tags_no_tags(self, tagger):
        assert tagger.strip_tags("hello world") == "hello world"

    def test_strip_tags_removes_verified(self, tagger):
        assert tagger.strip_tags("[VERIFIED] hello") == "hello"

    def test_strip_tags_removes_uncertain(self, tagger):
        assert tagger.strip_tags("[UNCERTAIN] maybe") == "maybe"

    def test_strip_tags_removes_retrieved(self, tagger):
        result = tagger.strip_tags("[RETRIEVED](https://x.com) content")
        assert result == "content"

    def test_tag_response_no_provenance(self, tagger):
        assert tagger.tag_response("hello", None) == "hello"

    def test_tag_response_empty_provenance(self, tagger):
        assert tagger.tag_response("hello", {}) == "hello"

    def test_tag_response_web_search(self, tagger):
        result = tagger.tag_response("It is sunny today", {"source": "web_search", "url": "https://weather.com"})
        assert "[RETRIEVED]" in result
        assert "weather.com" in result

    def test_tag_response_inference(self, tagger):
        result = tagger.tag_response("I think so", {"source": "inference"})
        assert "[ASSUMED]" in result

    def test_tag_response_unknown(self, tagger):
        result = tagger.tag_response("not sure", {"source": "unknown"})
        assert "[UNCERTAIN]" in result

    def test_tag_response_claim_map(self, tagger):
        result = tagger.tag_response("Paris is in France. The sun is hot.", {
            "source": "inference",
            "claim_map": {"Paris": "web_search", "sun": "inference"},
        })
        assert "[VERIFIED]" in result or "[RETRIEVED]" in result

    def test_strip_then_tag_roundtrip(self, tagger):
        text = "Some important fact"
        tagged = tagger.tag_response(text, {"source": "web_search", "url": "https://example.com"})
        stripped = tagger.strip_tags(tagged)
        assert stripped == text

    @pytest.mark.parametrize("source,expected_tag", [
        ("web_search", "VERIFIED"),
        ("search", "VERIFIED"),
        ("memory", "VERIFIED"),
        ("tool_result", "VERIFIED"),
        ("tool", "VERIFIED"),
        ("inference", "ASSUMED"),
        ("low_conf_memory", "ASSUMED"),
        ("unknown", "UNCERTAIN"),
    ])
    def test_tag_sources(self, tagger, source, expected_tag):
        result = tagger.tag_response("test sentence", {"source": source})
        assert f"[{expected_tag}]" in result
